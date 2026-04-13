from __future__ import annotations

import asyncio
import json
import os
import select
import sys
import re

from data.const import (
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_LOGIN_STATE_PATH,
    TELEGRAM_SESSION_PATH,
)

PHONE_PATTERN = re.compile(r"^\+?\d{8,15}$")
CODE_PATTERN = re.compile(r"^\d{5,6}$")
AUTH_POLL_INTERVAL_SECONDS = max(5, int(os.getenv("SHAFA_TELEGRAM_AUTH_POLL_INTERVAL", "5")))


def _normalize_step(step: str | None) -> str:
    clean_step = str(step or "").strip().upper()
    aliases = {
        "": "INIT",
        "IDLE": "INIT",
        "INIT": "INIT",
        "WAIT_PHONE": "WAIT_PHONE",
        "WAIT_PHONE_INPUT": "WAIT_PHONE",
        "PHONE_RECEIVED": "WAIT_PHONE",
        "SENDING_CODE": "WAIT_PHONE",
        "PHONE_SUBMITTED": "WAIT_PHONE",
        "WAIT_CODE": "WAIT_CODE",
        "WAIT_CODE_INPUT": "WAIT_CODE",
        "WAITING_FOR_CODE": "WAIT_CODE",
        "AWAITING_CODE_INPUT": "WAIT_CODE",
        "CODE_RECEIVED": "WAIT_CODE",
        "VERIFYING": "WAIT_CODE",
        "VERIFYING_CODE": "WAIT_CODE",
        "SUCCESS": "SUCCESS",
        "FAILED": "FAILED",
    }
    return aliases.get(clean_step, "INIT")


def send_code(phone: str) -> None:
    asyncio.run(_send_code(phone))


def complete_login(phone: str, code: str) -> None:
    asyncio.run(_complete_login(phone, code))


def interactive_login() -> None:
    asyncio.run(_interactive_login())


async def _send_code(phone: str) -> None:
    phone = _validate_phone(phone)
    _persist_login_state(
        phone_number=phone,
        verification_code="",
        current_auth_step="WAIT_PHONE",
        telegram_password="",
        code_confirmed=False,
    )
    print(f"[AUTH] Phone received: {phone}", flush=True)
    print("[AUTH] Sending phone to Telethon", flush=True)
    telegram_client_cls = _get_telegram_client_cls()
    api_id, api_hash = _require_telegram_credentials()
    async with telegram_client_cls(str(TELEGRAM_SESSION_PATH), api_id, api_hash) as client:
        sent = await client.send_code_request(phone)
    _persist_login_state(
        phone_number=phone,
        current_auth_step="WAIT_CODE",
        phone_code_hash=sent.phone_code_hash,
    )
    print("[AUTH] Waiting for code input", flush=True)


async def _complete_login(phone: str, code: str) -> None:
    payload = _read_login_state()
    phone = _validate_phone(phone)
    code = _validate_code(code)
    expected_phone = str(payload.get("phone_number") or payload.get("phone") or "").strip()
    phone_code_hash = str(payload.get("phone_code_hash") or "").strip()
    if not expected_phone or not phone_code_hash:
        raise RuntimeError("Telegram login was not initialized for this account.")
    if expected_phone != phone:
        raise RuntimeError("Phone number does not match the pending Telegram login.")
    _persist_login_state(
        phone_number=phone,
        verification_code=code,
        current_auth_step="WAIT_CODE",
        phone_code_hash=phone_code_hash,
        telegram_password=str(payload.get("telegram_password") or "").strip(),
        code_confirmed=True,
    )
    print(f"[AUTH] Code received: {code}", flush=True)
    print("[AUTH] Sending code to Telethon", flush=True)

    telegram_client_cls = _get_telegram_client_cls()
    api_id, api_hash = _require_telegram_credentials()
    async with telegram_client_cls(str(TELEGRAM_SESSION_PATH), api_id, api_hash) as client:
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except Exception as exc:
            if "SessionPasswordNeeded" not in exc.__class__.__name__:
                raise
            password = await _await_password_input(phone)
            _persist_login_state(
                phone_number=phone,
                verification_code=code,
                telegram_password=password,
                current_auth_step="WAIT_CODE",
                phone_code_hash=phone_code_hash,
                code_confirmed=True,
            )
            await client.sign_in(password=password)
    _persist_login_state(
        phone_number=phone,
        verification_code=code,
        current_auth_step="SUCCESS",
        phone_code_hash=phone_code_hash,
        telegram_password=str(payload.get("telegram_password") or "").strip(),
        code_confirmed=False,
    )
    print("[AUTH] Authentication success", flush=True)


