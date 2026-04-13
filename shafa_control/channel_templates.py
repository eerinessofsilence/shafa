from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from telegram_channels import sanitize_channel_links


@dataclass
class ChannelTemplate:
    name: str
    links: list[str]


class ChannelTemplateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def list_templates(self) -> list[ChannelTemplate]:
        payload = self._read_payload()
        return [
            ChannelTemplate(name=item["name"], links=sanitize_channel_links(item.get("links", [])))
            for item in payload
            if item.get("name")
        ]

    def save_template(self, name: str, links: list[str]) -> ChannelTemplate:
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Template name is required.")
        clean_links = sanitize_channel_links(links)
        if not clean_links:
            raise ValueError("Template must contain at least one Telegram channel.")
        templates = self._read_payload()
        updated = [item for item in templates if item.get("name") != clean_name]
        updated.append({"name": clean_name, "links": clean_links})
        self._write_payload(updated)
        return ChannelTemplate(name=clean_name, links=clean_links)

    def get_template(self, name: str) -> ChannelTemplate:
        clean_name = str(name).strip()
        for template in self.list_templates():
            if template.name == clean_name:
                return template
        raise KeyError(clean_name)

    def delete_template(self, name: str) -> None:
        clean_name = str(name).strip()
        templates = [item for item in self._read_payload() if item.get("name") != clean_name]
        self._write_payload(templates)

    def _read_payload(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def _write_payload(self, payload: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
