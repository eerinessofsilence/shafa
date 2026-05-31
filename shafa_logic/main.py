import json
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
import argparse

from utils.stdio import install_safe_stdio

install_safe_stdio()

from telegram_subscription import complete_login, send_code, session_status, submit_password, sync_channels_from_runtime_config
from utils.logging import log
from utils.pipeline_activity import is_product_pipeline_active

_ADD_CHANNEL = object()
SHAFA_LOGIN_URL = "https://shafa.ua/uk/login"
APP_MODE_ENV = "SHAFA_APP_MODE"
SHAFA_LOGIN_FRESH_CONTEXT_ENV = "SHAFA_LOGIN_FRESH_CONTEXT"
DISABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR_ENV = "SHAFA_DISABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR"
DEACTIVATE_ONLY_ENV = "SHAFA_DEACTIVATE_ONLY"
SHARED_DEACTIVATION_ENABLED_ENV = "SHAFA_SHARED_DEACTIVATION_ENABLED"
SHARED_DEACTIVATION_PLANNER_ENABLED_ENV = "SHAFA_SHARED_DEACTIVATION_PLANNER_ENABLED"
SHARED_DEACTIVATION_WORKER_ENABLED_ENV = "SHAFA_SHARED_DEACTIVATION_WORKER_ENABLED"
SHARED_DEACTIVATION_AUTO_RUN_ENV = "SHAFA_SHARED_DEACTIVATION_AUTO_RUN"
SHARED_DEACTIVATION_DRY_RUN_ENV = "SHAFA_SHARED_DEACTIVATION_DRY_RUN"
SHARED_DEACTIVATION_PLANNER_INTERVAL_ENV = (
    "SHAFA_SHARED_DEACTIVATION_PLANNER_INTERVAL_SECONDS"
)


def _env_flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
        "on",
        "ON",
    }


def _load_inquirer():
    try:
        import inquirer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Модуль 'inquirer' нужен только для интерактивного CLI-меню. "
            "Для запуска меню установи его в используемое окружение Python."
        ) from exc
    return inquirer

def _ensure_tty() -> bool:
    if not sys.stdin.isatty():
        print("Нужен интерактивный терминал.")
        return False
    return True


def _print_ascii_banner() -> None:
    path = Path(__file__).resolve().parent / "data" / "ascii.txt"
    if not path.exists():
        return
    try:
        banner = path.read_text(encoding="utf-8")
    except OSError:
        return
    if not banner:
        return
    if banner.endswith("\n"):
        sys.stdout.write(banner)
    else:
        sys.stdout.write(f"{banner}\n")


def _prompt_list(
    message: str, choices: list[tuple[str, Any]], default: Any = None
) -> Optional[Any]:
    if not _ensure_tty():
        return None
    inquirer = _load_inquirer()
    question = inquirer.List(
        "choice",
        message=message,
        choices=choices,
        default=default,
    )
    try:
        answers = inquirer.prompt([question])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    return answers.get("choice")


def _prompt_checkbox(
    message: str, choices: list[tuple[str, Any]]
) -> Optional[list[Any]]:
    if not _ensure_tty():
        return None
    inquirer = _load_inquirer()
    question = inquirer.Checkbox(
        "items",
        message=message,
        choices=choices,
    )
    try:
        answers = inquirer.prompt([question])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    return answers.get("items") or []


def _prompt_text(
    message: str,
    default: Optional[str] = None,
    required: bool = False,
    validator: Optional[Callable[[str], Any]] = None,
) -> Optional[str]:
    if not _ensure_tty():
        return None
    inquirer = _load_inquirer()

    def _validate(_: dict, value: str) -> Any:
        if required and not value:
            return "Поле обязательно."
        if validator is None:
            return True
        return validator(value)

    question = inquirer.Text(
        "value",
        message=message,
        default=default if default is not None else "",
        # When not required and no custom validator, always accept input.
        validate=_validate if required or validator else True,
    )
    try:
        answers = inquirer.prompt([question])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    return str(answers.get("value") or "")


def _prompt_int(
    message: str,
    default: Optional[int] = None,
    min_value: Optional[int] = None,
    required: bool = False,
) -> Optional[int]:
    if not _ensure_tty():
        return None
    inquirer = _load_inquirer()

    def _validate(_: dict, value: str) -> Any:
        if not value:
            if required:
                return "Введите число."
            return True
        if not value.isdigit():
            return "Введите число."
        number = int(value)
        if min_value is not None and number < min_value:
            return f"Минимум {min_value}."
        return True

    question = inquirer.Text(
        "value",
        message=message,
        default=str(default) if default is not None else "",
        validate=_validate if required or min_value is not None else None,
    )
    try:
        answers = inquirer.prompt([question])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    raw = str(answers.get("value") or "").strip()
    if not raw:
        return None
    return int(raw)


def _prompt_minutes() -> Optional[int]:
    return _prompt_int("Интервал в минутах (>=1):", default=10, min_value=1)


def _choose_yes_no(question: str, default: bool = True) -> Optional[bool]:
    if not _ensure_tty():
        return None
    inquirer = _load_inquirer()
    prompt = inquirer.Confirm("confirm", message=question, default=default)
    try:
        answers = inquirer.prompt([prompt])
    except KeyboardInterrupt:
        print()
        return None
    if not answers:
        return None
    return bool(answers.get("confirm"))


def _background_scan_interval_seconds() -> int:
    raw = os.getenv("SHAFA_BACKGROUND_TELEGRAM_SCAN_INTERVAL_SECONDS", "").strip()
    if not raw:
        return 60
    try:
        value = int(raw)
    except ValueError:
        return 60
    return min(max(value, 10), 3600)


def _background_invalid_products_interval_seconds() -> int:
    raw = os.getenv("SHAFA_BACKGROUND_INVALID_PRODUCTS_INTERVAL_SECONDS", "").strip()
    if not raw:
        return 40
    try:
        value = int(raw)
    except ValueError:
        return 40
    return min(max(value, 10), 3600)


def _background_old_product_deactivate_interval_range_seconds() -> tuple[int, int]:
    min_allowed_seconds = 60
    fixed_interval = os.getenv(
        "SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_INTERVAL_SECONDS", ""
    ).strip()
    if fixed_interval:
        try:
            value = int(fixed_interval)
        except ValueError:
            return 60, 180
        value = min(max(value, min_allowed_seconds), 86400)
        return value, value

    min_raw = os.getenv(
        "SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_MIN_INTERVAL_SECONDS", ""
    ).strip()
    max_raw = os.getenv(
        "SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_MAX_INTERVAL_SECONDS", ""
    ).strip()
    try:
        min_value = int(min_raw) if min_raw else 60
    except ValueError:
        min_value = 60
    try:
        max_value = int(max_raw) if max_raw else 180
    except ValueError:
        max_value = 180
    min_value = min(max(min_value, min_allowed_seconds), 86400)
    max_value = min(max(max_value, min_allowed_seconds), 86400)
    if max_value < min_value:
        max_value = min_value
    return min_value, max_value