async def _interactive_login() -> None:
    phone = ""
    try:
        telegram_client_cls = _get_telegram_client_cls()
        api_id, api_hash = _require_telegram_credentials()
        async with telegram_client_cls(str(TELEGRAM_SESSION_PATH), api_id, api_hash) as client:
            print("TG_AUTH:PHONE_REQUEST", flush=True)
            print("Please enter your phone:", flush=True)
            _persist_login_state(current_auth_step="WAIT_PHONE", code_confirmed=False)
            phone = await _await_phone_input()
            _persist_login_state(phone_number=phone, current_auth_step="WAIT_PHONE")
            print(f"[AUTH] Phone received: {phone}", flush=True)

            print("TG_AUTH:PHONE_RECEIVED", flush=True)
            print("[AUTH] Sending phone to Telethon", flush=True)
            sent = await client.send_code_request(phone)
            _persist_login_state(
                phone_number=phone,
                current_auth_step="WAIT_CODE",
                phone_code_hash=sent.phone_code_hash,
                telegram_password="",
                code_confirmed=False,
            )
            print("TG_AUTH:CODE_REQUESTED", flush=True)
            print("Please enter the code:", flush=True)
            print("[AUTH] Waiting for code input", flush=True)
            code = await _await_confirmed_code(phone)
            _persist_login_state(
                phone_number=phone,
                verification_code=code,
                current_auth_step="WAIT_CODE",
                phone_code_hash=sent.phone_code_hash,
                code_confirmed=True,
            )
            print(f"[AUTH] Code received: {code}", flush=True)

            print("TG_AUTH:CODE_RECEIVED", flush=True)
            print("[AUTH] Sending code to Telethon", flush=True)
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except Exception as exc:
                if "SessionPasswordNeeded" not in exc.__class__.__name__:
                    raise
                print("TG_AUTH:PASSWORD_REQUEST", flush=True)
                print("Please enter your password:", flush=True)
                password = await _await_password_input(phone)
                _persist_login_state(
                    phone_number=phone,
                    verification_code=code,
                    telegram_password=password,
                    current_auth_step="WAIT_CODE",
                    phone_code_hash=sent.phone_code_hash,
                    code_confirmed=True,
                )
                await client.sign_in(password=password)
        _persist_login_state(
            phone_number=phone,
            verification_code=code,
            current_auth_step="SUCCESS",
            phone_code_hash=sent.phone_code_hash,
            telegram_password=str(_read_login_state().get("telegram_password") or "").strip(),
            code_confirmed=False,
        )
        print("[AUTH] Authentication success", flush=True)
        print("TG_AUTH:SUCCESS", flush=True)
    except Exception as exc:
        _persist_login_state(phone_number=phone, current_auth_step="FAILED")
        print(f"[AUTH] Authentication failure: {exc}", flush=True)
        print(f"TG_AUTH:ERROR:{_classify_auth_error(exc)}", flush=True)
        raise


def _require_telegram_credentials() -> tuple[int, str]:
    if TELEGRAM_API_ID is None or not TELEGRAM_API_HASH:
        raise RuntimeError(
            "Missing Telegram credentials. "
            "Set SHAFA_TELEGRAM_API_ID and SHAFA_TELEGRAM_API_HASH."
        )
    return int(TELEGRAM_API_ID), TELEGRAM_API_HASH


def _get_telegram_client_cls():
    from telethon import TelegramClient

    return TelegramClient


def _read_line_nonblocking() -> str | None:
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
    except (OSError, ValueError):
        return None
    if not ready:
        return None
    line = sys.stdin.readline()
    if line == "":
        return None
    return line.strip()


