from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

from data.const import (
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_LOGIN_STATE_PATH,
    TELEGRAM_SESSION_PATH,
)

INIT = "INIT"
WAIT_PHONE = "WAIT_PHONE"
WAIT_CODE = "WAIT_CODE"
WAIT_PASSWORD = "WAIT_PASSWORD"
SUCCESS = "SUCCESS"
FAILED = "FAILED"

PHONE_PATTERN = re.compile(r"^\+?\d{8,15}$")
CODE_PATTERN = re.compile(r"^\d{5,6}$")

AUTH_STEP_ALIASES = {
    "": INIT,
    "IDLE": INIT,
    "INIT": INIT,
    "WAIT_PHONE": WAIT_PHONE,
    "WAIT_PHONE_INPUT": WAIT_PHONE,
    "PHONE_RECEIVED": WAIT_PHONE,
    "PHONE_SUBMITTED": WAIT_PHONE,
    "SENDING_CODE": WAIT_PHONE,
    "WAIT_CODE": WAIT_CODE,
    "WAIT_CODE_INPUT": WAIT_CODE,
    "WAITING_FOR_CODE": WAIT_CODE,
    "AWAITING_CODE_INPUT": WAIT_CODE,
    "CODE_RECEIVED": WAIT_CODE,
    "VERIFYING": WAIT_CODE,
    "VERIFYING_CODE": WAIT_CODE,
    "WAIT_PASSWORD": WAIT_PASSWORD,
    "PASSWORD_REQUIRED": WAIT_PASSWORD,
    "PASSWORD_REQUESTED": WAIT_PASSWORD,
    "SUCCESS": SUCCESS,
    "FAILED": FAILED,
}


def send_code(phone: str) -> None:
    asyncio.run(_run_auth_step(_send_code(phone)))


def complete_login(phone: str, code: str) -> None:
    asyncio.run(_run_auth_step(_complete_login(phone, code)))


def submit_password(password: str) -> None:
    asyncio.run(_run_auth_step(_submit_password(password)))


def session_status() -> bool:
    return asyncio.run(_run_auth_step(_session_status()))


async def _run_auth_step(coro):
    try:
        return await coro
    except Exception:
        raise


async def _send_code(phone: str) -> None:
    phone = _validate_phone(phone)
    session_path = _resolve_session_path()
    _persist_login_state(
        phone_number=phone,
        verification_code="",
        telegram_password="",
        current_auth_step=WAIT_PHONE,
        phone_code_hash="",
        session_path=str(session_path),
        code_confirmed=False,
    )
    _log_step(f"Starting Telegram auth for {phone}")
    _log_step(f"Using Telegram session file: {session_path}")

    telegram_client_cls = _get_telegram_client_cls()
    api_id, api_hash = _require_telegram_credentials()

    try:
        async with _connected_client(telegram_client_cls(str(session_path), api_id, api_hash)) as client:
            _log_step("Sending phone to Telethon")
            sent = await client.send_code_request(phone)
    except Exception as exc:
        _persist_failed_state(phone_number=phone, session_path=session_path)
        _log_step(f"Failed to send Telegram code: {_classify_auth_error(exc)}")
        raise

    _persist_login_state(
        phone_number=phone,
        verification_code="",
        telegram_password="",
        current_auth_step=WAIT_CODE,
        phone_code_hash=str(sent.phone_code_hash).strip(),
        session_path=str(session_path),
        code_confirmed=False,
    )
    _log_step("Verification code requested successfully")


