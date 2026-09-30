#!/usr/bin/env bash
# Load morning play/stop agents once ~/.xiaoai-broadcast/env has XIAOAI_DID.
set -euo pipefail

TOOL_HOME="$HOME/.xiaoai-broadcast"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

grep -q "^XIAOAI_DID=" "$TOOL_HOME/env" 2>/dev/null || {
  echo "XIAOAI_DID missing in $TOOL_HOME/env; run 'xiaoai-broadcast devices' first" >&2
  exit 1
}

for agent in com.rootgrove.xiaoai-morning-play com.rootgrove.xiaoai-morning-stop; do
  launchctl unload "$LAUNCH_AGENTS/$agent.plist" 2>/dev/null || true
  launchctl load "$LAUNCH_AGENTS/$agent.plist"
done
echo "alarms armed: 08:00 play / 08:12 stop (daily, content-driven)"
