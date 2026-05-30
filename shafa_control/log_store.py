from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_MAX_LOG_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5


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
        self.max_log_bytes = self._env_int(
            "SHAFA_MAX_LOG_FILE_BYTES",
            DEFAULT_MAX_LOG_BYTES,
            min_value=1024,
        )
        self.backup_count = self._env_int(
            "SHAFA_LOG_BACKUP_COUNT",
            DEFAULT_LOG_BACKUP_COUNT,
            min_value=1,
            max_value=20,
        )

    def append(self, record: LogRecord, account_log_file: Path | None = None) -> None:
        line = record.render()
        self._append_line(self.all_logs_file, line)
        if account_log_file is not None:
            self._append_line(account_log_file, line)
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

    def _append_line(self, path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._rotate_if_needed(path, incoming_bytes=len(line.encode("utf-8")) + 1)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")

    def _rotate_if_needed(self, path: Path, *, incoming_bytes: int) -> None:
        if self.max_log_bytes <= 0 or self.backup_count <= 0:
            return
        try:
            current_size = path.stat().st_size
        except OSError:
            return
        if current_size + max(int(incoming_bytes), 0) <= self.max_log_bytes:
            return

        oldest = path.with_name(f"{path.name}.{self.backup_count}")
        try:
            if oldest.exists():
                oldest.unlink()
            for index in range(self.backup_count - 1, 0, -1):
                source = path.with_name(f"{path.name}.{index}")
                if source.exists():
                    source.rename(path.with_name(f"{path.name}.{index + 1}"))
            path.rename(path.with_name(f"{path.name}.1"))
        except OSError:
            return

    @staticmethod
    def _env_int(
        name: str,
        default: int,
        *,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        raw = os.getenv(name, "").strip()
        if not raw:
            value = default
        else:
            try:
                value = int(raw)
            except ValueError:
                value = default
        if min_value is not None:
            value = max(value, min_value)
        if max_value is not None:
            value = min(value, max_value)
        return value

    @staticmethod
    def detect_level(message: str) -> str:
        lower = message.lower()
        if "[debug]" in lower or lower.startswith("debug "):
            return "DEBUG"
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
