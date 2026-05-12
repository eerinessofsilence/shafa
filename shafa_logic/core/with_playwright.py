import os
from pathlib import Path

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ModuleNotFoundError:  # pragma: no cover - optional at import time for tests
    class PlaywrightTimeoutError(Exception):
        pass

    def sync_playwright():
        raise RuntimeError("playwright is required for browser mode")

from controller.data_controller import (
    build_product_raw_data,
    catalog_requires_brand,
    download_product_photos,
    get_product_photo_message_ids,
    get_next_product_for_upload,
    mark_product_created,
    rebuild_product_data_from_source,
    should_run_first_fetch,
)
from core.context import new_context_with_storage, storage_state_has_cookies
from core.core import get_csrftoken_from_context
from core.product_failures import (
    handle_non_retryable_product_failure,
    handle_retryable_product_failure,
    summarize_exception,
    summarize_graph_errors,
)
from core.requests.create_product import create_product
from core.requests.get_brands import get_brands, resolve_brand_catalog_slug
from core.requests.get_sizes import get_sizes
from core.requests.upload_photo import upload_photo
from data.const import (
    DEFAULT_MARKUP,
    DEFAULT_MESSAGE_PARSE_LIMIT,
    HEADLESS,
    MAX_UPLOAD_BYTES,
    MEDIA_DIR_PATH,
    REFERER_URL,
    STORAGE_STATE_PATH,
    get_price_markup,
)
from data.db import init_db, save_cookies, save_uploaded_product
from utils.logging import log
from utils.media import (
    cleanup_prepared_media_uploads,
    list_media_files,
    prepare_media_batch_for_upload,
    reset_media_dir,
    total_media_size_bytes,
)
from utils.pipeline_activity import enter_product_pipeline, exit_product_pipeline
from utils.progress import ProgressBar, verbose_photo_logs_enabled


def _has_invalid_size_error(errors: list[dict]) -> bool:
    for err in errors:
        field = str(err.get("field") or "").strip().casefold()
        if field == "size":
            return True
    return False


def main() -> None:
    enter_product_pipeline()
    try:
        _main_impl()
    finally:
        exit_product_pipeline()


