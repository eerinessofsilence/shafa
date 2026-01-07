import os
import shutil
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
    product_data = get_next_product_for_upload(message_amount=10)
    if not product_data:
        print("Нет новых товаров для создания.")
        return
    product_raw_data = product_data["product_raw_data"]
    message_id = product_data["message_id"]

    media_dir = Path(MEDIA_DIR_PATH)
    reset_media_dir(media_dir)
    downloaded = download_product_photos(message_id, media_dir)
    if downloaded == 0:
        print(f"Не нашёл фото для message_id={message_id} в Telegram.")
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
                input("Залогинься в окне браузера, затем нажми Enter...")
                ctx.storage_state(path=str(STORAGE_STATE_PATH))

            csrftoken = get_csrftoken_from_context(ctx)
            if not csrftoken:
                raise RuntimeError("Не нашёл csrftoken в cookies контекста")
            save_cookies(ctx.cookies())

            photo_ids: list[str] = []
            if os.path.exists(MEDIA_DIR_PATH) & os.path.isdir(MEDIA_DIR_PATH): 
                for photo in os.listdir(MEDIA_DIR_PATH):
                    photo_id = upload_photo(ctx, csrftoken, Path(os.path.join(MEDIA_DIR_PATH, photo)))
                    photo_ids.append(photo_id)
                    print("photo_id:", photo_id)

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
                print("Ошибки создания товара:", errors)
            else:
                product_id = created_product.get("id")
                print(f"Товар создан успешно. ID: {product_id}. Фото: {len(photo_ids)}.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
