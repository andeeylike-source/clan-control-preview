# CC/KM Auto-Recognition R&D — Findings 2026-04-25

## Conclusion

Icon-only automatic recognition of character class (class2/profa) from real 18×20 px JPEG/Telegram crops is not reliable enough for production use. All tested approaches reached top1 accuracy 0–10% on real crops.

## Dead Paths

| Approach | Result |
|---|---|
| Gemini Vision — icon-only crop | DEAD — hallucinated labels, no real signal |
| Clean template cosine similarity | DEAD — crop vs clean template domain gap too large |
| RGB / SSIM / preprocessing variants | DEAD — 18×20px too small for pixel matching |
| HOG cosine-kNN (pure numpy, augmented bank) | DEAD — top1=0/10 |
| ORB + TM_CCOEFF_NORMED fused (cv2) | DEAD — top1=1/10 (10%) |
| MobileNetV2 CNN embedding (1280-dim, ImageNet) | DEAD — top1=1/10 (10%), both direct_resize and pad_square modes |

## Useful Signals Observed

- Manual precise click/crop (browser icon picker) was the only reliable method.
- Center-refine of crop coordinates improved cosine score in some cases.
- 20×20 px crop sometimes outperformed 16×16 px crop.
- `extracted_site_icons_v3` (clean icon catalog) is a useful clean reference for future trained models.
- `class2Source` / `profaSource` field tracking correctly identified which assignments to trust.

## Root Cause Hypothesis

The bottleneck is likely not the matcher algorithm but the crop itself:
- Auto-crop center may be off by a few pixels (enough to misalign the 18px icon entirely).
- Row-level crop includes UI noise (HP bars, borders, background).
- No ground truth bounding box for the icon within the row.

## Next Path (if resumed)

1. Full row / right panel / full screenshot context — not icon-only crop.
2. Precise icon center via fixed offset from row top-left (needs calibration per screenshot resolution).
3. Vision API (Gemini 1.5 Pro / GPT-4V) on full row with prompt: "what class icon is in this row".
4. Trained classifier on real labeled dataset (needs 50+ labeled crops per class minimum).

## Stop Doing

- Matcher-derived class2/profa written to roster (unreliable, causes false profas).
- Top-3 user choice from matcher suggestions (misleads user with wrong candidates).
- Chaotic icon-only PoC iterations without first fixing crop quality.
- Manual picker as the primary UX path (acceptable as fallback, not as main flow).

## Status in Codebase

- `renderDayAnalyzedPlayers()`: matcher-derived class2/profa suppressed from display.
- `applyDayParsedStats()`: matcher-derived profa blocked from writing to roster.
- `renderProfaAssignList()`: matcher hints replaced with static "Автоподсказка отключена".
- Inline manual profa picker added to scan preview cards as temporary fallback.
- All PoC scripts in `tools/local_icon_matcher/` — untracked, not deployed.
