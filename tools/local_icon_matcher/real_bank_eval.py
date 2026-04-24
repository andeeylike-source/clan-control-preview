"""
real_bank_eval.py — evaluate real-bank RGB32 template matching on labeled CC icon crops.

Data sources (priority order):
  1. labeled_rows_auto.json + labeled_rows.json + crop image files  (PRIMARY — missing in repo)
  2. audit_crops/ + audit_rows.json   (FALLBACK — pseudo-GT = previous matcher best_match)
  3. roi_row_crops/ + roi_rows.json   (FALLBACK — pseudo-GT = previous matcher best_match)

Template bank: extracted_site_icons_v3/*.png  (72 clean class templates)

Feature: 32x32 grayscale, mean-subtract, L2-normalize, cosine similarity
Class score: max similarity among all templates of that class
"""

import json
import csv
import numpy as np
from pathlib import Path
from collections import defaultdict

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
REPO         = SCRIPT_DIR.parent.parent
OUT          = SCRIPT_DIR / 'out'

LABELED_AUTO = OUT / 'labeled_rows_auto.json'
LABELED_MAN  = OUT / 'labeled_rows.json'
AUDIT_ROWS   = OUT / 'audit_rows.json'
AUDIT_CROPS  = OUT / 'audit_crops'
ROI_ROWS     = OUT / 'roi_rows.json'
ROI_CROPS    = OUT / 'roi_row_crops'

TEMPLATES_DIR = REPO / 'extracted_site_icons_v3'
if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR = REPO / 'extracted_site_icons'

OUT_JSON = OUT / 'real_bank_eval.json'
OUT_CSV  = OUT / 'real_bank_confusion.csv'

FEAT_SIZE               = 32
MIN_SAMPLES_FOR_METRIC  = 4  # classes with fewer samples → insufficient_data

# ── Feature extraction ────────────────────────────────────────────────────────
def img_to_feat(img_path: Path) -> np.ndarray:
    """32×32 grayscale → mean-subtract → L2-normalize."""
    from PIL import Image
    img = Image.open(img_path).convert('L').resize(
        (FEAT_SIZE, FEAT_SIZE), Image.BILINEAR
    )
    v = np.array(img, dtype=np.float32).ravel()
    v -= v.mean()
    n = np.linalg.norm(v)
    if n > 0:
        v /= n
    return v

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))

# ── Build template bank ───────────────────────────────────────────────────────
def build_bank() -> dict:
    bank = defaultdict(list)
    for p in sorted(TEMPLATES_DIR.glob('*.png')):
        try:
            bank[p.stem].append(img_to_feat(p))
        except Exception as e:
            print(f'  WARNING: could not load template {p.name}: {e}')
    return dict(bank)

# ── Classify ──────────────────────────────────────────────────────────────────
def classify(feat: np.ndarray, bank: dict, topk: int = 3):
    scores = {cls: max(cosine(feat, t) for t in tmpl)
              for cls, tmpl in bank.items()}
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top1_cls, top1_score = ranked[0]
    top2_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin     = top1_score - top2_score
    top3_cls   = [c for c, _ in ranked[:topk]]
    return top1_cls, top1_score, margin, top3_cls

# ── Load test data ────────────────────────────────────────────────────────────
def load_labeled(base: Path) -> list:
    """Load samples from labeled_rows*.json where crop image files exist."""
    samples = []
    for jf in [LABELED_AUTO, LABELED_MAN]:
        if not jf.exists():
            continue
        with open(jf, encoding='utf-8') as f:
            rows = json.load(f)
        for r in rows:
            cls = r.get('final_class')
            cp  = r.get('crop_path')
            if not cls or not cp:
                continue
            p = SCRIPT_DIR / cp
            if not p.exists():
                continue
            try:
                samples.append({
                    'cls':    cls,
                    'screen': r.get('screenshot', '?'),
                    'feat':   img_to_feat(p),
                    'source': 'labeled',
                })
            except Exception:
                pass
    return samples


