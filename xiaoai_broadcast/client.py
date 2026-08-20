"""Async MiNA cloud client wrapper around miservice_fork.

Credential contract (first match wins):
    MI_USER / MI_PASS                    -- miservice convention
    XIAOMI_USER / XIAOMI_PASSWORD        -- rootgrove Keychain protocol

Device id contract:
    device_list() items carry both `deviceID` (MiNA calls want this) and
    `miotDID` (what xiaomusic calls "did"). Our --did accepts either.

Token cache: ~/.xiaoai-broadcast/mi_token.json (auto-managed by MiAccount).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import aiohttp
from miservice import MiAccount, MiNAService

_HOME = Path.home() / ".xiaoai-broadcast"
_TOKEN_PATH = _HOME / "mi_token.json"


def _credential(env_a: str, env_b: str) -> str:
    value = os.environ.get(env_a) or os.environ.get(env_b) or ""
    if not value:
        raise SystemExit(f"missing credential: export {env_a} (or {env_b})")
    return value


async def _call(command: str, args: tuple[Any, ...], retry: int) -> Any:
    _HOME.mkdir(parents=True, exist_ok=True)
    user = _credential("MI_USER", "XIAOMI_USER")
    password = _credential("MI_PASS", "XIAOMI_PASSWORD")
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


def play_url(device_id: str, url: str, retry: int = 3) -> Any:
    return asyncio.run(_call("play_by_url", (device_id, url), retry))


def stop(device_id: str) -> Any:
    return asyncio.run(_call("player_stop", (device_id,), 2))


def tts(device_id: str, text: str) -> Any:
    return asyncio.run(_call("text_to_speech", (device_id, text), 2))


def status(device_id: str) -> Any:
    return asyncio.run(_call("player_get_status", (device_id,), 2))
