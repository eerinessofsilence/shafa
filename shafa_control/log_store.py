from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class LogRecord:
    timestamp: datetime
    message: str
    level: str
    account_id: str | None = None
    account_name: str | None = None

    def render(self) -> str:
        prefix = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        account = f" [{self.account_name}]" if self.account_name else ""
        return f"[{prefix}] [{self.level}]{account} {self.message}"


class LogStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.all_logs_file = self.root_dir / "all.log"
        self.records: list[LogRecord] = []

    def append(self, record: LogRecord, account_log_file: Path | None = None) -> None:
        line = record.render()
        with self.all_logs_file.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
        if account_log_file is not None:
            account_log_file.parent.mkdir(parents=True, exist_ok=True)
            with account_log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
        self.records.append(record)

    def filtered(
        self,
        account_id: str | None = None,
        level: str | None = None,
    ) -> list[LogRecord]:
        target_level = (level or "").upper()
        result = self.records
        if account_id:
            result = [record for record in result if record.account_id == account_id]
        if target_level and target_level != "ALL":
            result = [record for record in result if record.level == target_level]
        return result

    def replace(self, records: Iterable[LogRecord]) -> None:
        self.records = list(records)

    @staticmethod
    def detect_level(message: str) -> str:
        lower = message.lower()
        if any(
            token in lower
            for token in (
                "[error]",
                "[warn]",
                "[warning]",
                " warning",
                " warn",
                " error",
                "ошибка",
                "не удалось",
                "failed",
            )
        ):
            if "[warn]" in lower or "[warning]" in lower or " warning" in lower or " warn" in lower:
                return "WARNING"
            return "ERROR"
        if any(
            token in lower
            for token in ("[ok]", "[success]", "success", "успеш", "saved")
        ):
            return "SUCCESS"
        return "INFO"
