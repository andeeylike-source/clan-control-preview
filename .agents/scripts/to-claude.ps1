param(
    [Parameter(Mandatory = $true)][string]$LastWriter,
    [Parameter(Mandatory = $true)][string]$Task,
    [string]$Layer = "",
    [Parameter(Mandatory = $true)][string]$Facts,
    [string]$Files = "",
    [string]$CommandsRun = "",
    [Parameter(Mandatory = $true)][string]$Result,
    [string]$NextAgent = "Claude",
    [Parameter(Mandatory = $true)][string]$NextStep,
    [string]$Blockers = "none"
)

$bridgePath = Join-Path (Resolve-Path ".") ".agents\BRIDGE.md"
$dir = Split-Path -Parent $bridgePath
if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
if (!(Test-Path $bridgePath)) { New-Item -ItemType File -Path $bridgePath -Force | Out-Null }

$block = @(
    ""
    "LAST_WRITER: $LastWriter"
    "TASK: $Task"
    "LAYER: $Layer"
    "FACTS: $Facts"
    "FILES: $Files"
    "COMMANDS_RUN: $CommandsRun"
    "RESULT: $Result"
    "NEXT_AGENT: $NextAgent"
    "NEXT_STEP: $NextStep"
    "BLOCKERS: $Blockers"
) -join [Environment]::NewLine

Add-Content -LiteralPath $bridgePath -Value $block
Write-Output "APPENDED .agents/BRIDGE.md"
Write-Output "LAST_WRITER=$LastWriter"
Write-Output "NEXT_AGENT=$NextAgent"
