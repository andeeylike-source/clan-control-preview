"""
audit_real_crops.py — visual audit + 4-mode ablation on 10 recovered real crops.

Modes tested:
  1. gray32       — current: 32x32 grayscale, mean-sub, L2-norm, cosine
  2. rgb32        — 32x32 RGB (96-dim), per-channel mean-sub, L2-norm, cosine
  3. gray32_pad4  — bbox expanded +4px each side, then gray32
  4. rgb32_pad4   — bbox expanded +4px each side, then rgb32

Extra pads also tabulated: pad0, pad2, pad4, pad6 for gray+rgb (8 sub-modes total).

Outputs:
  out/real_crop_audit.png    — contact sheet
  out/real_crop_ablation.json
"""

import json
import numpy as np
from pathlib import Path
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
REPO        = SCRIPT_DIR.parent.parent
OUT         = SCRIPT_DIR / 'out'
CROPS_DIR   = SCRIPT_DIR / 'crops'

LABELED     = OUT / 'labeled_rows_auto.json'
BATCH_EVAL  = OUT / 'batch_eval.json'

TEMPLATES_DIR = REPO / 'extracted_site_icons_v3'
if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR = REPO / 'extracted_site_icons'

OUT_AUDIT = OUT / 'real_crop_audit.png'
OUT_JSON  = OUT / 'real_crop_ablation.json'

FEAT_SIZE = 32
PAD_VALUES = [0, 2, 4, 6]

# ── Feature functions ──────────────────────────────────────────────────────────
def feat_gray(img: Image.Image) -> np.ndarray:
    """32x32 grayscale → mean-sub → L2-norm."""
    g = img.convert('L').resize((FEAT_SIZE, FEAT_SIZE), Image.BILINEAR)
    v = np.array(g, dtype=np.float32).ravel()
    v -= v.mean()
    n = np.linalg.norm(v)
    return v / n if n > 0 else v

def feat_rgb(img: Image.Image) -> np.ndarray:
    """32x32 RGB → per-channel mean-sub → L2-norm → 96-dim."""
    r = img.convert('RGB').resize((FEAT_SIZE, FEAT_SIZE), Image.BILINEAR)
    a = np.array(r, dtype=np.float32)          # (32,32,3)
    # per-channel mean subtract
    for c in range(3):
        a[:, :, c] -= a[:, :, c].mean()
    v = a.ravel()                               # 96-dim
    n = np.linalg.norm(v)
    return v / n if n > 0 else v

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))

# ── Load templates ─────────────────────────────────────────────────────────────
def load_templates() -> dict:
    """Returns {class_name: {'gray': feat, 'rgb': feat, 'img': PIL Image}}."""
    bank = {}
    for p in sorted(TEMPLATES_DIR.glob('*.png')):
        try:
            img = Image.open(p).convert('RGB')
            bank[p.stem] = {
                'gray': feat_gray(img),
                'rgb':  feat_rgb(img),
                'img':  img,
            }
        except Exception as e:
            print(f'  WARNING: template {p.name}: {e}')
    return bank

# ── Classify ──────────────────────────────────────────────────────────────────
def classify(feat: np.ndarray, bank: dict, mode: str, topk: int = 3):
    scores = {cls: cosine(feat, bank[cls][mode]) for cls in bank}
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top1, s1 = ranked[0]
    s2 = ranked[1][1] if len(ranked) > 1 else 0.0
    top3 = [c for c, _ in ranked[:topk]]
    return top1, s1, s1 - s2, top3

# ── Load test data ─────────────────────────────────────────────────────────────
def load_samples(bank: dict) -> list:
    """Load labeled crops + build features + pad variants."""
    with open(LABELED, encoding='utf-8') as f:
        labeled = json.load(f)
    with open(BATCH_EVAL, encoding='utf-8') as f:
        batch = json.load(f)

    # bbox index
    bbox_idx = {(r['_screen'], r['row']): r['bbox'] for r in batch if r.get('bbox')}

    # available screenshots
    available = {p.name: p for p in SCRIPT_DIR.glob('*.jpg')}

    samples = []
    for rec in labeled:
        screen  = rec['screenshot']
        row_idx = rec['row']
        cls     = rec['final_class']
        cp      = SCRIPT_DIR / rec['crop_path']

        if not cp.exists():
            print(f'  SKIP (no crop file): {cp.name}')
            continue

        bbox = bbox_idx.get((screen, row_idx))
        src  = available.get(screen)

        # Build pad crops from source image
        pad_crops = {}  # pad_px -> PIL Image
        if src and bbox:
            try:
                orig = Image.open(src)
                W, H = orig.size
                for pad in PAD_VALUES:
                    x0 = max(0, bbox['x0'] - pad)
                    y0 = max(0, bbox['y0'] - pad)
                    x1 = min(W, bbox['x1'] + pad)
                    y1 = min(H, bbox['y1'] + pad)
                    pad_crops[pad] = orig.crop((x0, y0, x1, y1))
            except Exception as e:
                print(f'  WARNING pad crops for {screen}: {e}')

        base_img = pad_crops.get(0) or Image.open(cp)

        # Compute all features
        feats = {}
        for pad in PAD_VALUES:
            img = pad_crops.get(pad, base_img)
            feats[f'gray_p{pad}'] = feat_gray(img)
            feats[f'rgb_p{pad}']  = feat_rgb(img)

        samples.append({
            'cls':      cls,
            'screen':   screen,
            'row':      row_idx,
            'crop_img': base_img,          # pad=0 original
            'pad_imgs': pad_crops,
            'feats':    feats,
            'cp':       cp,
        })

    return samples

