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
# Auth: passToken file (login-cookie) OR env creds -- at least one must exist.
if [[ ! -f "$TOOL_HOME/mi_token.json" ]] && [[ -z "${XIAOAI_USER:-}${MI_USER:-}" ]]; then
  echo "no auth: run 'xiaoai-broadcast login-cookie' (or set XIAOMI_USER/XIAOMI_PASSWORD)" >&2
  exit 1
fi

dow="$(date +%u)"
if [[ "$dow" -gt 5 ]]; then
  echo "$(date '+%F %T') weekend, skip"
  exit 0
fi

VOLUME="${XIAOAI_MORNING_VOLUME:-50}"
VOLUME_FILE="$TOOL_HOME/pre_play_volume"

echo "=== $(date '+%F %T') morning play start (did=$XIAOAI_DID vol=$VOLUME) ==="
# Save pre-play volume for restoration by morning_stop.sh
if "$VENV_PYTHON" -m xiaoai_broadcast volume --did "$XIAOAI_DID" > "$VOLUME_FILE" 2>/dev/null; then
  echo "pre-play volume saved: $(cat "$VOLUME_FILE")"
else
  rm -f "$VOLUME_FILE"
  echo "warn: could not read current volume; restore will be skipped"
fi
"$VENV_PYTHON" -m xiaoai_broadcast play \
  --did "$XIAOAI_DID" --file morning_brief.mp3 --volume "$VOLUME" --retry 3
