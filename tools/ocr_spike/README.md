# OCR Spike

Isolated local OCR spike for a KM table crop. It does not call cloud APIs and does not touch the single-file SPA.

## Install

```powershell
py -3.11 -m venv tools\ocr_spike\.venv
.\tools\ocr_spike\.venv\Scripts\python -m pip install -U pip
.\tools\ocr_spike\.venv\Scripts\python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
.\tools\ocr_spike\.venv\Scripts\python -m pip install "paddleocr[all]" opencv-python pillow
```

## Run

```powershell
.\tools\ocr_spike\.venv\Scripts\python tools\ocr_spike\ocr_spike.py --engine paddle --input tools\ocr_spike\competitor_test_crop.png --out tools\ocr_spike\out
```

## Regression check (all samples)

```powershell
.\tools\ocr_spike\.venv\Scripts\python tools\ocr_spike\regression_check.py
```

Exit code 0 = all cases pass. Exit code 1 = one or more failures (with per-row detail printed).

## Compare (single sample)

```powershell
.\tools\ocr_spike\.venv\Scripts\python tools\ocr_spike\compare_rows.py --actual tools\ocr_spike\out\competitor_test_crop.paddle.4e9545a69b5b.json --expected tools\ocr_spike\expected\competitor_test_crop.expected.json
```

The output JSON contains:

- `hash`
- `engine`
- `text`
- `boxes` with `text`, `confidence`, `polygon`, `bbox`, `cx`, `cy`
- `rows`
- `timing_ms`

`parser.py` is intentionally geometry-first: it clusters OCR boxes by `cy`, assigns tokens to fixed x-range columns, normalizes numeric cells, and emits `rows`.
