# BRIDGE.md

Read only the last confirmed handoff block.
Build handoff only from `FACTS`, `RESULT`, `NEXT_STEP`.
Do not guess and do not re-scan on handoff.

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
