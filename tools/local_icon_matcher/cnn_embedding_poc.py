"""
cnn_embedding_poc.py — MobileNetV2 CNN embedding matcher PoC.

Two preprocessing modes per sample:
  A) direct_resize  — crop/template → 224x224 bicubic
  B) pad_square     — pad to square first → 224x224 bicubic

Embedding: MobileNetV2 penultimate layer (before classifier), 1280-dim.
Matching:  cosine nearest-class over 72 template embeddings.

Outputs:
  out/cnn_embedding_eval.json
  out/cnn_embedding_confusion.csv

Verdict:
  CNN_ALIVE      if top1 >= 50% OR top3 >= 70%
  CNN_DEAD       if top1 <  50% AND top3 <  70%
  INCONCLUSIVE   if deps/data missing or model failed to load
"""

from __future__ import annotations
import csv
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
import torchvision.models as models
import torchvision.transforms as T
from PIL import Image

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent.parent
TEMPLATES   = ROOT / 'extracted_site_icons_v3'
CROPS_DIR   = Path(__file__).resolve().parent / 'crops'
LABELS_JSON = Path(__file__).resolve().parent / 'out' / 'labeled_rows.json'
OUT         = Path(__file__).resolve().parent / 'out'
OUT_EVAL    = OUT / 'cnn_embedding_eval.json'
OUT_CONF    = OUT / 'cnn_embedding_confusion.csv'

DEVICE = torch.device('cpu')


# ── preprocessing ──────────────────────────────────────────────────────────────

_NORMALIZE = T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])


def _to_rgb_pil(path: Path) -> Image.Image:
    """Load any PNG/JPEG as RGB PIL."""
    return Image.open(path).convert('RGB')


def preprocess_direct(img: Image.Image) -> torch.Tensor:
    """Mode A: direct bicubic resize to 224x224."""
    img = img.resize((224, 224), Image.BICUBIC)
    t = T.ToTensor()(img)        # [3,224,224] float32 in [0,1]
    return _NORMALIZE(t).unsqueeze(0)   # [1,3,224,224]