def load_fallback() -> list:
    """Load audit_crops + roi_row_crops with pseudo-GT from matcher results."""
    samples = []

    if AUDIT_ROWS.exists() and AUDIT_CROPS.exists():
        with open(AUDIT_ROWS, encoding='utf-8') as f:
            audit = json.load(f)
        for r in audit:
            cls = r.get('best_match')
            if not cls:
                continue
            p = AUDIT_CROPS / f"r{r['row']:02d}_icon_raw.png"
            if not p.exists():
                continue
            try:
                samples.append({
                    'cls':    cls,
                    'screen': 'audit_Shot00000',
                    'feat':   img_to_feat(p),
                    'source': 'audit_pseudo_gt',
                    'prev_conf': r.get('confidence'),
                })
            except Exception:
                pass

    if ROI_ROWS.exists() and ROI_CROPS.exists():
        with open(ROI_ROWS, encoding='utf-8') as f:
            roi = json.load(f)
        for r in roi:
            cls = r.get('best_match')
            if not cls:
                continue
            p = ROI_CROPS / f"row{r['row']:02d}_icon.png"
            if not p.exists():
                continue
            try:
                samples.append({
                    'cls':    cls,
                    'screen': 'roi_Shot00001',
                    'feat':   img_to_feat(p),
                    'source': 'roi_pseudo_gt',
                    'prev_conf': r.get('confidence'),
                })
            except Exception:
                pass

    return samples

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f'Template bank: {TEMPLATES_DIR}')
    bank = build_bank()
    n_templates = sum(len(v) for v in bank.values())
    print(f'  {len(bank)} classes, {n_templates} templates')

    # Primary: labeled crops
    samples = load_labeled(REPO)
    data_source = 'labeled_crops'
    primary_blocked = False

    if not samples:
        print('WARNING: labeled crop images not found. Using pseudo-GT fallback.')
        samples     = load_fallback()
        data_source = 'pseudo_gt_fallback (audit+roi, GT=matcher best_match)'
        primary_blocked = True

    if not samples:
        result = {
            'status':      'BLOCKED',
            'reason':      'No crop images found — labeled crop files and fallback crops both absent',
            'data_source': data_source,
            'verdict':     'INCONCLUSIVE',
        }
        with open(OUT_JSON, 'w') as f:
            json.dump(result, f, indent=2)
        print('BLOCKED: no crop images available.')
        return

    print(f'Test set: {len(samples)} samples  source={data_source}')
    screens = set(s['screen'] for s in samples)
    print(f'  screens: {sorted(screens)}')

    # ── Run classification ────────────────────────────────────────────────────
    rows = []
    for s in samples:
        top1, score, margin, top3 = classify(s['feat'], bank)
        rows.append({
            'cls':     s['cls'],
            'top1':    top1,
            'score':   round(score, 4),
            'margin':  round(margin, 4),
            'top3':    top3,
            'correct': top1 == s['cls'],
            'in_top3': s['cls'] in top3,
            'low_conf':margin < 0.05,
            'screen':  s['screen'],
            'source':  s['source'],
        })

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    n = len(rows)
    top1_acc      = sum(r['correct']  for r in rows) / n
    top3_acc      = sum(r['in_top3']  for r in rows) / n
    low_conf_rate = sum(r['low_conf'] for r in rows) / n

    by_class = defaultdict(list)
    for r in rows:
        by_class[r['cls']].append(r)

    per_class            = {}
    insufficient_classes = []
    sufficient_classes   = []

    for cls in sorted(by_class):
        cr  = by_class[cls]
        n_c = len(cr)
        acc = sum(x['correct'] for x in cr) / n_c
        per_class[cls] = {'n': n_c, 'top1_acc': round(acc, 3)}
        if n_c < MIN_SAMPLES_FOR_METRIC:
            insufficient_classes.append(cls)
        else:
            sufficient_classes.append(cls)

    suf_accs = [per_class[c]['top1_acc'] for c in sufficient_classes]

    # Confusion matrix
    confusion = defaultdict(lambda: defaultdict(int))
    for r in rows:
        confusion[r['cls']][r['top1']] += 1

    confusions = sorted(
        [(tc, pc, cnt) for tc, pd in confusion.items()
         for pc, cnt in pd.items() if pc != tc and cnt > 0],
        key=lambda x: -x[2]
    )

    # ── Verdict ───────────────────────────────────────────────────────────────
    if not sufficient_classes:
        verdict        = 'INCONCLUSIVE'
        verdict_reason = (f'No classes with >= {MIN_SAMPLES_FOR_METRIC} samples; '
                          f'need more labeled data')
    elif top1_acc >= 0.90 and all(a >= 0.90 for a in suf_accs):
        verdict        = 'TEMPLATE_PATH_ALIVE'
        verdict_reason = (f'top1={top1_acc:.1%}, all {len(sufficient_classes)} '
                          f'sufficient classes >= 90%')
    elif sum(1 for a in suf_accs if a < 0.85) >= 3:
        verdict        = 'TEMPLATE_PATH_DEAD'
        verdict_reason = (f'top1={top1_acc:.1%}, '
                          f'{sum(1 for a in suf_accs if a < 0.85)} classes < 85%')
    else:
        verdict        = 'INCONCLUSIVE'
        verdict_reason = (f'top1={top1_acc:.1%}; '
                          f'only {len(sufficient_classes)} sufficient class(es)')

    # ── Write outputs ─────────────────────────────────────────────────────────
    summary = {
        'status':               'OK',
        'data_source':          data_source,
        'primary_blocked':      primary_blocked,
        'primary_block_reason': 'labeled crop PNGs absent from repo' if primary_blocked else None,
        'n_samples':            n,
        'n_classes_in_test':    len(by_class),
        'top1_accuracy':        round(top1_acc, 4),
        'top3_accuracy':        round(top3_acc, 4),
        'low_conf_rate':        round(low_conf_rate, 4),
        'sufficient_classes':   sufficient_classes,
        'insufficient_classes': insufficient_classes,
        'per_class':            per_class,
        'top_confusions':       [{'true': t, 'pred': p, 'count': c}
                                 for t, p, c in confusions[:10]],
        'verdict':              verdict,
        'verdict_reason':       verdict_reason,
        'bank':                 {'dir': str(TEMPLATES_DIR), 'classes': len(bank),
                                 'templates': n_templates},
        'note':                 ('pseudo_gt: GT labels come from previous matcher '
                                 'best_match, not human annotation')
                                if primary_blocked else '',
    }

    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    all_classes = sorted(set(list(by_class.keys()) + [r['top1'] for r in rows]))
    with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['true\\pred'] + all_classes)
        for tc in all_classes:
            w.writerow([tc] + [confusion[tc].get(pc, 0) for pc in all_classes])

    # ── Console summary ───────────────────────────────────────────────────────
    print()
    print('=' * 62)
    print(f'  VERDICT: {verdict}')
    print(f'  {verdict_reason}')
    print(f'  data_source : {data_source}')
    print(f'  n_samples   : {n}   n_classes: {len(by_class)}')
    print(f'  top1_acc    : {top1_acc:.1%}   top3_acc: {top3_acc:.1%}   '
          f'low_conf: {low_conf_rate:.1%}')
    if sufficient_classes:
        for c in sufficient_classes:
            pc = per_class[c]
            print(f'    {c:30s}  n={pc["n"]}  acc={pc["top1_acc"]:.0%}')
    if insufficient_classes:
        print(f'  insufficient_data ({len(insufficient_classes)} classes): '
              + ', '.join(insufficient_classes))
    if confusions:
        print('  top confusions:')
        for t, p, c in confusions[:5]:
            print(f'    {t} -> {p}: {c}')
    print('=' * 62)
    print(f'  -> {OUT_JSON}')
    print(f'  -> {OUT_CSV}')


if __name__ == '__main__':
    main()
