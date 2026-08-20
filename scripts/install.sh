#!/usr/bin/env bash
# One-shot install: venv, editable install, LaunchAgents (serve now; play/stop later).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL_HOME="$HOME/.xiaoai-broadcast"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

mkdir -p "$TOOL_HOME"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi
[[ -n "$PYTHON_BIN" ]] || { echo "no python3 found" >&2; exit 1; }

"$PYTHON_BIN" -m venv "$TOOL_HOME/venv"
"$TOOL_HOME/venv/bin/pip" install -q -U pip
"$TOOL_HOME/venv/bin/pip" install -q -e "$REPO_ROOT"

for tpl in com.rootgrove.xiaoai-serve com.rootgrove.xiaoai-morning-play com.rootgrove.xiaoai-morning-stop; do
  sed -e "s|__VENV_PYTHON__|$TOOL_HOME/venv/bin/python|g" \
      -e "s|__REPO_ROOT__|$REPO_ROOT|g" \
      -e "s|__HOME__|$HOME|g" \
      "$REPO_ROOT/scripts/$tpl.plist" > "$LAUNCH_AGENTS/$tpl.plist"
  plutil -lint "$LAUNCH_AGENTS/$tpl.plist" >/dev/null
done

chmod +x "$REPO_ROOT/scripts/morning_play.sh" "$REPO_ROOT/scripts/morning_stop.sh"

# Serve agent starts now (KeepAlive). Play/stop agents load only when
# ~/.xiaoai-broadcast/env defines XIAOAI_DID -- run: xiaoai-broadcast-install-alarms
launchctl unload "$LAUNCH_AGENTS/com.rootgrove.xiaoai-serve.plist" 2>/dev/null || true
launchctl load "$LAUNCH_AGENTS/com.rootgrove.xiaoai-serve.plist"

echo "installed: venv + serve agent (port 8091)"
echo "next: set creds + XIAOAI_DID in $TOOL_HOME/env, then run install-alarms"
