import argparse
import concurrent.futures
from contextlib import redirect_stdout
from io import StringIO
import json
import os
import sys
import random
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True)
class ProductCandidate:
    product_id: str
    name: str
    product_date: date
    price: object = None
    url: str = ""


@dataclass(frozen=True)
class AccountSession:
    account_id: str
    name: str
    state_dir: Path
    auth_path: Path
    db_path: Path
    media_dir: Path
    accounts_dir: Optional[Path] = None


def parse_cli_date(value: object) -> date:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Дата обязательна")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Дата должна быть в формате YYYY-MM-DD") from exc


def parse_shafa_date(value: object) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def product_sale_label_date(product: dict) -> Optional[date]:
    sale_label = product.get("saleLabel") or {}
    if not isinstance(sale_label, dict):
        return None
    return parse_shafa_date(sale_label.get("date"))


def fetch_active_products(
    *,
    page_size: int = 50,
    feed_func: Optional[Callable[..., dict]] = None,
) -> list[dict]:
    if feed_func is None:
        from core.requests.get_my_clothes_products_feed import (
            get_my_clothes_products_feed,
        )

        feed_func = get_my_clothes_products_feed

    normalized_page_size = max(int(page_size), 1)
    products: list[dict] = []
    seen_ids: set[str] = set()
    after: Optional[str] = None

    while True:
        feed = feed_func(
            first=normalized_page_size,
            products_type="ACTIVE",
            after=after,
        )
        if not feed:
            raise RuntimeError("Не удалось загрузить активные товары Shafa.")

        errors = feed.get("errors") or []
        if errors:
            raise RuntimeError(f"Shafa вернула GraphQL errors: {errors}")

        edges = feed.get("edges") or []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            node = edge.get("node") or {}
            if not isinstance(node, dict):
                continue
            product_id = str(node.get("id") or "").strip()
            if not product_id or product_id in seen_ids:
                continue
            seen_ids.add(product_id)
            products.append(node)

        page_info = feed.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break

        next_after = str(page_info.get("endCursor") or "").strip() or None
        if next_after is None or next_after == after:
            break
        after = next_after

    if _debug_auth_enabled():
        print(f"Активных товаров Shafa всего: {len(products)}")
        for index, product in enumerate(products[:5], start=1):
            product_id = str(product.get("id") or "").strip() or "нет id"
            name = str(product.get("name") or "").strip() or "без названия"
            print(f"  sample {index}: {product_id} | {name}")

    return products


def select_products_for_deactivation(
    products: list[dict],
    *,
    start_date: date,
    end_date: date,
) -> list[ProductCandidate]:
    if start_date > end_date:
        raise ValueError("Дата начала не может быть позже даты конца")

    candidates: list[ProductCandidate] = []
    for product in products:
        product_date = product_sale_label_date(product)
        if product_date is None or product_date < start_date or product_date > end_date:
            continue
        product_id = str(product.get("id") or "").strip()
        if not product_id:
            continue
        candidates.append(
            ProductCandidate(
                product_id=product_id,
                name=str(product.get("name") or "").strip() or "без названия",
                product_date=product_date,
                price=product.get("price"),
                url=str(product.get("url") or "").strip(),
            )
        )
    return candidates


def print_candidates(candidates: list[ProductCandidate]) -> None:
    for index, candidate in enumerate(candidates, start=1):
        price = "" if candidate.price is None else f" | price={candidate.price}"
        url = "" if not candidate.url else f" | {candidate.url}"
        print(
            f"{index}. {candidate.product_date.isoformat()} | "
            f"{candidate.product_id} | {candidate.name}{price}{url}"
        )


