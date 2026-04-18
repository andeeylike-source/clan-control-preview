# AGENTS.md

## PROJECT
- Project: Clan Control
- Format: single-file SPA
- Main file: `BASA (1).html`
- Legacy files: do not edit `clan-control.html`, `BASA.html`, `BASAv1.html`
- Work only in this local repo
- Do not touch production without explicit user permission

## WORKFLOW — CLAUDE ONLY
- Executor: Claude only. No Codex, no watcher, no auto-handoff.
- Cycle: one defect → fix → commit → `git push preview main` → STOP
- After preview push: stop and wait for user decision (push to main or not)
- Fact first, then conclusion, then action
- Pick one best next step per cycle
- After a fix, check the adjacent scope for the same pattern
- Default flow: fix → local check → preview push → FINAL REPORT
- For UI changes, preview push is mandatory
- Run a local test before the final report if testing is possible
- Use `python .agents/skills/cc-fix-preview/scripts/verify_flow.py --local-file "BASA (1).html" --preview-url "https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html"` for the default hands-off verify path

## CONTEXT DISCIPLINE
- One defect per cycle — do not bundle unrelated fixes
- Do not pull long logs into context whole: first grep/find/read the narrow relevant section
- Prefer `grep -n pattern file | head -40` over reading full files
- Prefer `sed -n 'N,Mp'` over reading from offset when line range is known
- Do not re-scan the whole project without a new signal from the user
- Do not repeat tool output verbatim in prose — summarise or omit
- Shell output that exceeds what is needed for the decision: truncate with head/tail

## RTK (context economy — Windows)
- RTK is NOT currently installed (`rtk --version` → not found)
- When installed: use `rtk run <cmd>` to pipe shell/git/grep output as compressed context
- When installed: prefer `rtk grep`, `rtk git log`, `rtk read` over raw tool calls for large outputs
- Until installed: apply manual discipline — head/tail/grep with explicit limits on every read

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
- next_best_step:

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