def _main_impl() -> None:
    init_db()
    product_data = get_next_product_for_upload(
        message_amount=DEFAULT_MESSAGE_PARSE_LIMIT,
        first_fetch_check=should_run_first_fetch(),
        scan_before_pick=False,
    )
    if not product_data:
        log("INFO", "Нет новых товаров для создания.")
        return
    channel_id = product_data.get("channel_id")
    product_raw_data = product_data["product_raw_data"]
    parsed_data = product_data.get("parsed_data") or {}
    message_id = product_data["message_id"]
    photo_message_ids = get_product_photo_message_ids(product_data)
    product_name = product_raw_data.get("name") or parsed_data.get("name") or "—"
    log("INFO", f"Товар для создания: {product_name}.")

    catalog_slug = str(product_raw_data.get("category") or "").strip()
    if not catalog_slug:
        catalog_slug = "obuv/krossovki"
    if product_raw_data.get("size") is None:
        handle_retryable_product_failure(
            message_id=message_id,
            channel_id=channel_id,
            failure_reason="SIZE_NOT_RESOLVED",
            detail_message=(
                "Не удалось определить размер. "
                "Запусти Bootstrap sizes/brands."
            ),
        )
        return
    price_value = product_raw_data.get("price")
    if price_value is None or price_value <= 0:
        handle_retryable_product_failure(
            message_id=message_id,
            channel_id=channel_id,
            failure_reason="INVALID_PRICE",
            detail_message=(
                f"Некорректная цена: {price_value}. \n"
                + f"Parsed price: {parsed_data.get('price')!r}."
            ),
        )
        return
    price_markup = get_price_markup(DEFAULT_MARKUP)
    price_with_markup = price_value + price_markup
    log("INFO", f"Цена товара (с наценкой {price_markup}): {price_with_markup}.")

    try:
        media_dir = Path(MEDIA_DIR_PATH)
        reset_media_dir(media_dir)
        downloaded = download_product_photos(
            message_id,
            media_dir,
            channel_id=channel_id,
            message_ids=photo_message_ids,
        )
        if downloaded == 0:
            log("WARN", f"Не нашёл фото для message_id={message_id} в Telegram.")
        else:
            log("INFO", f"Скачано фото: {downloaded}.")
    except Exception as exc:
        handle_retryable_product_failure(
            message_id=message_id,
            channel_id=channel_id,
            failure_reason=(
                f"PRODUCT_PIPELINE_EXCEPTION: {summarize_exception(exc)}"
            ),
            detail_message=f"Не удалось обработать товар: {exc}",
        )
        return
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
            if (
                product_raw_data.get("brand") is None
                and catalog_requires_brand(catalog_slug)
                and parsed_data
            ):
                log("WARN", "Бренд не определён. Обновляю список брендов...")
                try:
                    brands = get_brands(ctx, csrftoken, catalog_slug=catalog_slug)
                    resolved_brand_catalog_slug = resolve_brand_catalog_slug(catalog_slug)
                    log(
                        "INFO",
                        f"Загружены бренды для {resolved_brand_catalog_slug}: {len(brands)}.",
                    )
                except Exception as exc:
                    handle_retryable_product_failure(
                        message_id=message_id,
                        channel_id=channel_id,
                        failure_reason="BRAND_REFRESH_FAILED",
                        detail_message=f"Не удалось обновить бренды: {exc}",
                    )
                    return
                parsed_data, product_raw_data = rebuild_product_data_from_source(product_data)
                if product_raw_data.get("brand") is None:
                    handle_non_retryable_product_failure(
                        message_id=message_id,
                        channel_id=channel_id,
                        failure_reason="BRAND_NOT_RESOLVED",
                        detail_message=(
                            "Не удалось распознать бренд. Запусти Bootstrap sizes/brands."
                        ),
                    )
                    return
            if (
                product_raw_data.get("brand") is None
                and catalog_requires_brand(catalog_slug)
            ):
                handle_non_retryable_product_failure(
                    message_id=message_id,
                    channel_id=channel_id,
                    failure_reason="BRAND_NOT_RESOLVED",
                    detail_message=(
                        "Не удалось распознать бренд. Запусти Bootstrap sizes/brands."
                    ),
                )
                return

            try:
                photo_ids: list[str] = []
                photo_paths = list_media_files(media_dir)
                if not photo_paths:
                    log("WARN", "Файлы для загрузки не найдены.")
                max_mb = MAX_UPLOAD_BYTES / (1024 * 1024)
                downloaded_total_mb = total_media_size_bytes(photo_paths) / (1024 * 1024)
                if photo_paths:
                    log(
                        "INFO",
                        f"Общий размер фото после скачивания из Telegram: "
                        + f"{downloaded_total_mb:.2f} MB.",
                    )
                log(
                    "INFO",
                    "Начинаю подготовку фото для загрузки.",
                )
                prepared_batch = prepare_media_batch_for_upload(photo_paths, MAX_UPLOAD_BYTES)
                log("INFO", "Подготовка фото для загрузки завершена.")
                filtered_paths = prepared_batch.items
                total_mb = prepared_batch.total_size_bytes / (1024 * 1024)
                for note in prepared_batch.notes:
                    log("INFO", note)
            except Exception as exc:
                handle_retryable_product_failure(
                    message_id=message_id,
                    channel_id=channel_id,
                    failure_reason=(
                        f"PRODUCT_PIPELINE_EXCEPTION: {summarize_exception(exc)}"
                    ),
                    detail_message=f"Не удалось обработать товар: {exc}",
                )
                return
            if photo_paths and not filtered_paths:
                log(
                    "WARN",
                    "Нет фото для загрузки после фильтрации размера.",
                )
            elif filtered_paths:
                log(
                    "INFO",
                    f"Общий размер подготовленных фото: {total_mb:.2f} MB / {max_mb:.2f} MB.",
                )
            if filtered_paths and not prepared_batch.within_budget:
                log(
                    "WARN",
                    f"После подготовки фото занимают {total_mb:.2f} MB, "
                    + f"что больше лимита {max_mb:.2f} MB.",
                )
            if not filtered_paths:
                handle_retryable_product_failure(
                    message_id=message_id,
                    channel_id=channel_id,
                    failure_reason="NO_UPLOADABLE_PHOTOS",
                    detail_message=(
                        "Не удалось подготовить ни одной фотографии для загрузки."
                    ),
                    detail_level="WARN",
                )
                return
            if not prepared_batch.within_budget:
                handle_retryable_product_failure(
                    message_id=message_id,
                    channel_id=channel_id,
                    failure_reason="NO_UPLOADABLE_PHOTOS",
                    detail_message=(
                        "Не удалось подготовить ни одной фотографии для загрузки."
                    ),
                    detail_level="WARN",
                )
                return
            try:
                verbose_photo_logs = verbose_photo_logs_enabled()
                with ProgressBar(
                    total=len(filtered_paths),
                    label="Загрузка фото",
                    enabled=not verbose_photo_logs,
                ) as progress:
                    for idx, upload_item in enumerate(filtered_paths, start=1):
                        upload_path = upload_item.upload_path
                        if upload_path is None:
                            continue
                        if verbose_photo_logs:
                            log(
                                "INFO",
                                f"Загрузка фото {idx}/{len(filtered_paths)}: "
                                f"{upload_item.source_path.name}",
                            )
                        photo_id = upload_photo(ctx, csrftoken, upload_path)
                        photo_ids.append(photo_id)
                        if verbose_photo_logs:
                            log("OK", f"Фото загружено: id={photo_id}")
                        if not verbose_photo_logs:
                            progress.advance()

                log("INFO", "Создаю товар...")
                result = create_product(
                    ctx,
                    csrftoken,
                    photo_ids,
                    product_raw_data,
                    markup=price_markup,
                )
                errors = result.get("errors") or []
                if errors and _has_invalid_size_error(errors) and parsed_data:
                    log(
                        "WARN",
                        "API отклонил размер. "
                        "Обновляю размеры и повторяю создание товара...",
                    )
                    try:
                        sizes = get_sizes(ctx, csrftoken, catalog_slug=catalog_slug)
                        log(
                            "INFO",
                            f"Загружены размеры для {catalog_slug}: {len(sizes)}.",
                        )
                    except Exception as exc:
                        handle_retryable_product_failure(
                            message_id=message_id,
                            channel_id=channel_id,
                            failure_reason="SIZE_REFRESH_FAILED",
                            detail_message=f"Не удалось обновить размеры: {exc}",
                        )
                        return
                    product_raw_data = build_product_raw_data(parsed_data)
                    if product_raw_data.get("size") is None:
                        handle_retryable_product_failure(
                            message_id=message_id,
                            channel_id=channel_id,
                            failure_reason="SIZE_NOT_RESOLVED",
                            detail_message=(
                                "Не удалось определить размер после обновления размеров."
                            ),
                        )
                        return
                    result = create_product(
                        ctx,
                        csrftoken,
                        photo_ids,
                        product_raw_data,
                        markup=price_markup,
                    )
                    errors = result.get("errors") or []
                if errors:
                    handle_retryable_product_failure(
                        message_id=message_id,
                        channel_id=channel_id,
                        failure_reason=(
                            f"CREATE_PRODUCT_ERRORS: {summarize_graph_errors(errors)}"
                        ),
                        detail_message=f"Ошибки создания товара: {errors}",
                    )
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
                log(
                    "OK",
                    f"Товар создан успешно. ID: {product_id}. Фото: {len(photo_ids)}.",
                )
                reset_media_dir(media_dir)
                log("INFO", "Фото удалены после создания товара.")
            except Exception as exc:
                handle_retryable_product_failure(
                    message_id=message_id,
                    channel_id=channel_id,
                    failure_reason=(
                        f"PRODUCT_PIPELINE_EXCEPTION: {summarize_exception(exc)}"
                    ),
                    detail_message=f"Не удалось обработать товар: {exc}",
                )
            finally:
                cleanup_prepared_media_uploads(filtered_paths)
        finally:
            browser.close()
