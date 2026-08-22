"""Harvest Xiaomi passToken via a dedicated Playwright browser profile.

mi_token.json's passToken can be revoked server-side (risk control, logout).
Re-seeding normally needs a human with DevTools. This module keeps a logged-in
browser profile at ~/.xiaoai-broadcast/browser-profile so the agent can
re-harvest {userId, passToken} headlessly any time the web session is alive.

Modes:
  default             harvest from the saved profile if the session is alive
  --headed            visible window, wait for a manual login, then harvest
  --account A --sms   drive the SMS login flow; the verification code is read
                      from the code file (default ~/.xiaoai-broadcast/
                      sms_code.txt) while this process waits, so the code can
                      be supplied remotely by a human or an agent in chat.

Exit codes: 0 harvested; 2 browser launch failed; 3 not logged in /
session dead; 4 Xiaomi login page layout changed (state dumped to stderr);
5 SMS code never arrived.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import string
import sys
import time
from pathlib import Path
from typing import Any

from .client import _load_token, _save_token

_HOME = Path.home() / ".xiaoai-broadcast"
PROFILE_DIR = _HOME / "browser-profile"
LOGIN_URL = "https://account.xiaomi.com/"
CODE_FILE = Path(os.environ.get("XIAOAI_SMS_CODE_FILE", str(_HOME / "sms_code.txt")))


def _new_device_id() -> str:
    return "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16)
    )


def _harvest(context: Any) -> dict[str, str] | None:
    jar = {
        c["name"]: c["value"].strip()
        for c in context.cookies("https://account.xiaomi.com")
        if c["domain"].endswith("xiaomi.com")
    }
    if jar.get("userId") and jar.get("passToken"):
        return {"userId": jar["userId"], "passToken": jar["passToken"]}
    return None


def _write_token(harvest: dict[str, str]) -> dict[str, str]:
    old = _load_token()
    token = {
        "deviceId": str(old.get("deviceId") or _new_device_id()),
        "userId": harvest["userId"],
        "passToken": harvest["passToken"],
    }
    _save_token(token)
    return token


def _dump(frame: Any) -> None:
    page = frame.page
    print(f"[page] url={page.url}", file=sys.stderr)
    print(f"[page] title={page.title()!r}", file=sys.stderr)
    try:
        body = re.sub(r"\s+", " ", frame.locator("body").inner_text(timeout=2000))
        print(f"[page] text={body[:400]}", file=sys.stderr)
    except Exception:
        pass


def _find_login_frame(page: Any, timeout_s: int = 15) -> Any:
    account_pat = re.compile("手机号|邮箱|账号|小米ID|password|username", re.I)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for frame in page.frames:
            try:
                if (
                    frame.locator("input#username").count()
                    or frame.get_by_placeholder(account_pat).count()
                    or frame.locator("input[type=password]").count()
                ):
                    return frame
            except Exception:
                continue
        page.wait_for_timeout(1000)
    return None


def _dismiss_cookie_banner(page: Any) -> None:
    for sel in ("text=同意并关闭", "text=同意并关闭提示"):
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible():
                loc.click()
                page.wait_for_timeout(800)
                return
        except Exception:
            continue


_INTERSTITIALS = (
    "text=同意并继续",
    "text=同意并关闭",
    "button:has-text('确定')",
    "text=立即验证",
)


def _click_interstitials(page: Any, budget_s: int = 30) -> None:
    """Click through post-submit consent/confirm dialogs until none remain."""
    deadline = time.time() + budget_s
    while time.time() < deadline:
        clicked = False
        for sel in _INTERSTITIALS:
            for frame in page.frames:
                loc = _first_visible(frame, (sel,))
                if loc is not None:
                    try:
                        loc.click()
                        page.wait_for_timeout(3000)
                        clicked = True
                        break
                    except Exception:
                        continue
            if clicked:
                break
        if _harvest(page.context):
            return
        if not clicked:
            return


def _agree_terms(frame: Any) -> None:
    box = _first_visible(
        frame, ("text=已阅读并同意", "input[type=checkbox]", "label:has(input[type=checkbox])")
    )
    if box is not None:
        try:
            box.click()
            frame.page.wait_for_timeout(800)
        except Exception:
            pass


def _first_visible(frame: Any, selectors: tuple[str, ...]) -> Any | None:
    for sel in selectors:
        loc = frame.locator(sel).first
        try:
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _switch_to_sms(frame: Any) -> bool:
    cand = _first_visible(
        frame,
        (
            "text=验证码登录",
            "text=短信登录",
            "text=手机号登录",
            "[role=tab]:has-text('验证码')",
        ),
    )
    if cand is None:
        return True
    cand.click()
    frame.page.wait_for_timeout(1500)
    return True


def _wait_harvest(context: Any, seconds: int) -> dict[str, str] | None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        harvest = _harvest(context)
        if harvest:
            return harvest
        context.pages[0].wait_for_timeout(2000) if context.pages else time.sleep(2)
    return None


def _launch(pw: Any, headless: bool) -> Any:
    channel = os.environ.get("XIAOAI_BROWSER_CHANNEL", "chrome")
    kwargs: dict[str, Any] = dict(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        args=["--no-first-run", "--no-default-browser-check"],
    )
    try:
        return pw.chromium.launch_persistent_context(channel=channel, **kwargs)
    except Exception as exc:
        print(f"chrome channel failed ({exc}); trying bundled chromium", file=sys.stderr)
        return pw.chromium.launch_persistent_context(**kwargs)


def _any_frame_first(page: Any, selectors: tuple[str, ...]):
    for frame in page.frames:
        loc = _first_visible(frame, selectors)
        if loc is not None:
            return frame, loc
    return None, None


def _password_flow(
    page: Any, account: str, password: str, timeout: int
) -> dict[str, str] | None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    _dismiss_cookie_banner(page)
    frame = _find_login_frame(page)
    if frame is None:
        _dump(page.main_frame)
        print("login form not found (layout change?)", file=sys.stderr)
        raise SystemExit(4)

    account_input = _first_visible(
        frame,
        (
            "input#username",
            "input[placeholder*='手机号']",
            "input[placeholder*='邮箱']",
            "input[placeholder*='账号']",
            "input[placeholder*='小米ID']",
            "input[type=text]",
            "input:not([type])",
        ),
    )
    if account_input is None:
        _dump(frame)
        print("account input not found", file=sys.stderr)
        raise SystemExit(4)
    account_input.fill(account)

    pwd_input = frame.locator("input[type=password]").first
    if not pwd_input.count():
        _dump(frame)
        print("password input not found", file=sys.stderr)
        raise SystemExit(4)
    pwd_input.fill(password)

    _agree_terms(frame)

    submit = _first_visible(
        frame, ("text=立即登录", "button:has-text('登录')", "input[type=submit]")
    )
    if submit is None:
        _dump(frame)
        print("submit button not found", file=sys.stderr)
        raise SystemExit(4)
    submit.click()
    page.wait_for_timeout(4000)

    _click_interstitials(page)

    for frame in page.frames:
        wrong = _first_visible(frame, ("text=密码不正确", "text=密码错误"))
        if wrong is not None:
            print("server rejected the password (stale/wrong creds)", file=sys.stderr)
            raise SystemExit(6)

    harvest = _wait_harvest(page.context, 10)
    if harvest:
        return harvest

    vframe, send_btn = _any_frame_first(
        page, ("text=获取验证码", "text=发送验证码", "button:has-text('验证码')")
    )
    if send_btn is None:
        _dump(page.main_frame)
        print("post-login verification UI not found", file=sys.stderr)
        raise SystemExit(4)
    send_btn.click()
    print(f"CODE_SENT: write the SMS code into {CODE_FILE} within {timeout}s", flush=True)

    code = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if CODE_FILE.is_file():
            text = CODE_FILE.read_text().strip()
            if text:
                code = text
                CODE_FILE.unlink()
                break
        page.wait_for_timeout(2000)
    if not code:
        print("SMS code never arrived in code file", file=sys.stderr)
        raise SystemExit(5)

    cframe, code_input = _any_frame_first(
        page, ("input#code", "input[placeholder*='验证码']")
    )
    if code_input is None:
        _dump(page.main_frame)
        print("verification code input not found", file=sys.stderr)
        raise SystemExit(4)
    code_input.fill(code)

    vsubmit = _any_frame_first(page, ("text=确定", "button:has-text('确定')", "text=立即验证"))
    if vsubmit[1] is not None:
        vsubmit[1].click()
    page.wait_for_timeout(5000)
    return _wait_harvest(page.context, 60)


def _find_code_input(frame: Any, account: str) -> Any | None:
    for sel in (
        "input#code",
        "input[placeholder*='验证码']",
        "input[placeholder*='短信']",
        "input[type=tel]",
        "input[type=text]",
        "input:not([type])",
    ):
        locs = frame.locator(sel)
        for i in range(min(locs.count(), 5)):
            loc = locs.nth(i)
            try:
                if not loc.is_visible():
                    continue
                if (loc.input_value() or "").strip() == account:
                    continue
                return loc
            except Exception:
                continue
    return None


def _sms_flow(page: Any, account: str, timeout: int) -> dict[str, str] | None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    _dismiss_cookie_banner(page)
    frame = _find_login_frame(page)
    if frame is None:
        _dump(page.main_frame)
        print("login form not found (layout change?)", file=sys.stderr)
        raise SystemExit(4)

    _switch_to_sms(frame)
    frame = _find_login_frame(page) or frame

    account_input = _first_visible(
        frame,
        (
            "input#username",
            "input[placeholder*='手机号']",
            "input[type=tel]",
            "input[placeholder*='邮箱']",
            "input[type=text]",
            "input:not([type])",
        ),
    )
    if account_input is None:
        _dump(frame)
        print("account input not found", file=sys.stderr)
        raise SystemExit(4)
    account_input.fill(account)

    _agree_terms(frame)

    next_btn = _first_visible(frame, ("text=下一步", "button:has-text('下一步')"))
    if next_btn is not None:
        next_btn.click()
        page.wait_for_timeout(3500)
        _click_interstitials(page, budget_s=15)
        frame = _find_login_frame(page) or frame

    def send_code() -> Any:
        return _first_visible(
            frame, ("text=获取验证码", "text=发送验证码", "button:has-text('验证码')")
        )

    btn = send_code()
    if btn is not None:
        btn.click()
        page.wait_for_timeout(2500)
        _click_interstitials(page, budget_s=15)
        if send_code() is not None and not re.search(
            r"\d+s|重新", page.locator("body").inner_text(timeout=3000)
        ):
            send_code().click()
        print(f"CODE_SENT: write the SMS code into {CODE_FILE} within {timeout}s", flush=True)
    else:
        body = page.locator("body").inner_text(timeout=3000)
        if re.search(r"\d+s|重新|验证码", body):
            print(f"CODE_SENT (auto): write the SMS code into {CODE_FILE} within {timeout}s", flush=True)
        else:
            _dump(page.main_frame)
            print("neither send-code button nor code page found", file=sys.stderr)
            raise SystemExit(4)

    code = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if CODE_FILE.is_file():
            text = CODE_FILE.read_text().strip()
            if text:
                code = text
                CODE_FILE.unlink()
                break
        page.wait_for_timeout(2000)
    if not code:
        print("SMS code never arrived in code file", file=sys.stderr)
        raise SystemExit(5)

    code_input = _find_code_input(frame, account)
    if code_input is None:
        _dump(frame)
        print("code input not found", file=sys.stderr)
        raise SystemExit(4)
    code_input.fill(code)

    _agree_terms(frame)
    submit = _first_visible(
        frame, ("text=立即登录", "button:has-text('登录')", "input[type=submit]")
    )
    if submit is None:
        _dump(frame)
        print("submit button not found", file=sys.stderr)
        raise SystemExit(4)
    submit.click()
    page.wait_for_timeout(4000)
    _click_interstitials(page)
    return _wait_harvest(page.context, 60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xiaoai-broadcast login-browser",
        description="Harvest passToken from the saved browser profile",
    )
    parser.add_argument("--headed", action="store_true", help="visible window for manual login")
    parser.add_argument("--account", help="account (phone/email) for the SMS flow")
    parser.add_argument("--sms", action="store_true", help="request SMS code, read it from the code file")
    parser.add_argument(
        "--password",
        action="store_true",
        help="password login (MI_PASS/XIAOMI_PASSWORD env); post-login SMS "
        "verification is handled via the code file",
    )
    parser.add_argument("--timeout", type=int, default=300, help="seconds to wait for manual login or SMS code")
    parser.add_argument("--wait-login", type=int, default=15, help="seconds to probe an existing session")
    args = parser.parse_args(argv)

    if args.sms and not args.account:
        print("--sms requires --account", file=sys.stderr)
        return 1
    if args.password and not args.account:
        print("--password requires --account", file=sys.stderr)
        return 1
    password = os.environ.get("MI_PASS") or os.environ.get("XIAOMI_PASSWORD") or ""
    if args.password and not password:
        print("--password needs MI_PASS/XIAOMI_PASSWORD in env", file=sys.stderr)
        return 1

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed: pip install playwright", file=sys.stderr)
        return 2

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        try:
            context = _launch(pw, headless=not args.headed)
        except Exception as exc:
            print(f"browser launch failed: {exc}", file=sys.stderr)
            return 2
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(10_000)
        try:
            if args.password:
                harvest = _password_flow(page, args.account, password, args.timeout)
            elif args.sms:
                harvest = _sms_flow(page, args.account, args.timeout)
            else:
                page.goto(LOGIN_URL, wait_until="domcontentloaded")
                wait = args.timeout if args.headed else args.wait_login
                harvest = _wait_harvest(context, wait)
            if not harvest:
                print(
                    "not logged in: run with --headed (manual) or "
                    "--account <phone|email> --sms (remote)",
                    file=sys.stderr,
                )
                return 3
            token = _write_token(harvest)
            masked = token["userId"][:3] + "***"
            print(f"harvested: userId={masked} -> mi_token.json (0600)")
            return 0
        finally:
            context.close()


if __name__ == "__main__":
    raise SystemExit(main())