# ── Run ablation ───────────────────────────────────────────────────────────────
def run_ablation(samples: list, bank: dict) -> dict:
    modes = [f'{c}_p{p}' for p in PAD_VALUES for c in ('gray', 'rgb')]
    # map feat key → bank mode key (gray or rgb)
    bank_mode_map = {f'gray_p{p}': 'gray' for p in PAD_VALUES}
    bank_mode_map.update({f'rgb_p{p}': 'rgb' for p in PAD_VALUES})

    results = {}  # mode -> {top1_acc, top3_acc, low_conf_rate, per_sample}
    for mode in modes:
        bmode = bank_mode_map[mode]
        per = []
        for s in samples:
            feat = s['feats'].get(mode)
            if feat is None:
                continue
            top1, score, margin, top3 = classify(feat, bank, bmode)
            per.append({
                'cls':     s['cls'],
                'top1':    top1,
                'score':   round(score, 4),
                'margin':  round(margin, 4),
                'correct': top1 == s['cls'],
                'in_top3': s['cls'] in top3,
                'low_conf': margin < 0.05,
                'top3':    top3,
            })
        n = len(per)
        if n == 0:
            continue
        results[mode] = {
            'top1_acc':      round(sum(x['correct'] for x in per) / n, 4),
            'top3_acc':      round(sum(x['in_top3'] for x in per) / n, 4),
            'low_conf_rate': round(sum(x['low_conf'] for x in per) / n, 4),
            'n':             n,
            'per_sample':    per,
        }

    return results

# ── Contact sheet ──────────────────────────────────────────────────────────────
CELL    = 56   # px per icon cell
THUMB   = 48   # icon display size
MARGIN  = 4
FONT_SZ = 9

