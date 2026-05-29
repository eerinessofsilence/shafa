from __future__ import annotations

import json
import os
import random
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from shafa_control import LogRecord, project_main_path, resolve_project_dir

from telegram_accounts_api.services.account_service import AccountService


class OutdatedProductCleanupService:
    def __init__(self, account_service: AccountService) -> None:
        self.account_service = account_service
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._run_lock = threading.Lock()

    def start(self) -> None:
        if self._is_disabled():
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker,
            name="outdated-products-cleanup",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def run_once(self) -> dict[str, int | float]:
        if not self._run_lock.acquire(blocking=False):
            return {
                "accounts": 0,
                "checked": 0,
                "deactivated": 0,
                "failed": 0,
                "execution_time_seconds": 0.0,
            }
        started_at = time.perf_counter()
        try:
            accounts = self.account_service.load_runtime_accounts()
            totals = {
                "accounts": len(accounts),
                "checked": 0,
                "deactivated": 0,
                "failed": 0,
            }
            if not accounts:
                self._append_global_log("cleanup worker found no configured accounts")
                totals["execution_time_seconds"] = round(
                    time.perf_counter() - started_at,
                    3,
                )
                return totals

            with ThreadPoolExecutor(max_workers=self._max_workers()) as executor:
                futures = [
                    executor.submit(self._cleanup_account, account)
                    for account in accounts
                ]
                for future in as_completed(futures):
                    try:
                        result = future.result()
                    except Exception:
                        totals["failed"] += 1
                        continue
                    totals["checked"] += int(result.get("checked") or 0)
                    totals["deactivated"] += int(result.get("deactivated") or 0)
                    totals["failed"] += int(result.get("failed") or 0)

            totals["execution_time_seconds"] = round(
                time.perf_counter() - started_at,
                3,
            )
            return totals
        finally:
            self._run_lock.release()

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            wait_seconds = self._next_wait_seconds()
            if self._stop_event.wait(wait_seconds):
                return
            self.run_once()

    @staticmethod
    def _is_disabled() -> bool:
        raw = os.getenv("SHAFA_DISABLE_OUTDATED_PRODUCT_CLEANUP", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _interval_range_seconds() -> tuple[int, int]:
        fixed_interval = os.getenv(
            "SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_INTERVAL_SECONDS",
            "",
        ).strip()
        if fixed_interval:
            try:
                value = int(fixed_interval)
            except ValueError:
                return 60, 180
            value = min(max(value, 60), 86400)
            return value, value

        min_raw = os.getenv(
            "SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_MIN_INTERVAL_SECONDS",
            "",
        ).strip()
        max_raw = os.getenv(
            "SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_MAX_INTERVAL_SECONDS",
            "",
        ).strip()
        try:
            min_value = int(min_raw) if min_raw else 60
        except ValueError:
            min_value = 60
        try:
            max_value = int(max_raw) if max_raw else 180
        except ValueError:
            max_value = 180
        min_value = min(max(min_value, 60), 86400)
        max_value = min(max(max_value, 60), 86400)
        if max_value < min_value:
            max_value = min_value
        return min_value, max_value

    @classmethod
    def _next_wait_seconds(cls) -> float:
        min_seconds, max_seconds = cls._interval_range_seconds()
        if min_seconds == max_seconds:
            return float(min_seconds)
        return random.uniform(min_seconds, max_seconds)

    @staticmethod
    def _max_workers() -> int:
        raw = os.getenv("SHAFA_OUTDATED_PRODUCT_CLEANUP_MAX_WORKERS", "").strip()
        if not raw:
            return 3
        try:
            value = int(raw)
        except ValueError:
            return 3
        return min(max(value, 1), 8)

    @staticmethod
    def _timeout_seconds() -> float:
        raw = os.getenv("SHAFA_OUTDATED_PRODUCT_CLEANUP_TIMEOUT_SECONDS", "").strip()
        if not raw:
            return 900.0
        try:
            value = float(raw)
        except ValueError:
            return 900.0
        return min(max(value, 30.0), 3600.0)

    @staticmethod
    def _cleanup_limit() -> int:
        raw = os.getenv("SHAFA_OUTDATED_PRODUCT_CLEANUP_LIMIT", "").strip()
        if not raw:
            return 0
        try:
            return int(raw)
        except ValueError:
            return 0

    @staticmethod
    def _cleanup_age_days() -> int | None:
        raw = os.getenv("SHAFA_TELEGRAM_PRODUCT_MAX_AGE_DAYS", "").strip()
        if not raw:
            return None
        try:
            return max(int(raw), 1)
        except ValueError:
            return None

    def _cleanup_account(self, account) -> dict[str, Any]:
        started_at = time.perf_counter()
        account_id = str(account.id or "").strip()
        account_name = str(account.name or account_id or "unknown").strip()
        if not account_id:
            self._append_global_log("cleanup skipped account with empty account_id")
            return {"checked": 0, "deactivated": 0, "failed": 1}
        self._append_log(
            account,
            "cleanup worker account selected "
            f"account={account_name}. account_id={account_id}. path={account.path}.",
        )
        if self.account_service._active_process(account_id) is not None:
            self._append_log(
                account,
                "cleanup skipped detached run because account process is active; "
                "in-process deactivator is responsible for this account. "
                f"account={account_name}. account_id={account_id}.",
            )
            return {"checked": 0, "deactivated": 0, "failed": 0}
        if not self.account_service.session_store.is_valid_shafa_session(account):
            age_days = self._cleanup_age_days() or 183
            self._append_log(
                account,
                "cleanup cycle start "
                f"account={account.name}. account_id={account.id}. "
                f"threshold_days={age_days}. limit=all. dry_run=False.",
            )
            self._append_log(
                account,
                f'{account.name} Product="unknown" message_id=unknown '
                'telegram_found=false telegram_channel="unknown" '
                "message_date=unknown age=unknown operation=deactivate "
                'action=SKIPPED reason="missing Shafa session"',
            )
            self._append_cycle_end(account, started_at, checked=0, deactivated=0)
            return {"checked": 0, "deactivated": 0, "failed": 0}

        project_path = resolve_project_dir(Path(account.path).expanduser())
        if not project_main_path(project_path).is_file():
            age_days = self._cleanup_age_days() or 183
            self._append_log(
                account,
                "cleanup cycle start "
                f"account={account.name}. account_id={account.id}. "
                f"threshold_days={age_days}. limit=all. dry_run=False.",
            )
            self._append_log(
                account,
                "cleanup cycle error "
                f"account={account.name}. account_id={account.id}. "
                f"action=ERROR reason=\"main.py not found: {project_path}\"",
            )
            self._append_cycle_end(account, started_at, checked=0, deactivated=0)
            return {"checked": 0, "deactivated": 0, "failed": 1}

        env = self.account_service.runtime.account_env(account)
        self._append_log(
            account,
            "cleanup launching detached deactivation "
            f"account={account.name}. account_id={account.id}. "
            f"cwd={project_path}. db_path={env.get('SHAFA_DB_PATH')}. "
            f"telegram_db_path={env.get('SHAFA_SHARED_TELEGRAM_DB_PATH')}.",
        )
        if account.channel_links:
            channels_file = self.account_service.runtime.export_channel_runtime_config(
                account
            )
            env["SHAFA_TELEGRAM_CHANNEL_LINKS_FILE"] = str(channels_file)
        command = [
            self.account_service.runtime.account_python(account),
            "main.py",
            "--deactivate-old-products-once",
            "--old-products-limit",
            str(self._cleanup_limit()),
            "--old-products-sleep-seconds",
            "0",
        ]
        age_days = self._cleanup_age_days()
        if age_days is not None:
            command.extend(["--old-products-age-days", str(age_days)])

        try:
            completed = subprocess.run(
                command,
                cwd=str(project_path),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout_seconds(),
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            self._append_log(
                account,
                "cleanup cycle error "
                f"account={account.name}. account_id={account.id}. "
                f'action=ERROR reason="timeout after {exc.timeout}s"',
            )
            self._append_cycle_end(account, started_at, checked=0, deactivated=0)
            return {"checked": 0, "deactivated": 0, "failed": 1}
        except OSError as exc:
            self._append_log(
                account,
                "cleanup cycle error "
                f"account={account.name}. account_id={account.id}. "
                f'action=ERROR reason="{exc}"',
            )
            self._append_cycle_end(account, started_at, checked=0, deactivated=0)
            return {"checked": 0, "deactivated": 0, "failed": 1}

        summary: dict[str, Any] = {"checked": 0, "deactivated": 0, "failed": 0}
        for raw_line in (completed.stdout or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            self._append_log(account, line)
            parsed = self._parse_summary(line)
            if parsed is not None:
                summary = parsed

        if completed.returncode != 0:
            self._append_log(
                account,
                "cleanup cycle error "
                f"account={account.name}. account_id={account.id}. "
                f'action=ERROR reason="process exited with code {completed.returncode}"',
            )
            summary["failed"] = int(summary.get("failed") or 0) + 1
            self._append_cycle_end(
                account,
                started_at,
                checked=int(summary.get("checked") or 0),
                deactivated=int(summary.get("deactivated") or 0),
            )
        return summary

    def _append_global_log(self, message: str) -> None:
        try:
            self.account_service.log_store.append(
                LogRecord(
                    timestamp=datetime.now(),
                    message=message,
                    level="INFO",
                    account_id="system",
                    account_name="system",
                )
            )
        except Exception:
            pass

    def _append_log(self, account, message: str) -> None:
        try:
            self.account_service._append_log(account, message)
        except Exception:
            pass

    def _append_cycle_end(
        self,
        account,
        started_at: float,
        *,
        checked: int,
        deactivated: int,
    ) -> None:
        execution_time = round(time.perf_counter() - started_at, 3)
        self._append_log(
            account,
            "cleanup cycle end "
            f"account={account.name}. account_id={account.id}. "
            f"total_checked_products={checked}. "
            f"total_deactivated_products={deactivated}. "
            f"execution_time={execution_time}s.",
        )

    @staticmethod
    def _parse_summary(line: str) -> dict[str, Any] | None:
        if not line.startswith("{") or not line.endswith("}"):
            return None
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload
