#!/usr/bin/env bash
# Ad-hoc delivery of morning_brief (manual / remote trigger):
# MP3 URL when the speaker can reach the serve, cloud TTS chunks otherwise.
# On auth failure tries one headless browser re-harvest before giving up.
set -euo pipefail

export TZ=Asia/Shanghai
TOOL_HOME="$HOME/.xiaoai-broadcast"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$TOOL_HOME/env"
export XIAOAI_DID XIAOAI_MORNING_VOLUME
VENV_PY="$TOOL_HOME/venv/bin/python"
VOL="${XIAOAI_MORNING_VOLUME:-50}"

pre="$("$VENV_PY" -m xiaoai_broadcast volume --did "$XIAOAI_DID" 2>/dev/null || true)"
if [[ -z "$pre" ]]; then
  echo "auth/conn failed; trying headless re-harvest..."
  "$VENV_PY" -m xiaoai_broadcast login-browser || true
  pre="$("$VENV_PY" -m xiaoai_broadcast volume --did "$XIAOAI_DID" 2>/dev/null || true)"
fi
if [[ -z "$pre" ]]; then
  echo "FATAL: no auth after re-harvest; needs: xiaoai-broadcast login-browser --account <phone|email> --sms" >&2
  if [[ -n "${XIAOAI_FAIL_HOOK:-}" && -x "$XIAOAI_FAIL_HOOK" ]]; then
    "$XIAOAI_FAIL_HOOK" "play_now no auth after re-harvest $(date '+%F %T')" || true
  fi
  exit 1
fi

mode="$("$VENV_PY" -m xiaoai_broadcast deliver --did "$XIAOAI_DID" --volume "$VOL" | tee /dev/stderr | tail -1)"
case "$mode" in
  *"MODE: url"*)
    echo "url playback started (pre-volume $pre, restore in ${XIAOAI_PLAY_WAIT:-75}s)"
    sleep "${XIAOAI_PLAY_WAIT:-75}"
    ;;
  *"MODE: tts"*)
    echo "tts delivery finished (pre-volume $pre)"
    ;;
  *)
    echo "FATAL: deliver failed" >&2
    if [[ -n "${XIAOAI_FAIL_HOOK:-}" && -x "$XIAOAI_FAIL_HOOK" ]]; then
      "$XIAOAI_FAIL_HOOK" "play_now deliver failed $(date '+%F %T')" || true
    fi
    exit 1
    ;;
esac
"$VENV_PY" -m xiaoai_broadcast volume --did "$XIAOAI_DID" "$pre" >/dev/null
echo "volume restored to $pre"
