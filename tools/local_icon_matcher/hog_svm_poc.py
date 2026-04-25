"""
hog_svm_poc.py — HOG + kNN icon classifier PoC (numpy-only, no sklearn/skimage).

Dependencies available:  numpy, PIL/Pillow
Dependencies missing:    scikit-learn, scikit-image
  To unlock LinearSVC/SVC-RBF and skimage.feature.hog, run:
    pip install scikit-learn scikit-image
  This script uses a pure-numpy HOG + cosine-kNN fallback that runs without them.

Pipeline:
  clean template (48-56px PNG)
    → downscale to live sizes (18x16, 20x18, 22x18)
    → JPEG compress (Q=40/55/65/75) via BytesIO
    → Gaussian noise (sigma 5/10/15)
    → brightness jitter (0.85/1.0/1.15)
    → pixel shift ±1/±2
    → HOG 32x32, 8px cells, 2x2 blocks, 9 bins  → 324-dim feature
    → kNN (cosine, k=5) over training bank

Eval: 10 real crops in tools/local_icon_matcher/crops/
Outputs:
  out/hog_svm_eval.json
  out/hog_svm_weights.json  (kNN bank serialized as lists; SVM=null)

Verdict thresholds:
  HOG_KNN_ALIVE   if top1 >= 50% AND top3 >= 70%
  HOG_KNN_DEAD    if top1 <  50%
  INCONCLUSIVE    otherwise
"""

from __future__ import annotations
import io
import json
import random
import time
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict
from PIL import Image, ImageFilter

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).parent
REPO          = SCRIPT_DIR.parent.parent
OUT           = SCRIPT_DIR / 'out'
CROPS_DIR     = SCRIPT_DIR / 'crops'
LABELED       = OUT / 'labeled_rows_auto.json'
TEMPLATES_DIR = REPO / 'extracted_site_icons_v3'
if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR = REPO / 'extracted_site_icons'

OUT_EVAL    = OUT / 'hog_svm_eval.json'
OUT_WEIGHTS = OUT / 'hog_svm_weights.json'

# ── HOG (numpy-only) ──────────────────────────────────────────────────────────
HOG_SIZE     = 32   # resize target before HOG
CELL_PX      = 8    # pixels per HOG cell
BLOCK_CELLS  = 2    # cells per block side
ORIENTATIONS = 9    # gradient orientation bins
EPS          = 1e-5

def _hog_feat(img: Image.Image) -> np.ndarray:
    """Pure-numpy HOG: 32x32 → 324-dim float32 feature vector."""
    g = img.convert('L').resize((HOG_SIZE, HOG_SIZE), Image.BILINEAR)
    a = np.array(g, dtype=np.float32)

    # Gradients (central differences, zero-padded at edges)
    gx = np.zeros_like(a)
    gy = np.zeros_like(a)
    gx[:, 1:-1] = a[:, 2:] - a[:, :-2]
    gy[1:-1, :]  = a[2:, :] - a[:-2, :]

    mag = np.sqrt(gx**2 + gy**2)
    ori = np.arctan2(np.abs(gy), np.abs(gx)) * (180.0 / np.pi)  # 0-90 → mapped to 0-180

    # Cell histograms
    n_cy = HOG_SIZE // CELL_PX
    n_cx = HOG_SIZE // CELL_PX
    cell_h = np.zeros((n_cy, n_cx, ORIENTATIONS), dtype=np.float32)
    bin_w  = 180.0 / ORIENTATIONS

    for cy in range(n_cy):
        for cx in range(n_cx):
            cm = mag[cy*CELL_PX:(cy+1)*CELL_PX, cx*CELL_PX:(cx+1)*CELL_PX]
            co = ori[cy*CELL_PX:(cy+1)*CELL_PX, cx*CELL_PX:(cx+1)*CELL_PX]
            bins = np.floor(co / bin_w).astype(int).clip(0, ORIENTATIONS - 1)
            for b in range(ORIENTATIONS):
                cell_h[cy, cx, b] = cm[bins == b].sum()

    # Block normalization (L2-Hys)
    blocks = []
    n_by = n_cy - BLOCK_CELLS + 1
    n_bx = n_cx - BLOCK_CELLS + 1
    for by in range(n_by):
        for bx in range(n_bx):
            blk = cell_h[by:by+BLOCK_CELLS, bx:bx+BLOCK_CELLS, :].ravel()
            blk = blk / (np.linalg.norm(blk) + EPS)
            blk = blk.clip(0.2)           # Hys clipping
            blk = blk / (np.linalg.norm(blk) + EPS)
            blocks.append(blk)

    return np.concatenate(blocks)  # (n_by * n_bx * BLOCK_CELLS^2 * ORIENTATIONS,)

