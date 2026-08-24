"""Deliver the morning brief: LAN MP3 pull when reachable, cloud TTS otherwise.

The speaker must fetch play_by_url audio over the LAN, which breaks whenever
speaker and Mac land on different networks (2026-08-23: router changed to
192.168.8.x, speaker stayed on the old 192.168.1.x segment; cloud commands
kept working so nothing *seemed* broken). Cloud TTS needs no LAN at all.

Delivery strategy, in order:
  1. auto-detect this Mac's LAN IP (en0/en1), self-check the serve port,
     push the MP3 URL, and VERIFY playback actually started (speaker
     status goes playing) -- the MiNA play API returns success even when
     the device can never reach the URL.
  2. fall back to chunked cloud TTS (<=300 chars per chunk, sequenced by
     polling speaker status), which works with zero LAN dependency.

Usage:
  python -m xiaoai_broadcast.deliver --did <D> [--volume 50] \
      --txt ~/.xiaomusic/music/morning/morning_brief.txt [--dry-run]

Prints "MODE: url" or "MODE: tts" on the last stdout line (for shell
volume-restore logic); exits non-zero only when BOTH paths fail.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .client import get_volume, play_url, resolve_device, status, tts, volume

_CHUNK_CHARS = 300
_STATUS_POLL_S = 5
_URL_CONFIRM_TIMEOUT_S = 30
_CHUNK_CAP_S = 150


def _lan_ip() -> str:
    for iface in ("en0", "en1"):
        try:
            out = subprocess.run(
                ["ipconfig", "getifaddr", iface], capture_output=True, text=True
            ).stdout.strip()
        except OSError:
            continue
        if out:
            return out
    return ""


def _serve_reachable(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status in (200, 206)
    except Exception:
        return False


def _is_playing(device_id: str) -> bool:
    try:
        resp = status(device_id)
        info = ((resp or {}).get("data") or {}).get("info") or "{}"
        parsed = info if isinstance(info, dict) else _loads(info)
        return int(parsed.get("status", 0)) == 1
    except Exception:
        return False


def _loads(raw: str) -> dict:
    import json

    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _split_chunks(text: str) -> list[str]:
    parts = [p for p in re.split(r"(?<=[。！？；\n])", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for part in parts:
        if len(cur) + len(part) > _CHUNK_CHARS and cur:
            chunks.append(cur.strip())
            cur = part
        else:
            cur += part
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def _try_url(device_id: str, mp3_url: str, vol: int, dry: bool) -> bool:
    print(f"[url] pushing {mp3_url}")
    if dry:
        print("[url] dry-run: would push and poll for playback start")
        return True
    volume(device_id, vol)
    try:
        play_url(device_id, mp3_url, retry=3)
    except SystemExit as exc:
        print(f"[url] play push failed: {exc}")
        return False
    deadline = time.time() + _URL_CONFIRM_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(_STATUS_POLL_S)
        if _is_playing(device_id):
            print("[url] playback confirmed (status=playing)")
            return True
    print("[url] no playback within timeout; speaker cannot reach the URL")
    return False


def _tts_chunks(device_id: str, text: str, vol: int, dry: bool) -> bool:
    chunks = _split_chunks(text)
    print(f"[tts] {len(text)} chars -> {len(chunks)} chunks")
    if dry:
        for i, chunk in enumerate(chunks, 1):
            print(f"[tts] dry-run chunk {i}/{len(chunks)} ({len(chunk)} chars): {chunk[:40]}...")
        return True
    volume(device_id, vol)
    for i, chunk in enumerate(chunks, 1):
        try:
            tts(device_id, chunk)
        except SystemExit as exc:
            print(f"[tts] chunk {i} send failed: {exc}")
            return False
        print(f"[tts] chunk {i}/{len(chunks)} sent ({len(chunk)} chars)")
        waited = 0
        while waited < _CHUNK_CAP_S:
            time.sleep(_STATUS_POLL_S)
            waited += _STATUS_POLL_S
            if not _is_playing(device_id):
                break
        print(f"[tts] chunk {i} settled (~{waited}s)")
        time.sleep(2)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xiaoai-broadcast deliver")
    parser.add_argument("--did", required=True)
    parser.add_argument("--volume", type=int, default=50)
    parser.add_argument(
        "--txt",
        default=str(Path.home() / ".xiaomusic/music/morning/morning_brief.txt"),
        help="script text for the TTS fallback",
    )
    parser.add_argument("--mp3", default="morning_brief.mp3")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    device = resolve_device(args.did)
    device_id = device["device_id"]

    ip = _lan_ip()
    mode = ""
    if ip:
        mp3_url = f"http://{ip}:{args.port}/{args.mp3}"
        if _serve_reachable(mp3_url):
            if _try_url(device_id, mp3_url, args.volume, args.dry_run):
                mode = "url"
        else:
            print(f"[url] serve not reachable on {ip}:{args.port}; skipping MP3 path")
    else:
        print("[url] no LAN IP detected; skipping MP3 path")

    if not mode:
        text = Path(args.txt).read_text(encoding="utf-8").strip()
        if not text:
            print(f"no fallback text at {args.txt}", file=sys.stderr)
            return 1
        if not _tts_chunks(device_id, text, args.volume, args.dry_run):
            return 1
        mode = "tts"

    print(f"MODE: {mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
