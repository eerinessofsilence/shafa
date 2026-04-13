from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Optional

from telegram_channels import sanitize_channel_links


@dataclass
class Account:
    id: str
    name: str
    path: str
    phone_number: str = ""
    branch: str = "main"
    open_browser: bool = False
    timer_minutes: int = 5
    channel_links: list[str] = field(default_factory=list)
    status: str = "stopped"
    last_run: str = "—"
    errors: int = 0
    process: Optional[subprocess.Popen] = None

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "phone_number": self.phone_number,
            "branch": self.branch,
            "open_browser": self.open_browser,
            "timer_minutes": self.timer_minutes,
            "channel_links": self.channel_links,
            "status": self.status,
            "last_run": self.last_run,
            "errors": self.errors,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Account":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=data.get("name", "unknown"),
            path=data.get("path", ""),
            phone_number=str(data.get("phone_number") or ""),
            branch=data.get("branch", "main"),
            open_browser=bool(data.get("open_browser", False)),
            timer_minutes=int(data.get("timer_minutes", 5)),
            channel_links=sanitize_channel_links(data.get("channel_links", [])),
            status=data.get("status", "stopped"),
            last_run=data.get("last_run", "—"),
            errors=int(data.get("errors", 0)),
        )
