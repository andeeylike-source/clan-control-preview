# BRIDGE.md

Read only the last confirmed handoff block.
Build handoff only from `FACTS`, `RESULT`, `NEXT_STEP`.
Do not guess and do not re-scan on handoff.

## RUNTIME HANDOFF
- Claude writes `.agents/bridge_trigger.json`
- Minimal helper command:
  `python .agents/scripts/write_bridge_trigger.py --status ready_for_codex --file "BASA (1).html" --preview "https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html" --message "..."`
- Watcher reads only `status`
- `ready_for_codex` = run local Codex-side surrogate verify
- `fail` or `not_ready` = do nothing
- Watcher writes `.agents/bridge_result.json`
- Minimal VS Code entrypoint: task `Clan Control: Bridge Watcher`

## CLAUDE RUNTIME APPROVALS
- Config: `.claude/settings.local.json` (gitignored, local-only)
- `defaultMode: acceptEdits` — Edit/Write/NotebookEdit auto-approved, no prompt
- Allow: `Bash(git:*)`, `verify_flow.py`, `write_bridge_trigger.py`, `bridge_watcher.py`
- Deny (hard, precedence over allow): `git push origin:*`, `git push --force*`, `git push --force-with-lease*`, `gh workflow run deploy-production-pages.yml`
- Result: Clan Control work-cycle (edit -> git add -> git commit -> git push preview main -> verify -> trigger -> watcher) runs without confirm
- Production push remains blocked at runtime layer, not only by convention
- Config changes take effect on next Claude Code session start; current session keeps whatever rules were loaded at boot

## TRIGGER JSON
```json
{
  "trigger_id": "string",
  "status": "ready_for_codex | fail | not_ready",
  "task": "string",
  "last_writer": "Claude",
  "files": ["BASA (1).html"],
  "preview_url": "https://...",
  "next_agent": "Codex",
  "next_step": "string"
}
```

## RESULT JSON
```json
{
  "trigger_id": "string",
  "source_status": "ready_for_codex",
  "status": "verify_completed | verify_failed | idle",
  "surrogate": "verify_flow.py",
  "verify_command": ["python", "..."],
  "verify_exit_code": 0,
  "verify_stdout": "raw output",
  "verify_stderr": "",
  "handled_at": "UTC ISO timestamp"
}
```

## TEMPLATE
LAST_WRITER:
TASK:
LAYER:
FACTS:
FILES:
COMMANDS_RUN:
RESULT:
NEXT_AGENT:
NEXT_STEP:
BLOCKERS:

## EXAMPLE: Codex -> Claude
LAST_WRITER: Codex
TASK: Hide preview debug markers
LAYER: UI
FACTS: preview only and Диагностика were visible in preview UI; scope limited to BASA (1).html
FILES: BASA (1).html
COMMANDS_RUN: git push preview main; python .agents/skills/cc-fix-preview/scripts/verify_flow.py --local-file "BASA (1).html" --preview-url "https://andeeylike-source.github.io/clan-control-preview/BASA%20(1).html"
RESULT: preview markers hidden; verify passed
NEXT_AGENT: Claude
NEXT_STEP: review the same UI scope only if a new defect is reported
BLOCKERS: none

## EXAMPLE: Claude -> Codex
LAST_WRITER: Claude
TASK: Narrow follow-up in scan review consumer
LAYER: consumer
FACTS: defect already localized; upstream and merge layers are not in scope
FILES: BASA (1).html
COMMANDS_RUN: none
RESULT: analysis complete; no code changes made
NEXT_AGENT: Codex
NEXT_STEP: apply the narrow fix in the confirmed consumer scope only
BLOCKERS: none

LAST_WRITER: Codex
TASK: Bridge smoke test to Claude
LAYER: 
FACTS: bridge append works
FILES: 
COMMANDS_RUN: 
RESULT: block appended
NEXT_AGENT: Claude
NEXT_STEP: Claude reads last block only
BLOCKERS: none

LAST_WRITER: Claude
TASK: Bridge smoke test to Codex
LAYER: 
FACTS: bridge append works both ways
FILES: 
COMMANDS_RUN: 
RESULT: block appended
NEXT_AGENT: Codex
NEXT_STEP: Codex reads last block only
BLOCKERS: none

LAST_WRITER: Claude
TASK: First real handoff — diagnose pending uncommitted changes
LAYER: working-tree / pre-commit
FACTS: PROJECT_STATE.md does not exist; last bridge block was smoke-test only (no real defect); git status shows unstaged modifications in BASA (1).html and .gitignore; untracked dirs: extracted_site_icons/, extracted_site_icons_v3/, tools/
FILES: BASA (1).html, .gitignore
COMMANDS_RUN: none (file-read only)
RESULT: analysis complete; no code changes made
NEXT_AGENT: Codex
NEXT_STEP: diagnosis-only — read the unstaged diff of BASA (1).html and .gitignore; identify what changed and whether it should be committed, reverted, or left as-is; do NOT modify any file; return facts only
BLOCKERS: no PROJECT_STATE.md — Codex should create it after diagnosis if useful

smoke test
