# AGENTS.md

## PROJECT
- Project: Clan Control
- Format: single-file SPA
- Main file: `BASA (1).html`
- Legacy files: do not edit `clan-control.html`, `BASA.html`, `BASAv1.html`
- Work only in this local repo
- Do not touch production without explicit user permission

## WORKFLOW
- Fact first, then conclusion, then action
- Pick one best next step
- Do not re-scan the whole project without need
- Work only in the nearest relevant scope
- After a fix, check the adjacent scope for the same pattern
- Default flow: fix -> local check -> preview/site check -> FINAL REPORT
- For UI changes, preview push is mandatory
- Run a local test before the final report if testing is possible
- Use `python .agents/skills/cc-fix-preview/scripts/verify_flow.py --local-file "BASA (1).html" --preview-url "https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html"` for the default hands-off verify path

## OUTPUT POLICY
- Do not end replies with tool logs
- Always end with exactly:

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

- If commit/preview/test did not happen, write `none` / `no` explicitly
- Do not add long explanations after `FINAL REPORT`

## SCAN/REVIEW PIPELINE RULES
- Do not mix unified path and review path unless necessary
- Canonical unified row: `screenshot`, `side`, `row`, `nick`, `kills`, `deaths`, `pvp`, `pve`, `class`, `confidence`, `source_by_field`
- Treat `recommended_status` as optional meta, not a required canonical field
- Raw `review.json` path may use `final_class` separately
- Do not edit `tools/local_icon_matcher/merge_unified.py` without explicit request
- For scan-review tasks, first locate the defect: upstream, merge, or consumer

## SAFETY / GIT
- Do not push to `origin/main` without explicit permission
- Use the preview remote only through the local flow
- If preview remote is behind, inspect it safely first and do not touch `origin`
- Do not do broad refactors without request
