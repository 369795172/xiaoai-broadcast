"""Async MiNA cloud client wrapper around miservice_fork.

Two credential paths (MFA-safe):

1. passToken bootstrap (recommended for MFA-enabled accounts):
   `xiaoai-broadcast login-cookie` seeds ~/.xiaoai-broadcast/mi_token.json
   with {deviceId, userId, passToken} taken from a logged-in browser.
   miservice then authenticates via cookie -- no password, no SMS.

2. Password env fallback (accounts without MFA):
   MI_USER / MI_PASS  or  XIAOMI_USER / XIAOMI_PASSWORD.

Token cache: ~/.xiaoai-broadcast/mi_token.json (0600, auto-managed).
"""
from __future__ import annotations

import asyncio
import getpass
import json
import os
import stat
import string
import secrets
from pathlib import Path
from typing import Any

import aiohttp
from miservice import MiAccount, MiNAService

_HOME = Path.home() / ".xiaoai-broadcast"
_TOKEN_PATH = _HOME / "mi_token.json"


def _load_token() -> dict[str, Any]:
    try:
        data = json.loads(_TOKEN_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_token(token: dict[str, Any]) -> None:
    _HOME.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(json.dumps(token, indent=2))
    _TOKEN_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)


def has_pass_token() -> bool:
    token = _load_token()
    return bool(token.get("passToken") and token.get("userId"))


def bootstrap_cookie_login() -> dict[str, Any]:
    """Interactively seed the token file from a logged-in browser session.

    Get the values from DevTools -> Application -> Cookies -> account.xiaomi.com:
      userId, passToken. Input here is hidden; nothing is printed or logged.
    """
    user_id = input("userId (from cookie of account.xiaomi.com): ").strip()
    pass_token = getpass.getpass("passToken (hidden input): ").strip()
    if not user_id or not pass_token:
        raise SystemExit("both userId and passToken are required")
    device_id = "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16)
    )
    token = {"deviceId": device_id, "userId": user_id, "passToken": pass_token}
    _save_token(token)
    return token


def _env(name: str) -> str:
    return os.environ.get(name, "")


async def _call(command: str, args: tuple[Any, ...], retry: int) -> Any:
    _HOME.mkdir(parents=True, exist_ok=True)
    token = _load_token()
    user = _env("MI_USER") or _env("XIAOMI_USER") or str(token.get("userId", ""))
    password = _env("MI_PASS") or _env("XIAOMI_PASSWORD")
    if not user:
        raise SystemExit(
            "no credentials: run `xiaoai-broadcast login-cookie` "
            "(MFA accounts) or export MI_USER/MI_PASS"
        )
    session = aiohttp.ClientSession()
    try:
        account = MiAccount(session, user, password, str(_TOKEN_PATH))
        service = MiNAService(account)
        last_error: Exception | None = None
        for attempt in range(max(1, retry)):
            try:
                return await getattr(service, command)(*args)
            except Exception as exc:  # retried, then surfaced
                last_error = exc
                if attempt < retry - 1:
                    await asyncio.sleep(3)
        raise SystemExit(f"mina command {command} failed: {last_error}")
    finally:
        await session.close()


def list_devices() -> list[dict[str, str]]:
    """Return [{did, device_id, hardware, name}] sorted by name."""
    raw = asyncio.run(_call("device_list", (), 2))
    devices: list[dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        name = item.get("alias") or item.get("name") or "?"
        devices.append(
            {
                "did": str(item.get("miotDID", "")),
                "device_id": str(item.get("deviceID", "")),
                "hardware": str(item.get("hardware", "?")),
                "name": str(name),
            }
        )
    devices.sort(key=lambda d: d["name"])
    return devices


def resolve_device(value: str) -> dict[str, str]:
    """Match a user-supplied id against did (miotDID) or device_id."""
    devices = list_devices()
    for device in devices:
        if value in (device["did"], device["device_id"]):
            return device
    known = ", ".join(f'{d["name"]}({d["did"]})' for d in devices)
    raise SystemExit(f"device not found: {value}; known: {known}")


def volume(device_id: str, level: int) -> Any:
    return asyncio.run(_call("player_set_volume", (device_id, level), 2))


def get_volume(device_id: str) -> int:
    """Current playback volume via player_get_status (data.info JSON)."""
    import json as _json

    resp = asyncio.run(_call("player_get_status", (device_id,), 2))
    info = ((resp or {}).get("data") or {}).get("info") or "{}"
    parsed = _json.loads(info) if isinstance(info, str) else info
    return int(parsed.get("volume", 0))


def play_url(device_id: str, url: str, retry: int = 3) -> Any:
    return asyncio.run(_call("play_by_url", (device_id, url), retry))


def stop(device_id: str) -> Any:
    return asyncio.run(_call("player_stop", (device_id,), 2))


def tts(device_id: str, text: str) -> Any:
    return asyncio.run(_call("text_to_speech", (device_id, text), 2))


def status(device_id: str) -> Any:
    return asyncio.run(_call("player_get_status", (device_id,), 2))
