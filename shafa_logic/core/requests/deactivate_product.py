import json
import re
from pathlib import Path
from typing import Optional

from controller.data_controller import is_valid_uploaded_product_identity
from core.no_playwright import (
    _base_headers,
    _get_csrftoken_from_cookies,
    _is_allowed_cookie_domain,
    _load_storage_state_cookies,
    _load_shafa_cookies,
    _request_json,
)
from data.const import API_URL, DB_PATH, ORIGIN_URL, STORAGE_STATE_PATH
from data.db import (
    clear_invalid_uploaded_products,
    list_active_uploaded_product_payloads,
    list_pending_invalid_uploaded_products,
    load_cookies,
    mark_invalid_uploaded_products_error,
    mark_invalid_uploaded_products_processed,
    mark_uploaded_products_deactivated,
    save_invalid_uploaded_product,
)
from .get_my_clothes_products_feed import MY_CLOTHES_PRODUCTS_FEED_QUERY
from utils.logging import log

DEACTIVATE_PRODUCTS_OPERATION_NAME = "WEB_ProductDetailsDeactivateProduct"
DEACTIVATE_PRODUCTS_MUTATION = """
mutation WEB_ProductDetailsDeactivateProduct($includeIds: [Int]) {
  deactivateProducts(includeIds: $includeIds) {
    errors {
      ...errorsData
      __typename
    }
    __typename
  }
}

fragment errorsData on GraphResponseError {
  field
  messages {
    code
    message
    __typename
  }
  __typename
}
"""


def parse_product_ids(value: str) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for token in re.findall(r"\d+", value):
        product_id = int(token)
        if product_id not in seen:
            seen.add(product_id)
            ids.append(product_id)
    return ids


def _is_deactivate_result_successful(result: dict) -> bool:
    if not result:
        return False
    errors = result.get("errors")
    return not errors


def deactivate_products(product_ids: list[int]) -> dict:
    if not product_ids:
        raise ValueError("product_ids is required")
    cookies = _load_shafa_cookies()
    if not cookies:
        log("ERROR", "No saved cookies. Log in via main.py first.")
        return {}
    csrftoken = _get_csrftoken_from_cookies(cookies)
    if not csrftoken:
        raise RuntimeError("csrftoken not found in cookies")
    payload = {
        "operationName": DEACTIVATE_PRODUCTS_OPERATION_NAME,
        "variables": {
            "includeIds": product_ids,
        },
        "query": DEACTIVATE_PRODUCTS_MUTATION,
    }
    headers = {
        **_base_headers(csrftoken),
        "Accept": "*/*",
        "Content-Type": "application/json",
    }
    data = _request_json(
        API_URL,
        json.dumps(payload).encode("utf-8"),
        headers,
        cookies,
    )
    errors = data.get("errors") or []
    if errors:
        log("ERROR", f"GraphQL errors: {errors}")
        return {"errors": errors}
    return data.get("data", {}).get("deactivateProducts") or {}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_shafa_cookies_for_account(
    *,
    storage_state_path: Optional[Path],
    db_path: Path,
) -> list[dict]:
    filtered: list[dict] = []
    if storage_state_path is not None:
        cookies = _load_storage_state_cookies(storage_state_path)
        filtered = [
            cookie
            for cookie in cookies
            if _is_allowed_cookie_domain(cookie.get("domain", ""), ORIGIN_URL)
        ]
    if not filtered:
        cookies = load_cookies(ORIGIN_URL, db_path=db_path)
        filtered = [
            cookie
            for cookie in cookies
            if _is_allowed_cookie_domain(cookie.get("domain", ""), ORIGIN_URL)
        ]
    return filtered


def _discover_shafa_account_contexts() -> list[dict]:
    root_dir = _repo_root()
    contexts: list[dict] = []
    seen: set[tuple[str, str]] = set()

    candidates = [
        {
            "name": "default",
            "storage_state_path": STORAGE_STATE_PATH if STORAGE_STATE_PATH.exists() else None,
            "db_path": DB_PATH,
        }
    ]
    accounts_dir = root_dir / "accounts"
    if accounts_dir.exists():
        for account_dir in sorted(path for path in accounts_dir.iterdir() if path.is_dir()):
            auth_path = account_dir / "auth.json"
            db_path = account_dir / "shafa.sqlite3"
            candidates.append(
                {
                    "name": account_dir.name,
                    "storage_state_path": auth_path if auth_path.exists() else None,
                    "db_path": db_path,
                }
            )

    for candidate in candidates:
        storage_state_path = candidate["storage_state_path"]
        db_path = Path(candidate["db_path"])
        if storage_state_path is None and not db_path.exists():
            continue
        key = (
            str(storage_state_path.resolve()) if storage_state_path is not None else "",
            str(db_path.resolve()),
        )
        if key in seen:
            continue
        seen.add(key)
        contexts.append(
            {
                "name": candidate["name"],
                "storage_state_path": storage_state_path,
                "db_path": db_path,
            }
        )
    return contexts


