from __future__ import annotations

import ast
import asyncio
import logging
import re
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAX_LOG_ENTRIES_PER_ACCOUNT = 1000
_ACCOUNT_LOGGER_NAME = "telegram_accounts_api.account"
_HANDLER_NAME = "telegram_accounts_api.account_log_handler"
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)\b(password|api_hash|token|sessionid|csrftoken|authorization|cookie)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"),
)
_ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_INLINE_LEVEL_PREFIX_PATTERN = re.compile(
    r"^(?:\[(?P<level>INFO|WARN(?:ING)?|ERROR|OK|SUCCESS)\]\s*)+",
    re.IGNORECASE,
)
_SEPARATOR_ONLY_PATTERN = re.compile(r"^[\s_=+\-—–~.]{8,}$")
_SIZE_LOG_PATTERN = re.compile(r"^Размеры товара:\s*(?P<payload>\{.*\})$", re.DOTALL)
_RUN_STARTED_PATTERN = re.compile(r"^\[RUN\]\s+started pid=(?P<pid>\d+)$", re.IGNORECASE)
_CHANNELS_EXPORTED_PATTERN = re.compile(
    r"^\[CHANNELS\]\s+exported (?P<count>\d+) link\(s\)$",
    re.IGNORECASE,
)
_STOP_REQUESTED_PATTERN = re.compile(
    r"^\[STOP\]\s+stop requested from API$",
    re.IGNORECASE,
)
_STOP_EXITED_PATTERN = re.compile(
    r"^\[STOP\]\s+process exited with code (?P<code>-?\d+)$",
    re.IGNORECASE,
)
_ERROR_EXITED_PATTERN = re.compile(
    r"^\[ERROR\]\s+process exited with code (?P<code>-?\d+)$",
    re.IGNORECASE,
)
_ACCOUNT_STARTED_PATTERN = re.compile(
    r"^Account status changed to started \(pid=(?P<pid>\d+)\)\.$",
    re.IGNORECASE,
)
_SESSION_COPIED_PATTERN = re.compile(
    r"^Telegram session copied from account '(?P<account>[^']+)'\.$",
    re.IGNORECASE,
)
_SESSION_IMPORTED_PATTERN = re.compile(
    r"^Telegram session imported from file '(?P<filename>[^']+)'\.$",
    re.IGNORECASE,
)
_REJECTED_PHONE_PATTERN = re.compile(
    r"^Rejected Telegram phone number: (?P<detail>.+)$",
    re.IGNORECASE,
)
_TG_CODE_REQUEST_FAILED_PATTERN = re.compile(
    r"^Telegram verification code request failed: (?P<detail>.+)$",
    re.IGNORECASE,
)
_TG_CODE_REQUEST_UNEXPECTED_PATTERN = re.compile(
    r"^Unexpected Telegram code request failure: (?P<detail>.+)$",
    re.IGNORECASE,
)
_TG_CODE_SUBMIT_FAILED_PATTERN = re.compile(
    r"^Telegram code submission failed: (?P<detail>.+)$",
    re.IGNORECASE,
)
_TG_CODE_SUBMIT_UNEXPECTED_PATTERN = re.compile(
    r"^Unexpected Telegram code submission failure: (?P<detail>.+)$",
    re.IGNORECASE,
)
_TG_PASSWORD_SUBMIT_FAILED_PATTERN = re.compile(
    r"^Telegram password submission failed: (?P<detail>.+)$",
    re.IGNORECASE,
)
_TG_PASSWORD_SUBMIT_UNEXPECTED_PATTERN = re.compile(
    r"^Unexpected Telegram password submission failure: (?P<detail>.+)$",
    re.IGNORECASE,
)
_SHAFA_PROFILE_FAILED_PATTERN = re.compile(
    r"^Failed to fetch Shafa profile data: (?P<detail>.+)$",
    re.IGNORECASE,
)
_SHAFA_LOGIN_FAILED_PATTERN = re.compile(
    r"^Failed to start Shafa login flow: (?P<detail>.+)$",
    re.IGNORECASE,
)
_SHAFA_LOGIN_UNEXPECTED_PATTERN = re.compile(
    r"^Unexpected Shafa login launcher failure: (?P<detail>.+)$",
    re.IGNORECASE,
)
_SHAFA_SAVE_UNEXPECTED_PATTERN = re.compile(
    r"^Unexpected Shafa session save failure: (?P<detail>.+)$",
    re.IGNORECASE,
)
_PRODUCT_NAME_PATTERN = re.compile(
    r"^Товар для создания: (?P<name>.+)\.$"
)
_PRODUCT_CATALOG_PATTERN = re.compile(
    r"^Каталог из данных товара: (?P<slug>.+)\.$"
)
_PRODUCT_PRICE_PATTERN = re.compile(
    r"^Цена товара \(с наценкой (?P<markup>-?\d+)\): (?P<price>.+)\.$"
)
_DOWNLOADED_PHOTO_COUNT_PATTERN = re.compile(
    r"^Скачано фото: (?P<count>\d+)\.$"
)
_BRANDS_LOADED_PATTERN = re.compile(
    r"^Загружены бренды для (?P<slug>[^:]+): (?P<count>\d+)\.$"
)
_SIZES_LOADED_PATTERN = re.compile(
    r"^Загружены размеры для (?P<slug>[^:]+): (?P<count>\d+)\.$"
)
_PRODUCT_CREATED_NAMED_PATTERN = re.compile(
    r"^Товар создан успешно\. Имя товара: (?P<name>.+)\. ID: (?P<id>[^.]+)\. Фото: (?P<count>\d+)\.$"
)
_PRODUCT_CREATED_SIMPLE_PATTERN = re.compile(
    r"^Товар создан успешно\. ID: (?P<id>[^.]+)\. Фото: (?P<count>\d+)\.$"
)
_RENDERED_LOG_PATTERN = re.compile(
    r"^\[(?P<timestamp>[^\]]+)\]\s+\[(?P<level>[^\]]+)\](?:\s+\[(?P<account_name>[^\]]+)\])?\s+(?P<message>.*)$"
)
_FIELD_LABELS = {
    "brand": "бренд",
    "category": "категория",
    "price": "цена",
    "size": "размер",
}


