#!/usr/bin/env bash
# Weekday 07:50: stop the room speaker.
set -euo pipefail

export TZ=Asia/Shanghai

TOOL_HOME="$HOME/.xiaoai-broadcast"
VENV_PYTHON="$TOOL_HOME/venv/bin/python"

ROOTGROVE_ENV="$HOME/CursorWorks/rootgrove/tools/secrets/source_env.sh"
if [[ -f "$ROOTGROVE_ENV" ]]; then
  # shellcheck source=/dev/null
  source "$ROOTGROVE_ENV"
fi
if [[ -f "$TOOL_HOME/env" ]]; then
  # shellcheck source=/dev/null
  source "$TOOL_HOME/env"
fi

: "${XIAOAI_DID:?XIAOAI_DID not set}"

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
