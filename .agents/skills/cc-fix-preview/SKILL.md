---
name: cc-fix-preview
description: Use for already-diagnosed Clan Control tasks that need a narrow local fix, adjacent-scope pattern check, local verification when possible, commit, preview push, and a strict FINAL REPORT.
---

# NAME
cc-fix-preview

## WHEN TO USE
Use only when the task is already diagnosed and needs a narrow local fix in Clan Control.

## RULES
- Work only in the nearest relevant scope
- Do not re-scan the whole project
- Do not edit `clan-control.html`, `BASA.html`, `BASAv1.html`
- Do not touch production without explicit permission
- After a local fix, check the adjacent scope for the same pattern
- If preview remote is behind, inspect its state safely first
- Do not touch `origin/main`
- Use the repo verify script for hands-off checks when verification is possible

## EXECUTION FLOW
- Make only the narrow fix
- Run `python .agents/skills/cc-fix-preview/scripts/verify_flow.py --local-file "BASA (1).html" --preview-url "https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html"` after the fix
- `git add` only relevant files
- `git commit -m "short message"`
- `git push preview main` via local flow
- Run the same verify command again after preview push
- If normal push is rejected by fast-forward, inspect preview state safely and act only within preview remote
- Always end with `FINAL REPORT`

## OUTPUT FORMAT
FINAL REPORT
- changed:
- files:
- commit:
- preview:
- tested:
- result:
- residual:
- verify_command:
- verify_scope:

## PROJECT NOTES
- Main file: `BASA (1).html`
- Project: single-file SPA
- For scan/review tasks canonical unified row: `screenshot`, `side`, `row`, `nick`, `kills`, `deaths`, `pvp`, `pve`, `class`, `confidence`, `source_by_field`
- Treat `recommended_status` as optional meta
- Do not mix `review.json` path and unified path unless necessary
- Default verify checks:
  local = file read + local temporary HTTP fetch of `BASA (1).html`
  preview = HTTP fetch of preview URL and marker check
