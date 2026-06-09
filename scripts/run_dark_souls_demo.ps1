param(
    [string]$Recording = (Join-Path $PSScriptRoot "..\..\work\test-media\dark-souls\tj_kumail_dark_souls_20min.mp4"),
    [string]$OutputDir = (Join-Path $PSScriptRoot "..\demo-runs\dark-souls-20m-mvp")
)

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$BaseUrl = if ($env:LEMONADE_BASE_URL) { $env:LEMONADE_BASE_URL } else { "http://127.0.0.1:13305" }
$ChatModel = if ($env:LEMONADE_CHAT_MODEL) { $env:LEMONADE_CHAT_MODEL } else { "Qwen3-8B-GGUF" }
$SttModel = if ($env:LEMONADE_STT_MODEL) { $env:LEMONADE_STT_MODEL } else { "Whisper-Tiny" }
$Goal = if ($env:LRS_GOAL) { $env:LRS_GOAL } else { "Make a funny Dark Souls replay. Prioritize deaths, panic, HP drops, insults, and moments friends would want to rewatch." }
$Python = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

if (-not (Test-Path $Recording)) {
    Write-Error "Recording not found: $Recording. Pass a recording path as -Recording, or see DEMO_FOOTAGE.md for the demo fixture."
}

& $Python -m lemonade_replay_studio.cli doctor `
    --provider lemonade `
    --base-url $BaseUrl `
    --chat-model $ChatModel `
    --stt-model $SttModel

& $Python -m lemonade_replay_studio.cli analyze $Recording `
    --provider lemonade `
    --base-url $BaseUrl `
    --chat-model $ChatModel `
    --stt-model $SttModel `
    --output-dir $OutputDir `
    --preset dark-souls `
    --goal $Goal

Write-Host ""
Write-Host "Demo artifacts:"
Write-Host "  $OutputDir\moment_map.html"
Write-Host "  $OutputDir\highlight_reel.mp4"