def deactivate_candidates(
    candidates: list[ProductCandidate],
    *,
    deactivate_func: Optional[Callable[[str], None]] = None,
    mark_inactive_func: Optional[Callable[..., bool]] = None,
    sleep_min_seconds: float = 10.0,
    sleep_max_seconds: float = 15.0,
    on_candidate_processed: Optional[Callable[[ProductCandidate, bool], None]] = None,
    account_name: str = "",
    progress_every: int = 1,
    verify_deactivation_flow: bool = False,
) -> dict[str, int]:
    if deactivate_func is None and not verify_deactivation_flow:
        from core.requests.deactivate_product import deactivate_product

        deactivate_func = deactivate_product
    if mark_inactive_func is None and not verify_deactivation_flow:
        from data.db import mark_uploaded_product_inactive

        mark_inactive_func = mark_uploaded_product_inactive

    deactivated = 0
    failed = 0
    mark_failed = 0
    sleep_min = max(float(sleep_min_seconds), 0.0)
    sleep_max = max(float(sleep_max_seconds), 0.0)
    normalized_progress_every = max(int(progress_every), 1)
    progress_account_name = str(account_name or os.getenv("SHAFA_ACCOUNT_NAME") or "").strip()
    progress_prefix = f"[{progress_account_name}] " if progress_account_name else ""

    if candidates:
        print(
            f"First deactivation attempt for account {progress_account_name or 'current'}",
            flush=True,
        )

    for index, candidate in enumerate(candidates, start=1):
        should_print_progress = (
            index == 1
            or index == len(candidates)
            or index % normalized_progress_every == 0
        )
        if should_print_progress:
            print(
                f"{progress_prefix}[{index}/{len(candidates)}] "
                f"Deactivating {candidate.product_id} | {candidate.name}",
                flush=True,
            )
        success = False
        try:
            if verify_deactivation_flow:
                time.sleep(0.1)
            else:
                if deactivate_func is None:
                    raise RuntimeError("deactivate_func is not configured")
                deactivate_func(candidate.product_id)
        except Exception as exc:
            failed += 1
            print(
                f"{progress_prefix}ERROR {candidate.product_id}: {exc}",
                flush=True,
            )
        else:
            deactivated += 1
            if not verify_deactivation_flow:
                try:
                    if mark_inactive_func is None:
                        raise RuntimeError("mark_inactive_func is not configured")
                    mark_inactive_func(
                        candidate.product_id,
                        status_title="Деактивовано",
                    )
                except Exception as exc:
                    mark_failed += 1
                    print(
                        f"{progress_prefix}WARN {candidate.product_id}: "
                        f"товар деактивирован, но локальная БД не обновлена: {exc}",
                        flush=True,
                    )
                else:
                    if should_print_progress:
                        print(
                            f"{progress_prefix}OK {candidate.product_id}",
                            flush=True,
                        )
            else:
                if should_print_progress:
                    print(
                        f"{progress_prefix}OK simulated {candidate.product_id}",
                        flush=True,
                    )
            success = True

        if on_candidate_processed is not None:
            on_candidate_processed(candidate, success)

        if index < len(candidates):
            delay = 0.1 if verify_deactivation_flow else random.uniform(sleep_min, sleep_max)
            if should_print_progress:
                print(
                    f"{progress_prefix}Sleeping {delay:.1f} seconds before next product",
                    flush=True,
                )
            time.sleep(delay)

    return {
        "deactivated": deactivated,
        "failed": failed,
        "mark_failed": mark_failed,
    }


def prompt_date(label: str) -> date:
    while True:
        try:
            return parse_cli_date(input(f"{label} (YYYY-MM-DD): "))
        except ValueError as exc:
            print(exc)


def confirm_deactivation(count: int) -> bool:
    answer = input(
        f"Деактивировать {count} товаров? Введите yes или да для подтверждения: "
    )
    return answer.strip().lower() in {"yes", "да"}


