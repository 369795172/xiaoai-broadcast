#!/usr/bin/env bash
# Weekday 08:00: set volume, then play morning_brief.mp3 on the room speaker.
set -euo pipefail

export TZ=Asia/Shanghai
export PYTHONUNBUFFERED=1

TOOL_HOME="$HOME/.xiaoai-broadcast"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$TOOL_HOME/venv/bin/python"

# Credentials come ONLY from ~/.xiaoai-broadcast/env (passToken auth lives in
# ~/.xiaoai-broadcast/mi_token.json). Never source rootgrove source_env.sh
# here: its XIAOMI_USER/PASSWORD would override the token account.
[[ -f "$TOOL_HOME/env" ]] && source "$TOOL_HOME/env"
export XIAOAI_DID XIAOAI_BASE_URL XIAOAI_MORNING_VOLUME

: "${XIAOAI_DID:?XIAOAI_DID not set (put it in $TOOL_HOME/env)}"
# XIAOAI_BASE_URL is optional now: deliver.py auto-detects the LAN IP and
# falls back to cloud TTS chunks when the speaker cannot reach the serve.
# Auth: passToken file required (login-browser/login-cookie seed it).
if [[ ! -f "$TOOL_HOME/mi_token.json" ]]; then
  echo "no auth: run 'xiaoai-broadcast login-browser' (or login-cookie)" >&2
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
if ! "$VENV_PYTHON" -m xiaoai_broadcast.deliver \
  --did "$XIAOAI_DID" --volume "$VOLUME"; then
  echo "deliver failed (url+tts); passToken may need refresh (login-browser)"
  if [[ -n "${XIAOAI_FAIL_HOOK:-}" && -x "$XIAOAI_FAIL_HOOK" ]]; then
    "$XIAOAI_FAIL_HOOK" "morning_play deliver failed $(date '+%F %T')" || true
  fi
  exit 1
fi