# ── kNN (cosine, numpy-only) ───────────────────────────────────────────────────
def _cosine_topk(query: np.ndarray, bank_feats: np.ndarray,
                 bank_labels: list[str], k: int = 5, topk_cls: int = 3):
    """Return top1 class, top1 score, margin, and topk_cls distinct classes."""
    sims = bank_feats @ query  # (N,) cosine similarities (all feats L2-normed)
    order = np.argsort(sims)[::-1]

    # Aggregate by class: best sim per class
    class_best: dict[str, float] = {}
    for idx in order:
        cls = bank_labels[idx]
        s   = float(sims[idx])
        if cls not in class_best:
            class_best[cls] = s
        if len(class_best) >= topk_cls + 5:
            break

    ranked = sorted(class_best.items(), key=lambda x: -x[1])
    top1, s1 = ranked[0]
    s2       = ranked[1][1] if len(ranked) > 1 else 0.0
    top3     = [c for c, _ in ranked[:topk_cls]]
    return top1, s1, s1 - s2, top3

# ── Augmentation ──────────────────────────────────────────────────────────────
LIVE_SIZES   = [(18, 16), (20, 18), (22, 18)]
JPEG_QUALS   = [None, 40, 55, 65, 75]   # None = no JPEG
NOISE_SIGMAS = [0, 8, 15]
BRIGHTNESSES = [0.85, 1.0, 1.15]
SHIFTS       = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0)]

CANVAS_SIZE  = (HOG_SIZE, HOG_SIZE)   # final size fed to HOG

def _jpeg_compress(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=quality)
    buf.seek(0)
    return Image.open(buf).copy()

def _add_noise(img: Image.Image, sigma: float) -> Image.Image:
    a = np.array(img, dtype=np.float32)
    a += np.random.randn(*a.shape) * sigma
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))

def _brightness(img: Image.Image, factor: float) -> Image.Image:
    a = np.array(img, dtype=np.float32) * factor
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))

def _shift(img: Image.Image, dx: int, dy: int) -> Image.Image:
    """Shift by (dx,dy), fill border with edge color."""
    if dx == 0 and dy == 0:
        return img
    w, h = img.size
    canvas = Image.new(img.mode, (w, h), 0)
    canvas.paste(img, (dx, dy))
    return canvas

def augment_template(template_img: Image.Image, seed: int = 0) -> list[Image.Image]:
    """Generate augmented variants of one clean template."""
    rng = random.Random(seed)
    results = []

    for tw, th in LIVE_SIZES:
        small = template_img.resize((tw, th), Image.BILINEAR)
        for jq in JPEG_QUALS:
            j_img = _jpeg_compress(small, jq) if jq else small
            big   = j_img.resize(CANVAS_SIZE, Image.BILINEAR)
            for sigma in NOISE_SIGMAS:
                n_img = _add_noise(big, sigma) if sigma else big
                for bf in BRIGHTNESSES:
                    b_img = _brightness(n_img, bf) if bf != 1.0 else n_img
                    for dx, dy in SHIFTS:
                        results.append(_shift(b_img, dx, dy))
    # shuffle so kNN doesn't skew on systematic patterns
    rng.shuffle(results)
    return results

# ── Build training bank ────────────────────────────────────────────────────────
def build_bank() -> tuple[np.ndarray, list[str], list[str]]:
    """Returns (feats_matrix N×D, labels list, classes list)."""
    feats_list: list[np.ndarray] = []
    labels:     list[str]        = []

    for p in sorted(TEMPLATES_DIR.glob('*.png')):
        cls = p.stem
        try:
            tmpl = Image.open(p).convert('RGB')
        except Exception as e:
            print(f'  WARN: skip {p.name}: {e}')
            continue

        augmented = augment_template(tmpl, seed=hash(cls) & 0xFFFF)
        for aug in augmented:
            feat = _hog_feat(aug)
            # L2-normalize for cosine
            n = np.linalg.norm(feat)
            if n > EPS:
                feat /= n
            feats_list.append(feat)
            labels.append(cls)

    feats = np.array(feats_list, dtype=np.float32)
    classes = sorted(set(labels))
    print(f'  Bank: {len(classes)} classes, {len(feats)} training samples '
          f'({len(feats) // len(classes)} aug/class), feat_dim={feats.shape[1]}')
    return feats, labels, classes

# ── Load test crops ────────────────────────────────────────────────────────────
def load_test() -> list[dict]:
    with open(LABELED, encoding='utf-8') as f:
        labeled = json.load(f)

    samples = []
    for rec in labeled:
        cp  = SCRIPT_DIR / rec['crop_path']
        cls = rec['final_class']
        if not cp.exists():
            continue
        try:
            img  = Image.open(cp).convert('RGB')
            feat = _hog_feat(img)
            n    = np.linalg.norm(feat)
            if n > EPS:
                feat /= n
            samples.append({'cls': cls, 'feat': feat, 'screen': rec['screenshot'],
                             'row': rec['row'], 'path': str(cp)})
        except Exception as e:
            print(f'  WARN: crop {cp.name}: {e}')
    return samples

