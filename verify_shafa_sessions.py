import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional
from urllib import error, request


ROOT = Path(__file__).resolve().parent
SHAFA_LOGIC_DIR = ROOT / "shafa_logic"
for path in (ROOT, SHAFA_LOGIC_DIR):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from deactivate_products_by_date import find_all_accounts_dirs  # noqa: E402
from shafa_logic.data.const import (  # noqa: E402
    API_BATCH_URL,
    APP_PLATFORM,
    APP_VERSION,
    ORIGIN_URL,
)
from shafa_logic.utils.proxy import load_runtime_proxy_config, open_url  # noqa: E402


SHAFA_PROFILE_QUERY = """query WEB_MainInfoSettingsFormData {
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


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _account_auth_path(account_file: Path, payload: dict[str, Any]) -> Path:
    state_dir = account_file.parent
    raw_path = (
        payload.get("shafa_session_path")
        or payload.get("browser_session_path")
        or state_dir / "auth.json"
    )
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = state_dir / path
    return path.expanduser().resolve(strict=False)


def _load_storage_cookies(auth_path: Path) -> list[dict[str, Any]]:
    payload = _load_json(auth_path)
    if not isinstance(payload, dict):
        return []
    cookies = payload.get("cookies")
    return [cookie for cookie in cookies if isinstance(cookie, dict)] if isinstance(cookies, list) else []


def _csrftoken(cookies: list[dict[str, Any]]) -> str:
    for cookie in cookies:
        if str(cookie.get("name") or "").strip() == "csrftoken":
            return str(cookie.get("value") or "").strip()
    return ""


def _cookie_header(cookies: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        value = cookie.get("value")
        if not name or value in (None, ""):
            continue
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def _fetch_viewer(
    cookies: list[dict[str, Any]],
    *,
    proxy_config_path: Optional[Path] = None,
) -> dict[str, Any]:
    token = _csrftoken(cookies)
    if not token:
        raise RuntimeError("csrftoken missing")

    payload = json.dumps(
        [
            {
                "operationName": "WEB_MainInfoSettingsFormData",
                "variables": {},
                "query": SHAFA_PROFILE_QUERY,
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
            "Cookie": _cookie_header(cookies),
            "Origin": ORIGIN_URL,
            "Referer": "https://shafa.ua/uk/my/settings",
            "User-Agent": "Mozilla/5.0",
            "batch": "true",
            "x-app-platform": APP_PLATFORM,
            "x-app-version": APP_VERSION,
            "x-csrftoken": token,
        },
        method="POST",
    )
    proxy_config = (
        load_runtime_proxy_config(proxy_config_path)
        if proxy_config_path is not None
        else None
    )
    with open_url(http_request, config=proxy_config, timeout=20) as response:
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
    raise RuntimeError("viewer missing")


def _viewer_name(viewer: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            str(viewer.get("firstName") or "").strip(),
            str(viewer.get("lastName") or "").strip(),
            str(viewer.get("patronymic") or "").strip(),
        )
        if part
    )


def _viewer_identity(viewer: Optional[dict[str, Any]]) -> str:
    if not viewer:
        return "-"
    return (
        f"id={viewer.get('id') or '-'}; "
        f"name={_viewer_name(viewer) or '-'}; "
        f"email={viewer.get('email') or '-'}; "
        f"phone={viewer.get('phone') or '-'}"
    )


def _identity_key(viewer: Optional[dict[str, Any]]) -> str:
    if not viewer:
        return ""
    for key in ("id", "email", "phone"):
        value = str(viewer.get(key) or "").strip()
        if value:
            return f"{key}:{value.casefold()}"
    name = _viewer_name(viewer).casefold()
    return f"name:{name}" if name else ""


def _normalize_phone(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _metadata_mismatch(account: dict[str, Any], viewer: Optional[dict[str, Any]]) -> bool:
    if not viewer:
        return False
    local_phone = _normalize_phone(account.get("phone_number"))
    viewer_phone = _normalize_phone(viewer.get("phone"))
    return bool(local_phone and viewer_phone and local_phone != viewer_phone)


def _proxy_config_path(payload: dict[str, Any]) -> Optional[Path]:
    raw_path = str(payload.get("proxy_config_path") or "").strip()
    if not raw_path:
        return None
    return Path(raw_path).expanduser().resolve(strict=False)


def _iter_account_files(
    accounts_dirs: Optional[list[str]] = None,
    accounts_search_roots: Optional[list[str]] = None,
) -> list[Path]:
    account_files: list[Path] = []
    for accounts_dir in find_all_accounts_dirs(
        accounts_dirs=accounts_dirs,
        accounts_search_roots=accounts_search_roots,
    ):
        account_files.extend(sorted(accounts_dir.glob("*/account.json")))
    seen: set[Path] = set()
    result: list[Path] = []
    for account_file in account_files:
        resolved = account_file.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def verify_sessions(
    accounts_dirs: Optional[list[str]] = None,
    accounts_search_roots: Optional[list[str]] = None,
) -> int:
    rows: list[dict[str, Any]] = []
    for account_file in _iter_account_files(accounts_dirs, accounts_search_roots):
        payload = _load_json(account_file)
        if not isinstance(payload, dict):
            continue
        auth_path = _account_auth_path(account_file, payload)
        cookies = _load_storage_cookies(auth_path)
        viewer: Optional[dict[str, Any]] = None
        error_message = ""
        status = "OK"
        if not auth_path.exists() or not _csrftoken(cookies):
            status = "NOT AUTHENTICATED"
        else:
            try:
                viewer = _fetch_viewer(
                    cookies,
                    proxy_config_path=_proxy_config_path(payload),
                )
            except (RuntimeError, OSError, error.URLError, json.JSONDecodeError) as exc:
                status = "NOT AUTHENTICATED"
                error_message = str(exc)
        rows.append(
            {
                "local_name": str(payload.get("name") or account_file.parent.name),
                "local_id": str(payload.get("id") or account_file.parent.name),
                "phone_number": str(payload.get("phone_number") or ""),
                "auth_path": auth_path,
                "viewer": viewer,
                "identity_key": _identity_key(viewer),
                "status": status,
                "error": error_message,
            }
        )

    identity_counts: dict[str, int] = {}
    for row in rows:
        key = row["identity_key"]
        if key:
            identity_counts[key] = identity_counts.get(key, 0) + 1
    for row in rows:
        if row["status"] != "OK":
            continue
        if identity_counts.get(row["identity_key"], 0) > 1 or _metadata_mismatch(row, row["viewer"]):
            row["status"] = "MISMATCH"

    for row in rows:
        print(f"Local account: {row['local_name']} | {row['local_id']}")
        print(f"Auth: {row['auth_path']}")
        print(f"Actual Shafa viewer: {_viewer_identity(row['viewer'])}")
        print(f"Status: {row['status']}")
        if row["error"]:
            print(f"Detail: {row['error']}")
        print("")

    return 1 if any(row["status"] in {"MISMATCH", "NOT AUTHENTICATED"} for row in rows) else 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify saved Shafa auth.json sessions.")
    parser.add_argument("--accounts-dir", action="append", default=None)
    parser.add_argument("--accounts-search-root", action="append", default=None)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    raise SystemExit(
        verify_sessions(
            accounts_dirs=args.accounts_dir,
            accounts_search_roots=args.accounts_search_root,
        )
    )


if __name__ == "__main__":
    main()