@dataclass(frozen=True)
class AccountLogEntry:
    index: int
    account_id: str
    timestamp: datetime
    level: str
    message: str


@dataclass(frozen=True)
class _Subscriber:
    id: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[AccountLogEntry]


def normalize_log_level(level: str | None) -> str:
    normalized = str(level or "INFO").strip().upper()
    aliases = {
        "WARN": "WARNING",
        "OK": "SUCCESS",
    }
    return aliases.get(normalized, normalized or "INFO")


def _join_preview(values: list[Any], *, limit: int = 5) -> str:
    normalized = [str(value).strip() for value in values if str(value).strip()]

    if not normalized:
        return ""

    preview = ", ".join(normalized[:limit])
    if len(normalized) > limit:
        return f"{preview}…"
    return preview


def _format_size_log_message(message: str) -> str | None:
    match = _SIZE_LOG_PATTERN.match(message)
    if not match:
        return None

    try:
        payload = ast.literal_eval(match.group("payload"))
    except (SyntaxError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    catalog = str(payload.get("catalog") or "").strip()
    raw_size = str(payload.get("raw_size") or "").strip()
    raw_additional_sizes = payload.get("raw_additional_sizes")
    preferred_system = str(payload.get("preferred_size_system") or "").strip()
    resolved_size = payload.get("resolved_size")
    resolved_additional_sizes = payload.get("resolved_additional_sizes")
    additional_preview = (
        _join_preview(raw_additional_sizes)
        if isinstance(raw_additional_sizes, list)
        else ""
    )
    resolved_additional_count = (
        len(resolved_additional_sizes)
        if isinstance(resolved_additional_sizes, list)
        else 0
    )

    parts: list[str] = []
    if raw_size:
        parts.append(f"Размер: {raw_size}.")
    if additional_preview:
        parts.append(f"Доп. размеры: {additional_preview}.")
    if catalog:
        parts.append(f"Каталог: {catalog}.")
    if preferred_system:
        parts.append(f"Система: {preferred_system.upper()}.")
    if resolved_size is not None:
        if resolved_additional_count > 0:
            parts.append(
                f"Размер сопоставлен, доп. размеров: {resolved_additional_count}."
            )
        else:
            parts.append("Размер сопоставлен.")
    else:
        parts.append("Размер не сопоставлен автоматически.")

    return " ".join(parts).strip() or None


def _format_graph_response_error_message(message: str) -> str | None:
    stripped = message.strip()
    if "__typename" not in stripped or stripped[:1] not in "[{":
        return None

    try:
        payload = ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return None

    items = payload if isinstance(payload, list) else [payload]
    details: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        field = str(item.get("field") or "").strip().lower()
        field_label = _FIELD_LABELS.get(field, field)
        messages = item.get("messages")

        if not isinstance(messages, list):
            continue

        for message_item in messages:
            if not isinstance(message_item, dict):
                continue

            text = str(message_item.get("message") or "").strip()
            if not text:
                continue

            if field_label:
                details.append(f"{field_label}: {text}")
            else:
                details.append(text)

    if not details:
        return None

    unique_details = list(dict.fromkeys(details))
    return "Shafa API: " + "; ".join(unique_details)


def _translate_system_message(message: str) -> str | None:
    run_started_match = _RUN_STARTED_PATTERN.match(message)
    if run_started_match:
        return f"Процесс запущен (PID {run_started_match.group('pid')})."

    channels_exported_match = _CHANNELS_EXPORTED_PATTERN.match(message)
    if channels_exported_match:
        return (
            f"Ссылки Telegram-каналов экспортированы: "
            f"{channels_exported_match.group('count')}."
        )

    if _STOP_REQUESTED_PATTERN.match(message):
        return "Остановка запрошена из API."

    stop_exited_match = _STOP_EXITED_PATTERN.match(message)
    if stop_exited_match:
        return f"Процесс остановлен (код {stop_exited_match.group('code')})."

    error_exited_match = _ERROR_EXITED_PATTERN.match(message)
    if error_exited_match:
        return (
            f"Процесс завершился с ошибкой "
            f"(код {error_exited_match.group('code')})."
        )

    account_started_match = _ACCOUNT_STARTED_PATTERN.match(message)
    if account_started_match:
        return (
            f"Статус аккаунта: запущен "
            f"(PID {account_started_match.group('pid')})."
        )

    session_copied_match = _SESSION_COPIED_PATTERN.match(message)
    if session_copied_match:
        return (
            f"Сессия Telegram скопирована из аккаунта "
            f"«{session_copied_match.group('account')}»."
        )

    session_imported_match = _SESSION_IMPORTED_PATTERN.match(message)
    if session_imported_match:
        return (
            f"Сессия Telegram импортирована из файла "
            f"«{session_imported_match.group('filename')}»."
        )

    rejected_phone_match = _REJECTED_PHONE_PATTERN.match(message)
    if rejected_phone_match:
        return f"Телефон Telegram отклонён: {rejected_phone_match.group('detail')}"

    tg_code_request_failed_match = _TG_CODE_REQUEST_FAILED_PATTERN.match(message)
    if tg_code_request_failed_match:
        return (
            f"Не удалось запросить код Telegram: "
            f"{tg_code_request_failed_match.group('detail')}"
        )

    tg_code_request_unexpected_match = _TG_CODE_REQUEST_UNEXPECTED_PATTERN.match(message)
    if tg_code_request_unexpected_match:
        return (
            f"Сбой запроса кода Telegram: "
            f"{tg_code_request_unexpected_match.group('detail')}"
        )

    tg_code_submit_failed_match = _TG_CODE_SUBMIT_FAILED_PATTERN.match(message)
    if tg_code_submit_failed_match:
        return (
            f"Не удалось подтвердить код Telegram: "
            f"{tg_code_submit_failed_match.group('detail')}"
        )

    tg_code_submit_unexpected_match = _TG_CODE_SUBMIT_UNEXPECTED_PATTERN.match(message)
    if tg_code_submit_unexpected_match:
        return (
            f"Сбой отправки кода Telegram: "
            f"{tg_code_submit_unexpected_match.group('detail')}"
        )

    tg_password_submit_failed_match = _TG_PASSWORD_SUBMIT_FAILED_PATTERN.match(message)
    if tg_password_submit_failed_match:
        return (
            f"Не удалось подтвердить пароль Telegram: "
            f"{tg_password_submit_failed_match.group('detail')}"
        )

    tg_password_submit_unexpected_match = _TG_PASSWORD_SUBMIT_UNEXPECTED_PATTERN.match(message)
    if tg_password_submit_unexpected_match:
        return (
            f"Сбой отправки пароля Telegram: "
            f"{tg_password_submit_unexpected_match.group('detail')}"
        )

    shafa_profile_failed_match = _SHAFA_PROFILE_FAILED_PATTERN.match(message)
    if shafa_profile_failed_match:
        return (
            f"Не удалось получить профиль Shafa: "
            f"{shafa_profile_failed_match.group('detail')}"
        )

    shafa_login_failed_match = _SHAFA_LOGIN_FAILED_PATTERN.match(message)
    if shafa_login_failed_match:
        return (
            f"Не удалось запустить вход в Shafa: "
            f"{shafa_login_failed_match.group('detail')}"
        )

    shafa_login_unexpected_match = _SHAFA_LOGIN_UNEXPECTED_PATTERN.match(message)
    if shafa_login_unexpected_match:
        return (
            f"Сбой запуска входа в Shafa: "
            f"{shafa_login_unexpected_match.group('detail')}"
        )

    shafa_save_unexpected_match = _SHAFA_SAVE_UNEXPECTED_PATTERN.match(message)
    if shafa_save_unexpected_match:
        return (
            f"Сбой сохранения сессии Shafa: "
            f"{shafa_save_unexpected_match.group('detail')}"
        )

    direct_rewrites = {
        "Account created.": "Аккаунт создан.",
        "Account settings updated.": "Настройки аккаунта обновлены.",
        "Account deleted.": "Аккаунт удалён.",
        "Account status changed to stopped.": "Статус аккаунта: остановлен.",
        "Telegram API credentials saved.": "Telegram API-данные сохранены.",
        "Starting Telegram login: requesting verification code.": "Запрашиваю код Telegram.",
        "Telegram code request blocked: credentials are missing.": "Запрос кода Telegram заблокирован: нет API-данных.",
        "Telegram login already has an active pending step.": "Вход в Telegram уже ожидает следующий шаг.",
        "Telegram verification code requested.": "Код Telegram запрошен.",
        "Submitting Telegram verification code.": "Отправляю код Telegram.",
        "Telegram verification code accepted.": "Код Telegram подтверждён.",
        "Submitting Telegram 2FA password.": "Отправляю пароль 2FA Telegram.",
        "Telegram login completed successfully.": "Вход в Telegram завершён.",
        "Telegram session removed.": "Сессия Telegram удалена.",
        "Telegram phone number resolved from authorized session.": "Номер телефона получен из Telegram-сессии.",
        "Rejected Telegram credentials: invalid API ID.": "Telegram API ID отклонён: нужен integer.",
        "Rejected Telegram credentials: API hash missing.": "Telegram API hash не указан.",
        "Telegram code requested.": "Код Telegram запрошен.",
        "Telegram password accepted.": "Пароль Telegram подтверждён.",
        "Telegram session is authorized.": "Сессия Telegram авторизована.",
        "Telegram login completed.": "Вход в Telegram завершён.",
        "Saving Shafa authentication state.": "Сохраняю сессию Shafa.",
        "Rejected Shafa cookies: valid session cookie was not found.": "Cookie Shafa отклонены: не найдена валидная сессия.",
        "Shafa session saved.": "Сессия Shafa сохранена.",
        "Starting Shafa browser login flow.": "Запускаю вход в Shafa через браузер.",
        "Shafa browser login flow started.": "Окно входа Shafa открыто.",
        "Shafa session removed.": "Сессия Shafa удалена.",
    }
    return direct_rewrites.get(message)


def _translate_business_message(message: str) -> str | None:
    product_name_match = _PRODUCT_NAME_PATTERN.match(message)
    if product_name_match:
        return f"Готовлю товар: «{product_name_match.group('name')}»."

    product_catalog_match = _PRODUCT_CATALOG_PATTERN.match(message)
    if product_catalog_match:
        return f"Каталог: {product_catalog_match.group('slug')}."

    product_price_match = _PRODUCT_PRICE_PATTERN.match(message)
    if product_price_match:
        return (
            f"Цена рассчитана: {product_price_match.group('price')} "
            f"(наценка {product_price_match.group('markup')})."
        )

    downloaded_photo_count_match = _DOWNLOADED_PHOTO_COUNT_PATTERN.match(message)
    if downloaded_photo_count_match:
        return f"Фото скачаны: {downloaded_photo_count_match.group('count')}."

    brands_loaded_match = _BRANDS_LOADED_PATTERN.match(message)
    if brands_loaded_match:
        return (
            f"Бренды обновлены для {brands_loaded_match.group('slug')}: "
            f"{brands_loaded_match.group('count')}."
        )

    sizes_loaded_match = _SIZES_LOADED_PATTERN.match(message)
    if sizes_loaded_match:
        return (
            f"Размеры обновлены для {sizes_loaded_match.group('slug')}: "
            f"{sizes_loaded_match.group('count')}."
        )

    product_created_named_match = _PRODUCT_CREATED_NAMED_PATTERN.match(message)
    if product_created_named_match:
        return (
            "Товар создан успешно: "
            f"«{product_created_named_match.group('name')}», "
            f"ID {product_created_named_match.group('id')}, "
            f"фото {product_created_named_match.group('count')}."
        )

    product_created_simple_match = _PRODUCT_CREATED_SIMPLE_PATTERN.match(message)
    if product_created_simple_match:
        return (
            "Товар создан успешно: "
            f"ID {product_created_simple_match.group('id')}, "
            f"фото {product_created_simple_match.group('count')}."
        )

    direct_rewrites = {
        "Нет новых товаров для создания.": "Новых товаров нет.",
        "Бренд не определён. Обновляю список брендов...": "Бренд не определён, обновляю бренды.",
        "Размер не определён. Обновляю список размеров...": "Размер не определён, обновляю размеры.",
        "Создаю товар...": "Создаю товар.",
        "API отклонил размер. Обновляю размеры и повторяю создание товара...": "Размер отклонён API, обновляю размеры и повторяю создание.",
        "Фото удалены после создания товара.": "Временные фото удалены.",
        "Нет фото для загрузки после фильтра/сжатия.": "После фильтрации фото не осталось.",
    }
    return direct_rewrites.get(message)


def normalize_log_message(message: str) -> str:
    normalized = _ANSI_ESCAPE_PATTERN.sub("", str(message)).strip()

    for pattern in _SENSITIVE_VALUE_PATTERNS:
        if "Bearer" in pattern.pattern:
            normalized = pattern.sub("Bearer [REDACTED]", normalized)
        else:
            normalized = pattern.sub(
                lambda match: f"{match.group(1)}=[REDACTED]",
                normalized,
            )

    normalized = _INLINE_LEVEL_PREFIX_PATTERN.sub("", normalized).strip()

    formatted_size_message = _format_size_log_message(normalized)
    if formatted_size_message:
        return formatted_size_message

    formatted_error_message = _format_graph_response_error_message(normalized)
    if formatted_error_message:
        return formatted_error_message

    translated_system_message = _translate_system_message(normalized)
    if translated_system_message:
        return translated_system_message

    translated_business_message = _translate_business_message(normalized)
    if translated_business_message:
        return translated_business_message

    return normalized


def is_ignorable_log_message(message: str) -> bool:
    normalized = str(message).strip()
    return not normalized or bool(_SEPARATOR_ONLY_PATTERN.fullmatch(normalized))


class AccountLogStore:
    def __init__(self, max_entries_per_account: int = _MAX_LOG_ENTRIES_PER_ACCOUNT) -> None:
        self.max_entries_per_account = max(1, int(max_entries_per_account))
        self._entries: dict[str, deque[AccountLogEntry]] = defaultdict(
            lambda: deque(maxlen=self.max_entries_per_account)
        )
        self._next_index: dict[str, int] = defaultdict(int)
        self._subscribers: dict[str, dict[str, _Subscriber]] = defaultdict(dict)
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._next_index.clear()
            self._subscribers.clear()

    def clear_entries(self, account_id: str | int | None = None) -> None:
        with self._lock:
            if account_id is None:
                self._entries.clear()
                self._next_index.clear()
                return

            normalized_account_id = str(account_id)
            self._entries.pop(normalized_account_id, None)
            self._next_index.pop(normalized_account_id, None)

    def append(
        self,
        account_id: str | int,
        level: str,
        message: str,
        *,
        timestamp: datetime | None = None,
    ) -> AccountLogEntry:
        normalized_account_id = str(account_id)
        normalized_level = normalize_log_level(level)
        normalized_message = normalize_log_message(message)
        entry = AccountLogEntry(
            index=self._next_index[normalized_account_id],
            account_id=normalized_account_id,
            timestamp=normalize_log_timestamp(timestamp or datetime.now(UTC)),
            level=normalized_level,
            message=normalized_message,
        )
        with self._lock:
            self._entries[normalized_account_id].append(entry)
            self._next_index[normalized_account_id] += 1
            subscribers = list(self._subscribers.get(normalized_account_id, {}).values())
        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(subscriber.queue.put_nowait, entry)
            except RuntimeError:
                self.unsubscribe(normalized_account_id, subscriber.id)
        return entry

    def list_entries(
        self,
        account_id: str | int,
        *,
        limit: int = 100,
        level: str | None = None,
        since_index: int | None = None,
        since_timestamp: datetime | None = None,
    ) -> list[AccountLogEntry]:
        normalized_account_id = str(account_id)
        target_level = str(level or "").upper()
        normalized_timestamp = since_timestamp.astimezone(UTC) if since_timestamp else None
        with self._lock:
            entries = list(self._entries.get(normalized_account_id, ()))
        if target_level:
            entries = [entry for entry in entries if entry.level == target_level]
        if since_index is not None:
            entries = [entry for entry in entries if entry.index > since_index]
        if normalized_timestamp is not None:
            entries = [entry for entry in entries if entry.timestamp >= normalized_timestamp]
        bounded_limit = max(1, min(int(limit), self.max_entries_per_account))
        return entries[-bounded_limit:]

    def subscribe(self, account_id: str | int) -> tuple[str, asyncio.Queue[AccountLogEntry]]:
        normalized_account_id = str(account_id)
        subscription = _Subscriber(
            id=uuid.uuid4().hex,
            loop=asyncio.get_running_loop(),
            queue=asyncio.Queue(),
        )
        with self._lock:
            self._subscribers[normalized_account_id][subscription.id] = subscription
        return subscription.id, subscription.queue

    def unsubscribe(self, account_id: str | int, subscription_id: str) -> None:
        normalized_account_id = str(account_id)
        with self._lock:
            subscribers = self._subscribers.get(normalized_account_id)
            if not subscribers:
                return
            subscribers.pop(subscription_id, None)
            if not subscribers:
                self._subscribers.pop(normalized_account_id, None)


class AccountLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        account_id = getattr(record, "account_id", None)
        if account_id in (None, ""):
            return
        try:
            get_account_log_store().append(
                account_id=account_id,
                level=record.levelname,
                message=record.getMessage(),
                timestamp=datetime.fromtimestamp(record.created, tz=UTC),
            )
        except Exception:
            self.handleError(record)


_store_lock = threading.RLock()
_account_log_store: AccountLogStore | None = None


def get_account_log_store() -> AccountLogStore:
    global _account_log_store
    with _store_lock:
        if _account_log_store is None:
            _account_log_store = AccountLogStore()
        return _account_log_store


def set_account_log_store(store: AccountLogStore) -> AccountLogStore:
    global _account_log_store
    with _store_lock:
        _account_log_store = store
    return store


def install_account_log_handler() -> None:
    root_logger = logging.getLogger()
    if any(getattr(handler, "name", "") == _HANDLER_NAME for handler in root_logger.handlers):
        return
    handler = AccountLogHandler()
    handler.setLevel(logging.DEBUG)
    handler.name = _HANDLER_NAME
    root_logger.addHandler(handler)


def sanitize_log_message(message: str) -> str:
    return normalize_log_message(message)


def normalize_log_timestamp(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or UTC
        timestamp = timestamp.replace(tzinfo=local_tz)
    return timestamp.astimezone(UTC)


def load_account_log_file_entries(
    account_id: str | int,
    log_file: Path,
) -> list[AccountLogEntry]:
    if not log_file.exists() or not log_file.is_file():
        return []

    entries: list[AccountLogEntry] = []
    try:
        raw_lines = log_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    normalized_account_id = str(account_id)
    for raw_line in raw_lines:
        match = _RENDERED_LOG_PATTERN.match(raw_line.strip())
        if not match:
            continue
        try:
            timestamp = datetime.strptime(
                match.group("timestamp"),
                "%Y-%m-%d %H:%M:%S",
            )
        except ValueError:
            continue
        entries.append(
            AccountLogEntry(
                index=0,
                account_id=normalized_account_id,
                timestamp=normalize_log_timestamp(timestamp),
                level=normalize_log_level(match.group("level")),
                message=normalize_log_message(match.group("message") or ""),
            )
        )
    entries = [
        entry for entry in entries if not is_ignorable_log_message(entry.message)
    ]
    start_index = -len(entries)
    return [
        AccountLogEntry(
            index=start_index + offset,
            account_id=entry.account_id,
            timestamp=entry.timestamp,
            level=entry.level,
            message=entry.message,
        )
        for offset, entry in enumerate(entries)
    ]


def merge_account_log_entries(*groups: list[AccountLogEntry]) -> list[AccountLogEntry]:
    merged_by_key: dict[tuple[str, str, str, str], AccountLogEntry] = {}

    for group in groups:
        for entry in group:
            dedupe_key = (
                entry.account_id,
                normalize_log_timestamp(entry.timestamp)
                .replace(microsecond=0)
                .isoformat(),
                entry.level,
                entry.message,
            )
            existing = merged_by_key.get(dedupe_key)
            if existing is None or entry.index > existing.index:
                merged_by_key[dedupe_key] = entry

    return sorted(
        merged_by_key.values(),
        key=lambda entry: (
            normalize_log_timestamp(entry.timestamp),
            entry.index,
            entry.message,
        ),
    )


def filter_account_log_entries(
    entries: list[AccountLogEntry],
    *,
    limit: int = 100,
    level: str | None = None,
    since_index: int | None = None,
    since_timestamp: datetime | None = None,
    max_entries: int = _MAX_LOG_ENTRIES_PER_ACCOUNT,
) -> list[AccountLogEntry]:
    target_level = str(level or "").upper()
    normalized_since_timestamp = (
        normalize_log_timestamp(since_timestamp)
        if since_timestamp is not None
        else None
    )
    bounded_limit = max(1, min(int(limit), int(max_entries)))

    filtered = entries
    if target_level:
        filtered = [entry for entry in filtered if entry.level == target_level]
    if since_index is not None:
        filtered = [entry for entry in filtered if entry.index > since_index]
    if normalized_since_timestamp is not None:
        filtered = [
            entry
            for entry in filtered
            if normalize_log_timestamp(entry.timestamp) >= normalized_since_timestamp
        ]
    return filtered[-bounded_limit:]


def log(account_id: str | int, level: str, message: str) -> None:
    install_account_log_handler()
    logger = logging.getLogger(_ACCOUNT_LOGGER_NAME)
    if logger.level in {logging.NOTSET, logging.WARNING, logging.ERROR, logging.CRITICAL}:
        logger.setLevel(logging.DEBUG)
    normalized_level = normalize_log_level(level)
    log_level = getattr(logging, normalized_level, logging.INFO)
    logger.log(
        log_level,
        normalize_log_message(message),
        extra={"account_id": str(account_id)},
    )
