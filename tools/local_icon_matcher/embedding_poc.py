"""
embedding_poc.py — ORB/AKAZE + template-match PoC (cv2 only, no torch/onnx).

Runs three matchers:
  1. ORB  (BFMatcher Hamming, top-k keypoint overlap)
  2. AKAZE (BFMatcher Hamming)
  3. TM   (cv2.TM_CCOEFF_NORMED — resize template to crop size)

For each crop the best cosine/score class is picked; top1/top3 computed.

Outputs:
  out/embedding_eval.json
  out/embedding_confusion.csv

Verdict:
  EMBEDDING_ALIVE  if top1 >= 50% OR top3 >= 70%
  EMBEDDING_DEAD   if top1 <  50% AND top3 <  70%
  INCONCLUSIVE     if deps/data missing
"""

from __future__ import annotations
import csv
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

# cv2.imread fails on Windows Unicode paths — use imdecode instead
def _cv2_imread_unicode(path: Path, flags: int = cv2.IMREAD_GRAYSCALE) -> np.ndarray | None:
    buf = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(buf, flags)

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent.parent
TEMPLATES  = ROOT / 'extracted_site_icons_v3'
CROPS_DIR  = Path(__file__).resolve().parent / 'crops'
LABELS_JSON= Path(__file__).resolve().parent / 'out' / 'labeled_rows.json'
OUT        = Path(__file__).resolve().parent / 'out'
OUT_EVAL   = OUT / 'embedding_eval.json'
OUT_CONF   = OUT / 'embedding_confusion.csv'

# ── constants ──────────────────────────────────────────────────────────────────
RESIZE     = (32, 32)   # all images normalised to this before matching
TOP_K      = 5          # for ORB/AKAZE: keep top-K matches per pair


# ── helpers ───────────────────────────────────────────────────────────────────

def load_gray(path: Path) -> np.ndarray | None:
    """Load image as uint8 grayscale via cv2 (Unicode-safe on Windows)."""
    img = _cv2_imread_unicode(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return cv2.resize(img, RESIZE, interpolation=cv2.INTER_AREA)


def labeled_crop_to_filename(crop_path_str: str) -> str:
    """
    labeled_rows.json stores paths like:
      crops/photo_2026-03-26_22-45-09 (3).jpg_row001.png
    Actual files on disk:
      photo_2026-03-26_22-45-09_(3)_row001.png
    """
    base = Path(crop_path_str).name          # photo_2026-03-26_22-45-09 (3).jpg_row001.png
    # remove .jpg part that appears in the middle
    base = re.sub(r'\.jpg_row', '_row', base)   # → photo_2026-03-26_22-45-09 (3)_row001.png
    # replace space+paren with underscore+paren
    base = re.sub(r' \((\d+)\)', r'_(\1)', base) # → photo_2026-03-26_22-45-09_(3)_row001.png
    return base


def orb_score(det, img_a: np.ndarray, img_b: np.ndarray) -> float:
    """
    ORB or AKAZE: returns fraction of good matches / TOP_K (0..1).
    Higher = more similar.
    """
    kp_a, des_a = det.detectAndCompute(img_a, None)
    kp_b, des_b = det.detectAndCompute(img_b, None)
    if des_a is None or des_b is None or len(des_a) < 2 or len(des_b) < 2:
        return 0.0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des_a, des_b)
    if not matches:
        return 0.0
    matches = sorted(matches, key=lambda m: m.distance)[:TOP_K]
    # normalise: distance 0 → score 1, distance 256 → score 0
    scores = [max(0.0, 1.0 - m.distance / 256.0) for m in matches]
    return float(np.mean(scores))