async def _complete_login(phone: str, code: str) -> None:
    payload = _read_login_state()
    phone = _validate_phone(phone)
    code = _validate_code(code)
    session_path = _session_path_from_payload(payload)
    current_step = _normalize_step(payload.get("current_auth_step"))
    expected_phone = str(payload.get("phone_number") or payload.get("phone") or "").strip()
    phone_code_hash = str(payload.get("phone_code_hash") or "").strip()

    if current_step != WAIT_CODE:
        raise RuntimeError("Telegram login is not waiting for a verification code.")
    if not expected_phone or not phone_code_hash:
        raise RuntimeError("Telegram login was not initialized for this account.")
    if expected_phone != phone:
        raise RuntimeError("Phone number does not match the pending Telegram login.")

    _persist_login_state(
        phone_number=phone,
        verification_code=code,
        telegram_password=str(payload.get("telegram_password") or ""),
        current_auth_step=WAIT_CODE,
        phone_code_hash=phone_code_hash,
        session_path=str(session_path),
        code_confirmed=True,
    )
    _log_step(f"Submitting verification code for {phone}")

    telegram_client_cls = _get_telegram_client_cls()
    api_id, api_hash = _require_telegram_credentials()

    try:
        async with _connected_client(telegram_client_cls(str(session_path), api_id, api_hash)) as client:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    except Exception as exc:
        if _is_password_needed_error(exc):
            _persist_login_state(
                phone_number=phone,
                verification_code=code,
                telegram_password=str(payload.get("telegram_password") or ""),
                current_auth_step=WAIT_PASSWORD,
                phone_code_hash=phone_code_hash,
                session_path=str(session_path),
                code_confirmed=True,
            )
            _log_step("Telegram requires a 2FA password")
            return
        if _is_invalid_code_error(exc):
            _persist_login_state(
                phone_number=phone,
                verification_code="",
                telegram_password=str(payload.get("telegram_password") or ""),
                current_auth_step=WAIT_CODE,
                phone_code_hash=phone_code_hash,
                session_path=str(session_path),
                code_confirmed=False,
            )
            _log_step("Telegram sign-in failed: INVALID_CODE")
            raise RuntimeError("Неверный код Telegram. Проверь код и попробуй ещё раз.") from None
        if _is_expired_code_error(exc):
            _persist_failed_state(
                phone_number=phone,
                verification_code="",
                telegram_password=str(payload.get("telegram_password") or ""),
                phone_code_hash=phone_code_hash,
                session_path=session_path,
            )
            _log_step("Telegram sign-in failed: EXPIRED_CODE")
            raise RuntimeError("Код Telegram истёк. Запроси новый код и попробуй снова.") from None
        _persist_failed_state(
            phone_number=phone,
            verification_code=code,
            telegram_password=str(payload.get("telegram_password") or ""),
            phone_code_hash=phone_code_hash,
            session_path=session_path,
        )
        _log_step(f"Telegram sign-in failed: {_classify_auth_error(exc)}")
        raise RuntimeError(_humanize_auth_error(exc)) from None

    _mark_auth_success(
        phone_number=phone,
        verification_code=code,
        telegram_password=str(payload.get("telegram_password") or ""),
        phone_code_hash=phone_code_hash,
        session_path=session_path,
    )


async def _submit_password(password: str) -> None:
    payload = _read_login_state()
    session_path = _session_path_from_payload(payload)
    current_step = _normalize_step(payload.get("current_auth_step"))
    phone = _validate_phone(str(payload.get("phone_number") or payload.get("phone") or "").strip())
    code = _validate_code(str(payload.get("verification_code") or "").strip())
    phone_code_hash = str(payload.get("phone_code_hash") or "").strip()
    password = _validate_password(password)

    if current_step != WAIT_PASSWORD:
        raise RuntimeError("Telegram login is not waiting for a password.")
    if not phone_code_hash:
        raise RuntimeError("Telegram login is missing the phone_code_hash.")

    _persist_login_state(
        phone_number=phone,
        verification_code=code,
        telegram_password=password,
        current_auth_step=WAIT_PASSWORD,
        phone_code_hash=phone_code_hash,
        session_path=str(session_path),
        code_confirmed=True,
    )
    _log_step(f"Submitting Telegram 2FA password for {phone}")

    telegram_client_cls = _get_telegram_client_cls()
    api_id, api_hash = _require_telegram_credentials()

    try:
        async with _connected_client(telegram_client_cls(str(session_path), api_id, api_hash)) as client:
            await client.sign_in(password=password)
    except Exception as exc:
        if _is_invalid_password_error(exc):
            _persist_login_state(
                phone_number=phone,
                verification_code=code,
                telegram_password="",
                current_auth_step=WAIT_PASSWORD,
                phone_code_hash=phone_code_hash,
                session_path=str(session_path),
                code_confirmed=True,
            )
            _log_step("Telegram password sign-in failed: INVALID_PASSWORD")
            raise RuntimeError("Неверный Telegram 2FA пароль. Попробуй ещё раз.") from None
        _persist_failed_state(
            phone_number=phone,
            verification_code=code,
            telegram_password=password,
            phone_code_hash=phone_code_hash,
            session_path=session_path,
        )
        _log_step(f"Telegram password sign-in failed: {_classify_auth_error(exc)}")
        raise RuntimeError(_humanize_auth_error(exc)) from None

    _mark_auth_success(
        phone_number=phone,
        verification_code=code,
        telegram_password=password,
        phone_code_hash=phone_code_hash,
        session_path=session_path,
    )


async def _session_status() -> bool:
    session_path = _resolve_session_path()
    if not session_path.exists():
        _log_step("Telegram session file does not exist")
        return False

    telegram_client_cls = _get_telegram_client_cls()
    api_id, api_hash = _require_telegram_credentials()
    try:
        async with _connected_client(telegram_client_cls(str(session_path), api_id, api_hash)) as client:
            authorized = await client.is_user_authorized()
    except Exception as exc:
        _log_step(f"Telegram session check failed: {_classify_auth_error(exc)}")
        return False

    if not authorized:
        _log_step("Telegram session is unauthorized")
        return False

    _persist_login_state(
        current_auth_step=SUCCESS,
        session_path=str(session_path),
        code_confirmed=False,
    )
    _log_step(f"Telegram session is authorized: {session_path}")
    return True


