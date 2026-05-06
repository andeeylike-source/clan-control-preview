# OCR Spike

Isolated local OCR spike for a KM table crop. It does not touch the single-file SPA.

## OpenRouter Vision Benchmark

`openrouter_vision_benchmark.html` — test multiple OpenRouter vision models on the same KM screenshots.
No backend. No build step. API key stays in localStorage only — never in git.

### How to open

```powershell
# from repo root
python -m http.server 8080
```

Then open: **http://localhost:8080/tools/ocr_spike/openrouter_vision_benchmark.html**

Or from inside ocr_spike:

```powershell
python -m http.server 8080 --directory tools\ocr_spike
# → http://localhost:8080/openrouter_vision_benchmark.html
```

### Workflow

1. Paste your OpenRouter API key → **Save**
2. Click **Load OpenRouter Models** — fetches live model list, filters to vision-capable
3. Use **only free** checkbox to shortlist $0 models
4. Upload 1–3 KM screenshots (`competitor_test_crop.png`, `second_test_crop.png`, etc.)
5. Select models (checkbox), click **▶ Run Benchmark**
6. Confirm the prompt — non-free models will charge your account
7. Results appear grouped by image: latency, parsed rows, raw response, estimated cost
8. **Download benchmark JSON** to save results

### Safety

- Requires manual checkbox selection — no auto-run
- Confirmation dialog for >5 models or >3 images
- Cost warning for non-free models
- API key is never sent anywhere except `openrouter.ai/api/v1`

## Install

```powershell
py -3.11 -m venv tools\ocr_spike\.venv
.\tools\ocr_spike\.venv\Scripts\python -m pip install -U pip
.\tools\ocr_spike\.venv\Scripts\python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
.\tools\ocr_spike\.venv\Scripts\python -m pip install "paddleocr[all]" opencv-python pillow
```

## Run local OCR server

Start the HTTP server (port 5050, or set `$env:OCR_LOCAL_PORT`):

```powershell
.\tools\ocr_spike\.venv\Scripts\python tools\ocr_spike\server.py
```

### Test endpoints

```powershell
# Health check
Invoke-RestMethod http://localhost:5050/health

# OCR a crop image
$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path "tools\ocr_spike\competitor_test_crop.png"))
$b64   = [Convert]::ToBase64String($bytes)
$body  = @{ base64 = $b64; filename = "competitor_test_crop.png" } | ConvertTo-Json -Compress
Invoke-RestMethod -Method POST -Uri http://localhost:5050/ocr `
    -Body $body -ContentType "application/json; charset=utf-8" |
    Select-Object ok, provider, cached, timing_ms, boxes_count,
        @{n='rows';e={$_.parsed.Count}}
```

Pass `known_names` (string array) and `aliases` (object) in the body to override
the default `expected/known_names.json` with the site's live roster — per-request only,
no global mutation.

## Run (CLI, single file)

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

## Browser-only OCR benchmark (Tesseract.js, no backend)

`browser_ocr_benchmark.html` runs Tesseract.js entirely in the browser — no server, no API key, works on phone.

### How to open

```powershell
# From the repo root
python -m http.server 8080 --directory tools\ocr_spike
```

Then open: **http://localhost:8080/browser_ocr_benchmark.html**

On first run, the browser downloads Tesseract traineddata (~4 MB for `eng`, ~10 MB for `rus`) from jsDelivr/projectnaptha. Subsequent runs use the browser cache.

### What to test

Upload any KM crop from `tools/ocr_spike/`:
- `competitor_test_crop.png`
- `second_test_crop.png`
- `third_test_crop.png`

Select language combos (`eng`, `rus`, `eng+rus`) and click **Run OCR**.

### Expected observations

| Scenario | Expected |
|---|---|
| Latin-only names + digits | eng: ~80–90% conf, readable |
| Cyrillic names (Кара, Умра …) | rus or eng+rus required |
| Mixed script in one row | eng+rus, conf drops to 40–60% |
| Timing (desktop) | 2–8 s per language pass |
| Timing (phone) | 10–30 s; WASM is slower on mobile |

### Known limits

- Tesseract struggles with small aliased fonts common in game UI.
- PaddleOCR (local server) outperforms Tesseract on this class of images.
- This benchmark is for feasibility only — not integrated into the site.
