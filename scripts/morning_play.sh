#!/usr/bin/env bash
# Weekday 07:38: set volume, then play morning_brief.mp3 on the room speaker.
set -euo pipefail

export TZ=Asia/Shanghai
export PYTHONUNBUFFERED=1

TOOL_HOME="$HOME/.xiaoai-broadcast"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$TOOL_HOME/venv/bin/python"

# Credentials: prefer rootgrove Keychain loader, fall back to local env file.
ROOTGROVE_ENV="$HOME/CursorWorks/rootgrove/tools/secrets/source_env.sh"
if [[ -f "$ROOTGROVE_ENV" ]]; then
  # shellcheck source=/dev/null
  source "$ROOTGROVE_ENV"
fi
if [[ -f "$TOOL_HOME/env" ]]; then
  # shellcheck source=/dev/null
  source "$TOOL_HOME/env"
fi

: "${XIAOAI_DID:?XIAOAI_DID not set (put it in $TOOL_HOME/env)}"
: "${XIAOAI_BASE_URL:?XIAOAI_BASE_URL not set (e.g. http://192.168.1.124:8091)}"
: "${XIAOAI_USER:?XIAOAI_USER not set (Keychain or $TOOL_HOME/env)}"
: "${XIAOMI_PASSWORD:?XIAOMI_PASSWORD not set (Keychain or $TOOL_HOME/env)}"

dow="$(date +%u)"
if [[ "$dow" -gt 5 ]]; then
  echo "$(date '+%F %T') weekend, skip"
  exit 0
fi

VOLUME="${XIAOAI_MORNING_VOLUME:-40}"

echo "=== $(date '+%F %T') morning play start (did=$XIAOAI_DID vol=$VOLUME) ==="
"$VENV_PYTHON" -m xiaoai_broadcast play \
  --did "$XIAOAI_DID" --file morning_brief.mp3 --volume "$VOLUME" --retry 3
