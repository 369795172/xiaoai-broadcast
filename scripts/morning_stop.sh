#!/usr/bin/env bash
# Daily 08:12: stop the room speaker.
set -euo pipefail

export TZ=Asia/Shanghai

TOOL_HOME="$HOME/.xiaoai-broadcast"
VENV_PYTHON="$TOOL_HOME/venv/bin/python"

[[ -f "$TOOL_HOME/env" ]] && source "$TOOL_HOME/env"
export XIAOAI_DID XIAOAI_BASE_URL

: "${XIAOAI_DID:?XIAOAI_DID not set}"

brief_date="$(date -r "$HOME/.xiaomusic/music/morning/morning_brief.mp3" +%F 2>/dev/null || echo none)"
if [[ "$brief_date" != "$(date +%F)" ]]; then
  echo "$(date '+%F %T') brief not from today ($brief_date), skip stop — no repeat"
  exit 0
fi

echo "=== $(date '+%F %T') morning stop (did=$XIAOAI_DID) ==="
"$VENV_PYTHON" -m xiaoai_broadcast stop --did "$XIAOAI_DID"

# Restore pre-play volume if morning_play.sh saved it
VOLUME_FILE="$TOOL_HOME/pre_play_volume"
if [[ -s "$VOLUME_FILE" ]]; then
  RESTORE_VOL="$(cat "$VOLUME_FILE")"
  if "$VENV_PYTHON" -m xiaoai_broadcast volume --did "$XIAOAI_DID" "$RESTORE_VOL"; then
    echo "volume restored to $RESTORE_VOL"
  fi
  rm -f "$VOLUME_FILE"
fi
