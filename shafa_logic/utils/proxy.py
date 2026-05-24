from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib import request as urllib_request
from urllib.parse import quote

PROXY_DB_ENV = "SHAFA_PROXY_DB_PATH"
PROXY_CONFIG_ENV = "SHAFA_PROXY_CONFIG_PATH"
PROXY_STATUS_UNKNOWN = "unknown"
PROXY_STATUS_HEALTHY = "healthy"
PROXY_STATUS_DEGRADED = "degraded"
PROXY_STATUS_FAILING = "failing"
PROXY_STATUS_DISABLED = "disabled"
SUPPORTED_PROXY_SCHEMES = ("http", "https", "socks5")
HTTP_PROXY_SCHEMES = ("http", "https")
TELEGRAM_PROXY_SCHEMES = ("http", "socks5")
DEFAULT_PROXY_MAX_ACCOUNTS = 3
_URLOPENER_CACHE: dict[str, urllib_request.OpenerDirector] = {}
_URLOPENER_LOCK = threading.RLock()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_proxy_scheme(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in SUPPORTED_PROXY_SCHEMES:
        raise ValueError(f"Unsupported proxy scheme: {value}")
    return normalized


def normalize_proxy_identifier(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


@dataclass(frozen=True)
class RuntimeProxyConfig:
    proxy_id: str
    name: str
    scheme: str
    host: str
    port: int
    username: str = ""
    password: str = ""
    enabled: bool = True
    max_accounts: int = DEFAULT_PROXY_MAX_ACCOUNTS

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RuntimeProxyConfig":
        host = str(payload.get("host") or "").strip()
        if not host:
            raise ValueError("Proxy host is required")
        port = int(payload.get("port") or 0)
        if port <= 0 or port > 65535:
            raise ValueError("Proxy port must be between 1 and 65535")
        return cls(
            proxy_id=str(payload.get("id") or payload.get("proxy_id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            scheme=normalize_proxy_scheme(payload.get("scheme")),
            host=host,
            port=port,
            username=str(payload.get("username") or "").strip(),
            password=str(payload.get("password") or ""),
            enabled=bool(payload.get("enabled", True)),
            max_accounts=max(
                1,
                int(payload.get("max_accounts") or DEFAULT_PROXY_MAX_ACCOUNTS),
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.proxy_id,
            "name": self.name,
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "enabled": self.enabled,
            "max_accounts": self.max_accounts,
        }

    def cache_key(self) -> str:
        return "|".join(
            [
                self.scheme,
                self.host,
                str(self.port),
                self.username,
                self.password,
            ]
        )

    def proxy_server_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def proxy_url(self) -> str:
        if not self.username:
            return self.proxy_server_url()
        username = quote(self.username, safe="")
        password = quote(self.password, safe="")
        return f"{self.scheme}://{username}:{password}@{self.host}:{self.port}"


def proxy_db_path_from_env(default: Path | None = None) -> Path | None:
    raw = os.getenv(PROXY_DB_ENV, "").strip()
    if raw:
        return Path(raw)
    return default


def proxy_config_path_from_env(default: Path | None = None) -> Path | None:
    raw = os.getenv(PROXY_CONFIG_ENV, "").strip()
    if raw:
        return Path(raw)
    return default


def load_runtime_proxy_config(path: Path | None = None) -> RuntimeProxyConfig | None:
    resolved_path = path or proxy_config_path_from_env()
    if resolved_path is None or not resolved_path.exists():
        return None
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return RuntimeProxyConfig.from_payload(payload)
    except (TypeError, ValueError):
        return None


def write_runtime_proxy_config(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def delete_runtime_proxy_config(path: Path) -> None:
    path.unlink(missing_ok=True)


def build_playwright_proxy_settings(
    config: RuntimeProxyConfig | None,
) -> dict[str, str] | None:
    if config is None:
        return None
    if not config.enabled:
        raise RuntimeError(f"Proxy '{config.name or config.proxy_id}' is disabled.")
    settings = {"server": config.proxy_server_url()}
    if config.username:
        settings["username"] = config.username
        settings["password"] = config.password
    return settings


def build_telethon_proxy_settings(
    config: RuntimeProxyConfig | None,
) -> dict[str, object] | None:
    if config is None:
        return None
    if not config.enabled:
        raise RuntimeError(f"Proxy '{config.name or config.proxy_id}' is disabled.")
    if config.scheme not in TELEGRAM_PROXY_SCHEMES:
        raise RuntimeError(
            "Telegram connections support only HTTP or SOCKS5 proxies. "
            f"Configured scheme: {config.scheme}.",
        )
    if config.scheme == "socks5":
        try:
            import socks  # type: ignore[import-not-found]  # noqa: F401
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "SOCKS5 proxy support requires the 'PySocks' package. "
                "Reinstall runtime dependencies and try again."
            ) from exc
    return {
        "proxy_type": config.scheme,
        "addr": config.host,
        "port": config.port,
        "username": config.username or None,
        "password": config.password or None,
    }


def _build_urllib_proxy_map(config: RuntimeProxyConfig) -> dict[str, str]:
    if config.scheme not in HTTP_PROXY_SCHEMES:
        raise RuntimeError(
            "HTTP requests support only HTTP or HTTPS proxies. "
            f"Configured scheme: {config.scheme}.",
        )
    proxy_url = config.proxy_url()
    return {
        "http": proxy_url,
        "https": proxy_url,
    }


def get_urllib_opener(
    config: RuntimeProxyConfig | None,
) -> urllib_request.OpenerDirector | None:
    if config is None:
        return None
    if not config.enabled:
        raise RuntimeError(f"Proxy '{config.name or config.proxy_id}' is disabled.")
    cache_key = config.cache_key()
    with _URLOPENER_LOCK:
        opener = _URLOPENER_CACHE.get(cache_key)
        if opener is not None:
            return opener
        opener = urllib_request.build_opener(
            urllib_request.ProxyHandler(_build_urllib_proxy_map(config))
        )
        _URLOPENER_CACHE[cache_key] = opener
        return opener


def open_url(
    http_request: urllib_request.Request,
    *,
    config: RuntimeProxyConfig | None,
    timeout: float,
):
    opener = get_urllib_opener(config)
    if opener is None:
        return urllib_request.urlopen(http_request, timeout=timeout)
    return opener.open(http_request, timeout=timeout)


def ensure_proxy_database_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS proxies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                scheme TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT,
                password TEXT,
                max_accounts INTEGER NOT NULL DEFAULT 3,
                enabled INTEGER NOT NULL DEFAULT 1,
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'unknown',
                last_used_at TEXT,
                last_success_at TEXT,
                last_failure_at TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                total_requests INTEGER NOT NULL DEFAULT 0,
                total_failures INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proxy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proxy_id TEXT NOT NULL,
                account_id TEXT,
                target TEXT,
                success INTEGER NOT NULL DEFAULT 0,
                error_type TEXT,
                error_message TEXT,
                occurred_at TEXT NOT NULL,
                FOREIGN KEY(proxy_id) REFERENCES proxies(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_proxy_events_proxy_time
                ON proxy_events(proxy_id, occurred_at DESC);
            """
        )


def compute_proxy_status(enabled: bool, consecutive_failures: int, total_requests: int) -> str:
    if not enabled:
        return PROXY_STATUS_DISABLED
    if total_requests <= 0:
        return PROXY_STATUS_UNKNOWN
    if consecutive_failures >= 3:
        return PROXY_STATUS_FAILING
    if consecutive_failures > 0:
        return PROXY_STATUS_DEGRADED
    return PROXY_STATUS_HEALTHY


def record_proxy_request_result(
    proxy_id: str | None,
    *,
    account_id: str | None = None,
    target: str | None = None,
    success: bool,
    db_path: Path | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    normalized_proxy_id = normalize_proxy_identifier(proxy_id)
    resolved_db_path = db_path or proxy_db_path_from_env()
    if normalized_proxy_id is None or resolved_db_path is None:
        return
    ensure_proxy_database_schema(resolved_db_path)
    occurred_at = _utc_now()
    with sqlite3.connect(resolved_db_path) as conn:
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute(
            """
            INSERT INTO proxy_events (
                proxy_id,
                account_id,
                target,
                success,
                error_type,
                error_message,
                occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_proxy_id,
                normalize_proxy_identifier(account_id),
                str(target or "").strip() or None,
                1 if success else 0,
                str(error_type or "").strip() or None,
                str(error_message or "").strip() or None,
                occurred_at,
            ),
        )
        conn.execute(
            """
            UPDATE proxies
            SET total_requests = COALESCE(total_requests, 0) + 1,
                total_failures = COALESCE(total_failures, 0) + ?,
                consecutive_failures = CASE
                    WHEN ? = 1 THEN 0
                    ELSE COALESCE(consecutive_failures, 0) + 1
                END,
                last_used_at = ?,
                last_success_at = CASE WHEN ? = 1 THEN ? ELSE last_success_at END,
                last_failure_at = CASE WHEN ? = 1 THEN last_failure_at ELSE ? END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                0 if success else 1,
                1 if success else 0,
                occurred_at,
                1 if success else 0,
                occurred_at,
                1 if success else 0,
                occurred_at,
                occurred_at,
                normalized_proxy_id,
            ),
        )
        row = conn.execute(
            """
            SELECT enabled, consecutive_failures, total_requests
            FROM proxies
            WHERE id = ?
            """,
            (normalized_proxy_id,),
        ).fetchone()
        if row is None:
            return
        status = compute_proxy_status(
            bool(row[0]),
            int(row[1] or 0),
            int(row[2] or 0),
        )
        conn.execute(
            "UPDATE proxies SET status = ?, updated_at = ? WHERE id = ?",
            (status, occurred_at, normalized_proxy_id),
        )
