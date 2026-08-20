# xiaoai-broadcast

Lean XiaoAi (Xiaomi) speaker broadcaster. No WebUI, no polling, no daemon beyond a static file server — just the MiNA cloud API from [`miservice_fork`](https://pypi.org/project/miservice-fork/) (the same library xiaomusic is built on) plus launchd.

Born as a replacement for a discontinued upstream ([hanxi/xiaomusic](https://github.com/hanxi/xiaomusic) stopped maintenance 2026-06): keep the engine, drop the car body.

## What it does

- Morning brief: weekdays 07:38 set volume → play `morning_brief.mp3` → 07:50 stop
- Ad-hoc: list devices, push any audio URL/file, short TTS, status

## Architecture

```
launchd 07:15 (rootgrove aggregate.py)  →  music dir / morning_brief.mp3
                                              │
launchd KeepAlive: xiaoai_broadcast.server ── serve :8091 (LAN, no-cache)
                                              │
launchd 07:38: morning_play.sh → MiNA cloud API → speaker pulls the URL
```

The speaker fetches the audio over LAN itself; nothing streams from the Mac after the push.

## Install

```bash
git clone https://github.com/369795172/xiaoai-broadcast
cd xiaoai-broadcast && scripts/install.sh
```

Configure `~/.xiaoai-broadcast/env`:

```bash
XIAOAI_USER=...          # or rely on rootgrove Keychain loader
XIAOMI_PASSWORD=...      # never commit this file
XIAOAI_BASE_URL=http://<mac-lan-ip>:8091
XIAOAI_DID=...           # from: xiaoai-broadcast devices
```

Then:

```bash
~/.xiaoai-broadcast/venv/bin/xiaoai-broadcast devices
scripts/install_alarms.sh
```

## Usage

```bash
xiaoai-broadcast devices                 # list did / device_id
xiaoai-broadcast play --did <D> --file morning_brief.mp3 --volume 40
xiaoai-broadcast play --did <D> --url http://...mp3
xiaoai-broadcast stop --did <D>
xiaoai-broadcast tts  --did <D> "brief hello"
xiaoai-broadcast status --did <D>
xiaoai-broadcast serve --port 8091 --dir ~/music   # manual server run
```

`--did` accepts either `miotDID` (xiaomusic-style did) or MiNA `deviceID`.

## Notes

- macOS firewall must allow inbound on the serve port (speaker pulls from LAN).
- Reserve the Mac's LAN IP via DHCP, or pin `XIAOAI_BASE_URL` accordingly.
- Token cache: `~/.xiaoai-broadcast/mi_token.json` (auto refresh by miservice).