def _next_background_old_product_deactivate_wait_seconds() -> float:
    min_seconds, max_seconds = _background_old_product_deactivate_interval_range_seconds()
    if min_seconds == max_seconds:
        return float(min_seconds)
    return random.uniform(min_seconds, max_seconds)


def _background_old_product_deactivate_limit() -> int:
    raw = os.getenv("SHAFA_BACKGROUND_OLD_PRODUCT_DEACTIVATE_LIMIT", "").strip()
    if not raw:
        return 1
    try:
        return int(raw)
    except ValueError:
        return 1


def _shared_deactivation_scan_seconds() -> float:
    raw = os.getenv("SHAFA_SHARED_DEACTIVATION_SCAN_SECONDS", "").strip()
    if not raw:
        return 10.0
    try:
        value = float(raw)
    except ValueError:
        return 10.0
    return min(max(value, 1.0), 300.0)


def _shared_deactivation_planner_interval_seconds() -> float:
    raw = os.getenv(SHARED_DEACTIVATION_PLANNER_INTERVAL_ENV, "").strip()
    if not raw:
        return 300.0
    try:
        value = float(raw)
    except ValueError:
        return 300.0
    return min(max(value, 30.0), 3600.0)


def _shared_deactivation_auto_run_enabled() -> bool:
    return _env_flag_enabled(SHARED_DEACTIVATION_AUTO_RUN_ENV)


def _shared_deactivation_enabled() -> bool:
    return _shared_deactivation_auto_run_enabled() or _env_flag_enabled(
        SHARED_DEACTIVATION_ENABLED_ENV
    )


def _shared_deactivation_planner_enabled() -> bool:
    return _shared_deactivation_enabled() and (
        _shared_deactivation_auto_run_enabled()
        or _env_flag_enabled(SHARED_DEACTIVATION_PLANNER_ENABLED_ENV)
    )


def _shared_deactivation_worker_enabled() -> bool:
    return _shared_deactivation_enabled() and (
        _shared_deactivation_auto_run_enabled()
        or _env_flag_enabled(SHARED_DEACTIVATION_WORKER_ENABLED_ENV)
    )


def _shared_deactivation_dry_run_enabled() -> bool:
    raw = os.getenv(SHARED_DEACTIVATION_DRY_RUN_ENV, "").strip()
    if not raw:
        return not _shared_deactivation_auto_run_enabled()
    return raw in {"1", "true", "TRUE", "yes", "YES", "on", "ON"}


def _bootstrap_new_account_telegram_queue_if_needed() -> int:
    marker_value = os.getenv("SHAFA_TELEGRAM_QUEUE_SEED_MARKER_PATH", "").strip()
    if not marker_value:
        return 0
    marker_path = Path(marker_value)
    if not marker_path.exists():
        return 0
    account_id = str(os.getenv("SHAFA_ACCOUNT_ID") or "").strip()
    if not account_id:
        raise RuntimeError("Не задан SHAFA_ACCOUNT_ID для bootstrap очереди нового аккаунта.")
    from data.db import seed_account_telegram_products_from_existing_db

    seeded = seed_account_telegram_products_from_existing_db(account_id)
    try:
        marker_path.unlink(missing_ok=True)
    except OSError as exc:
        print(
            "Не удалось удалить marker bootstrap очереди "
            + f"для аккаунта {account_id}: {exc}"
        )
    print(
        f"Bootstrap очереди Telegram для нового аккаунта {account_id}: "
        + f"добавлено {seeded} товар(ов)."
    )
    return seeded