def tm_score(templ: np.ndarray, crop: np.ndarray) -> float:
    """Normalised cross-correlation template match, returns value in [0,1]."""
    res = cv2.matchTemplate(crop, templ, cv2.TM_CCOEFF_NORMED)
    _, val, _, _ = cv2.minMaxLoc(res)
    return float((val + 1.0) / 2.0)   # shift from [-1,1] to [0,1]


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()

    # ── load templates ──
    if not TEMPLATES.exists():
        print(f'ERROR: templates dir missing: {TEMPLATES}')
        _write_inconclusive('templates_dir_missing')
        return

    tmpl_imgs: dict[str, np.ndarray] = {}
    for p in sorted(TEMPLATES.glob('*.png')):
        cls = p.stem
        img = load_gray(p)
        if img is not None:
            tmpl_imgs[cls] = img

    if not tmpl_imgs:
        print('ERROR: no template images found')
        _write_inconclusive('no_templates')
        return

    classes = sorted(tmpl_imgs.keys())
    print(f'Templates loaded: {len(classes)} classes')

    # ── load crop labels ──
    if not LABELS_JSON.exists():
        print(f'ERROR: labels missing: {LABELS_JSON}')
        _write_inconclusive('labels_missing')
        return

    with open(LABELS_JSON, encoding='utf-8') as f:
        label_rows = json.load(f)

    test_pairs: list[tuple[str, np.ndarray]] = []
    for row in label_rows:
        gt_cls  = row.get('final_class', '')
        cp_str  = row.get('crop_path', '')
        fname   = labeled_crop_to_filename(cp_str)
        cp_path = CROPS_DIR / fname
        if not cp_path.exists():
            print(f'  WARN: crop not found: {cp_path.name}')
            continue
        img = load_gray(cp_path)
        if img is None:
            print(f'  WARN: failed to load: {cp_path.name}')
            continue
        test_pairs.append((gt_cls, img))

    if not test_pairs:
        print('ERROR: no test crops loaded')
        _write_inconclusive('no_crops')
        return

    print(f'Test crops loaded: {len(test_pairs)}')

    # ── detectors ──
    orb  = cv2.ORB_create(nfeatures=64)
    try:
        akaze = cv2.AKAZE_create()
        _akaze_ok = True
    except Exception:
        akaze = None
        _akaze_ok = False

    # ── evaluate ──
    rows_out = []
    for gt_cls, crop in test_pairs:
        best: dict[str, tuple[str, float]] = {}   # matcher → (pred_cls, score)

        orb_scores:   dict[str, float] = {}
        akaze_scores: dict[str, float] = {}
        tm_scores:    dict[str, float] = {}

        for cls, tmpl in tmpl_imgs.items():
            orb_scores[cls]  = orb_score(orb, tmpl, crop)
            if _akaze_ok and akaze is not None:
                akaze_scores[cls] = orb_score(akaze, tmpl, crop)
            # template match: tmpl is already RESIZE, crop too
            tm_scores[cls] = tm_score(tmpl, crop)

        def top_n(scores, n):
            return sorted(scores.items(), key=lambda x: -x[1])[:n]

        orb_top  = top_n(orb_scores, 3)
        tm_top   = top_n(tm_scores, 3)

        # fused score (simple average of normalised TM + ORB)
        fused: dict[str, float] = {}
        for cls in classes:
            fused[cls] = 0.5 * tm_scores.get(cls, 0.0) + 0.5 * orb_scores.get(cls, 0.0)
        fused_top = top_n(fused, 3)

        pred1_cls, pred1_sc = fused_top[0]
        top3_cls = [c for c, _ in fused_top]

        ok1 = pred1_cls == gt_cls
        ok3 = gt_cls in top3_cls

        # find gt rank
        fused_sorted = sorted(fused.items(), key=lambda x: -x[1])
        gt_rank = next((i+1 for i, (c,_) in enumerate(fused_sorted) if c == gt_cls), len(classes))

        rows_out.append({
            'gt_class':   gt_cls,
            'pred_class': pred1_cls,
            'pred_score': round(pred1_sc, 4),
            'top3':       top3_cls,
            'ok1':        ok1,
            'ok3':        ok3,
            'gt_rank':    gt_rank,
            'orb_pred':   orb_top[0][0],
            'orb_score':  round(orb_top[0][1], 4),
            'tm_pred':    tm_top[0][0],
            'tm_score':   round(tm_top[0][1], 4),
        })

        mark1 = 'OK' if ok1 else 'FAIL'
        mark3 = 'top3' if ok3 else ''
        print(f'  {gt_cls:<22} -> {pred1_cls:<22} ({pred1_sc:.3f}) {mark1} {mark3}')

    # ── metrics ──
    n = len(rows_out)
    top1_n = sum(r['ok1'] for r in rows_out)
    top3_n = sum(r['ok3'] for r in rows_out)
    top1_acc = top1_n / n if n else 0.0
    top3_acc = top3_n / n if n else 0.0

    low_conf_n = sum(1 for r in rows_out if r['pred_score'] < 0.55)
    low_conf   = low_conf_n / n if n else 0.0

    if top1_acc >= 0.5 or top3_acc >= 0.7:
        verdict = 'EMBEDDING_ALIVE'
    else:
        verdict = 'EMBEDDING_DEAD'

    # confusion matrix (gt vs pred)
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows_out:
        confusion[r['gt_class']][r['pred_class']] += 1

    print(f'\n{"="*60}')
    print(f'  VERDICT: {verdict}')
    print(f'  top1_acc  : {top1_acc*100:.1f}% ({top1_n}/{n})')
    print(f'  top3_acc  : {top3_acc*100:.1f}% ({top3_n}/{n})')
    print(f'  low_conf  : {low_conf*100:.1f}%')
    print(f'{"="*60}')

    # ── outputs ──
    OUT.mkdir(exist_ok=True)

    summary = {
        'matcher':    'ORB+TM_fused (cv2, no torch/onnx)',
        'resize':     list(RESIZE),
        'top_k_feat': TOP_K,
        'n_templates': len(classes),
        'n_test':     n,
        'top1_acc':   round(top1_acc, 4),
        'top3_acc':   round(top3_acc, 4),
        'low_conf':   round(low_conf, 4),
        'verdict':    verdict,
        'missing_deps': ['torch (CNN embeddings)', 'onnxruntime', 'scikit-image'],
        'per_sample': rows_out,
        'elapsed_s':  round(time.time() - t0, 1),
    }
    with open(OUT_EVAL, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f'\n  -> {OUT_EVAL}')

    # confusion CSV
    gt_classes_seen = sorted({r['gt_class'] for r in rows_out})
    pred_classes_seen = sorted({r['pred_class'] for r in rows_out})
    all_cls = sorted(set(gt_classes_seen) | set(pred_classes_seen))
    with open(OUT_CONF, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['gt\\pred'] + all_cls)
        for gt in gt_classes_seen:
            row_vals = [confusion[gt].get(pc, 0) for pc in all_cls]
            w.writerow([gt] + row_vals)
    print(f'  -> {OUT_CONF}')
    print(f'\n  Total time: {time.time()-t0:.1f}s')


def _write_inconclusive(reason: str) -> None:
    OUT.mkdir(exist_ok=True)
    summary = {
        'verdict': 'INCONCLUSIVE',
        'reason':  reason,
        'missing_deps': ['torch', 'onnxruntime'],
        'available': ['cv2'],
    }
    with open(OUT_EVAL, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    # empty confusion
    with open(OUT_CONF, 'w', newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(['gt\\pred', 'INCONCLUSIVE'])
    print(f'  -> {OUT_EVAL} (INCONCLUSIVE: {reason})')


if __name__ == '__main__':
    main()
