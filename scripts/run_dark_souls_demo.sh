#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECORDING="${1:-${ROOT_DIR}/../../work/test-media/dark-souls/tj_kumail_dark_souls_20min.mp4}"
OUTPUT_DIR="${2:-${ROOT_DIR}/demo-runs/dark-souls-20m-mvp}"
BASE_URL="${LEMONADE_BASE_URL:-http://127.0.0.1:13305}"
CHAT_MODEL="${LEMONADE_CHAT_MODEL:-Qwen3-8B-GGUF}"
STT_MODEL="${LEMONADE_STT_MODEL:-Whisper-Tiny}"
GOAL="${LRS_GOAL:-Make a funny Dark Souls replay. Prioritize deaths, panic, HP drops, insults, and moments friends would want to rewatch.}"
PYTHON="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="python3"
fi

if [[ ! -f "${RECORDING}" ]]; then
  echo "Recording not found: ${RECORDING}" >&2
  echo "Pass a recording path as the first argument, or see DEMO_FOOTAGE.md for the demo fixture." >&2
  exit 1
fi

"${PYTHON}" -m lemonade_replay_studio.cli doctor \
  --provider lemonade \
  --base-url "${BASE_URL}" \
  --chat-model "${CHAT_MODEL}" \
  --stt-model "${STT_MODEL}"

"${PYTHON}" -m lemonade_replay_studio.cli analyze "${RECORDING}" \
  --provider lemonade \
  --base-url "${BASE_URL}" \
  --chat-model "${CHAT_MODEL}" \
  --stt-model "${STT_MODEL}" \
  --output-dir "${OUTPUT_DIR}" \
  --preset dark-souls \
  --goal "${GOAL}"

echo
echo "Demo artifacts:"
echo "  ${OUTPUT_DIR}/moment_map.html"
echo "  ${OUTPUT_DIR}/highlight_reel.mp4"
