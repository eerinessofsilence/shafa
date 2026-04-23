from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from shafa_control import AccountSessionStore
from telegram_accounts_api.dependencies import get_account_log_store, get_account_service, get_auth_service
from telegram_accounts_api.main import app
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.auth_service import AccountAuthService
from telegram_accounts_api.utils.account_logging import AccountLogStore, log, set_account_log_store
from telegram_accounts_api.utils.storage import JsonListStorage


class AccountLogsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.accounts_file = self.base_dir / "accounts_state.json"
        self.accounts_dir = self.base_dir / "accounts"
        self.accounts_file.write_text(
            json.dumps(
                [
                    {
                        "id": "acc-1",
                        "name": "Alpha",
                        "phone_number": "",
                        "path": "/tmp/project",
                        "branch": "main",
                        "timer_minutes": 5,
                        "channel_links": [],
                        "status": "stopped",
                        "last_run": None,
                        "errors": 0,
                    },
                    {
                        "id": "acc-2",
                        "name": "Beta",
                        "phone_number": "",
                        "path": "/tmp/project",
                        "branch": "main",
                        "timer_minutes": 5,
                        "channel_links": [],
                        "status": "stopped",
                        "last_run": None,
                        "errors": 0,
                    },
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.account_service = AccountService(
            storage=JsonListStorage(self.accounts_file),
            accounts_dir=self.accounts_dir,
        )
        self.log_store = AccountLogStore(max_entries_per_account=3)
        self.previous_store = set_account_log_store(self.log_store)
        store = AccountSessionStore(
            base_dir=self.base_dir,
            accounts_dir=self.accounts_dir,
            legacy_state_file=self.accounts_file,
        )
        self.auth_service = AccountAuthService(
            account_service=self.account_service,
            store=store,
            shafa_login_launcher=lambda _account, _args: None,
        )
        app.dependency_overrides[get_account_service] = lambda: self.account_service
        app.dependency_overrides[get_auth_service] = lambda: self.auth_service
        app.dependency_overrides[get_account_log_store] = lambda: self.log_store
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(lambda: set_account_log_store(AccountLogStore()))
        self.client = TestClient(app)
        self.local_tz = datetime.now().astimezone().tzinfo or UTC

    def test_get_account_logs_returns_only_requested_account(self) -> None:
        log("acc-1", "INFO", "Login started")
        log("acc-1", "ERROR", "password=secret should be hidden")
        log("acc-2", "INFO", "Other account event")

        response = self.client.get("/accounts/acc-1/logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["account_id"] for item in payload], ["acc-1", "acc-1"])
        self.assertEqual(payload[-1]["level"], "ERROR")
        self.assertIn("password=[REDACTED]", payload[-1]["message"])

    def test_get_account_logs_supports_level_limit_and_since_index(self) -> None:
        log("acc-1", "INFO", "one")
        log("acc-1", "ERROR", "two")
        log("acc-1", "ERROR", "three")
        log("acc-1", "ERROR", "four")

        response = self.client.get("/accounts/acc-1/logs", params={"level": "ERROR", "limit": 2, "since": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["message"] for item in payload], ["three", "four"])
        self.assertEqual([item["index"] for item in payload], [2, 3])

    def test_get_account_logs_reads_history_from_account_app_log(self) -> None:
        account_log = self.accounts_dir / "acc-1" / "logs" / "app.log"
        account_log.parent.mkdir(parents=True, exist_ok=True)
        account_log.write_text(
            "\n".join(
                [
                    "[2026-04-18 13:54:09] [INFO] [Alpha] [RUN] started pid=3544",
                    "[2026-04-18 13:54:13] [SUCCESS] [Alpha] Товар создан успешно. ID: 42.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.get("/accounts/acc-1/logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["message"] for item in payload],
            ["Процесс запущен (PID 3544).", "Товар создан успешно. ID: 42."],
        )
        self.assertEqual([item["level"] for item in payload], ["INFO", "SUCCESS"])

    def test_get_account_logs_merges_file_history_with_live_runtime_entries(self) -> None:
        account_log = self.accounts_dir / "acc-1" / "logs" / "app.log"
        account_log.parent.mkdir(parents=True, exist_ok=True)
        account_log.write_text(
            "[2026-04-18 13:54:09] [INFO] [Alpha] [RUN] started pid=3544\n",
            encoding="utf-8",
        )
        self.log_store.append(
            "acc-1",
            "ERROR",
            "Не удалось обработать товар.",
            timestamp=datetime(2026, 4, 18, 13, 54, 13, tzinfo=self.local_tz),
        )

        response = self.client.get("/accounts/acc-1/logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["message"] for item in payload],
            ["Процесс запущен (PID 3544).", "Не удалось обработать товар."],
        )

    def test_get_account_logs_dedupes_identical_file_and_runtime_entries(self) -> None:
        account_log = self.accounts_dir / "acc-1" / "logs" / "app.log"
        account_log.parent.mkdir(parents=True, exist_ok=True)
        account_log.write_text(
            "[2026-04-18 13:54:09] [INFO] [Alpha] [RUN] started pid=3544\n",
            encoding="utf-8",
        )
        self.log_store.append(
            "acc-1",
            "INFO",
            "[RUN] started pid=3544",
            timestamp=datetime(2026, 4, 18, 13, 54, 9, tzinfo=self.local_tz),
        )

        response = self.client.get("/accounts/acc-1/logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["message"] for item in payload],
            ["Процесс запущен (PID 3544)."],
        )

    def test_account_log_store_normalizes_inline_levels(self) -> None:
        entry = self.log_store.append(
            "acc-1",
            "WARN",
            "[WARN] API отклонил размер. Обновляю размеры и повторяю создание товара...",
        )

        self.assertEqual(entry.level, "WARNING")
        self.assertEqual(
            entry.message,
            "Размер отклонён API, обновляю размеры и повторяю создание.",
        )

    def test_account_log_store_translates_system_messages(self) -> None:
        store = AccountLogStore(max_entries_per_account=10)

        store.append("acc-1", "INFO", "[RUN] started pid=3544")
        store.append("acc-1", "INFO", "Account settings updated.")
        store.append(
            "acc-1",
            "INFO",
            "Telegram verification code requested.",
        )
        store.append("acc-1", "INFO", "Shafa session saved.")

        entries = store.list_entries("acc-1", limit=10)

        self.assertEqual(
            [entry.message for entry in entries],
            [
                "Процесс запущен (PID 3544).",
                "Настройки аккаунта обновлены.",
                "Код Telegram запрошен.",
                "Сессия Shafa сохранена.",
            ],
        )

    def test_account_log_store_translates_business_messages(self) -> None:
        store = AccountLogStore(max_entries_per_account=10)

        store.append("acc-1", "INFO", "Товар для создания: Nike Air Force 1.")
        store.append("acc-1", "INFO", "Цена товара (с наценкой 400): 2400.")
        store.append("acc-1", "INFO", "Скачано фото: 10.")
        store.append(
            "acc-1",
            "INFO",
            "Загружены бренды для zhenskaya-obuv/krossovki: 500.",
        )
        store.append(
            "acc-1",
            "SUCCESS",
            "Товар создан успешно. Имя товара: Nike Air Force 1. ID: 42. Фото: 10.",
        )

        entries = store.list_entries("acc-1", limit=10)

        self.assertEqual(
            [entry.message for entry in entries],
            [
                "Готовлю товар: «Nike Air Force 1».",
                "Цена рассчитана: 2400 (наценка 400).",
                "Фото скачаны: 10.",
                "Бренды обновлены для zhenskaya-obuv/krossovki: 500.",
                "Товар создан успешно: «Nike Air Force 1», ID 42, фото 10.",
            ],
        )

    def test_get_account_logs_normalizes_noise_and_structured_errors(self) -> None:
        account_log = self.accounts_dir / "acc-1" / "logs" / "app.log"
        account_log.parent.mkdir(parents=True, exist_ok=True)
        account_log.write_text(
            "\n".join(
                [
                    "[2026-04-18 13:54:09] [WARN] [Alpha] [WARN] API отклонил размер. Обновляю размеры и повторяю создание товара...",
                    "[2026-04-18 13:54:10] [INFO] [Alpha] __________________________________",
                    "[2026-04-18 13:54:11] [INFO] [Alpha] Размеры товара: {\"catalog\": \"zhenskaya-obuv/krossovki\", \"raw_size\": \"36\", \"raw_additional_sizes\": [\"37\", \"38\"], \"expanded_sizes\": [\"36\", \"37\", \"38\"], \"preferred_size_system\": \"eu\", \"resolved_size\": 1196, \"resolved_additional_sizes\": [1198, 1200]}",
                    "[2026-04-18 13:54:12] [ERROR] [Alpha] [{'field': 'size', 'messages': [{'code': 'invalid', 'message': 'Потрібно вибрати розмір речі', '__typename': 'GraphErrorMessage'}], '__typename': 'GraphResponseError'}]",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.get("/accounts/acc-1/logs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [item["level"] for item in payload],
            ["WARNING", "INFO", "ERROR"],
        )
        self.assertEqual(
            payload[0]["message"],
            "Размер отклонён API, обновляю размеры и повторяю создание.",
        )
        self.assertEqual(
            payload[1]["message"],
            "Размер: 36. Доп. размеры: 37, 38. Каталог: zhenskaya-obuv/krossovki. Система: EU. Размер сопоставлен, доп. размеров: 2.",
        )
        self.assertEqual(
            payload[2]["message"],
            "Shafa API: размер: Потрібно вибрати розмір речі",
        )

    def test_websocket_streams_new_account_logs(self) -> None:
        with self.client.websocket_connect("/ws/logs/acc-1") as websocket:
            log("acc-1", "INFO", "Browser login started")
            message = websocket.receive_json()

        self.assertEqual(message["account_id"], "acc-1")
        self.assertEqual(message["level"], "INFO")
        self.assertEqual(message["message"], "Browser login started")

    def test_invalid_since_returns_bad_request(self) -> None:
        response = self.client.get("/accounts/acc-1/logs", params={"since": "not-a-timestamp"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("since", response.json()["detail"])

    def test_clear_logs_removes_runtime_and_account_log_files(self) -> None:
        runtime_log = self.base_dir / "runtime" / "logs" / "all.log"
        runtime_log.parent.mkdir(parents=True, exist_ok=True)
        runtime_log.write_text("[2026-04-18 13:54:09] [INFO] [Alpha] runtime\n", encoding="utf-8")

        account_log = self.accounts_dir / "acc-1" / "logs" / "app.log"
        account_log.parent.mkdir(parents=True, exist_ok=True)
        account_log.write_text(
            "[2026-04-18 13:54:09] [INFO] [Alpha] account\n",
            encoding="utf-8",
        )
        self.log_store.append("acc-1", "INFO", "live entry")

        response = self.client.post("/logs/clear")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Логи очищены", response.json()["detail"])
        self.assertFalse(runtime_log.exists())
        self.assertFalse(account_log.exists())
        self.assertEqual(self.log_store.list_entries("acc-1"), [])


if __name__ == "__main__":
    unittest.main()
