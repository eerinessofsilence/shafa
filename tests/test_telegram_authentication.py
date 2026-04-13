from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telegram_subscription import auth as telegram_auth


class _FakeTelegramClient:
    require_password = False

    def __init__(self) -> None:
        self.send_code_calls: list[str] = []
        self.sign_in_calls: list[tuple[str, str, str]] = []
        self.password_calls: list[str] = []

    async def __aenter__(self) -> "_FakeTelegramClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def send_code_request(self, phone: str) -> SimpleNamespace:
        self.send_code_calls.append(phone)
        return SimpleNamespace(phone_code_hash="hash-123")

    async def sign_in(
        self,
        *,
        phone: str | None = None,
        code: str | None = None,
        phone_code_hash: str | None = None,
        password: str | None = None,
    ) -> None:
        if password is not None:
            self.password_calls.append(password)
            return
        assert phone is not None and code is not None and phone_code_hash is not None
        self.sign_in_calls.append((phone, code, phone_code_hash))
        if self.require_password:
            self.require_password = False

            class SessionPasswordNeededError(Exception):
                pass

            raise SessionPasswordNeededError("password required")


class TelegramAuthenticationTest(unittest.IsolatedAsyncioTestCase):
    async def test_interactive_login_uses_persisted_phone_and_code(self) -> None:
        fake_client = _FakeTelegramClient()
        persisted_states: list[dict] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "telegram_login_state.json"
            session_path = Path(temp_dir) / "telegram.session"

            original_persist = telegram_auth._persist_login_state

            def _capture_persist(**kwargs) -> None:
                original_persist(**kwargs)
                persisted_states.append(telegram_auth._read_login_state())

            with (
                patch.object(telegram_auth, "TELEGRAM_LOGIN_STATE_PATH", state_path),
                patch.object(telegram_auth, "TELEGRAM_SESSION_PATH", session_path),
                patch.object(telegram_auth, "_require_telegram_credentials", return_value=(1, "hash")),
                patch.object(telegram_auth, "_get_telegram_client_cls", return_value=lambda *_args, **_kwargs: fake_client),
                patch.object(telegram_auth, "_await_phone_input", return_value="+380501112233"),
                patch.object(telegram_auth, "_await_confirmed_code", return_value="123456"),
                patch.object(telegram_auth, "_persist_login_state", side_effect=_capture_persist),
            ):
                await telegram_auth._interactive_login()

        self.assertEqual(fake_client.send_code_calls, ["+380501112233"])
        self.assertEqual(fake_client.sign_in_calls, [("+380501112233", "123456", "hash-123")])
        self.assertTrue(any(state.get("phone_number") == "+380501112233" for state in persisted_states))
        self.assertTrue(any(state.get("verification_code") == "123456" for state in persisted_states))
        self.assertEqual(persisted_states[-1]["current_auth_step"], "SUCCESS")

    async def test_interactive_login_handles_password_prompt(self) -> None:
        fake_client = _FakeTelegramClient()
        fake_client.require_password = True

        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "telegram_login_state.json"
            session_path = Path(temp_dir) / "telegram.session"

            with (
                patch.object(telegram_auth, "TELEGRAM_LOGIN_STATE_PATH", state_path),
                patch.object(telegram_auth, "TELEGRAM_SESSION_PATH", session_path),
                patch.object(telegram_auth, "_require_telegram_credentials", return_value=(1, "hash")),
                patch.object(telegram_auth, "_get_telegram_client_cls", return_value=lambda *_args, **_kwargs: fake_client),
                patch.object(telegram_auth, "_await_phone_input", return_value="+380501112233"),
                patch.object(telegram_auth, "_await_confirmed_code", return_value="12345"),
                patch.object(telegram_auth, "_await_password_input", return_value="secret-pass"),
            ):
                await telegram_auth._interactive_login()

        self.assertEqual(fake_client.send_code_calls, ["+380501112233"])
        self.assertEqual(fake_client.sign_in_calls, [("+380501112233", "12345", "hash-123")])
        self.assertEqual(fake_client.password_calls, ["secret-pass"])


if __name__ == "__main__":
    unittest.main()
