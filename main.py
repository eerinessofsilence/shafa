from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from controller.data_controller import (
    download_product_photos,
    get_next_product_for_upload,
    mark_product_created,
)
from core.context import new_context_with_storage, storage_state_has_cookies
from core.core import get_csrftoken_from_context
from core.create_product import create_product
from core.upload_photo import upload_photo
from data.const import (
    DEFAULT_MARKUP,
    HEADLESS,
    MEDIA_DIR_PATH,
    REFERER_URL,
    STORAGE_STATE_PATH,
)
from data.db import init_db, save_cookies, save_uploaded_product
from utils.logging import log
from utils.media import list_media_files, reset_media_dir


def main() -> None:
    init_db()
    product_data = get_next_product_for_upload(message_amount=50)
    if not product_data:
        log("INFO", "Нет новых товаров для создания.")
        return
    channel_id = product_data.get("channel_id")
    product_raw_data = product_data["product_raw_data"]
    parsed_data = product_data.get("parsed_data") or {}
    message_id = product_data["message_id"]
    product_name = parsed_data.get("name") or product_raw_data.get("name") or "—"
    log("INFO", f"Товар для создания: {product_name}.")

    if product_raw_data.get("size") is None:
        log("ERROR", "Не удалось определить размер. Запусти Bootstrap sizes/brands.")
        return
    price_value = product_raw_data.get("price")
    if price_value is None or price_value <= 0:
        log(
            "ERROR",
            f"Некорректная цена: {price_value}. Parsed price: {parsed_data.get('price')!r}.",
        )
        return
    price_with_markup = price_value + DEFAULT_MARKUP
    log("INFO", f"Цена товара (база): {price_value}.")
    log("INFO", f"Цена товара (с наценкой {DEFAULT_MARKUP}): {price_with_markup}.")

    media_dir = Path(MEDIA_DIR_PATH)
    reset_media_dir(media_dir)
    downloaded = download_product_photos(message_id, media_dir, channel_id=channel_id)
    if downloaded == 0:
        log("WARN", f"Не нашёл фото для message_id={message_id} в Telegram.")
    else:
        log("INFO", f"Скачано фото: {downloaded}.")
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
            if not storage_state_has_cookies(STORAGE_STATE_PATH):
                log("INFO", "Залогинься в окне браузера, затем нажми Enter.")
                input()
                ctx.storage_state(path=str(STORAGE_STATE_PATH))

            csrftoken = get_csrftoken_from_context(ctx)
            if not csrftoken:
                raise RuntimeError("Не нашёл csrftoken в cookies контекста")
            save_cookies(ctx.cookies())

            photo_ids: list[str] = []
            photo_paths = list_media_files(media_dir)
            if not photo_paths:
                log("WARN", "Файлы для загрузки не найдены.")
            for idx, photo_path in enumerate(photo_paths, start=1):
                log("INFO", f"Загрузка фото {idx}/{len(photo_paths)}: {photo_path.name}")
                photo_id = upload_photo(ctx, csrftoken, photo_path)
                photo_ids.append(photo_id)
                log("OK", f"Фото загружено: id={photo_id}")

            log("INFO", "Создаю товар...")
            result = create_product(
                ctx,
                csrftoken,
                photo_ids,
                product_raw_data,
                markup=DEFAULT_MARKUP,
            )
            errors = result.get("errors") or []
            if errors:
                log("ERROR", f"Ошибки создания товара: {errors}")
                return
            created_product = result.get("createdProduct") or {}
            save_uploaded_product(
                product_id=created_product.get("id"),
                product_raw_data=product_raw_data,
                photo_ids=photo_ids,
            )
            mark_product_created(
                message_id,
                created_product.get("id"),
                channel_id=channel_id,
            )
            product_id = created_product.get("id")
            log("OK", f"Товар создан успешно. ID: {product_id}. Фото: {len(photo_ids)}.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
