import os
from pathlib import Path
from core.upload_photo import upload_photo
from core.create_product import create_product
from playwright.sync_api import sync_playwright
from core.core import get_csrftoken_from_context
from controller.data_controller import product_raw_data
from data.const import HEADLESS, REFERER_URL, MEDIA_DIR_PATH, STORAGE_STATE_PATH

def new_context_with_storage(browser):
    if STORAGE_STATE_PATH.exists():
        return browser.new_context(storage_state=str(STORAGE_STATE_PATH))
    return browser.new_context()

def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            ctx = new_context_with_storage(browser)
            page = ctx.new_page()

            page.goto(REFERER_URL, wait_until="networkidle")
            if not STORAGE_STATE_PATH.exists():
                input("Залогинься в окне браузера, затем нажми Enter...")
                ctx.storage_state(path=str(STORAGE_STATE_PATH))

            csrftoken = get_csrftoken_from_context(ctx)
            if not csrftoken:
                raise RuntimeError("Не нашёл csrftoken в cookies контекста")

            photo_ids: list[str] = []
            if os.path.exists(MEDIA_DIR_PATH) & os.path.isdir(MEDIA_DIR_PATH): 
                for photo in os.listdir(MEDIA_DIR_PATH):
                    photo_id = upload_photo(ctx, csrftoken, Path(os.path.join(MEDIA_DIR_PATH, photo)))
                    photo_ids.append(photo_id)
                    print("photo_id:", photo_id)

            result = create_product(ctx, csrftoken, photo_ids, product_raw_data)
            print("createdProduct:", result.get("createdProduct"))
            print("errors:", result.get("errors"))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
