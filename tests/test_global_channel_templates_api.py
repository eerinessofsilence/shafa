from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from telegram_accounts_api.dependencies import get_channel_template_service, get_telegram_service
from telegram_accounts_api.main import app
from telegram_accounts_api.models.channel_template import ResolvedTelegramChannel
from telegram_accounts_api.services.account_service import AccountService
from telegram_accounts_api.services.channel_template_service import ChannelTemplateService
from telegram_accounts_api.utils.storage import JsonListStorage


class GlobalChannelTemplatesApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base_dir = Path(self.temp_dir.name)
        self.templates_file = self.base_dir / "telegram_templates" / "channel_templates.json"
        self.accounts_file = self.base_dir / "accounts_state.json"
        self.accounts_file.write_text("[]", encoding="utf-8")
        self.service = ChannelTemplateService(
            storage=JsonListStorage(self.templates_file),
            account_service=AccountService(
                storage=JsonListStorage(self.accounts_file),
                accounts_dir=self.base_dir / "accounts",
            ),
        )
        app.dependency_overrides[get_channel_template_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def _write_accounts(self, payload: list[dict]) -> None:
        self.accounts_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_templates(self) -> list[dict]:
        return json.loads(self.templates_file.read_text(encoding="utf-8"))

    def test_global_channel_template_crud(self) -> None:
        create_response = self.client.post(
            "/channel-templates",
            json={
                "name": "Drop clothes",
                "type": "clothes",
                "links": ["t.me/one", "https://t.me/two"],
            },
        )

        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertIsNone(created["account_id"])
        self.assertEqual(created["type"], "clothes")
        self.assertEqual(created["links"], ["https://t.me/one", "https://t.me/two"])

        list_response = self.client.get("/channel-templates?type=clothes")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["id"] for item in list_response.json()], [created["id"]])

        update_response = self.client.put(
            f"/channel-templates/{created['id']}",
            json={
                "name": "Drop shoes",
                "type": "shoes",
                "links": ["t.me/shoes"],
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated = update_response.json()
        self.assertEqual(updated["name"], "Drop shoes")
        self.assertEqual(updated["type"], "shoes")
        self.assertEqual(updated["links"], ["https://t.me/shoes"])

        empty_clothes = self.client.get("/channel-templates?type=clothes")
        self.assertEqual(empty_clothes.status_code, 200)
        self.assertEqual(empty_clothes.json(), [])

        delete_response = self.client.delete(f"/channel-templates/{created['id']}")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(self.client.get("/channel-templates").json(), [])

    def test_duplicate_names_are_scoped_by_template_type(self) -> None:
        first = self.client.post(
            "/channel-templates",
            json={"name": "Main", "type": "clothes", "links": ["t.me/clothes"]},
        )
        second = self.client.post(
            "/channel-templates",
            json={"name": "Main", "type": "shoes", "links": ["t.me/shoes"]},
        )
        duplicate = self.client.post(
            "/channel-templates",
            json={"name": "Main", "type": "clothes", "links": ["t.me/other"]},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(duplicate.status_code, 400)

    def test_legacy_type_wrapped_template_is_migrated(self) -> None:
        self.templates_file.parent.mkdir(parents=True, exist_ok=True)
        self.templates_file.write_text(
            json.dumps(
                [
                    {
                        "clothes": {
                            "id": "tpl-legacy",
                            "links": ["t.me/legacy"],
                            "created_at": "2026-01-01T00:00:00+00:00",
                            "updated_at": "2026-01-01T00:00:00+00:00",
                        }
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/channel-templates")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()[0] | {"created_at": "", "updated_at": ""},
            {
                "id": "tpl-legacy",
                "account_id": None,
                "name": "clothes",
                "type": "clothes",
                "links": ["https://t.me/legacy"],
                "resolved_channels": [],
                "created_at": "",
                "updated_at": "",
            },
        )
        self.assertEqual(self._read_templates()[0]["name"], "clothes")

    def test_resolve_global_channel_uses_connected_account(self) -> None:
        self._write_accounts(
            [
                {
                    "id": "acc-1",
                    "name": "Account",
                    "phone_number": "",
                    "path": "/tmp/project",
                    "branch": "main",
                    "timer_minutes": 5,
                    "channel_links": [],
                    "status": "stopped",
                    "last_run": None,
                    "errors": 0,
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        )
        account_dir = self.base_dir / "accounts" / "acc-1"
        account_dir.mkdir(parents=True, exist_ok=True)
        (account_dir / "telegram.session").write_bytes(b"SQLite format 3\x00payload")
        captured: list[tuple[str, list[str]]] = []

        class FakeTelegramService:
            async def resolve_channel_links(self, account_id: str, links: list[str]):
                captured.append((account_id, links))
                return [
                    ResolvedTelegramChannel(
                        channel_id=-1001,
                        title="Valid channel",
                        alias="main",
                    )
                ]

        app.dependency_overrides[get_telegram_service] = lambda: FakeTelegramService()

        response = self.client.post(
            "/channel-templates/resolve",
            json={"links": ["t.me/valid"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured, [("acc-1", ["https://t.me/valid"])])
        self.assertEqual(response.json()[0]["title"], "Valid channel")

    def test_resolve_global_channel_requires_connected_account(self) -> None:
        response = self.client.post(
            "/channel-templates/resolve",
            json={"links": ["t.me/missing"]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("подключите Telegram", response.json()["detail"])
