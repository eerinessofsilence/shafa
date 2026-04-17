from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shafa_logic"))

from telegram_subscription import auth as telegram_auth


def _make_fake_client_class(require_password: bool = False, authorized: bool = True):
    class _FakeTelegramClient:
        def __init__(self, session_path: str, *_args, **_kwargs) -> None:
            self.session_path = Path(session_path)
            self.send_code_calls: list[str] = []
            self.sign_in_calls: list[tuple[str, str, str]] = []
            self.password_calls: list[str] = []
            self.require_password = require_password
            self.authorized = authorized
            self.connect_calls = 0
            self.disconnect_calls = 0
            self.enter_calls = 0

        async def __aenter__(self) -> "_FakeTelegramClient":
            self.enter_calls += 1
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def connect(self) -> None:
            self.connect_calls += 1

        async def disconnect(self) -> None:
            self.disconnect_calls += 1

        async def is_user_authorized(self) -> bool:
            return self.authorized

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
                self.session_path.write_bytes(b"SQLite format 3\x00payload")
                return
            assert phone is not None and code is not None and phone_code_hash is not None
            self.sign_in_calls.append((phone, code, phone_code_hash))
            if self.require_password:
                self.require_password = False

                class SessionPasswordNeededError(Exception):
                    pass

                raise SessionPasswordNeededError("password required")
            self.session_path.write_bytes(b"SQLite format 3\x00payload")

    return _FakeTelegramClient


def _make_invalid_code_client_class():
    class _FakeTelegramClient:
        def __init__(self, session_path: str, *_args, **_kwargs) -> None:
            self.session_path = Path(session_path)

        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        async def send_code_request(self, phone: str) -> SimpleNamespace:
            return SimpleNamespace(phone_code_hash="hash-123")

        async def sign_in(
            self,
            *,
            phone: str | None = None,
            code: str | None = None,
            phone_code_hash: str | None = None,
            password: str | None = None,
        ) -> None:
            class PhoneCodeInvalidError(Exception):
                pass

            raise PhoneCodeInvalidError("The phone code entered was invalid")

    return _FakeTelegramClient


