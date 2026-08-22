#!/usr/bin/env bash
# Ad-hoc play of morning_brief.mp3 (manual / remote trigger).
# On auth failure tries one headless browser re-harvest before giving up.
set -euo pipefail

export TZ=Asia/Shanghai
TOOL_HOME="$HOME/.xiaoai-broadcast"
source "$TOOL_HOME/env"
export XIAOAI_DID XIAOAI_BASE_URL XIAOAI_MORNING_VOLUME
VENV_PY="$TOOL_HOME/venv/bin/python"
VOL="${XIAOAI_MORNING_VOLUME:-50}"

get_volume() { "$VENV_PY" -m xiaoai_broadcast volume --did "$XIAOAI_DID" 2>/dev/null || true; }

pre="$(get_volume)"
if [[ -z "$pre" ]]; then
  echo "auth/conn failed; trying headless re-harvest..."
  "$VENV_PY" -m xiaoai_broadcast login-browser || true
  pre="$(get_volume)"
fi
if [[ -z "$pre" ]]; then
  echo "FATAL: no auth after re-harvest; needs: xiaoai-broadcast login-browser --account <phone|email> --sms" >&2
  if [[ -n "${XIAOAI_FAIL_HOOK:-}" && -x "$XIAOAI_FAIL_HOOK" ]]; then
    "$XIAOAI_FAIL_HOOK" "play_now no auth after re-harvest $(date '+%F %T')" || true
  fi
  exit 1
fi

"$VENV_PY" -m xiaoai_broadcast play --did "$XIAOAI_DID" --file morning_brief.mp3 --volume "$VOL" --retry 3
echo "playing (pre-volume $pre, restore in ${XIAOAI_PLAY_WAIT:-75}s)"
sleep "${XIAOAI_PLAY_WAIT:-75}"
"$VENV_PY" -m xiaoai_broadcast volume --did "$XIAOAI_DID" "$pre" >/dev/null
echo "volume restored to $pre"
