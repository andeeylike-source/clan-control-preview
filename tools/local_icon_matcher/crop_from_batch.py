"""
crop_from_batch.py — cut labeled icon crops from available screenshots.

Sources:
  - labeled_rows_auto.json  → (screen, row, final_class, crop_path)
  - batch_eval.json         → (screen, row, bbox)
  - screenshots in SCRIPT_DIR matching screen filename

Output: crops/<crop_path basename> saved under SCRIPT_DIR/crops/
"""

import json
from pathlib import Path
from PIL import Image

SCRIPT_DIR = Path(__file__).parent
BATCH_EVAL = SCRIPT_DIR / 'out' / 'batch_eval.json'
LABELED    = SCRIPT_DIR / 'out' / 'labeled_rows_auto.json'
CROPS_DIR  = SCRIPT_DIR / 'crops'

CROPS_DIR.mkdir(exist_ok=True)

def main():
    with open(BATCH_EVAL, encoding='utf-8') as f:
        batch = json.load(f)
    with open(LABELED, encoding='utf-8') as f:
        labeled = json.load(f)

    # Build bbox index: (screen, row) -> bbox
    bbox_idx = {}
    for r in batch:
        key = (r['_screen'], r['row'])
        if r.get('bbox'):
            bbox_idx[key] = r['bbox']

    # Find available screenshots
    available = {p.name: p for p in SCRIPT_DIR.glob('*.jpg')}
    print(f'Available JPGs: {sorted(available.keys())}')
    print(f'bbox index size: {len(bbox_idx)}')
    print(f'labeled rows: {len(labeled)}')

    saved = 0
    skipped_no_screen = 0
    skipped_no_bbox = 0

    for rec in labeled:
        screen  = rec['screenshot']
        row_idx = rec['row']
        cls     = rec['final_class']
        cp      = rec['crop_path']  # e.g. crops/photo_..._row001.png

        if screen not in available:
            skipped_no_screen += 1
            continue

        key = (screen, row_idx)
        if key not in bbox_idx:
            skipped_no_bbox += 1
            continue

        bbox  = bbox_idx[key]
        img   = Image.open(available[screen])
        crop  = img.crop((bbox['x0'], bbox['y0'], bbox['x1'], bbox['y1']))
        out_p = SCRIPT_DIR / cp  # cp is "crops/filename.png"
        out_p.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out_p)
        print(f'  saved: {out_p.name}  ({cls})')
        saved += 1

    print(f'\nDone: {saved} crops saved, {skipped_no_screen} skipped (no screen), {skipped_no_bbox} skipped (no bbox)')

if __name__ == '__main__':
    main()