class TelegramAuthenticationTest(unittest.IsolatedAsyncioTestCase):
    async def test_complete_login_creates_session_and_persists_state(self) -> None:
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
                patch.object(telegram_auth, "_get_telegram_client_cls", return_value=_make_fake_client_class()),
                patch.object(telegram_auth, "_persist_login_state", side_effect=_capture_persist),
            ):
                await telegram_auth._send_code("+380501112233")
                await telegram_auth._complete_login("+380501112233", "123456")
                self.assertTrue(session_path.exists())
                self.assertEqual(persisted_states[0]["current_auth_step"], "WAIT_PHONE")
                self.assertEqual(persisted_states[1]["current_auth_step"], "WAIT_CODE")
                self.assertEqual(persisted_states[-1]["current_auth_step"], "SUCCESS")
                self.assertEqual(persisted_states[-1]["session_path"], str(session_path))
                self.assertEqual(persisted_states[-1]["verification_code"], "123456")

    async def test_complete_login_switches_to_wait_password_and_submit_password_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "telegram_login_state.json"
            session_path = Path(temp_dir) / "telegram.session"

            with (
                patch.object(telegram_auth, "TELEGRAM_LOGIN_STATE_PATH", state_path),
                patch.object(telegram_auth, "TELEGRAM_SESSION_PATH", session_path),
                patch.object(telegram_auth, "_require_telegram_credentials", return_value=(1, "hash")),
                patch.object(telegram_auth, "_get_telegram_client_cls", return_value=_make_fake_client_class(require_password=True)),
            ):
                await telegram_auth._send_code("+380501112233")
                await telegram_auth._complete_login("+380501112233", "12345")

                state_after_code = telegram_auth._read_login_state()
                self.assertEqual(state_after_code["current_auth_step"], "WAIT_PASSWORD")
                self.assertEqual(state_after_code["verification_code"], "12345")
                self.assertEqual(state_after_code["session_path"], str(session_path))

                await telegram_auth._submit_password("secret-pass")
                final_state = telegram_auth._read_login_state()
                self.assertEqual(final_state["current_auth_step"], "SUCCESS")
                self.assertEqual(final_state["telegram_password"], "secret-pass")
                self.assertTrue(session_path.exists())

    async def test_complete_login_keeps_wait_code_for_invalid_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "telegram_login_state.json"
            session_path = Path(temp_dir) / "telegram.session"

            with (
                patch.object(telegram_auth, "TELEGRAM_LOGIN_STATE_PATH", state_path),
                patch.object(telegram_auth, "TELEGRAM_SESSION_PATH", session_path),
                patch.object(telegram_auth, "_require_telegram_credentials", return_value=(1, "hash")),
                patch.object(telegram_auth, "_get_telegram_client_cls", return_value=_make_invalid_code_client_class()),
            ):
                await telegram_auth._send_code("+380501112233")

                with self.assertRaisesRegex(RuntimeError, "Неверный код Telegram"):
                    await telegram_auth._complete_login("+380501112233", "12 345")

                state_after_failure = telegram_auth._read_login_state()
                self.assertEqual(state_after_failure["current_auth_step"], "WAIT_CODE")
                self.assertEqual(state_after_failure["phone_number"], "+380501112233")
                self.assertEqual(state_after_failure["verification_code"], "")
                self.assertEqual(state_after_failure["phone_code_hash"], "hash-123")

    async def test_send_code_reuses_session_path_in_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "telegram_login_state.json"
            session_path = Path(temp_dir) / "telegram.session"

            with (
                patch.object(telegram_auth, "TELEGRAM_LOGIN_STATE_PATH", state_path),
                patch.object(telegram_auth, "TELEGRAM_SESSION_PATH", session_path),
                patch.object(telegram_auth, "_require_telegram_credentials", return_value=(1, "hash")),
                patch.object(telegram_auth, "_get_telegram_client_cls", return_value=_make_fake_client_class()),
            ):
                await telegram_auth._send_code("+380501112233")
                first_state = telegram_auth._read_login_state()
                await telegram_auth._complete_login("+380501112233", "123456")
                second_state = telegram_auth._read_login_state()
                self.assertEqual(first_state["session_path"], str(session_path))
                self.assertEqual(second_state["session_path"], str(session_path))
                self.assertTrue(session_path.exists())

    async def test_send_code_uses_connect_instead_of_telethon_start_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "telegram_login_state.json"
            session_path = Path(temp_dir) / "telegram.session"
            created_clients: list[object] = []

            def _factory(*args, **kwargs):
                client = _make_fake_client_class()(*args, **kwargs)
                created_clients.append(client)
                return client

            with (
                patch.object(telegram_auth, "TELEGRAM_LOGIN_STATE_PATH", state_path),
                patch.object(telegram_auth, "TELEGRAM_SESSION_PATH", session_path),
                patch.object(telegram_auth, "_require_telegram_credentials", return_value=(1, "hash")),
                patch.object(telegram_auth, "_get_telegram_client_cls", return_value=_factory),
            ):
                await telegram_auth._send_code("+380501112233")

            self.assertEqual(len(created_clients), 1)
            client = created_clients[0]
            self.assertEqual(client.connect_calls, 1)
            self.assertEqual(client.disconnect_calls, 1)
            self.assertEqual(client.enter_calls, 0)

    async def test_session_status_returns_true_for_authorized_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "telegram_login_state.json"
            session_path = Path(temp_dir) / "telegram.session"
            session_path.write_bytes(b"SQLite format 3\x00payload")

            with (
                patch.object(telegram_auth, "TELEGRAM_LOGIN_STATE_PATH", state_path),
                patch.object(telegram_auth, "TELEGRAM_SESSION_PATH", session_path),
                patch.object(telegram_auth, "_require_telegram_credentials", return_value=(1, "hash")),
                patch.object(telegram_auth, "_get_telegram_client_cls", return_value=_make_fake_client_class()),
            ):
                result = await telegram_auth._session_status()
                persisted_state = telegram_auth._read_login_state()

            self.assertTrue(result)
            self.assertEqual(persisted_state["current_auth_step"], "SUCCESS")

    async def test_session_status_returns_false_for_unauthorized_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "telegram_login_state.json"
            session_path = Path(temp_dir) / "telegram.session"
            session_path.write_bytes(b"SQLite format 3\x00payload")

            with (
                patch.object(telegram_auth, "TELEGRAM_LOGIN_STATE_PATH", state_path),
                patch.object(telegram_auth, "TELEGRAM_SESSION_PATH", session_path),
                patch.object(telegram_auth, "_require_telegram_credentials", return_value=(1, "hash")),
                patch.object(
                    telegram_auth,
                    "_get_telegram_client_cls",
                    return_value=_make_fake_client_class(authorized=False),
                ),
            ):
                result = await telegram_auth._session_status()

            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