def _mark_auth_success(
    *,
    phone_number: str,
    verification_code: str,
    telegram_password: str,
    phone_code_hash: str,
    session_path: Path,
) -> None:
    _persist_login_state(
        phone_number=phone_number,
        verification_code=verification_code,
        telegram_password=telegram_password,
        current_auth_step=SUCCESS,
        phone_code_hash=phone_code_hash,
        session_path=str(session_path),
        code_confirmed=False,
    )
    _log_step(f"Telegram session saved to {session_path}")


def _persist_failed_state(
    *,
    phone_number: str | None = None,
    verification_code: str | None = None,
    telegram_password: str | None = None,
    phone_code_hash: str | None = None,
    session_path: Path | None = None,
) -> None:
    _persist_login_state(
        phone_number=phone_number,
        verification_code=verification_code,
        telegram_password=telegram_password,
        current_auth_step=FAILED,
        phone_code_hash=phone_code_hash,
        session_path=str(session_path or _resolve_session_path()),
        code_confirmed=False,
    )


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


class _connected_client:
    def __init__(self, client) -> None:
        self.client = client

    async def __aenter__(self):
        await self.client.connect()
        return self.client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.client.disconnect()


def _read_login_state() -> dict:
    if not TELEGRAM_LOGIN_STATE_PATH.exists():
        return {"session_path": str(_resolve_session_path()), "current_auth_step": INIT}
    try:
        payload = json.loads(TELEGRAM_LOGIN_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"session_path": str(_resolve_session_path()), "current_auth_step": INIT}
    payload.setdefault("session_path", str(_resolve_session_path()))
    payload["current_auth_step"] = _normalize_step(payload.get("current_auth_step"))
    return payload


def _persist_login_state(
    *,
    phone_number: str | None = None,
    verification_code: str | None = None,
    current_auth_step: str | None = None,
    phone_code_hash: str | None = None,
    telegram_password: str | None = None,
    session_path: str | None = None,
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
        payload["telegram_password"] = str(telegram_password)
    if session_path is not None:
        payload["session_path"] = str(session_path).strip()
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
        raise RuntimeError("Phone number is required for Telegram login")
    clean_phone = re.sub(r"[\s()-]+", "", clean_phone)
    if not PHONE_PATTERN.fullmatch(clean_phone):
        raise RuntimeError("Phone number is required for Telegram login")
    return clean_phone


def _validate_code(code: str) -> str:
    clean_code = re.sub(r"[\s-]+", "", str(code or "").strip())
    if not CODE_PATTERN.fullmatch(clean_code):
        raise RuntimeError("Verification code must be 5 or 6 digits.")
    return clean_code


def _validate_password(password: str) -> str:
    clean_password = str(password or "")
    if clean_password == "":
        raise RuntimeError("Telegram password is required.")
    return clean_password


def _resolve_session_path() -> Path:
    TELEGRAM_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    return TELEGRAM_SESSION_PATH


def _session_path_from_payload(payload: dict) -> Path:
    raw_path = str(payload.get("session_path") or "").strip()
    if not raw_path:
        return _resolve_session_path()
    return Path(raw_path).expanduser()


def _normalize_step(step: str | None) -> str:
    clean_step = str(step or "").strip().upper()
    return AUTH_STEP_ALIASES.get(clean_step, INIT)


def _is_password_needed_error(exc: Exception) -> bool:
    return "SessionPasswordNeeded" in exc.__class__.__name__


def _is_invalid_code_error(exc: Exception) -> bool:
    return "PhoneCodeInvalid" in exc.__class__.__name__


def _is_expired_code_error(exc: Exception) -> bool:
    return "PhoneCodeExpired" in exc.__class__.__name__


def _is_invalid_password_error(exc: Exception) -> bool:
    return "PasswordHashInvalid" in exc.__class__.__name__


def _humanize_auth_error(exc: Exception) -> str:
    if _is_invalid_code_error(exc):
        return "Неверный код Telegram. Проверь код и попробуй ещё раз."
    if _is_expired_code_error(exc):
        return "Код Telegram истёк. Запроси новый код и попробуй снова."
    if _is_invalid_password_error(exc):
        return "Неверный Telegram 2FA пароль. Попробуй ещё раз."
    if _is_password_needed_error(exc):
        return "Telegram требует пароль двухфакторной защиты."
    return str(exc).strip() or exc.__class__.__name__


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
    if "PasswordHashInvalid" in name:
        return f"INVALID_PASSWORD:{message}"
    if "ApiIdInvalid" in name:
        return f"INVALID_API:{message}"
    return f"GENERIC:{message}"


def _log_step(message: str) -> None:
    print(f"[AUTH] {message}", flush=True)
