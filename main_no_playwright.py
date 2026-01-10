import gzip
import json
import os
import shutil
import sys
import uuid
import zlib
from pathlib import Path
from typing import Optional
from urllib import error, request
from urllib.parse import urlparse

from controller.data_controller import (
    download_product_photos,
    get_next_product_for_upload,
    mark_product_created,
)
from data.const import (
    API_URL,
    APP_PLATFORM,
    APP_VERSION,
    CREATE_PRODUCT_MUTATION,
    MEDIA_DIR_PATH,
    ORIGIN_URL,
    REFERER_URL,
    STORAGE_STATE_PATH,
    UPLOAD_PHOTO_MUTATION,
)
from data.db import init_db, load_cookies, save_cookies, save_uploaded_product
from models.product import Product

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


_COLORS = {
    "INFO": "\033[34m",
    "WARN": "\033[33m",
    "ERROR": "\033[31m",
    "OK": "\033[32m",
}
_RESET = "\033[0m"


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _log(level: str, message: str) -> None:
    tag = f"[{level}]"
    if _supports_color() and level in _COLORS:
        tag = f"{_COLORS[level]}{tag}{_RESET}"
    print(f"{tag} {message}")


def _debug_http_enabled() -> bool:
    value = os.getenv("SHAFA_DEBUG_HTTP", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def reset_media_dir(media_dir: Path) -> None:
    if media_dir.exists():
        for item in media_dir.iterdir():
            if item.is_file():
                item.unlink()
            else:
                shutil.rmtree(item)
    else:
        media_dir.mkdir(parents=True, exist_ok=True)


def _normalize_domain(domain: str) -> str:
    domain = domain.strip()
    if "://" in domain:
        parsed = urlparse(domain)
        if parsed.hostname:
            domain = parsed.hostname
    return domain.lstrip(".").lower()


def _is_allowed_cookie_domain(domain: str, base_domain: str) -> bool:
    normalized = _normalize_domain(domain)
    base = _normalize_domain(base_domain)
    return normalized == base or normalized.endswith(f".{base}")


def _load_storage_state_cookies(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    cookies = data.get("cookies") or []
    return cookies if isinstance(cookies, list) else []


def _load_shafa_cookies() -> list[dict]:
    cookies = _load_storage_state_cookies(STORAGE_STATE_PATH)
    filtered = [
        cookie
        for cookie in cookies
        if _is_allowed_cookie_domain(cookie.get("domain", ""), ORIGIN_URL)
    ]
    if not filtered:
        cookies = load_cookies(ORIGIN_URL)
        filtered = [
            cookie
            for cookie in cookies
            if _is_allowed_cookie_domain(cookie.get("domain", ""), ORIGIN_URL)
        ]
    if filtered:
        save_cookies(filtered)
    return filtered


def _build_cookie_header(cookies: list[dict]) -> str:
    parts: list[str] = []
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def _get_csrftoken_from_cookies(cookies: list[dict]) -> Optional[str]:
    for cookie in cookies:
        if cookie.get("name") == "csrftoken":
            return cookie.get("value")
    return None


def _base_headers(csrftoken: str) -> dict:
    return {
        "Origin": ORIGIN_URL,
        "Referer": REFERER_URL,
        "X-CSRFToken": csrftoken,
        "x-app-platform": APP_PLATFORM,
        "x-app-version": APP_VERSION,
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "identity",
    }


def _decode_body(body: bytes, encoding: str) -> bytes:
    encoding = (encoding or "").lower()
    if "gzip" in encoding:
        return gzip.decompress(body)
    if "deflate" in encoding:
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def _read_response_text(resp) -> str:
    body = resp.read()
    body = _decode_body(body, resp.headers.get("Content-Encoding", ""))
    return body.decode("utf-8", errors="replace")


def _request_json(
    url: str,
    payload: bytes,
    headers: dict,
    cookies: list[dict],
    preview: int = 2000,
) -> dict:
    cookie_header = _build_cookie_header(cookies)
    merged_headers = dict(headers)
    if cookie_header:
        merged_headers["Cookie"] = cookie_header

    req = request.Request(url, data=payload, headers=merged_headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as resp:
            text = _read_response_text(resp)
    except error.HTTPError as exc:
        text = _read_response_text(exc)
        if _debug_http_enabled():
            print(text[:preview])
        raise RuntimeError(f"HTTP error {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Request failed: {exc.reason}") from exc

    if _debug_http_enabled():
        print(text[:preview])
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Response is not valid JSON") from exc


def _encode_multipart(
    fields: dict[str, str],
    files: dict[str, tuple[str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body_parts: list[bytes] = []

    def add_part(part: bytes) -> None:
        body_parts.append(part)

    for name, value in fields.items():
        add_part(f"--{boundary}".encode())
        add_part(f'Content-Disposition: form-data; name="{name}"'.encode())
        add_part(b"")
        add_part(str(value).encode("utf-8"))

    for name, (filename, content_type, file_bytes) in files.items():
        add_part(f"--{boundary}".encode())
        add_part(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
        )
        add_part(f"Content-Type: {content_type}".encode())
        add_part(b"")
        add_part(file_bytes)

    add_part(f"--{boundary}--".encode())
    add_part(b"")

    return b"\r\n".join(body_parts), boundary


def _build_create_product_payload(photo_ids: list[str], product_raw_data: dict) -> dict:
    product = Product(**product_raw_data)
    variables: dict = {
        "nameUk": product.name,
        "descriptionUk": product.description,
        "isUkToRuTranslationEnabled": product.translation_enabled,
        "catalog": product.category,
        "condition": product.condition,
        "brand": product.brand,
        "colors": product.colors,
        "size": product.size,
        "additionalSizes": product.additional_sizes,
        "characteristics": product.characteristics,
        "count": (
            product.amount
            if product.amount >= len(product.additional_sizes) + 1
            else len(product.additional_sizes) + 1
        ),
        "sellingCondition": product.selling_condition,
        "price": product.price,
        "keyWords": product.keywords,
        "photosStr": photo_ids,
    }

    return {
        "operationName": "WEB_CreateProduct",
        "variables": variables,
        "query": CREATE_PRODUCT_MUTATION,
    }


def upload_photo(csrftoken: str, cookies: list[dict], file_path: Path) -> str:
    fields = {
        "operationName": "UploadPhoto",
        "query": UPLOAD_PHOTO_MUTATION,
        "variables": json.dumps({"file": "file"}),
    }
    files = {
        "file": (file_path.name, "image/jpeg", file_path.read_bytes()),
    }
    body, boundary = _encode_multipart(fields, files)
    headers = {
        **_base_headers(csrftoken),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }

    data = _request_json(API_URL, body, headers, cookies)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    upload = data.get("data", {}).get("uploadPhoto") or {}
    if upload.get("errors"):
        raise RuntimeError(f"Upload errors: {upload['errors']}")

    photo_id = upload.get("idStr")
    if not photo_id:
        raise RuntimeError("Upload response missing idStr")

    return photo_id


def create_product(
    csrftoken: str,
    cookies: list[dict],
    photo_ids: list[str],
    product_raw_data: dict,
) -> dict:
    payload = _build_create_product_payload(photo_ids, product_raw_data)
    headers = {
        **_base_headers(csrftoken),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    data = _request_json(
        API_URL,
        json.dumps(payload).encode("utf-8"),
        headers,
        cookies,
    )

    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    return data.get("data", {}).get("createProduct") or {}


def main() -> None:
    init_db()
    product_data = get_next_product_for_upload(message_amount=10)
    if not product_data:
        _log("INFO", "Нет новых товаров для создания.")
        return
    product_raw_data = product_data["product_raw_data"]
    message_id = product_data["message_id"]

    media_dir = Path(MEDIA_DIR_PATH)
    reset_media_dir(media_dir)
    downloaded = download_product_photos(message_id, media_dir)
    if downloaded == 0:
        _log("WARN", f"Не нашёл фото для message_id={message_id} в Telegram.")
    else:
        _log("INFO", f"Скачано фото: {downloaded}.")

    cookies = _load_shafa_cookies()
    if not cookies:
        _log("ERROR", "Нет сохранённых cookies. Сначала залогинься через main.py.")
        return
    csrftoken = _get_csrftoken_from_cookies(cookies)
    if not csrftoken:
        raise RuntimeError("Не нашёл csrftoken в cookies")

    photo_ids: list[str] = []
    photo_paths = (
        sorted(
            [path for path in media_dir.iterdir() if path.is_file()],
            key=lambda path: path.name,
        )
        if media_dir.is_dir()
        else []
    )
    if not photo_paths:
        _log("WARN", "Файлы для загрузки не найдены.")
    for idx, photo_path in enumerate(photo_paths, start=1):
        _log("INFO", f"Загрузка фото {idx}/{len(photo_paths)}: {photo_path.name}")
        photo_id = upload_photo(csrftoken, cookies, photo_path)
        photo_ids.append(photo_id)
        _log("OK", f"Фото загружено: id={photo_id}")

    _log("INFO", "Создаю товар...")
    result = create_product(csrftoken, cookies, photo_ids, product_raw_data)
    created_product = result.get("createdProduct") or {}
    save_uploaded_product(
        product_id=created_product.get("id"),
        product_raw_data=product_raw_data,
        photo_ids=photo_ids,
    )
    mark_product_created(message_id, created_product.get("id"))
    errors = result.get("errors") or []
    if errors:
        _log("ERROR", f"Ошибки создания товара: {errors}")
    else:
        product_id = created_product.get("id")
        _log("OK", f"Товар создан успешно. ID: {product_id}. Фото: {len(photo_ids)}.")


if __name__ == "__main__":
    main()