def _debug_auth_enabled() -> bool:
    return os.getenv("SHAFA_DEBUG_AUTH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolved_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _has_shafa_csrftoken(auth_path: Path) -> bool:
    payload = _load_json(auth_path)
    if not isinstance(payload, dict):
        return False
    cookies = payload.get("cookies") or []
    if not isinstance(cookies, list):
        return False
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        domain = str(cookie.get("domain") or "").strip().lstrip(".").lower()
        value = cookie.get("value")
        if (
            name == "csrftoken"
            and isinstance(value, str)
            and value.strip()
            and (domain == "shafa.ua" or domain.endswith(".shafa.ua"))
        ):
            return True
    return False


def is_valid_accounts_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(child.is_file() for child in path.glob("*/account.json"))


def find_accounts_dirs_under(root: Path, max_depth: int = 6) -> list[Path]:
    root = _resolved_path(root)
    if not root.exists() or not root.is_dir():
        return []

    found: list[Path] = []
    visited: set[Path] = set()

    def _walk(current: Path, depth: int) -> None:
        if current.is_symlink():
            return
        resolved = _resolved_path(current)
        if resolved in visited:
            return
        visited.add(resolved)

        if current.name == "accounts" and is_valid_accounts_dir(current):
            found.append(resolved)

        if depth >= max_depth:
            return

        try:
            children = sorted(current.iterdir(), key=lambda item: str(item).lower())
        except OSError:
            return

        for child in children:
            try:
                if child.is_dir() and not child.is_symlink():
                    _walk(child, depth + 1)
            except OSError:
                continue

    _walk(root, 0)
    return found


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        resolved = _resolved_path(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _fallback_accounts_search_roots() -> list[tuple[Path, int]]:
    script_dir = Path(__file__).resolve().parent
    bases = [Path.cwd(), script_dir]
    roots: list[tuple[Path, int]] = []
    seen: set[Path] = set()
    home = _resolved_path(Path.home())

    for base in bases:
        current = _resolved_path(base)
        for _ in range(3):
            if current in seen:
                if current == home or current.parent == current:
                    break
                current = current.parent
                continue
            seen.add(current)
            max_depth = 6
            if current == home:
                max_depth = 2
            roots.append((current, max_depth))
            if current == home or current.parent == current:
                break
            current = current.parent

    return roots


def find_all_accounts_dirs(
    accounts_dirs: Optional[list[str | Path]] = None,
    accounts_search_roots: Optional[list[str | Path]] = None,
) -> list[Path]:
    found: list[Path] = []

    for raw_dir in accounts_dirs or []:
        accounts_dir = _resolved_path(Path(raw_dir))
        if is_valid_accounts_dir(accounts_dir):
            found.append(accounts_dir)
        else:
            print(f"WARN: accounts folder is invalid or empty: {accounts_dir}")

    for raw_root in accounts_search_roots or []:
        root = _resolved_path(Path(raw_root))
        if not root.exists() or not root.is_dir():
            print(f"WARN: accounts search root is invalid: {root}")
            continue
        found.extend(find_accounts_dirs_under(root))

    if not accounts_dirs and not accounts_search_roots:
        for root, max_depth in _fallback_accounts_search_roots():
            found.extend(find_accounts_dirs_under(root, max_depth=max_depth))

    deduped = _dedupe_paths(found)
    if not deduped:
        raise RuntimeError(
            "Не нашёл ни одной папки accounts с account.json. "
            "Укажи --accounts-dir или --accounts-search-root."
        )
    return deduped


def _session_auth_path(payload: dict, state_dir: Path) -> Path:
    raw_path = (
        payload.get("shafa_session_path")
        or payload.get("browser_session_path")
        or state_dir / "auth.json"
    )
    auth_path = Path(str(raw_path))
    if not auth_path.is_absolute():
        auth_path = state_dir / auth_path
    return _resolved_path(auth_path)


def list_account_sessions(
    accounts_dirs: Optional[list[str | Path]] = None,
    accounts_search_roots: Optional[list[str | Path]] = None,
) -> list[AccountSession]:
    discovered_accounts_dirs = find_all_accounts_dirs(
        accounts_dirs=accounts_dirs,
        accounts_search_roots=accounts_search_roots,
    )
    sessions: list[AccountSession] = []
    seen_sessions: set[tuple[str, Path]] = set()
    for accounts_dir in discovered_accounts_dirs:
        for account_file in sorted(accounts_dir.glob("*/account.json")):
            payload = _load_json(account_file)
            if not isinstance(payload, dict):
                continue
            account_id = str(payload.get("id") or account_file.parent.name).strip()
            if not account_id:
                continue
            name = str(payload.get("name") or account_id).strip()
            state_dir = _resolved_path(account_file.parent)
            auth_path = _session_auth_path(payload, state_dir)
            db_path = state_dir / "shafa.sqlite3"
            if not auth_path.exists() or not _has_shafa_csrftoken(auth_path):
                continue
            session_key = (account_id, auth_path)
            if session_key in seen_sessions:
                continue
            seen_sessions.add(session_key)
            session = AccountSession(
                account_id=account_id,
                name=name,
                state_dir=state_dir,
                auth_path=auth_path,
                db_path=db_path,
                media_dir=state_dir / "media",
                accounts_dir=accounts_dir,
            )
            sessions.append(session)
            print(
                "Loaded Shafa session: "
                f"{session.name} | {session.account_id} | folder: {accounts_dir}"
            )
    return sessions


def _find_account_session(
    sessions: list[AccountSession],
    selector: str,
) -> AccountSession:
    normalized = str(selector or "").strip()
    if not normalized:
        raise ValueError("account_id is required")

    exact = [
        account
        for account in sessions
        if account.account_id == normalized or account.name == normalized
    ]
    if len(exact) == 1:
        return exact[0]

    prefix = [
        account
        for account in sessions
        if account.account_id.startswith(normalized)
    ]
    if len(prefix) == 1:
        return prefix[0]

    available = ", ".join(
        f"{account.name} ({account.account_id})" for account in sessions
    )
    if exact or prefix:
        raise RuntimeError(f"Аккаунт задан неоднозначно. Доступны: {available}")
    raise RuntimeError(f"Аккаунт не найден. Доступны: {available}")


def _prompt_account_session(sessions: list[AccountSession]) -> AccountSession:
    print("Найдено несколько сохранённых Shafa-сессий. Выберите аккаунт:")
    for index, account in enumerate(sessions, start=1):
        folder = account.accounts_dir or account.state_dir.parent
        print(f"{index}. {account.name} | {account.account_id} | {folder}")
    while True:
        raw = input("Номер аккаунта: ").strip()
        if raw.lower() in {"q", "quit", "exit", "отмена"}:
            raise RuntimeError("Отменено.")
        try:
            index = int(raw)
        except ValueError:
            print("Введите номер из списка.")
            continue
        if 1 <= index <= len(sessions):
            return sessions[index - 1]
        print("Введите номер из списка.")


def _apply_account_environment(selected: AccountSession) -> None:
    os.environ["SHAFA_ACCOUNT_ID"] = selected.account_id
    os.environ["SHAFA_ACCOUNT_NAME"] = selected.name
    os.environ["SHAFA_ACCOUNT_STATE_DIR"] = str(selected.state_dir)
    os.environ["SHAFA_STORAGE_STATE_PATH"] = str(selected.auth_path)
    os.environ["SHAFA_DB_PATH"] = str(selected.db_path)
    os.environ["SHAFA_MEDIA_DIR_PATH"] = str(selected.media_dir)
    os.environ["SHAFA_SHARED_TELEGRAM_DB_PATH"] = str(
        project_root() / "telegram_shared" / "telegram_feed.sqlite3"
    )


def configure_account_environment(
    account_id: Optional[str] = None,
    accounts_dirs: Optional[list[str | Path]] = None,
    accounts_search_roots: Optional[list[str | Path]] = None,
) -> Optional[AccountSession]:
    configured_storage_path = str(os.getenv("SHAFA_STORAGE_STATE_PATH") or "").strip()
    if configured_storage_path:
        auth_path = Path(configured_storage_path)
        if auth_path.exists() and _has_shafa_csrftoken(auth_path):
            return None
        raise RuntimeError(
            "SHAFA_STORAGE_STATE_PATH задан, но auth.json не найден "
            "или не содержит csrftoken Shafa."
        )

    sessions = list_account_sessions(
        accounts_dirs=accounts_dirs,
        accounts_search_roots=accounts_search_roots,
    )
    if not sessions:
        raise RuntimeError(
            "Не нашёл сохранённые cookies Shafa. Войди в аккаунт через desktop UI "
            "или через `./venv/bin/python shafa_logic/main.py`."
        )

    selector = str(account_id or os.getenv("SHAFA_ACCOUNT_ID") or "").strip()
    if selector:
        selected = _find_account_session(sessions, selector)
    elif len(sessions) == 1:
        selected = sessions[0]
    elif sys.stdin.isatty():
        selected = _prompt_account_session(sessions)
    else:
        available = ", ".join(
            f"{account.name} ({account.account_id})" for account in sessions
        )
        raise RuntimeError(
            "Найдено несколько Shafa-сессий. Запусти скрипт с --account-id. "
            f"Доступны: {available}"
        )

    _apply_account_environment(selected)
    return selected


def collect_current_account_candidates(
    start_date: date,
    end_date: date,
    page_size: int,
) -> list[ProductCandidate]:
    print("Загружаю ACTIVE товары Shafa...")
    products = fetch_active_products(page_size=page_size)
    candidates = select_products_for_deactivation(
        products,
        start_date=start_date,
        end_date=end_date,
    )
    print(
        f"Загружено активных товаров: {len(products)}. "
        f"Кандидатов по saleLabel.date: {len(candidates)}."
    )
    return candidates


def process_current_account(
    start_date: date,
    end_date: date,
    page_size: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    dry_run: bool,
    yes: bool,
    candidates: Optional[list[ProductCandidate]] = None,
    on_candidate_processed: Optional[Callable[[ProductCandidate, bool], None]] = None,
    account_name: str = "",
    progress_every: int = 1,
    verify_deactivation_flow: bool = False,
    print_candidate_list: bool = True,
) -> dict[str, int]:
    if candidates is None:
        candidates = collect_current_account_candidates(
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
        )
    else:
        print(f"Кандидатов по saleLabel.date: {len(candidates)}.")

    if not candidates:
        return {"deactivated": 0, "failed": 0, "mark_failed": 0}

    if print_candidate_list:
        print_candidates(candidates)
    if dry_run:
        print("dry-run: деактивация не выполнялась.")
        return {"deactivated": 0, "failed": 0, "mark_failed": 0}

    if not verify_deactivation_flow and not yes and not confirm_deactivation(len(candidates)):
        print("Отменено.")
        return {"deactivated": 0, "failed": 0, "mark_failed": 0}

    result = deactivate_candidates(
        candidates,
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        on_candidate_processed=on_candidate_processed,
        account_name=account_name,
        progress_every=progress_every,
        verify_deactivation_flow=verify_deactivation_flow,
    )
    print(
        "Готово. "
        f"Деактивировано: {result['deactivated']}. "
        f"Ошибок: {result['failed']}. "
        f"Ошибок локальной отметки: {result['mark_failed']}."
    )
    return result


def _account_folder(session: AccountSession) -> Path:
    return session.accounts_dir or session.state_dir.parent


def _session_to_data(session: AccountSession) -> dict[str, Optional[str]]:
    return {
        "account_id": session.account_id,
        "name": session.name,
        "state_dir": str(session.state_dir),
        "auth_path": str(session.auth_path),
        "db_path": str(session.db_path),
        "media_dir": str(session.media_dir),
        "accounts_dir": str(session.accounts_dir) if session.accounts_dir else None,
    }


def _session_from_data(data: dict[str, Optional[str]]) -> AccountSession:
    accounts_dir = data.get("accounts_dir")
    return AccountSession(
        account_id=str(data["account_id"]),
        name=str(data["name"]),
        state_dir=Path(str(data["state_dir"])),
        auth_path=Path(str(data["auth_path"])),
        db_path=Path(str(data["db_path"])),
        media_dir=Path(str(data["media_dir"])),
        accounts_dir=Path(accounts_dir) if accounts_dir else None,
    )


def _candidate_to_data(candidate: ProductCandidate) -> dict[str, object]:
    return {
        "product_id": candidate.product_id,
        "name": candidate.name,
        "product_date": candidate.product_date.isoformat(),
        "price": candidate.price,
        "url": candidate.url,
    }


def _candidate_from_data(data: dict[str, object]) -> ProductCandidate:
    return ProductCandidate(
        product_id=str(data["product_id"]),
        name=str(data["name"]),
        product_date=parse_cli_date(data["product_date"]),
        price=data.get("price"),
        url=str(data.get("url") or ""),
    )


def collect_account_candidates_worker(
    session_data: dict[str, Optional[str]],
    start_date: date,
    end_date: date,
    page_size: int,
) -> dict[str, object]:
    output = StringIO()
    try:
        with redirect_stdout(output):
            session = _session_from_data(session_data)
            _apply_account_environment(session)
            candidates = collect_current_account_candidates(
                start_date=start_date,
                end_date=end_date,
                page_size=page_size,
            )
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "candidates": [],
            "candidate_count": 0,
            "log": output.getvalue(),
        }
    return {
        "ok": True,
        "error": "",
        "candidates": [_candidate_to_data(candidate) for candidate in candidates],
        "candidate_count": len(candidates),
        "log": output.getvalue(),
    }


def process_account_worker(
    session_data: dict[str, Optional[str]],
    start_date: date,
    end_date: date,
    page_size: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    dry_run: bool,
    yes: bool,
    candidates_data: list[dict[str, object]],
    progress_every: int,
    verify_deactivation_flow: bool,
) -> dict[str, object]:
    processed_count = 0
    try:
        session = _session_from_data(session_data)
        _apply_account_environment(session)
        candidates = [
            _candidate_from_data(candidate_data)
            for candidate_data in candidates_data
        ]
        if verify_deactivation_flow:
            candidates = candidates[:3]
        print(
            f"Worker started for account {session.name} with {len(candidates)} candidates",
            flush=True,
        )

        def _count_processed(
            candidate: ProductCandidate,
            success: bool,
        ) -> None:
            nonlocal processed_count
            processed_count += 1

        result = process_current_account(
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            sleep_min_seconds=sleep_min_seconds,
            sleep_max_seconds=sleep_max_seconds,
            dry_run=dry_run,
            yes=yes,
            candidates=candidates,
            on_candidate_processed=_count_processed,
            account_name=session.name,
            progress_every=progress_every,
            verify_deactivation_flow=verify_deactivation_flow,
            print_candidate_list=False,
        )
        print(
            f"Worker finished for account {session.name}: "
            f"deactivated={result['deactivated']} "
            f"failed={result['failed']} mark_failed={result['mark_failed']}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"Worker failed for account {session_data.get('name')}: {exc}",
            flush=True,
        )
        return {
            "ok": False,
            "error": str(exc),
            "processed_count": processed_count,
            "deactivated": 0,
            "failed": 0,
            "mark_failed": 0,
            "log": "",
        }
    return {
        "ok": True,
        "error": "",
        "processed_count": processed_count,
        "deactivated": result["deactivated"],
        "failed": result["failed"],
        "mark_failed": result["mark_failed"],
        "log": "",
    }


def _print_account_header(
    index: int,
    total: int,
    session: AccountSession,
    *,
    phase: str = "",
) -> None:
    phase_text = f" | {phase}" if phase else ""
    print(
        f"=== [{index}/{total}] Account: "
        f"{session.name} | {session.account_id} | folder: {_account_folder(session)}"
        f"{phase_text} ==="
    )


def _clamped_workers(max_workers: int, session_count: int) -> int:
    return max(1, min(int(max_workers), max(session_count, 1)))


def _collect_all_account_candidates_sequential(
    sessions: list[AccountSession],
    start_date: date,
    end_date: date,
    page_size: int,
) -> tuple[list[tuple[AccountSession, list[ProductCandidate]]], int]:
    collected: list[tuple[AccountSession, list[ProductCandidate]]] = []
    accounts_failed = 0
    for index, session in enumerate(sessions, start=1):
        _print_account_header(index, len(sessions), session, phase="collection")
        try:
            _apply_account_environment(session)
            candidates = collect_current_account_candidates(
                start_date=start_date,
                end_date=end_date,
                page_size=page_size,
            )
        except Exception as exc:
            accounts_failed += 1
            print(f"ERROR: account collection failed: {exc}")
            continue
        print(f"Кандидатов для аккаунта: {len(candidates)}")
        collected.append((session, candidates))
    return collected, accounts_failed


def _collect_all_account_candidates_parallel(
    sessions: list[AccountSession],
    start_date: date,
    end_date: date,
    page_size: int,
    max_workers: int,
) -> tuple[list[tuple[AccountSession, list[ProductCandidate]]], int]:
    collected: list[tuple[AccountSession, list[ProductCandidate]]] = []
    accounts_failed = 0
    worker_count = _clamped_workers(max_workers, len(sessions))
    future_to_session: dict[concurrent.futures.Future, tuple[int, AccountSession]] = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
        for index, session in enumerate(sessions, start=1):
            future = executor.submit(
                collect_account_candidates_worker,
                _session_to_data(session),
                start_date,
                end_date,
                page_size,
            )
            future_to_session[future] = (index, session)

        for future in concurrent.futures.as_completed(future_to_session):
            index, session = future_to_session[future]
            _print_account_header(index, len(sessions), session, phase="collection")
            try:
                result = future.result()
            except Exception as exc:
                accounts_failed += 1
                print(f"ERROR: account collection failed: {exc}")
                continue

            log_text = str(result.get("log") or "")
            if log_text:
                print(log_text, end="" if log_text.endswith("\n") else "\n")
            if not result.get("ok"):
                accounts_failed += 1
                print(f"ERROR: account collection failed: {result.get('error')}")
                continue
            candidates = result.get("candidates")
            if not isinstance(candidates, list):
                candidates = []
            candidates = [
                _candidate_from_data(candidate)
                for candidate in candidates
                if isinstance(candidate, dict)
            ]
            print(f"Кандидатов для аккаунта: {len(candidates)}")
            collected.append((session, candidates))
    return collected, accounts_failed


def _print_all_account_summary(
    *,
    accounts_folders_count: int,
    accounts_processed: int,
    accounts_failed: int,
    total_candidates: int,
    total_deactivated: int,
    total_failed: int,
    total_mark_failed: int,
    remaining: int,
) -> None:
    print(
        "Summary. "
        f"Accounts folders found: {accounts_folders_count}. "
        f"Accounts processed: {accounts_processed}. "
        f"Accounts failed: {accounts_failed}. "
        f"Total candidates: {total_candidates}. "
        f"Total deactivated: {total_deactivated}. "
        f"Total failed: {total_failed}. "
        f"Total local mark_failed: {total_mark_failed}. "
        f"Remaining: {remaining}."
    )


def _print_deactivation_time_estimate(
    collected: list[tuple[AccountSession, list[ProductCandidate]]],
    *,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    parallel_accounts: bool,
    max_workers: int,
) -> None:
    average_sleep = (max(float(sleep_min_seconds), 0.0) + max(float(sleep_max_seconds), 0.0)) / 2
    total_candidates = sum(len(candidates) for _, candidates in collected)
    if total_candidates <= 0:
        return
    account_estimates = [
        max(len(candidates) - 1, 0) * average_sleep
        for _, candidates in collected
    ]
    if parallel_accounts:
        worker_count = _clamped_workers(max_workers, len(collected))
        worker_loads = [0.0 for _ in range(worker_count)]
        for estimate in sorted(account_estimates, reverse=True):
            lightest_index = min(range(worker_count), key=lambda index: worker_loads[index])
            worker_loads[lightest_index] += estimate
        total_seconds = max(worker_loads) if worker_loads else 0.0
    else:
        total_seconds = sum(account_estimates)
    print(
        "Estimated deactivation time from sleep only: "
        f"~{total_seconds / 3600:.1f} hours "
        f"(avg sleep {average_sleep:.1f}s, candidates {total_candidates})."
    )
    if total_candidates > 1000:
        print(
            "WARNING: this may take many hours because each product has random sleep."
        )


def process_all_accounts(
    *,
    accounts_folders_count: int,
    sessions: list[AccountSession],
    start_date: date,
    end_date: date,
    page_size: int,
    sleep_min_seconds: float,
    sleep_max_seconds: float,
    dry_run: bool,
    yes: bool,
    parallel_accounts: bool,
    max_workers: int,
    progress_every: int,
    verify_deactivation_flow: bool,
) -> None:
    if parallel_accounts:
        collected, accounts_failed = _collect_all_account_candidates_parallel(
            sessions=sessions,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            max_workers=max_workers,
        )
    else:
        collected, accounts_failed = _collect_all_account_candidates_sequential(
            sessions=sessions,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
        )

    total_candidates = sum(len(candidates) for _, candidates in collected)
    remaining = total_candidates
    print(f"Всего товаров к деактивации по всем аккаунтам: {total_candidates}")
    _print_deactivation_time_estimate(
        collected,
        sleep_min_seconds=sleep_min_seconds,
        sleep_max_seconds=sleep_max_seconds,
        parallel_accounts=parallel_accounts,
        max_workers=max_workers,
    )

    if dry_run:
        for index, (session, candidates) in enumerate(collected, start=1):
            _print_account_header(index, len(collected), session, phase="dry-run")
            print_candidates(candidates)
        _print_all_account_summary(
            accounts_folders_count=accounts_folders_count,
            accounts_processed=len(collected),
            accounts_failed=accounts_failed,
            total_candidates=total_candidates,
            total_deactivated=0,
            total_failed=0,
            total_mark_failed=0,
            remaining=remaining,
        )
        return

    if total_candidates == 0:
        _print_all_account_summary(
            accounts_folders_count=accounts_folders_count,
            accounts_processed=len(collected),
            accounts_failed=accounts_failed,
            total_candidates=total_candidates,
            total_deactivated=0,
            total_failed=0,
            total_mark_failed=0,
            remaining=remaining,
        )
        return

    if not verify_deactivation_flow and not yes and not confirm_deactivation(total_candidates):
        print("Отменено.")
        _print_all_account_summary(
            accounts_folders_count=accounts_folders_count,
            accounts_processed=len(collected),
            accounts_failed=accounts_failed,
            total_candidates=total_candidates,
            total_deactivated=0,
            total_failed=0,
            total_mark_failed=0,
            remaining=remaining,
        )
        return

    total_deactivated = 0
    total_failed = 0
    total_mark_failed = 0

    if parallel_accounts:
        worker_count = _clamped_workers(max_workers, len(collected))
        processed_candidates = 0
        completed_accounts = 0
        future_to_session: dict[
            concurrent.futures.Future,
            tuple[int, AccountSession],
        ] = {}
        with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
            for index, (session, candidates) in enumerate(collected, start=1):
                submitted_count = min(len(candidates), 3) if verify_deactivation_flow else len(candidates)
                print(
                    f"Submitting account {session.name} with {submitted_count} candidates",
                    flush=True,
                )
                future = executor.submit(
                    process_account_worker,
                    _session_to_data(session),
                    start_date,
                    end_date,
                    page_size,
                    sleep_min_seconds,
                    sleep_max_seconds,
                    False,
                    True,
                    [_candidate_to_data(candidate) for candidate in candidates],
                    progress_every,
                    verify_deactivation_flow,
                )
                future_to_session[future] = (index, session)

            for future in concurrent.futures.as_completed(future_to_session):
                index, session = future_to_session[future]
                completed_accounts += 1
                _print_account_header(
                    index,
                    len(collected),
                    session,
                    phase="deactivation",
                )
                try:
                    result = future.result()
                except Exception as exc:
                    accounts_failed += 1
                    remaining = max(total_candidates - processed_candidates, 0)
                    print(f"ERROR: account failed: {exc}")
                    print(
                        "Глобально обработано аккаунтов: "
                        f"{completed_accounts}/{len(collected)}. "
                        f"Осталось товаров примерно: {remaining}"
                    )
                    continue

                log_text = str(result.get("log") or "")
                if log_text:
                    print(log_text, end="" if log_text.endswith("\n") else "\n")
                processed_count = int(result.get("processed_count") or 0)
                processed_candidates += processed_count
                if not result.get("ok"):
                    accounts_failed += 1
                    remaining = max(total_candidates - processed_candidates, 0)
                    print(f"ERROR: account failed: {result.get('error')}")
                    print(
                        "Глобально обработано аккаунтов: "
                        f"{completed_accounts}/{len(collected)}. "
                        f"Осталось товаров примерно: {remaining}"
                    )
                    continue

                total_deactivated += int(result.get("deactivated") or 0)
                total_failed += int(result.get("failed") or 0)
                total_mark_failed += int(result.get("mark_failed") or 0)
                remaining = max(total_candidates - processed_candidates, 0)
                print(
                    "Глобально обработано аккаунтов: "
                    f"{completed_accounts}/{len(collected)}. "
                    f"Осталось товаров примерно: {remaining}"
                )
    else:
        for index, (session, candidates) in enumerate(collected, start=1):
            _print_account_header(index, len(collected), session, phase="deactivation")

            def _decrement_remaining(
                candidate: ProductCandidate,
                success: bool,
            ) -> None:
                nonlocal remaining
                remaining = max(remaining - 1, 0)
                print(f"Осталось товаров к деактивации: {remaining}")

            try:
                _apply_account_environment(session)
                effective_candidates = candidates[:3] if verify_deactivation_flow else candidates
                result = process_current_account(
                    start_date=start_date,
                    end_date=end_date,
                    page_size=page_size,
                    sleep_min_seconds=sleep_min_seconds,
                    sleep_max_seconds=sleep_max_seconds,
                    dry_run=False,
                    yes=True,
                    candidates=effective_candidates,
                    on_candidate_processed=_decrement_remaining,
                    account_name=session.name,
                    progress_every=progress_every,
                    verify_deactivation_flow=verify_deactivation_flow,
                    print_candidate_list=False,
                )
            except Exception as exc:
                accounts_failed += 1
                print(f"ERROR: account failed: {exc}")
                continue
            total_deactivated += result["deactivated"]
            total_failed += result["failed"]
            total_mark_failed += result["mark_failed"]

    _print_all_account_summary(
        accounts_folders_count=accounts_folders_count,
        accounts_processed=len(collected),
        accounts_failed=accounts_failed,
        total_candidates=total_candidates,
        total_deactivated=total_deactivated,
        total_failed=total_failed,
        total_mark_failed=total_mark_failed,
        remaining=remaining,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Деактивирует активные товары Shafa по диапазону saleLabel.date."
        )
    )
    parser.add_argument("--from-date", help="Дата начала в формате YYYY-MM-DD")
    parser.add_argument("--to-date", help="Дата конца в формате YYYY-MM-DD")
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--sleep-min", type=float, default=10.0)
    parser.add_argument("--sleep-max", type=float, default=15.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Не спрашивать подтверждение",
    )
    parser.add_argument(
        "--account-id",
        help="ID или точное имя аккаунта из папки accounts/",
    )
    parser.add_argument(
        "--all-accounts",
        action="store_true",
        help="Обработать все найденные аккаунты Shafa.",
    )
    parser.add_argument(
        "--parallel-accounts",
        action="store_true",
        help="Обрабатывать несколько аккаунтов параллельно. Только с --all-accounts.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help="Максимум аккаунтов, обрабатываемых одновременно.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1,
        help="Печатать прогресс деактивации каждые N товаров.",
    )
    parser.add_argument(
        "--verify-deactivation-flow",
        action="store_true",
        help="Проверить parallel/progress flow без реальной деактивации.",
    )
    parser.add_argument(
        "--accounts-search-root",
        action="append",
        default=None,
        help="Корень для рекурсивного поиска папок accounts/. Можно указать несколько раз.",
    )
    parser.add_argument(
        "--accounts-dir",
        action="append",
        default=None,
        help="Явная папка accounts/. Можно указать несколько раз.",
    )
    parser.add_argument(
        "--debug-auth",
        action="store_true",
        help="Печатать диагностику auth.json/cookies для Shafa-запросов.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    try:
        if args.all_accounts and args.account_id:
            raise RuntimeError("--all-accounts и --account-id нельзя использовать вместе")
        if args.parallel_accounts and not args.all_accounts:
            raise RuntimeError(
                "--parallel-accounts можно использовать только вместе с --all-accounts"
            )
        if args.sleep_min > args.sleep_max:
            raise RuntimeError("--sleep-min не может быть больше --sleep-max")
        if args.debug_auth:
            os.environ["SHAFA_DEBUG_AUTH"] = "1"
        progress_every = max(int(args.progress_every), 1)

        start_date = (
            parse_cli_date(args.from_date)
            if args.from_date
            else prompt_date("Дата от")
        )
        end_date = (
            parse_cli_date(args.to_date)
            if args.to_date
            else prompt_date("Дата до")
        )
        if start_date > end_date:
            raise RuntimeError("Дата начала не может быть позже даты конца.")

        if args.all_accounts:
            accounts_folders = find_all_accounts_dirs(
                accounts_dirs=args.accounts_dir,
                accounts_search_roots=args.accounts_search_root,
            )
            sessions = list_account_sessions(accounts_dirs=accounts_folders)
            if not sessions:
                raise RuntimeError(
                    "Не нашёл сохранённые cookies Shafa. Войди в аккаунт через "
                    "desktop UI или через `./venv/bin/python shafa_logic/main.py`."
                )

            process_all_accounts(
                accounts_folders_count=len(accounts_folders),
                sessions=sessions,
                start_date=start_date,
                end_date=end_date,
                page_size=args.page_size,
                sleep_min_seconds=args.sleep_min,
                sleep_max_seconds=args.sleep_max,
                dry_run=args.dry_run,
                yes=args.yes,
                parallel_accounts=args.parallel_accounts,
                max_workers=args.max_workers,
                progress_every=progress_every,
                verify_deactivation_flow=args.verify_deactivation_flow,
            )
            return

        selected_account = configure_account_environment(
            args.account_id,
            accounts_dirs=args.accounts_dir,
            accounts_search_roots=args.accounts_search_root,
        )
        if selected_account is not None:
            print(
                "Аккаунт Shafa: "
                f"{selected_account.name} | {selected_account.account_id}"
            )

        process_current_account(
            start_date=start_date,
            end_date=end_date,
            page_size=args.page_size,
            sleep_min_seconds=args.sleep_min,
            sleep_max_seconds=args.sleep_max,
            dry_run=args.dry_run,
            yes=args.yes,
            account_name=selected_account.name if selected_account is not None else "",
            progress_every=progress_every,
            verify_deactivation_flow=args.verify_deactivation_flow,
        )
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