def _read_login_state() -> dict:
    if not TELEGRAM_LOGIN_STATE_PATH.exists():
        return {}
    try:
        return json.loads(TELEGRAM_LOGIN_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _persist_login_state(
    *,
    phone_number: str | None = None,
    verification_code: str | None = None,
    current_auth_step: str | None = None,
    phone_code_hash: str | None = None,
    telegram_password: str | None = None,
    code_confirmed: bool | None = None,
) -> None:
    payload = _read_login_state()
    if phone_number is not None:
        payload["phone_number"] = str(phone_number).strip()
        payload["phone"] = str(phone_number).strip()
    if verification_code is not None:
        payload["verification_code"] = str(verification_code).strip()
    if current_auth_step is not None:
        payload["current_auth_step"] = _normalize_step(current_auth_step)
    if phone_code_hash is not None:
        payload["phone_code_hash"] = str(phone_code_hash).strip()
    if telegram_password is not None:
        payload["telegram_password"] = str(telegram_password).strip()
    if code_confirmed is not None:
        payload["code_confirmed"] = bool(code_confirmed)
    TELEGRAM_LOGIN_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TELEGRAM_LOGIN_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _validate_phone(phone: str) -> str:
    clean_phone = str(phone or "").strip()
    if not clean_phone or clean_phone.casefold() in {"+380...", "phone", "none", "null"}:
        print("Phone number is required for Telegram login", flush=True)
        raise RuntimeError("Phone number is required for Telegram login")
    clean_phone = re.sub(r"[\s()-]+", "", clean_phone)
    if not PHONE_PATTERN.fullmatch(clean_phone):
        print("Phone number is required for Telegram login", flush=True)
        raise RuntimeError("Phone number is required for Telegram login")
    return clean_phone


def _validate_code(code: str) -> str:
    clean_code = str(code or "").strip()
    if not CODE_PATTERN.fullmatch(clean_code):
        raise RuntimeError("Verification code must be 5 or 6 digits.")
    return clean_code


def _validate_password(password: str) -> str:
    clean_password = str(password or "").strip()
    if not clean_password:
        raise RuntimeError("Telegram password is required.")
    return clean_password


async def _await_phone_input() -> str:
    while True:
        payload = _read_login_state()
        candidate = str(payload.get("phone_number") or payload.get("phone") or "").strip()
        try:
            if candidate:
                return _validate_phone(candidate)
        except RuntimeError:
            pass

        stdin_value = _read_line_nonblocking()
        if stdin_value:
            try:
                return _validate_phone(stdin_value)
            except RuntimeError:
                pass

        await asyncio.sleep(AUTH_POLL_INTERVAL_SECONDS)


async def _await_confirmed_code(phone: str) -> str:
    while True:
        payload = _read_login_state()
        pending_phone = str(payload.get("phone_number") or payload.get("phone") or "").strip()
        if pending_phone and pending_phone != phone:
            raise RuntimeError("Phone number does not match the pending Telegram login.")

        code_candidate = str(payload.get("verification_code") or "").strip()
        code_confirmed = bool(payload.get("code_confirmed", False))
        if code_candidate and code_confirmed:
            try:
                return _validate_code(code_candidate)
            except RuntimeError:
                pass

        stdin_value = _read_line_nonblocking()
        if stdin_value:
            try:
                return _validate_code(stdin_value)
            except RuntimeError:
                pass

        await asyncio.sleep(AUTH_POLL_INTERVAL_SECONDS)


async def _await_password_input(phone: str) -> str:
    while True:
        payload = _read_login_state()
        pending_phone = str(payload.get("phone_number") or payload.get("phone") or "").strip()
        if pending_phone and pending_phone != phone:
            raise RuntimeError("Phone number does not match the pending Telegram login.")

        password_candidate = str(payload.get("telegram_password") or "").strip()
        if password_candidate:
            try:
                return _validate_password(password_candidate)
            except RuntimeError:
                pass

        stdin_value = _read_line_nonblocking()
        if stdin_value:
            try:
                return _validate_password(stdin_value)
            except RuntimeError:
                pass

        await asyncio.sleep(AUTH_POLL_INTERVAL_SECONDS)


def _classify_auth_error(exc: Exception) -> str:
    name = exc.__class__.__name__
    message = str(exc).strip() or name
    if "FloodWait" in name:
        return f"RATE_LIMIT:{message}"
    if "PhoneCodeInvalid" in name:
        return f"INVALID_CODE:{message}"
    if "PhoneCodeExpired" in name:
        return f"EXPIRED_CODE:{message}"
    if "PhoneNumberInvalid" in name:
        return f"INVALID_PHONE:{message}"
    if "SessionPasswordNeeded" in name:
        return "PASSWORD_REQUIRED:Telegram password is required."
    if "ApiIdInvalid" in name:
        return f"INVALID_API:{message}"
    return f"GENERIC:{message}"