def _start_background_telegram_scanner() -> tuple[threading.Event, threading.Thread]:
    from controller.data_controller import (
        DEFAULT_TELEGRAM_SCAN_BATCH_SIZE,
        scan_next_due_telegram_channel,
    )

    stop_event = threading.Event()
    interval_seconds = _background_scan_interval_seconds()

    def _worker() -> None:
        while not stop_event.is_set():
            if is_product_pipeline_active():
                if stop_event.wait(5.0):
                    return
                continue
            started_at = time.time()
            try:
                result = scan_next_due_telegram_channel(
                    batch_size=DEFAULT_TELEGRAM_SCAN_BATCH_SIZE
                )
                if result.get("status") == "scanned":
                    inserted = int(result.get("inserted") or 0)
                    duplicates = int(result.get("duplicates") or 0)
                    channel_id = result.get("channel_id")
                    print(
                        "[INFO] Фоновая проверка Telegram завершена. "
                        f"Канал: {channel_id}. Новых товаров: {inserted}. "
                        f"Дубликатов: {duplicates}."
                    )
            except Exception as exc:
                print(f"[ERROR] Фоновое сканирование Telegram не выполнено: {exc}")
            elapsed = time.time() - started_at
            wait_seconds = max(1.0, interval_seconds - elapsed)
            if stop_event.wait(wait_seconds):
                return

    thread = threading.Thread(
        target=_worker,
        name="telegram-background-scanner",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _start_background_old_product_deactivator() -> tuple[threading.Event, threading.Thread]:
    from controller.data_controller import deactivate_old_telegram_products

    stop_event = threading.Event()
    min_seconds, max_seconds = _background_old_product_deactivate_interval_range_seconds()
    log(
        "INFO",
        "Фоновая деактивация старых товаров запущена. "
        f"interval_seconds={min_seconds}-{max_seconds}. "
        f"limit={_background_old_product_deactivate_limit()}.",
    )

    def _worker() -> None:
        backend_unavailable_reported = False
        while not stop_event.is_set():
            started_at = time.time()
            try:
                log("INFO", "Фоновая деактивация старых товаров: начинаю проверку.")
                result = deactivate_old_telegram_products(
                    dry_run=False,
                    limit=_background_old_product_deactivate_limit(),
                )
                found = int(result.get("found") or 0)
                deactivated = int(result.get("deactivated") or 0)
                failed = int(result.get("failed") or 0)
                checked = int(result.get("checked") or 0)
                active = int(result.get("active") or 0)
                skipped = int(result.get("skipped") or 0)
                not_found = int(result.get("not_found") or 0)
                log(
                    "INFO",
                    "Фоновая деактивация старых товаров завершена. "
                    f"Проверено: {checked}. Активных: {active}. "
                    f"Пропущено: {skipped}. Без связи Telegram: {not_found}. "
                    f"Найдено к деактивации: {found}. "
                    f"Деактивировано: {deactivated}. Ошибок: {failed}."
                )
                backend_unavailable_reported = False
            except Exception as exc:
                message = str(exc)
                print(f"[ERROR] Фоновая деактивация старых товаров не выполнена: {exc}")
                if (
                    "не реализована в API-слое" in message
                    or "не настроено" in message
                ):
                    if backend_unavailable_reported:
                        return
                    backend_unavailable_reported = True
                    return
                next_wait_seconds = _next_background_old_product_deactivate_wait_seconds()
            else:
                next_wait_seconds = _next_background_old_product_deactivate_wait_seconds()
            elapsed = time.time() - started_at
            wait_seconds = max(1.0, next_wait_seconds - elapsed)
            if stop_event.wait(wait_seconds):
                return

    thread = threading.Thread(
        target=_worker,
        name="old-products-background-deactivator",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _start_background_shared_deactivation_worker() -> tuple[threading.Event, threading.Thread]:
    from controller.data_controller import (
        plan_shared_old_product_deactivation,
        process_shared_deactivation_queue_once,
    )

    stop_event = threading.Event()
    scan_seconds = _shared_deactivation_scan_seconds()
    planner_interval_seconds = _shared_deactivation_planner_interval_seconds()
    last_planner_run_at: Optional[float] = None
    log(
        "INFO",
        "Shared deactivation worker started. "
        f"auto_run={_shared_deactivation_auto_run_enabled()}. "
        f"dry_run={_shared_deactivation_dry_run_enabled()}. "
        f"planner_enabled={_shared_deactivation_planner_enabled()}. "
        f"worker_enabled={_shared_deactivation_worker_enabled()}. "
        f"scan_seconds={scan_seconds}. "
        f"planner_interval_seconds={planner_interval_seconds}. "
        f"account_id={os.getenv('SHAFA_ACCOUNT_ID', '').strip() or 'default'}. "
        f"telegram_db_path={os.getenv('SHAFA_SHARED_TELEGRAM_DB_PATH', '')}.",
    )

    def _worker() -> None:
        nonlocal last_planner_run_at
        while not stop_event.is_set():
            claimed = 0
            try:
                now = time.monotonic()
                planner_due = (
                    last_planner_run_at is None
                    or now - last_planner_run_at >= planner_interval_seconds
                )
                if _shared_deactivation_planner_enabled() and planner_due:
                    log(
                        "INFO",
                        "Shared deactivation planner run started. "
                        f"account_id={os.getenv('SHAFA_ACCOUNT_ID', '').strip() or 'default'}.",
                    )
                    planner_result = plan_shared_old_product_deactivation()
                    last_planner_run_at = now
                    log(
                        "INFO",
                        "Shared deactivation planner run finished. "
                        f"checked={planner_result.get('checked')}. "
                        f"old={planner_result.get('old')}. "
                        f"fresh={planner_result.get('fresh')}. "
                        f"date_missing={planner_result.get('date_missing')}. "
                        f"tasks={planner_result.get('tasks')}. "
                        f"account_tasks={planner_result.get('account_tasks')}.",
                    )
                if _shared_deactivation_worker_enabled():
                    result = process_shared_deactivation_queue_once()
                    claimed = int(result.get("claimed") or 0)
            except Exception as exc:
                log("ERROR", f"Shared deactivation worker failed: {exc}")
            if claimed:
                continue
            if stop_event.wait(scan_seconds):
                return

    thread = threading.Thread(
        target=_worker,
        name="shared-deactivation-worker",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _deactivate_old_products_once(
    *,
    older_than_days: Optional[int] = None,
    limit: Optional[int] = None,
    sleep_seconds: Optional[float] = None,
    dry_run: bool = False,
) -> None:
    from controller.data_controller import deactivate_old_telegram_products

    result = deactivate_old_telegram_products(
        older_than_days=older_than_days,
        limit=limit,
        sleep_seconds=sleep_seconds,
        dry_run=dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def _shared_deactivation_plan_once() -> None:
    if not _shared_deactivation_enabled() and not _shared_deactivation_dry_run_enabled():
        raise RuntimeError(
            "Refusing non-dry-run shared deactivation planning because "
            f"{SHARED_DEACTIVATION_ENABLED_ENV} is not enabled."
        )
    from controller.data_controller import plan_shared_old_product_deactivation

    result = plan_shared_old_product_deactivation()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_periodic(action: Callable[[], None], label: str, shafa: bool | None = None) -> None:
    if shafa == False:
        minutes = _prompt_minutes()
    else:
        minutes = 5
    if minutes is None:
        return
    interval = minutes * 60
    print(f"Запуск периодического режима: {label}. Интервал: {minutes} мин.")
    while True:
        try:
            action()
        except Exception as exc:
            print(f"[ОШИБКА] {label} не выполнено: {exc}")
        try:
            percent = random.randint(1, 30)
            sign = random.choice((-1, 1))
            jitter = interval * (percent / 100.0)
            delay = max(1.0, interval + sign * jitter)
            next_at = time.strftime("%H:%M:%S", time.localtime(time.time() + delay))
            direction = "+" if sign > 0 else "-"
            delay_minutes = delay / 60.0
            print(
                "Следующий запуск в "
                f"{next_at}. Пауза: {delay_minutes:.1f} мин ({direction}{percent}%). "
                "Нажмите Ctrl+C для остановки."
            )
            time.sleep(delay)
        except KeyboardInterrupt:
            print()
            return


def _create_product() -> None:
    use_gui = _choose_yes_no("С окном браузера?", default=False)
    if use_gui is None:
        return
    if use_gui:
        from core.with_playwright import main as with_playwright_main

        with_playwright_main()
    else:
        from core.no_playwright import main as no_playwright_main

        no_playwright_main()


def _auto_create_product(shafa: bool | None = None) -> None:
    if shafa:
        from core.no_playwright import main as no_playwright_main

        run_periodic(no_playwright_main, "Без Playwright", shafa=shafa)
    else:
        use_gui = _choose_yes_no("С окном браузера?", default=False)
        if use_gui is None:
            return
        if use_gui:
            from core.with_playwright import main as with_playwright_main

            run_periodic(with_playwright_main, "Playwright")
        else:
            from core.no_playwright import main as no_playwright_main

            run_periodic(no_playwright_main, "Без Playwright")


def _bootstrap_project() -> None:
    from core import bootstrap

    bootstrap.main()


def _launch_visible_browser(playwright, *, headless: bool):
    from core.context import browser_launch_kwargs

    launch_kwargs = browser_launch_kwargs(headless=headless)
    last_error: Exception | None = None

    if os.name == "nt" and not headless:
        for channel in ("msedge", "chrome"):
            try:
                browser = playwright.chromium.launch(channel=channel, **launch_kwargs)
                return browser, channel
            except Exception as exc:  # pragma: no cover - exercised via fallback tests
                last_error = exc

    try:
        browser = playwright.chromium.launch(**launch_kwargs)
        return browser, "chromium"
    except Exception:
        if last_error is not None:
            raise last_error
        raise


def _login_fresh_context_enabled() -> bool:
    return os.getenv(SHAFA_LOGIN_FRESH_CONTEXT_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _normalize_match_text(value: object) -> str:
    return "".join(ch.casefold() for ch in str(value or "") if ch.isalnum())


def _normalize_match_phone(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _shafa_cookie_header(cookies: list[dict]) -> str:
    parts: list[str] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        value = cookie.get("value")
        if not name or value in (None, ""):
            continue
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def _shafa_csrftoken(cookies: list[dict]) -> str:
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        if str(cookie.get("name") or "").strip() == "csrftoken":
            return str(cookie.get("value") or "").strip()
    return ""


def _fetch_shafa_viewer_identity(cookies: list[dict]) -> dict[str, object]:
    from urllib import request

    from data.const import API_BATCH_URL, APP_PLATFORM, APP_VERSION, ORIGIN_URL
    from utils.proxy import load_runtime_proxy_config, open_url

    csrftoken = _shafa_csrftoken(cookies)
    if not csrftoken:
        raise RuntimeError("csrftoken not found in saved Shafa cookies")

    query = """query WEB_MainInfoSettingsFormData {
  viewer {
    id
    firstName
    lastName
    patronymic
    email
    phone
    __typename
  }
}"""
    payload = json.dumps(
        [
            {
                "operationName": "WEB_MainInfoSettingsFormData",
                "variables": {},
                "query": query,
            }
        ]
    ).encode("utf-8")
    http_request = request.Request(
        API_BATCH_URL,
        data=payload,
        headers={
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
            "Cookie": _shafa_cookie_header(cookies),
            "Origin": ORIGIN_URL,
            "Referer": "https://shafa.ua/uk/my/settings",
            "User-Agent": "Mozilla/5.0",
            "batch": "true",
            "x-app-platform": APP_PLATFORM,
            "x-app-version": APP_VERSION,
            "x-csrftoken": csrftoken,
        },
        method="POST",
    )
    with open_url(
        http_request,
        config=load_runtime_proxy_config(),
        timeout=20,
    ) as response:
        response_body = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(response_body)
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                viewer = item.get("data", {}).get("viewer")
                if isinstance(viewer, dict):
                    return viewer
    if isinstance(parsed, dict):
        viewer = parsed.get("data", {}).get("viewer")
        if isinstance(viewer, dict):
            return viewer
    raise RuntimeError("Shafa profile response does not contain viewer")


def _viewer_identity_text(viewer: dict[str, object]) -> str:
    name = " ".join(
        part
        for part in (
            str(viewer.get("firstName") or "").strip(),
            str(viewer.get("lastName") or "").strip(),
            str(viewer.get("patronymic") or "").strip(),
        )
        if part
    )
    parts = [
        f"id={viewer.get('id') or ''}",
        f"name={name or '-'}",
        f"email={viewer.get('email') or '-'}",
        f"phone={viewer.get('phone') or '-'}",
    ]
    return " | ".join(parts)


def _saved_session_matches_local_account(viewer: dict[str, object]) -> bool:
    local_name = os.getenv("SHAFA_ACCOUNT_NAME", "").strip()
    local_phone = os.getenv("SHAFA_ACCOUNT_PHONE", "").strip()
    viewer_name = " ".join(
        str(viewer.get(key) or "").strip()
        for key in ("firstName", "lastName", "patronymic")
    )
    viewer_identity = " ".join(
        str(viewer.get(key) or "").strip()
        for key in ("firstName", "lastName", "patronymic", "email", "phone")
    )
    local_phone_digits = _normalize_match_phone(local_phone)
    viewer_phone_digits = _normalize_match_phone(viewer.get("phone"))
    if local_phone_digits and viewer_phone_digits:
        return local_phone_digits == viewer_phone_digits
    local_name_key = _normalize_match_text(local_name)
    viewer_name_key = _normalize_match_text(viewer_name)
    viewer_identity_key = _normalize_match_text(viewer_identity)
    if local_name_key and viewer_name_key:
        return local_name_key in viewer_identity_key or viewer_name_key in local_name_key
    return True


def _verify_saved_shafa_login(cookies: list[dict]) -> None:
    account_name = os.getenv("SHAFA_ACCOUNT_NAME", "").strip() or "default"
    account_id = os.getenv("SHAFA_ACCOUNT_ID", "").strip() or "default"
    storage_path = os.getenv("SHAFA_STORAGE_STATE_PATH", "").strip()
    print(
        "Проверяю сохранённую Shafa-сессию: "
        f"local_account={account_name} | account_id={account_id} | auth={storage_path}"
    )
    try:
        viewer = _fetch_shafa_viewer_identity(cookies)
    except Exception as exc:
        print(f"WARNING: не удалось проверить сохранённую Shafa-сессию: {exc}")
        return
    print(f"Фактический Shafa viewer: {_viewer_identity_text(viewer)}")
    if not _saved_session_matches_local_account(viewer):
        print("WARNING: saved Shafa session does not match selected local account")


def _login_account() -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    from core.context import new_context_with_storage
    from core.core import get_csrftoken_from_context
    from data.const import STORAGE_STATE_PATH
    from data.db import init_db, save_cookies

    raw_confirmation_file = os.getenv("SHAFA_LOGIN_CONFIRMATION_FILE", "").strip()
    confirmation_file = Path(raw_confirmation_file) if raw_confirmation_file else None
    init_db()
    with sync_playwright() as p:
        browser, browser_name = _launch_visible_browser(p, headless=False)
        try:
            if _login_fresh_context_enabled():
                print("Открываю чистый браузерный контекст для выбранного аккаунта Shafa.")
                ctx = browser.new_context()
            else:
                ctx = new_context_with_storage(browser)
            page = ctx.new_page()
            page.set_default_timeout(60000)
            print(f"Открываю браузер Shafa через {browser_name}.")
            page.goto(SHAFA_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass

            print("Выполни вход в аккаунт в окне браузера. Ожидание сохранения сессии...")
            deadline = time.time() + 600
            last_seen_url = page.url
            redirect_detected_at: float | None = None
            login_detected_at: float | None = None
            while time.time() < deadline:
                current_url = page.url
                if current_url != last_seen_url:
                    last_seen_url = current_url
                    redirect_detected_at = time.time()
                    print(f"Обнаружен переход: {current_url}")

                waiting_for_auth_page = any(
                    token in current_url.lower() for token in ("login", "register")
                )
                csrftoken = get_csrftoken_from_context(ctx)
                if csrftoken and not waiting_for_auth_page:
                    if login_detected_at is None:
                        login_detected_at = time.time()
                        print("Вход обнаружен. Жду 3 секунды, чтобы завершился редирект и обновились cookies...")
                    wait_from = redirect_detected_at or login_detected_at
                    if wait_from is not None and time.time() - wait_from < 3:
                        time.sleep(0.5)
                        continue
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except PlaywrightTimeoutError:
                        pass
                    ctx.storage_state(path=str(STORAGE_STATE_PATH))
                    cookies = ctx.cookies()
                    save_cookies(cookies)
                    _verify_saved_shafa_login(cookies)
                    if confirmation_file is not None:
                        confirmation_file.write_text("ok\n", encoding="utf-8")
                    print(f"Вход сохранен. Cookies: {len(cookies)}.")
                    return
                time.sleep(2)
            print("Не удалось получить csrftoken. Проверь, что вход выполнен.")
        finally:
            browser.close()


def _print_products(limit: int = 20) -> list[dict]:
    from data.db import list_uploaded_products

    products = list_uploaded_products(limit=limit)
    if not products:
        print("Товары не найдены.")
        return []
    print("Товары:")
    for idx, row in enumerate(products, start=1):
        name = row.get("name") or "нет данных"
        product_id = row.get("product_id") or "нет данных"
        print(f"{idx}. {name} | {product_id}")
    return products


def _load_active_shafa_products(limit: int = 200) -> list[dict]:
    from data.db import sync_uploaded_products_from_shafa
    from core.requests.get_my_clothes_products_feed import get_my_clothes_products_feed

    normalized_limit = max(int(limit), 1)
    products: list[dict] = []
    seen_ids: set[str] = set()
    after: Optional[str] = None
    fetched_from_shafa = False
    fetch_failed = False
    while len(products) < normalized_limit:
        feed = get_my_clothes_products_feed(
            first=min(50, normalized_limit - len(products)),
            products_type="ACTIVE",
            after=after,
        )
        if not feed or feed.get("errors"):
            fetch_failed = True
            break
        fetched_from_shafa = True
        edges = feed.get("edges") or []
        for edge in edges:
            node = edge.get("node") or {}
            product_id = str(node.get("id") or "").strip()
            name = str(node.get("name") or "").strip()
            if not product_id or not name or product_id in seen_ids:
                continue
            seen_ids.add(product_id)
            products.append(
                {
                    "product_id": product_id,
                    "name": name,
                    "created_at": node.get("createdAt"),
                    "status_title": node.get("statusTitle"),
                    "size": node.get("size"),
                    "price": node.get("price"),
                    "raw_payload": node,
                }
            )
            if len(products) >= normalized_limit:
                break
        page_info = feed.get("pageInfo") or {}
        after = str(page_info.get("endCursor") or "").strip() or None
        if not page_info.get("hasNextPage") or after is None:
            break
    if fetched_from_shafa and not fetch_failed:
        sync_result = sync_uploaded_products_from_shafa(products)
        log(
            "INFO",
            "Товары загружены с Shafa и синхронизированы с локальной БД. "
            f"total={sync_result.get('total')}. "
            f"inserted={sync_result.get('inserted')}. "
            f"updated={sync_result.get('updated')}. "
            f"deactivated_local={sync_result.get('deactivated')}.",
        )
    elif fetch_failed:
        log(
            "WARN",
            "Не удалось полностью загрузить товары с Shafa, локальная БД не обновлялась.",
        )
    return products


def _parse_datetime_text_utc(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_days_from_datetime(moment: Optional[datetime]) -> Optional[float]:
    if moment is None:
        return None
    now_utc = datetime.now(timezone.utc)
    return round((now_utc - moment).total_seconds() / 86400.0, 1)


def _format_age_days(age_days: Optional[float]) -> str:
    if age_days is None:
        return "unknown"
    return f"{age_days:.1f}"


def _choose_active_shafa_product(limit: int = 200) -> Optional[dict]:
    products = _load_active_shafa_products(limit=limit)
    if not products:
        print("Активные товары Shafa не найдены.")
        return None
    return _prompt_list(
        "Выберите товар Shafa",
        [
            (f"{item['name']} | {item['product_id']}", item)
            for item in products
        ],
    )


def _resolve_product_name_for_telegram_search() -> Optional[str]:
    source = _prompt_list(
        "Откуда взять название товара?",
        [
            ("Выбрать из активных товаров Shafa", "shafa_active"),
            ("Ввести название вручную", "manual"),
        ],
    )
    if source is None:
        return None
    if source == "manual":
        value = _prompt_text(
            "Название товара для поиска в Telegram",
            required=True,
        )
        return str(value or "").strip() or None

    selection = _choose_active_shafa_product(limit=200)
    if selection is None:
        return None
    name = str(selection.get("name") or "").strip()
    product_id = str(selection.get("product_id") or "").strip()
    if name and product_id:
        print(f"Ищу в Telegram: {name} | {product_id}")
    return name or None


def _print_telegram_search_matches(product_name: str, matches: list[dict]) -> None:
    if not matches:
        print(f"Совпадения в Telegram для «{product_name}» не найдены.")
        return
    print(f"Совпадения в Telegram для «{product_name}»:")
    for idx, row in enumerate(matches, start=1):
        channel_name = row.get("channel_name") or row.get("channel_id") or "-"
        parsed_name = row.get("parsed_name") or "нет данных"
        message_id = row.get("message_id") or "-"
        score = float(row.get("score") or 0.0)
        message_date = row.get("telegram_message_date") or "-"
        preview = row.get("raw_message_preview") or ""
        print(
            f"{idx}. {parsed_name} | channel={channel_name} | "
            f"message_id={message_id} | score={score:.2f} | date={message_date}"
        )
        if preview:
            print(f"   {preview}")


def _find_product_in_telegram_by_name(product_name: Optional[str] = None) -> None:
    from controller.data_controller import find_telegram_matches_by_product_name

    resolved_name = str(product_name or "").strip() or _resolve_product_name_for_telegram_search()
    if not resolved_name:
        return
    per_channel_limit = 5
    if product_name is None:
        user_limit = _prompt_int(
            "Сколько совпадений показывать на канал?",
            default=5,
            min_value=1,
        )
        if user_limit is not None:
            per_channel_limit = user_limit
    matches = find_telegram_matches_by_product_name(
        resolved_name,
        per_channel_limit=per_channel_limit,
    )
    _print_telegram_search_matches(resolved_name, matches)


def _print_telegram_age_inspection(product: dict, inspection: dict) -> None:
    name = str(product.get("name") or "").strip() or "нет названия"
    product_id = str(product.get("product_id") or "").strip() or "нет id"
    status = str(inspection.get("status") or "")
    print(f"Товар Shafa: {name} | {product_id}")
    print(
        "Порог по возрасту Telegram: "
        f"{int(inspection.get('older_than_days') or 0)} дней."
    )
    if status == "not_found":
        print("Совпадения в Telegram не найдены.")
        return
    if status == "low_confidence":
        print("Найдены только слабые совпадения. Автодеактивация не выполнена.")
        best_match = inspection.get("best_match")
        if isinstance(best_match, dict):
            _print_telegram_search_matches(name, [best_match])
        return
    if status == "missing_message_date":
        print("Совпадение найдено, но у сообщения нет даты. Деактивация отменена.")
        best_match = inspection.get("best_match")
        if isinstance(best_match, dict):
            _print_telegram_search_matches(name, [best_match])
        return
    if status == "not_old_enough":
        best_match = inspection.get("best_match")
        if isinstance(best_match, dict):
            age_days = best_match.get("message_age_days")
            print(
                "Совпадение найдено, но товар в Telegram ещё недостаточно старый. "
                f"Возраст: {age_days} дней."
            )
            _print_telegram_search_matches(name, [best_match])
        return
    if status == "eligible":
        best_match = inspection.get("best_match")
        if isinstance(best_match, dict):
            age_days = best_match.get("message_age_days")
            print(
                "Совпадение найдено и подходит для деактивации. "
                f"Возраст сообщения в Telegram: {age_days} дней."
            )
            _print_telegram_search_matches(name, [best_match])
        return
    print("Не удалось определить состояние товара для деактивации.")


def _log_telegram_age_inspection(product: dict, inspection: dict) -> None:
    name = str(product.get("name") or "").strip() or "нет названия"
    product_id = str(product.get("product_id") or "").strip() or "нет id"
    threshold_days = int(inspection.get("older_than_days") or 0)
    status = str(inspection.get("status") or "")
    reason = str(inspection.get("decision_reason") or "").strip() or "-"
    shafa_created_at = _parse_datetime_text_utc(product.get("created_at"))
    shafa_age_days = _age_days_from_datetime(shafa_created_at)
    log(
        "INFO",
        "Проверяю возраст товара для деактивации. "
        f"name={name}. product_id={product_id}. "
        f"shafa_created_at={product.get('created_at') or '-'}. "
        f"shafa_age_days={_format_age_days(shafa_age_days)}. "
        f"threshold_days={threshold_days}.",
    )
    best_match = inspection.get("best_match")
    if isinstance(best_match, dict):
        telegram_age_days = best_match.get("message_age_days")
        log(
            "INFO",
            "Найдено совпадение в Telegram. "
            f"name={name}. product_id={product_id}. "
            f"channel_id={best_match.get('channel_id')}. "
            f"message_id={best_match.get('message_id')}. "
            f"telegram_created_at={best_match.get('telegram_message_date') or '-'}. "
            f"telegram_age_days={_format_age_days(float(telegram_age_days) if telegram_age_days is not None else None)}. "
            f"score={float(best_match.get('score') or 0.0):.2f}.",
        )
    if status == "eligible":
        log(
            "INFO",
            "Товар подходит под деактивацию по возрасту Telegram. "
            f"name={name}. product_id={product_id}. "
            f"telegram_age_days={_format_age_days(inspection.get('telegram_age_days'))}. "
            f"threshold_days={threshold_days}. "
            f"reason={reason}",
        )
        return
    level = "WARN" if status in {"not_found", "low_confidence", "missing_message_date"} else "INFO"
    log(
        level,
        "Товар не будет деактивирован. "
        f"name={name}. product_id={product_id}. "
        f"status={status or 'unknown'}. "
        f"telegram_age_days={_format_age_days(inspection.get('telegram_age_days'))}. "
        f"threshold_days={threshold_days}. "
        f"reason={reason}",
    )


def _deactivate_shafa_product_if_old_in_telegram() -> None:
    from controller.data_controller import inspect_shafa_product_telegram_age
    from core.requests.deactivate_product import deactivate_product

    product = _choose_active_shafa_product(limit=200)
    if product is None:
        return
    older_than_days = _prompt_int(
        "Деактивировать, если товар в Telegram старше скольких дней?",
        default=183,
        min_value=183,
    )
    if older_than_days is None:
        return
    inspection = inspect_shafa_product_telegram_age(
        str(product.get("name") or ""),
        older_than_days=older_than_days,
        per_channel_limit=5,
    )
    _log_telegram_age_inspection(product, inspection)
    _print_telegram_age_inspection(product, inspection)
    if not bool(inspection.get("eligible_for_deactivation")):
        return
    product_id = str(product.get("product_id") or "").strip()
    if not product_id:
        print("У товара Shafa отсутствует product_id.")
        return
    try:
        deactivate_product(product_id)
    except Exception as exc:
        log(
            "ERROR",
            "Не удалось деактивировать товар на Shafa. "
            f"name={product.get('name') or '-'}. product_id={product_id}. "
            f"telegram_age_days={_format_age_days(inspection.get('telegram_age_days'))}. "
            f"threshold_days={int(inspection.get('older_than_days') or 0)}. "
            f"error={exc}",
        )
        print(f"Не удалось деактивировать товар на Shafa: {exc}")
        return
    log(
        "OK",
        "Товар деактивирован на Shafa. "
        f"name={product.get('name') or '-'}. product_id={product_id}. "
        f"telegram_age_days={_format_age_days(inspection.get('telegram_age_days'))}. "
        f"threshold_days={int(inspection.get('older_than_days') or 0)}. "
        f"reason={inspection.get('decision_reason') or '-'}",
    )
    print(f"Товар деактивирован на Shafa: {product_id}.")


def _prompt_action_menu(
    title: str,
    actions: list[tuple[str, Callable[[], None]]],
    exit_label: str,
) -> Optional[Callable[[], None]]:
    choices: list[tuple[str, Any]] = [(label, action) for label, action in actions]
    if exit_label:
        choices.append((exit_label, None))
    return _prompt_list(title, choices)


def _add_telegram_channel() -> None:
    from data.db import save_telegram_channels

    channel_id = _prompt_int("ID Telegram-канала", required=True)
    if channel_id is None:
        return
    name = _prompt_text("Название канала", required=True)
    if not name:
        return
    alias = _prompt_text("Алиас (необязательно)") or None
    save_telegram_channels([(channel_id, name, alias)])
    print("Канал сохранен.")


def _list_telegram_channels() -> None:
    from data.db import load_telegram_channels

    channels = load_telegram_channels()
    if not channels:
        print("Telegram-каналы не настроены.")
        return
    print("Telegram-канал")
    for idx, row in enumerate(channels, start=1):
        alias = row.get("alias") or "-"
        print(f"{idx}. {row['channel_id']} | {row['name']} | {alias}")


def _format_channel_label(channel: dict) -> str:
    name = channel.get("name") or str(channel.get("channel_id") or "")
    alias = channel.get("alias")
    if alias:
        return f"{name} ({alias}) | {channel['channel_id']}"
    return f"{name} | {channel['channel_id']}"


def _delete_telegram_channel(channel: dict) -> None:
    from data.db import delete_telegram_channel

    label = _format_channel_label(channel)
    confirm = _choose_yes_no(f"Удалить канал {label}?", default=False)
    if confirm is None or not confirm:
        return
    delete_telegram_channel(channel["channel_id"])
    print("Канал удален.")


def _rename_telegram_channel(channel: dict) -> None:
    from data.db import rename_telegram_channel

    name = channel.get("name") or str(channel.get("channel_id") or "")
    raw = _prompt_text(f"Новое имя для {name}", required=True)
    if not raw:
        return
    if not rename_telegram_channel(channel["channel_id"], raw):
        print("Переименование не удалось.")
        return
    print("Канал переименован.")


def _change_telegram_channel_alias(channel: dict) -> None:
    from data.db import update_telegram_channel_alias

    name = channel.get("name") or str(channel.get("channel_id") or "")
    current = channel.get("alias") or "-"
    raw = _prompt_text(
        f"Новый алиас для {name} (пусто - удалить, текущий: {current}) "
    )
    if raw is None:
        return
    alias = raw or None
    if not update_telegram_channel_alias(channel["channel_id"], alias):
        print("Не удалось обновить алиас.")
        return
    print("Алиас обновлен.")


def _change_telegram_channel_id(channel: dict) -> None:
    from data.db import update_telegram_channel_id

    name = channel.get("name") or str(channel.get("channel_id") or "")
    current_id = channel.get("channel_id")
    new_id = _prompt_int(
        f"Новый ID канала для {name} (текущий: {current_id}) ",
        required=True,
    )
    if new_id is None:
        return
    if new_id == current_id:
        print("ID канала не изменен.")
        return
    if not update_telegram_channel_id(current_id, new_id):
        print("Не удалось обновить ID канала.")
        return
    print("ID канала обновлен.")


def _manage_telegram_channel_actions(channel: dict) -> None:
    actions = [
        ("Удалить канал", lambda: _delete_telegram_channel(channel)),
        ("Переименовать канал", lambda: _rename_telegram_channel(channel)),
        (
            "Изменить алиас (например, extra_photos)",
            lambda: _change_telegram_channel_alias(channel),
        ),
        ("Изменить ID", lambda: _change_telegram_channel_id(channel)),
    ]
    action = _prompt_action_menu("Что нужно сделать?", actions, "Назад")
    if action is None:
        return
    action()


def _manage_telegram_channels() -> None:
    from data.db import load_telegram_channels

    while True:
        channels = load_telegram_channels()
        choices: list[tuple[str, Any]] = [
            (_format_channel_label(row), row) for row in channels
        ]
        choices.append(("[ + ] Добавить Telegram-канал", _ADD_CHANNEL))
        choices.append(("Назад", None))
        selection = _prompt_list("Управление Telegram-каналами", choices)
        if selection is None:
            return
        if selection is _ADD_CHANNEL:
            _add_telegram_channel()
            continue
        _manage_telegram_channel_actions(selection)


def _clear_storage_state_cookies(path) -> bool:
    if not path.exists():
        return False
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return True
    if not isinstance(data, dict):
        data = {}
    data["cookies"] = []
    path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    return True


def _delete_account_cookies() -> None:
    from data.const import STORAGE_STATE_PATH
    from data.db import delete_all_cookies

    confirm = _choose_yes_no(
        "Удалить cookies аккаунта из БД и auth.json?",
        default=False,
    )
    if confirm is None or not confirm:
        return
    removed = delete_all_cookies()
    auth_updated = _clear_storage_state_cookies(STORAGE_STATE_PATH)
    if auth_updated:
        print(f"Удалено cookies: {removed}. auth.json обновлен.")
    else:
        print(f"Удалено cookies: {removed}. auth.json не найден.")


def _logout_and_reset_products() -> None:
    from data.const import STORAGE_STATE_PATH
    from data.db import delete_all_cookies, reset_telegram_products_created

    confirm = _choose_yes_no(
        "Выйти из аккаунта и вернуть все товары в очередь?",
        default=False,
    )
    if confirm is None or not confirm:
        return
    removed = delete_all_cookies()
    auth_updated = _clear_storage_state_cookies(STORAGE_STATE_PATH)
    reset_count = reset_telegram_products_created()
    if auth_updated:
        print(f"Удалено cookies: {removed}. auth.json обновлен.")
    else:
        print(f"Удалено cookies: {removed}. auth.json не найден.")
    print(f"Сброшено товаров: {reset_count}.")


def _product_management_menu() -> None:
    actions = [
        ("Создать товар", _create_product),
        ("Автосоздание товара", _auto_create_product),
        ("Список товаров", _print_products),
        ("Найти товар в Telegram по названию", _find_product_in_telegram_by_name),
        (
            "Найти в Telegram и деактивировать на Shafa, если товар старый",
            _deactivate_shafa_product_if_old_in_telegram,
        ),
    ]
    while True:
        action = _prompt_action_menu("Управление товарами", actions, "Назад")
        if action is None:
            return
        action()


def _settings_menu() -> None:
    actions = [
        ("Инициализация проекта", _bootstrap_project),
        ("Войти в аккаунт", _login_account),
        ("Управление Telegram-каналами", _manage_telegram_channels),
        ("Удалить cookies аккаунта", _delete_account_cookies),
        ("Выйти и вернуть товары в очередь", _logout_and_reset_products),
    ]
    while True:
        action = _prompt_action_menu("Настройки", actions, "Назад")
        if action is None:
            return
        action()


def _legacy_menu(actions: list[tuple[str, Callable[[], None]]]) -> None:
    while True:
        action = _prompt_action_menu("Выберите действие", actions, "Выход")
        if action is None:
            return
        action()


def main(
    actions: Optional[list[tuple[str, Callable[[], None]]]] = None,
    shafa: bool = False,
    login_shafa: bool = False,
    mode: Optional[str] = None,
    deactivate_old_products_once: bool = False,
    old_products_age_days: Optional[int] = None,
    old_products_limit: Optional[int] = None,
    old_products_sleep_seconds: Optional[float] = None,
    old_products_dry_run: bool = False,
    shared_deactivation_plan_once: bool = False,
    find_telegram_by_name: Optional[str] = None,
    telegram_send_code_phone: Optional[str] = None,
    telegram_login_phone: Optional[str] = None,
    telegram_login_code: Optional[str] = None,
    telegram_login_password: Optional[str] = None,
    telegram_session_status: bool = False,
) -> None:
    if mode:
        os.environ[APP_MODE_ENV] = mode
    account_id = str(os.getenv("SHAFA_ACCOUNT_ID") or "").strip() or "default"
    account_name = str(os.getenv("SHAFA_ACCOUNT_NAME") or "").strip() or account_id
    log(
        "INFO",
        "Runtime context initialized. "
        f"account={account_name}. account_id={account_id}. "
        f"db_path={os.getenv('SHAFA_DB_PATH', '')}. "
        f"telegram_db_path={os.getenv('SHAFA_SHARED_TELEGRAM_DB_PATH', '')}. "
        f"state_dir={os.getenv('SHAFA_ACCOUNT_STATE_DIR', '')}. "
        f"deactivator_disabled={_env_flag_enabled(DISABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR_ENV)}.",
    )
    log(
        "INFO",
        "Shared deactivation startup flags. "
        f"auto_run={_shared_deactivation_auto_run_enabled()}. "
        f"dry_run={_shared_deactivation_dry_run_enabled()}. "
        f"planner_enabled={_shared_deactivation_planner_enabled()}. "
        f"worker_enabled={_shared_deactivation_worker_enabled()}. "
        f"account_id={account_id}. "
        f"telegram_db_path={os.getenv('SHAFA_SHARED_TELEGRAM_DB_PATH', '')}.",
    )
    if deactivate_old_products_once:
        _deactivate_old_products_once(
            older_than_days=old_products_age_days,
            limit=old_products_limit,
            sleep_seconds=old_products_sleep_seconds,
            dry_run=old_products_dry_run,
        )
        return
    if shared_deactivation_plan_once:
        _shared_deactivation_plan_once()
        return
    if find_telegram_by_name:
        _find_product_in_telegram_by_name(find_telegram_by_name)
        return
    if login_shafa:
        _login_account()
        return
    if telegram_send_code_phone:
        send_code(telegram_send_code_phone)
        print("Код Telegram запрошен.")
        return
    if telegram_login_password:
        submit_password(telegram_login_password)
        print("Пароль Telegram подтверждён.")
        return
    if telegram_session_status:
        if session_status():
            print("Сессия Telegram авторизована.")
            return
        raise RuntimeError("Сессия Telegram отсутствует или не авторизована.")
    if telegram_login_phone and telegram_login_code:
        complete_login(telegram_login_phone, telegram_login_code)
        print("Вход в Telegram завершён.")
        return
    if shafa:
        _bootstrap_new_account_telegram_queue_if_needed()
        sync_channels_from_runtime_config()
        if _env_flag_enabled(DEACTIVATE_ONLY_ENV):
            if _env_flag_enabled(DISABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR_ENV):
                raise RuntimeError(
                    "SHAFA_DEACTIVATE_ONLY=1, но деактиватор отключён через "
                    f"{DISABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR_ENV}."
                )
            if _shared_deactivation_worker_enabled():
                log(
                    "INFO",
                    "Old direct deactivator skipped because shared worker is enabled.",
                )
                deactivate_stop_event, deactivate_thread = (
                    _start_background_shared_deactivation_worker()
                )
            else:
                deactivate_stop_event, deactivate_thread = (
                    _start_background_old_product_deactivator()
                )
            log(
                "INFO",
                "Запущен режим только деактивации. "
                "Создание товаров и фоновое сканирование Telegram отключены.",
            )
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
            finally:
                deactivate_stop_event.set()
                deactivate_thread.join(timeout=5)
            return

        os.environ["SHAFA_BACKGROUND_TELEGRAM_SCANNER"] = "1"
        stop_event, scanner_thread = _start_background_telegram_scanner()
        deactivate_stop_event = None
        deactivate_thread = None
        if _shared_deactivation_worker_enabled():
            deactivate_stop_event, deactivate_thread = (
                _start_background_shared_deactivation_worker()
            )
        if not _env_flag_enabled(DISABLE_ACCOUNT_OLD_PRODUCT_DEACTIVATOR_ENV):
            if _shared_deactivation_worker_enabled():
                log(
                    "INFO",
                    "Old direct deactivator skipped because shared worker is enabled.",
                )
            elif deactivate_thread is None:
                deactivate_stop_event, deactivate_thread = _start_background_old_product_deactivator()
        try:
            _auto_create_product(shafa=shafa)
        finally:
            stop_event.set()
            scanner_thread.join(timeout=5)
            if deactivate_stop_event is not None and deactivate_thread is not None:
                deactivate_stop_event.set()
                deactivate_thread.join(timeout=5)
        return

    _print_ascii_banner()
    if actions:
        _legacy_menu(actions)
        return

    actions = [
        ("Управление товарами", _product_management_menu),
        ("Настройки", _settings_menu),
    ]
    while True:
        action = _prompt_action_menu("Выберите действие", actions, "Выход")
        if action is None:
            return
        action()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shafa", action="store_true")
    parser.add_argument("--login-shafa", action="store_true")
    parser.add_argument("--mode", choices=["clothes", "sneakers"])
    parser.add_argument("--deactivate-old-products-once", action="store_true")
    parser.add_argument("--old-products-age-days", type=int)
    parser.add_argument("--old-products-limit", type=int)
    parser.add_argument("--old-products-sleep-seconds", type=float)
    parser.add_argument("--old-products-dry-run", action="store_true")
    parser.add_argument("--shared-deactivation-plan-once", action="store_true")
    parser.add_argument("--find-telegram-by-name")
    parser.add_argument("--telegram-send-code")
    parser.add_argument("--telegram-login-phone")
    parser.add_argument("--telegram-login-code")
    parser.add_argument("--telegram-login-password")
    parser.add_argument("--telegram-session-status", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        main(
            shafa=args.shafa,
            login_shafa=args.login_shafa,
            mode=args.mode,
            deactivate_old_products_once=args.deactivate_old_products_once,
            old_products_age_days=args.old_products_age_days,
            old_products_limit=args.old_products_limit,
            old_products_sleep_seconds=args.old_products_sleep_seconds,
            old_products_dry_run=args.old_products_dry_run,
            shared_deactivation_plan_once=args.shared_deactivation_plan_once,
            find_telegram_by_name=args.find_telegram_by_name,
            telegram_send_code_phone=args.telegram_send_code,
            telegram_login_phone=args.telegram_login_phone,
            telegram_login_code=args.telegram_login_code,
            telegram_login_password=args.telegram_login_password,
            telegram_session_status=args.telegram_session_status,
        )
    except Exception as exc:
        print(str(exc) or exc.__class__.__name__, file=sys.stderr)
        raise SystemExit(1) from None
