import os
import shutil
import sys
from pathlib import Path
from core.upload_photo import upload_photo
from core.get_sizes import get_sizes
from core.get_brands import get_brands
from core.create_product import create_product
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from core.core import get_csrftoken_from_context
from controller.data_controller import (
    download_product_photos,
    get_next_product_for_upload,
    mark_product_created,
)
from data.const import HEADLESS, ORIGIN_URL, REFERER_URL, MEDIA_DIR_PATH, STORAGE_STATE_PATH
from data.db import init_db, load_cookies, save_cookies, save_uploaded_product

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


def new_context_with_storage(browser):
    if STORAGE_STATE_PATH.exists():
        return browser.new_context(storage_state=str(STORAGE_STATE_PATH))
    ctx = browser.new_context()
    saved_cookies = load_cookies(ORIGIN_URL)
    if saved_cookies:
        ctx.add_cookies(saved_cookies)
    return ctx

def reset_media_dir(media_dir: Path) -> None:
    if media_dir.exists():
        for item in media_dir.iterdir():
            if item.is_file():
                item.unlink()
            else:
                shutil.rmtree(item)
    else:
        media_dir.mkdir(parents=True, exist_ok=True)

def main() -> None:
    init_db()
    product_data = get_next_product_for_upload(message_amount=200)
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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            ctx = new_context_with_storage(browser)
            page = ctx.new_page()
            page.set_default_timeout(60000)

            page.goto(REFERER_URL, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass
            if not STORAGE_STATE_PATH.exists():
                _log("INFO", "Залогинься в окне браузера, затем нажми Enter.")
                input()
                ctx.storage_state(path=str(STORAGE_STATE_PATH))

            csrftoken = get_csrftoken_from_context(ctx)
            if not csrftoken:
                raise RuntimeError("Не нашёл csrftoken в cookies контекста")
            save_cookies(ctx.cookies())

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
                photo_id = upload_photo(ctx, csrftoken, photo_path)
                photo_ids.append(photo_id)
                _log("OK", f"Фото загружено: id={photo_id}")

            _log("INFO", "Создаю товар...")
            result = create_product(ctx, csrftoken, photo_ids, product_raw_data)
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
        finally:
            browser.close()


if __name__ == "__main__":
    main()