def _deactivate_products_with_cookies(product_ids: list[int], cookies: list[dict]) -> dict:
    if not product_ids:
        raise ValueError("product_ids is required")
    if not cookies:
        return {}
    csrftoken = _get_csrftoken_from_cookies(cookies)
    if not csrftoken:
        raise RuntimeError("csrftoken not found in cookies")
    payload = {
        "operationName": DEACTIVATE_PRODUCTS_OPERATION_NAME,
        "variables": {
            "includeIds": product_ids,
        },
        "query": DEACTIVATE_PRODUCTS_MUTATION,
    }
    headers = {
        **_base_headers(csrftoken),
        "Accept": "*/*",
        "Content-Type": "application/json",
    }
    data = _request_json(
        API_URL,
        json.dumps(payload).encode("utf-8"),
        headers,
        cookies,
    )
    errors = data.get("errors") or []
    if errors:
        log("ERROR", f"GraphQL errors: {errors}")
        return {"errors": errors}
    return data.get("data", {}).get("deactivateProducts") or {}


def _extract_uploaded_product_name(row: dict) -> str:
    raw_payload = row.get("raw_payload")
    if raw_payload:
        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            name = str(payload.get("name") or "").strip()
            if name:
                return name
    return str(row.get("name") or "").strip()


def _extract_uploaded_product_payload(row: dict) -> dict:
    raw_payload = row.get("raw_payload")
    if not raw_payload:
        return {}
    try:
        payload = json.loads(raw_payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_uploaded_product_brand(row: dict) -> object:
    payload = _extract_uploaded_product_payload(row)
    return payload.get("brand")


def _normalize_product_name_key(name: object) -> str:
    return " ".join(str(name or "").split()).strip().casefold()


def _normalize_product_name_for_validation(name: object) -> str:
    text = str(name or "").replace("–", "-").replace("—", "-")
    text = re.sub(r"[_/]+", " ", text)
    text = re.sub(r"[^\w\s-]+", " ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    return " ".join(text.split()).strip()


def _is_invalid_uploaded_product_row(row: dict) -> bool:
    product_name = _normalize_product_name_for_validation(
        _extract_uploaded_product_name(row)
    )
    product_brand = _extract_uploaded_product_brand(row)
    return not is_valid_uploaded_product_identity(product_name, product_brand)


def _invalid_uploaded_product_reason(row: dict) -> str:
    del row
    return "missing_brand_and_clothes_name"


def _format_invalid_uploaded_product(row: dict) -> dict | None:
    product_id_raw = str(row.get("product_id") or "").strip()
    product_ids = parse_product_ids(product_id_raw)
    if not product_ids:
        return None
    return {
        "product_id": product_ids[0],
        "name": str(row.get("name") or "").strip(),
        "created_at": row.get("created_at"),
        "invalid_reason": row.get("invalid_reason"),
    }


def _refresh_invalid_uploaded_products(
    limit: Optional[int] = None,
    *,
    db_path: Path = DB_PATH,
) -> list[dict]:
    valid_product_ids: list[str] = []
    for row in list_active_uploaded_product_payloads(limit=limit, db_path=db_path):
        product_id_raw = str(row.get("product_id") or "").strip()
        if not product_id_raw:
            continue
        if _is_invalid_uploaded_product_row(row):
            save_invalid_uploaded_product(
                product_id_raw,
                _extract_uploaded_product_name(row),
                _invalid_uploaded_product_reason(row),
                raw_payload=row.get("raw_payload"),
                created_at=row.get("created_at"),
                db_path=db_path,
            )
            continue
        valid_product_ids.append(product_id_raw)
    if valid_product_ids:
        clear_invalid_uploaded_products(valid_product_ids, db_path=db_path)
    return list_pending_invalid_uploaded_products(limit=limit, db_path=db_path)


def _load_account_active_product_name_index(
    cookies: list[dict],
    *,
    first: int = 50,
    max_pages: int = 40,
) -> dict[str, list[int]]:
    after: Optional[str] = None
    name_index: dict[str, list[int]] = {}
    for _ in range(max_pages):
        payload = {
            "operationName": "WEB_MyClothesProductsFeed",
            "variables": {
                "catalogSlug": "",
                "productsType": "ACTIVE",
                "first": first,
                "orderBy": "1",
                "after": after,
            },
            "query": MY_CLOTHES_PRODUCTS_FEED_QUERY,
        }
        csrftoken = _get_csrftoken_from_cookies(cookies)
        if not csrftoken:
            raise RuntimeError("csrftoken not found in cookies")
        headers = {
            **_base_headers(csrftoken),
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Referer": "https://shafa.ua/uk/my/clothes",
        }
        data = _request_json(
            API_URL,
            json.dumps(payload).encode("utf-8"),
            headers,
            cookies,
        )
        errors = data.get("errors") or []
        if errors:
            raise RuntimeError(f"GraphQL errors: {errors}")
        feed = data.get("data", {}).get("viewer", {}).get("products") or {}
        edges = feed.get("edges") or []
        for edge in edges:
            node = edge.get("node") or {}
            name_key = _normalize_product_name_key(node.get("name"))
            product_ids = parse_product_ids(str(node.get("id") or ""))
            if not name_key or not product_ids:
                continue
            ids = name_index.setdefault(name_key, [])
            product_id = product_ids[0]
            if product_id not in ids:
                ids.append(product_id)
        page_info = feed.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
        if not after:
            break
    return name_index


def _select_active_product_id_for_invalid_row(
    row: dict,
    active_name_index: dict[str, list[int]],
    used_product_ids: set[int],
) -> Optional[int]:
    name_key = _normalize_product_name_key(row.get("name"))
    if not name_key:
        return None
    candidate_ids = [
        product_id
        for product_id in active_name_index.get(name_key, [])
        if product_id not in used_product_ids
    ]
    if not candidate_ids:
        return None
    row_product_id = parse_product_ids(str(row.get("product_id") or ""))
    if row_product_id:
        preferred_id = row_product_id[0]
        if preferred_id in candidate_ids:
            return preferred_id
    return candidate_ids[0]


def find_invalid_uploaded_products(
    limit: Optional[int] = None,
    *,
    db_path: Path = DB_PATH,
) -> list[dict]:
    invalid_products: list[dict] = []
    for row in _refresh_invalid_uploaded_products(limit=limit, db_path=db_path):
        item = _format_invalid_uploaded_product(row)
        if item is not None:
            invalid_products.append(item)
    return invalid_products


def _deactivate_invalid_uploaded_products_for_account(
    *,
    account_name: str,
    storage_state_path: Optional[Path],
    db_path: Path,
    limit: Optional[int] = None,
    max_items: Optional[int] = None,
) -> dict:
    checked_rows = list_active_uploaded_product_payloads(limit=limit, db_path=db_path)
    invalid_rows = _refresh_invalid_uploaded_products(limit=limit, db_path=db_path)
    invalid_products = [
        item
        for row in invalid_rows
        for item in [_format_invalid_uploaded_product(row)]
        if item is not None
    ]
    if not invalid_products:
        return {
            "account": account_name,
            "checked": len(checked_rows),
            "invalid": [],
            "deactivated": [],
            "errors": [],
        }

    cookies = _load_shafa_cookies_for_account(
        storage_state_path=storage_state_path,
        db_path=db_path,
    )
    if not cookies:
        return {
            "account": account_name,
            "checked": len(checked_rows),
            "invalid": invalid_products,
            "deactivated": [],
            "errors": [
                {
                    "product_id": None,
                    "name": "",
                    "reason": "missing_cookies",
                }
            ],
        }

    try:
        active_name_index = _load_account_active_product_name_index(cookies)
    except Exception as exc:
        return {
            "account": account_name,
            "checked": len(checked_rows),
            "invalid": invalid_products,
            "deactivated": [],
            "errors": [
                {
                    "product_id": None,
                    "name": "",
                    "reason": str(exc),
                }
            ],
        }

    deactivated_ids: list[int] = []
    errors: list[dict] = []
    used_product_ids: set[int] = set()
    processed_items = 0
    for row in invalid_rows:
        if max_items is not None and processed_items >= max_items:
            break
        row_product_id_raw = str(row.get("product_id") or "").strip()
        if not row_product_id_raw:
            continue
        sample_name = str(row.get("name") or "").strip()
        target_product_id = _select_active_product_id_for_invalid_row(
            row,
            active_name_index,
            used_product_ids,
        )
        if target_product_id is None:
            mark_invalid_uploaded_products_error(
                [row_product_id_raw],
                last_error="not_found_by_name",
                db_path=db_path,
            )
            formatted = _format_invalid_uploaded_product(row)
            if formatted is not None:
                errors.append(
                    {
                        "product_id": formatted["product_id"],
                        "name": formatted.get("name") or "",
                        "reason": "not_found_by_name",
                    }
                )
                processed_items += 1
            continue

        result = _deactivate_products_with_cookies([target_product_id], cookies)
        if not result:
            mark_invalid_uploaded_products_error(
                [row_product_id_raw],
                last_error="empty_response",
                db_path=db_path,
            )
            errors.append(
                {
                    "product_id": target_product_id,
                    "name": sample_name,
                    "reason": "empty_response",
                }
            )
            processed_items += 1
            continue
        result_errors = result.get("errors") or []
        if result_errors:
            mark_invalid_uploaded_products_error(
                [row_product_id_raw],
                last_error=str(result_errors),
                db_path=db_path,
            )
            errors.append(
                {
                    "product_id": target_product_id,
                    "name": sample_name,
                    "reason": result_errors,
                }
            )
            processed_items += 1
            continue
        if _is_deactivate_result_successful(result):
            mark_uploaded_products_deactivated(
                sorted(
                    set(
                        [
                            target_product_id,
                            *[
                                int(pid)
                                for pid in [row_product_id_raw]
                                if pid.isdigit()
                            ],
                        ]
                    )
                ),
                db_path=db_path,
            )
            mark_invalid_uploaded_products_processed(
                [row_product_id_raw],
                db_path=db_path,
            )
            deactivated_ids.append(target_product_id)
            used_product_ids.add(target_product_id)
            processed_items += 1
            continue
        mark_invalid_uploaded_products_error(
            [row_product_id_raw],
            last_error="deactivation_failed",
            db_path=db_path,
        )
        errors.append(
            {
                "product_id": target_product_id,
                "name": sample_name,
                "reason": "deactivation_failed",
            }
        )
        processed_items += 1

    return {
        "account": account_name,
        "checked": len(checked_rows),
        "invalid": invalid_products,
        "deactivated": deactivated_ids,
        "errors": errors,
    }


def deactivate_invalid_uploaded_products(limit: Optional[int] = None) -> dict:
    account_results: list[dict] = []
    all_invalid: list[dict] = []
    all_deactivated: list[dict] = []
    all_errors: list[dict] = []
    total_checked = 0

    for context in _discover_shafa_account_contexts():
        result = _deactivate_invalid_uploaded_products_for_account(
            account_name=context["name"],
            storage_state_path=context["storage_state_path"],
            db_path=context["db_path"],
            limit=limit,
        )
        account_results.append(result)
        total_checked += int(result.get("checked") or 0)
        for item in result.get("invalid") or []:
            all_invalid.append({"account": context["name"], **item})
        for product_id in result.get("deactivated") or []:
            all_deactivated.append({"account": context["name"], "product_id": product_id})
        for item in result.get("errors") or []:
            all_errors.append({"account": context["name"], **item})

    return {
        "checked": total_checked,
        "accounts": account_results,
        "invalid": all_invalid,
        "deactivated": all_deactivated,
        "errors": all_errors,
    }


def deactivate_next_invalid_uploaded_product() -> dict:
    total_checked = 0
    account_results: list[dict] = []
    all_invalid: list[dict] = []
    all_deactivated: list[dict] = []
    all_errors: list[dict] = []

    for context in _discover_shafa_account_contexts():
        result = _deactivate_invalid_uploaded_products_for_account(
            account_name=context["name"],
            storage_state_path=context["storage_state_path"],
            db_path=context["db_path"],
            max_items=1,
        )
        account_results.append(result)
        total_checked += int(result.get("checked") or 0)
        for item in result.get("invalid") or []:
            all_invalid.append({"account": context["name"], **item})
        for product_id in result.get("deactivated") or []:
            all_deactivated.append({"account": context["name"], "product_id": product_id})
        for item in result.get("errors") or []:
            all_errors.append({"account": context["name"], **item})
        if (result.get("deactivated") or result.get("errors")) and (result.get("invalid") or []):
            break

    return {
        "checked": total_checked,
        "accounts": account_results,
        "invalid": all_invalid,
        "deactivated": all_deactivated,
        "errors": all_errors,
    }


def main() -> None:
    raw = input("Product id(s) to deactivate: ").strip()
    if not raw or raw.lower() in {"q", "quit"}:
        return
    product_ids = parse_product_ids(raw)
    if not product_ids:
        print("No valid product ids provided.")
        return
    result = deactivate_products(product_ids)
    if not result:
        return
    errors = result.get("errors") or []
    if errors:
        print(f"Deactivation errors: {errors}")
        return
    if _is_deactivate_result_successful(result):
        mark_uploaded_products_deactivated(product_ids)
        print(f"Deactivated {len(product_ids)} product(s).")
        return
    print("Deactivation failed.")


if __name__ == "__main__":
    main()