def try_font(size=FONT_SZ):
    for name in ('arial.ttf', 'DejaVuSans.ttf', 'LiberationSans-Regular.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()

def make_contact_sheet(samples: list, bank: dict, ablation: dict) -> Image.Image:
    font     = try_font(FONT_SZ)
    font_hdr = try_font(10)

    # Use gray_p0 and rgb_p4 for display (baseline vs best pad)
    display_modes = ['gray_p0', 'rgb_p0', 'gray_p4', 'rgb_p4']
    bank_mode_map = {f'gray_p{p}': 'gray' for p in PAD_VALUES}
    bank_mode_map.update({f'rgb_p{p}': 'rgb' for p in PAD_VALUES})

    n_crops  = len(samples)
    # Layout: header row + one row per crop
    # Columns: idx | crop_x1 | crop_x4 | exp_tmpl | top1_tmpl_gray | top1_tmpl_rgb | text cols
    COL_LABEL = 120
    COL_ICON  = CELL + MARGIN
    n_icon_cols = 2 + 1 + len(display_modes)  # crop_orig, crop_pad4, exp_tmpl, top1 x4
    ROW_H  = CELL + 30
    HDR_H  = 20
    W = COL_LABEL + n_icon_cols * COL_ICON + 10
    H = HDR_H + n_crops * ROW_H + 10

    sheet = Image.new('RGB', (W, H), (30, 30, 30))
    draw  = ImageDraw.Draw(sheet)

    # Header
    headers = ['class', 'crop×1', 'crop×4', 'exp tmpl', 'gray_p0', 'rgb_p0', 'gray_p4', 'rgb_p4']
    x = MARGIN
    for hdr in headers:
        draw.text((x, 4), hdr, font=font_hdr, fill=(180, 180, 180))
        x += COL_LABEL if hdr == 'class' else COL_ICON

    for ri, s in enumerate(samples):
        y = HDR_H + ri * ROW_H
        x = MARGIN

        # Class label
        draw.text((x, y + 4), s['cls'], font=font, fill=(255, 255, 180))
        draw.text((x, y + 16), f"{s['screen'][-8:]} r{s['row']}", font=font, fill=(120, 120, 120))
        x += COL_LABEL

        # crop original (1:1)
        c_orig = s['crop_img'].convert('RGB')
        sheet.paste(c_orig, (x + MARGIN, y + MARGIN))
        x += COL_ICON

        # crop ×4 (nearest)
        cw, ch = c_orig.size
        c_big = c_orig.resize((min(THUMB, cw * 4), min(THUMB, ch * 4)), Image.NEAREST)
        sheet.paste(c_big, (x + MARGIN, y + MARGIN))
        x += COL_ICON

        # expected template
        if s['cls'] in bank:
            tmpl_img = bank[s['cls']]['img'].convert('RGB').resize((THUMB, THUMB), Image.BILINEAR)
            sheet.paste(tmpl_img, (x + MARGIN, y + MARGIN))
        x += COL_ICON

        # per mode: top1 template + score text
        for mode in display_modes:
            feat = s['feats'].get(mode)
            if feat is None:
                x += COL_ICON
                continue
            bmode = bank_mode_map[mode]
            top1, score, margin_val, top3 = classify(feat, bank, bmode)
            correct = top1 == s['cls']
            col = (100, 220, 100) if correct else (220, 80, 80)

            if top1 in bank:
                t_img = bank[top1]['img'].convert('RGB').resize((THUMB // 2, THUMB // 2), Image.BILINEAR)
                sheet.paste(t_img, (x + MARGIN, y + MARGIN))

            # Short class name (first word or 8 chars)
            short = top1.split()[0][:8]
            draw.text((x + MARGIN, y + THUMB // 2 + MARGIN + 4), short, font=font, fill=col)
            draw.text((x + MARGIN, y + THUMB // 2 + MARGIN + 14),
                      f's={score:.2f} m={margin_val:.2f}', font=font, fill=(160, 160, 160))
            x += COL_ICON

        # Row separator
        draw.line([(0, y + ROW_H - 1), (W, y + ROW_H - 1)], fill=(60, 60, 60))

    return sheet

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f'Templates: {TEMPLATES_DIR}')
    bank = load_templates()
    print(f'  {len(bank)} classes')

    samples = load_samples(bank)
    print(f'Samples loaded: {len(samples)}')
    if not samples:
        print('ERROR: no samples found')
        return

    ablation = run_ablation(samples, bank)

    # ── Console summary ───────────────────────────────────────────────────────
    print()
    print('=' * 70)
    print(f'  {"mode":<14} {"top1":>6} {"top3":>6} {"low_conf":>9}')
    print('  ' + '-' * 36)
    best_top1 = -1
    best_mode = ''
    for mode, res in sorted(ablation.items()):
        mark = ''
        if res['top1_acc'] > best_top1:
            best_top1 = res['top1_acc']
            best_mode = mode
            mark = ' <'
        print(f'  {mode:<14} {res["top1_acc"]:>6.1%} {res["top3_acc"]:>6.1%} {res["low_conf_rate"]:>9.1%}{mark}')
    print('=' * 70)
    print(f'  best mode: {best_mode}  top1={best_top1:.1%}')

    # Detailed per-sample for best mode
    if best_mode in ablation:
        print(f'\n  Per-sample [{best_mode}]:')
        for p in ablation[best_mode]['per_sample']:
            ok = 'OK' if p['correct'] else 'FAIL'
            print(f'    {p["cls"]:<22} -> {p["top1"]:<22} s={p["score"]:.3f} m={p["margin"]:.3f}  [{ok}]')

    # ── Write outputs ─────────────────────────────────────────────────────────
    summary = {
        'n_samples':   len(samples),
        'n_classes':   len({s['cls'] for s in samples}),
        'templates':   {'dir': str(TEMPLATES_DIR), 'classes': len(bank)},
        'best_mode':   best_mode,
        'best_top1':   best_top1,
        'modes':       {
            m: {k: v for k, v in res.items() if k != 'per_sample'}
            for m, res in ablation.items()
        },
        'per_sample_best': ablation.get(best_mode, {}).get('per_sample', []),
        'verdict': (
            'RGB_OR_PAD_HELPS' if best_top1 > 0.3 else
            'FEATURE_SPACE_DEAD'
        ),
        'verdict_reason': (
            f'best={best_mode} top1={best_top1:.1%}; '
            + ('padding/RGB improves over gray_p0 baseline'
               if best_mode != 'gray_p0' else 'no improvement from pad/RGB')
        ),
    }

    OUT.mkdir(exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f'\n  -> {OUT_JSON}')

    sheet = make_contact_sheet(samples, bank, ablation)
    sheet.save(OUT_AUDIT)
    print(f'  -> {OUT_AUDIT}  ({sheet.width}x{sheet.height})')
    print('=' * 70)


if __name__ == '__main__':
    main()