# ── Evaluate ───────────────────────────────────────────────────────────────────
def evaluate(samples: list[dict], bank_feats: np.ndarray,
             bank_labels: list[str]) -> list[dict]:
    rows = []
    for s in samples:
        top1, score, margin, top3 = _cosine_topk(s['feat'], bank_feats, bank_labels)
        rows.append({
            'cls':      s['cls'],
            'top1':     top1,
            'score':    round(score, 4),
            'margin':   round(margin, 4),
            'correct':  top1 == s['cls'],
            'in_top3':  s['cls'] in top3,
            'low_conf': margin < 0.05,
            'top3':     top3,
            'screen':   s['screen'],
            'row':      s['row'],
        })
    return rows

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f'Templates: {TEMPLATES_DIR}')
    print(f'Crops:     {CROPS_DIR}')
    print()

    t0 = time.time()
    print('Building augmented HOG training bank ...')
    bank_feats, bank_labels, classes = build_bank()
    print(f'  Done in {time.time()-t0:.1f}s')

    print('\nLoading test crops ...')
    samples = load_test()
    print(f'  {len(samples)} test crops')
    if not samples:
        print('ERROR: no test crops found')
        return

    print('\nEvaluating ...')
    rows = evaluate(samples, bank_feats, bank_labels)

    n = len(rows)
    top1_acc      = sum(r['correct']  for r in rows) / n
    top3_acc      = sum(r['in_top3']  for r in rows) / n
    low_conf_rate = sum(r['low_conf'] for r in rows) / n

    # Verdict
    if top1_acc >= 0.50 and top3_acc >= 0.70:
        verdict = 'HOG_KNN_ALIVE'
    elif top1_acc < 0.50:
        verdict = 'HOG_KNN_DEAD'
    else:
        verdict = 'INCONCLUSIVE'

    # Console
    print()
    print('=' * 60)
    print(f'  VERDICT: {verdict}')
    print(f'  top1_acc    : {top1_acc:.1%}   ({sum(r["correct"] for r in rows)}/{n})')
    print(f'  top3_acc    : {top3_acc:.1%}   ({sum(r["in_top3"] for r in rows)}/{n})')
    print(f'  low_conf    : {low_conf_rate:.1%}')
    print()
    print(f'  {"class":<22} {"pred":<22} {"score":>6} {"margin":>7}  ok?')
    print('  ' + '-' * 64)
    for r in rows:
        ok = 'OK  ' if r['correct'] else 'FAIL'
        print(f'  {r["cls"]:<22} {r["top1"]:<22} {r["score"]:>6.3f} {r["margin"]:>7.3f}  {ok}')
    print('=' * 60)

    # Write eval JSON
    summary = {
        'verdict':        verdict,
        'n_samples':      n,
        'n_classes':      len({r['cls'] for r in rows}),
        'top1_accuracy':  round(top1_acc, 4),
        'top3_accuracy':  round(top3_acc, 4),
        'low_conf_rate':  round(low_conf_rate, 4),
        'model':          'HOG_cosine_kNN',
        'hog_params': {
            'feat_size':    HOG_SIZE,
            'cell_px':      CELL_PX,
            'block_cells':  BLOCK_CELLS,
            'orientations': ORIENTATIONS,
            'feat_dim':     bank_feats.shape[1],
        },
        'aug_params': {
            'live_sizes':   LIVE_SIZES,
            'jpeg_quals':   JPEG_QUALS,
            'noise_sigmas': NOISE_SIGMAS,
            'brightnesses': BRIGHTNESSES,
            'shifts':       SHIFTS,
            'n_aug_per_class': len(bank_feats) // len(classes),
        },
        'per_sample': rows,
        'missing_deps': ['scikit-learn (LinearSVC/SVC-RBF)', 'scikit-image (hog)'],
        'pip_install':  'pip install scikit-learn scikit-image',
    }

    OUT.mkdir(exist_ok=True)
    with open(OUT_EVAL, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f'\n  -> {OUT_EVAL}')

    # Write weights JSON
    # Serialize full kNN bank (may be large but usable for JS lookup)
    weights = {
        'model':       'HOG_cosine_kNN',
        'feat_dim':    bank_feats.shape[1],
        'n_train':     len(bank_feats),
        'classes':     classes,
        'note': (
            'kNN bank is too large for practical JS export. '
            'To get compact weights, install scikit-learn and run with LinearSVC: '
            'pip install scikit-learn scikit-image'
        ),
        'exportable':  False,
        'reason':      'kNN requires full training bank (~' + str(len(bank_feats)) + ' vectors x ' +
                       str(bank_feats.shape[1]) + ' dims); no compact weight representation',
        'svm_weights': None,
    }

    with open(OUT_WEIGHTS, 'w', encoding='utf-8') as f:
        json.dump(weights, f, indent=2)
    print(f'  -> {OUT_WEIGHTS}')
    print(f'\n  Total time: {time.time()-t0:.1f}s')


if __name__ == '__main__':
    main()