def preprocess_pad(img: Image.Image) -> torch.Tensor:
    """Mode B: pad to square first, then resize 224x224."""
    w, h = img.size
    side = max(w, h)
    new_img = Image.new('RGB', (side, side), (0, 0, 0))
    new_img.paste(img, ((side - w) // 2, (side - h) // 2))
    new_img = new_img.resize((224, 224), Image.BICUBIC)
    t = T.ToTensor()(new_img)
    return _NORMALIZE(t).unsqueeze(0)


# ── model ─────────────────────────────────────────────────────────────────────

def build_model():
    """MobileNetV2 pretrained, strip classifier, return feature extractor."""
    print('  Loading MobileNetV2 pretrained weights ...')
    try:
        weights = models.MobileNet_V2_Weights.DEFAULT
        m = models.mobilenet_v2(weights=weights)
    except Exception as e:
        print(f'  ERROR loading pretrained weights: {e}')
        return None
    # penultimate: features + adaptive pool → 1280-dim vector
    m.classifier = torch.nn.Identity()
    m.eval()
    m.to(DEVICE)
    return m


@torch.no_grad()
def embed(model, tensor: torch.Tensor) -> np.ndarray:
    """Returns L2-normalised 1280-dim embedding."""
    x = model.features(tensor.to(DEVICE))          # [1,1280,7,7]
    x = F.adaptive_avg_pool2d(x, 1).flatten(1)     # [1,1280]
    x = F.normalize(x, dim=1)
    return x.cpu().numpy()[0]                       # (1280,)


# ── label mapping ─────────────────────────────────────────────────────────────

def labeled_crop_to_filename(crop_path_str: str) -> str:
    base = Path(crop_path_str).name
    base = re.sub(r'\.jpg_row', '_row', base)
    base = re.sub(r' \((\d+)\)', r'_(\1)', base)
    return base


# ── cosine nearest ────────────────────────────────────────────────────────────

def cosine_top_n(query: np.ndarray, bank_vecs: np.ndarray,
                 bank_labels: list[str], n: int = 3):
    """Return [(cls, score)] sorted descending."""
    sims = bank_vecs @ query          # already L2-normed
    idx  = np.argsort(-sims)
    return [(bank_labels[i], float(sims[i])) for i in idx[:n]]


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    OUT.mkdir(exist_ok=True)

    # ── guard: templates ──
    if not TEMPLATES.exists():
        _inconclusive('templates_dir_missing'); return

    # ── guard: labels ──
    if not LABELS_JSON.exists():
        _inconclusive('labels_missing'); return

    with open(LABELS_JSON, encoding='utf-8') as f:
        label_rows = json.load(f)

    # ── load model ──
    model = build_model()
    if model is None:
        _inconclusive('model_load_failed'); return

    # ── two preprocessing functions ──
    MODES = {
        'direct_resize': preprocess_direct,
        'pad_square':    preprocess_pad,
    }

    # ── build template bank (per mode) ──
    tmpl_paths = sorted(TEMPLATES.glob('*.png'))
    if not tmpl_paths:
        _inconclusive('no_template_files'); return

    print(f'  Building template banks ({len(tmpl_paths)} classes) ...')
    banks: dict[str, tuple[np.ndarray, list[str]]] = {}
    for mode_name, preproc in MODES.items():
        vecs, labels = [], []
        for p in tmpl_paths:
            try:
                img = _to_rgb_pil(p)
                v   = embed(model, preproc(img))
                vecs.append(v)
                labels.append(p.stem)
            except Exception as e:
                print(f'  WARN tmpl {p.name}: {e}')
        bank_arr = np.stack(vecs)      # already L2-normed row-wise
        banks[mode_name] = (bank_arr, labels)
        print(f'    [{mode_name}] bank: {bank_arr.shape}')

    # ── load test crops ──
    test_pairs: list[tuple[str, Path]] = []
    for row in label_rows:
        gt_cls = row.get('final_class', '')
        fname  = labeled_crop_to_filename(row.get('crop_path', ''))
        cp     = CROPS_DIR / fname
        if cp.exists():
            test_pairs.append((gt_cls, cp))
        else:
            print(f'  WARN crop missing: {fname}')

    if not test_pairs:
        _inconclusive('no_crops_loaded'); return

    print(f'  Test crops: {len(test_pairs)}')
    print()

    # ── evaluate both modes ──
    mode_results: dict[str, dict] = {}

    for mode_name, preproc in MODES.items():
        bank_arr, bank_labels = banks[mode_name]
        rows_out = []
        print(f'  Mode: {mode_name}')

        for gt_cls, cp in test_pairs:
            try:
                img  = _to_rgb_pil(cp)
                qvec = embed(model, preproc(img))
            except Exception as e:
                print(f'  WARN {cp.name}: {e}')
                continue

            top3 = cosine_top_n(qvec, bank_arr, bank_labels, n=3)
            pred1_cls, pred1_sc = top3[0]
            top3_cls = [c for c, _ in top3]
            ok1 = pred1_cls == gt_cls
            ok3 = gt_cls in top3_cls
            margin = pred1_sc - top3[1][1] if len(top3) > 1 else 0.0

            rows_out.append({
                'gt_class':   gt_cls,
                'pred_class': pred1_cls,
                'pred_score': round(pred1_sc, 4),
                'margin':     round(margin, 4),
                'top3':       top3_cls,
                'ok1':        ok1,
                'ok3':        ok3,
            })
            mark = 'OK' if ok1 else ('top3' if ok3 else 'FAIL')
            print(f'    {gt_cls:<22} -> {pred1_cls:<22} ({pred1_sc:.4f}) {mark}')

        n       = len(rows_out)
        top1_n  = sum(r['ok1'] for r in rows_out)
        top3_n  = sum(r['ok3'] for r in rows_out)
        top1_acc = top1_n / n if n else 0.0
        top3_acc = top3_n / n if n else 0.0
        low_conf = sum(1 for r in rows_out if r['pred_score'] < 0.8) / n if n else 0.0

        print(f'    top1={top1_acc*100:.1f}%  top3={top3_acc*100:.1f}%  low_conf={low_conf*100:.1f}%')
        print()

        mode_results[mode_name] = {
            'top1_acc':  round(top1_acc, 4),
            'top3_acc':  round(top3_acc, 4),
            'low_conf':  round(low_conf, 4),
            'n':         n,
            'per_sample': rows_out,
        }

    # ── overall verdict (best mode wins) ──
    best_mode = max(mode_results, key=lambda m: mode_results[m]['top1_acc'])
    best      = mode_results[best_mode]
    top1_acc  = best['top1_acc']
    top3_acc  = best['top3_acc']

    if top1_acc >= 0.5 or top3_acc >= 0.7:
        verdict = 'CNN_ALIVE'
    else:
        verdict = 'CNN_DEAD'

    print('=' * 60)
    print(f'  VERDICT: {verdict}  (best mode: {best_mode})')
    print(f'  top1_acc : {top1_acc*100:.1f}%')
    print(f'  top3_acc : {top3_acc*100:.1f}%')
    print(f'  low_conf : {best["low_conf"]*100:.1f}%')
    print('=' * 60)

    # ── confusion (best mode) ──
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in best['per_sample']:
        confusion[r['gt_class']][r['pred_class']] += 1

    gt_cls_list   = sorted({r['gt_class']   for r in best['per_sample']})
    pred_cls_list = sorted({r['pred_class'] for r in best['per_sample']})
    all_cls       = sorted(set(gt_cls_list) | set(pred_cls_list))

    with open(OUT_CONF, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['gt\\pred'] + all_cls)
        for gt in gt_cls_list:
            w.writerow([gt] + [confusion[gt].get(pc, 0) for pc in all_cls])

    # ── eval JSON ──
    summary = {
        'model':        'MobileNetV2_pretrained_ImageNet',
        'embed_dim':    1280,
        'n_templates':  len(tmpl_paths),
        'n_test':       len(test_pairs),
        'best_mode':    best_mode,
        'verdict':      verdict,
        'modes':        mode_results,
        'elapsed_s':    round(time.time() - t0, 1),
    }
    with open(OUT_EVAL, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f'\n  -> {OUT_EVAL}')
    print(f'  -> {OUT_CONF}')
    print(f'  Total: {time.time()-t0:.1f}s')


def _inconclusive(reason: str) -> None:
    OUT.mkdir(exist_ok=True)
    d = {'verdict': 'INCONCLUSIVE', 'reason': reason}
    with open(OUT_EVAL, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2)
    with open(OUT_CONF, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(['gt\\pred', 'INCONCLUSIVE'])
    print(f'  INCONCLUSIVE: {reason}')


if __name__ == '__main__':
    main()
