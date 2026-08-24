"""CLI entry: devices / volume / play / stop / tts / status / serve."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from . import client, server


def _base_url() -> str:
    base = os.environ.get("XIAOAI_BASE_URL", "").rstrip("/")
    if not base:
        raise SystemExit(
            "missing XIAOAI_BASE_URL (e.g. http://192.168.1.124:8091)"
        )
    return base


def _music_dir() -> Path:
    return Path(
        os.environ.get("XIAOAI_MUSIC_DIR", str(server.DEFAULT_DIR))
    ).expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xiaoai-broadcast",
        description="Lean XiaoAi speaker broadcaster (MiNA cloud API)",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("devices", help="list speakers (did + device_id)")
    sub.add_parser(
        "login-cookie",
        help="seed auth from browser cookies (MFA-safe, interactive)",
    )
    p_browser = sub.add_parser(
        "login-browser",
        help="harvest passToken from a saved Playwright browser profile",
    )
    p_browser.add_argument("--headed", action="store_true", help="visible window, manual login")
    p_browser.add_argument("--account", help="phone/email for the SMS login flow")
    p_browser.add_argument(
        "--sms", action="store_true", help="request SMS code; read it from the code file"
    )
    p_browser.add_argument(
        "--password",
        action="store_true",
        help="password login (MI_PASS/XIAOMI_PASSWORD env); verification via code file",
    )
    p_browser.add_argument(
        "--timeout", type=int, default=300, help="seconds to wait for manual login or code"
    )
    p_browser.add_argument(
        "--wait-login", type=int, default=15, help="seconds to probe an existing session"
    )

    p_vol = sub.add_parser("volume", help="get or set volume")
    p_vol.add_argument("--did", required=True)
    p_vol.add_argument("level", type=int, nargs="?", help="omit to print current")

    p_play = sub.add_parser("play", help="play a file or URL on a speaker")
    p_play.add_argument("--did", required=True)
    p_play.add_argument("--file", help="filename under XIAOAI_MUSIC_DIR")
    p_play.add_argument("--url", help="full URL (alternative to --file)")
    p_play.add_argument(
        "--volume", type=int, help="set volume first, then play"
    )
    p_play.add_argument("--retry", type=int, default=3)

    p_stop = sub.add_parser("stop", help="stop playback")
    p_stop.add_argument("--did", required=True)

    p_tts = sub.add_parser("tts", help="short text-to-speech")
    p_tts.add_argument("--did", required=True)
    p_tts.add_argument("text")

    p_status = sub.add_parser("status", help="playback status")
    p_status.add_argument("--did", required=True)

    p_deliver = sub.add_parser(
        "deliver",
        help="morning brief: MP3 URL when reachable, cloud TTS fallback",
    )
    p_deliver.add_argument("--did", required=True)
    p_deliver.add_argument("--volume", type=int, default=50)
    p_deliver.add_argument("--txt", help="script text for the TTS fallback")
    p_deliver.add_argument("--mp3", default="morning_brief.mp3")
    p_deliver.add_argument("--port", type=int, default=8091)
    p_deliver.add_argument("--dry-run", action="store_true")

    p_serve = sub.add_parser("serve", help="static audio server (LAN)")
    p_serve.add_argument("--port", type=int, default=server.DEFAULT_PORT)
    p_serve.add_argument("--dir", type=Path, default=_music_dir())

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        server.serve(args.dir, args.port)
        return 0

    if args.cmd == "login-browser":
        from . import browser_login

        return browser_login.main(
            [
                *([] if not args.headed else ["--headed"]),
                *(["--account", args.account] if args.account else []),
                *(["--sms"] if args.sms else []),
                *(["--password"] if args.password else []),
                "--timeout",
                str(args.timeout),
                "--wait-login",
                str(args.wait_login),
            ]
        )

    if args.cmd == "login-cookie":
        token = client.bootstrap_cookie_login()
        print(
            f"token seeded: userId={token['userId']} "
            f"(device {token['deviceId']}, file 0600)"
        )
        rows = client.list_devices()
        print(f"login OK, {len(rows)} device(s):")
        for r in rows:
            print(
                f"  {r['name']:<20} {r['hardware']:<8} "
                f"did={r['did']} device_id={r['device_id']}"
            )
        return 0

    if args.cmd == "deliver":
        from . import deliver

        extra = ["--txt", args.txt] if args.txt else []
        return deliver.main(
            [
                "--did",
                args.did,
                "--volume",
                str(args.volume),
                "--mp3",
                args.mp3,
                "--port",
                str(args.port),
                *extra,
                *(["--dry-run"] if args.dry_run else []),
            ]
        )

    if args.cmd == "devices":
        rows = client.list_devices()
        if not rows:
            print("no devices found")
            return 1
        print(f"{'name':<20} {'hardware':<8} did        device_id")
        for r in rows:
            print(
                f"{r['name']:<20} {r['hardware']:<8} {r['did']:<10} {r['device_id']}"
            )
        return 0

    device = client.resolve_device(args.did)

    if args.cmd == "volume":
        if args.level is None:
            print(client.get_volume(device["device_id"]))
        else:
            client.volume(device["device_id"], args.level)
            print(f"volume -> {args.level} on {device['name']}")
    elif args.cmd == "play":
        if bool(args.file) == bool(args.url):
            print("specify exactly one of --file / --url", file=sys.stderr)
            return 2
        if args.file:
            target = _music_dir() / args.file
            if not target.is_file():
                print(f"not found: {target}", file=sys.stderr)
                return 2
            url = f"{_base_url()}/{args.file}"
        else:
            url = str(args.url)
        if args.volume is not None:
            client.volume(device["device_id"], args.volume)
        client.play_url(device["device_id"], url, retry=args.retry)
        print(f"playing {url} on {device['name']}")
    elif args.cmd == "stop":
        client.stop(device["device_id"])
        print(f"stopped {device['name']}")
    elif args.cmd == "tts":
        client.tts(device["device_id"], args.text)
        print(f"tts sent to {device['name']}")
    elif args.cmd == "status":
        print(client.status(device["device_id"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
