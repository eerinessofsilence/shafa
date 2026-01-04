from data.const import HEADLESS, REFERER_URL, FILE_PATH
from core.core import get_csrftoken_from_context
from core.upload_photo import upload_photo
from core.create_product import create_product
from playwright.sync_api import sync_playwright

def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            ctx = browser.new_context()
            page = ctx.new_page()

            page.goto(REFERER_URL, wait_until="networkidle")
            input("Если нужно — залогинься в окне браузера, затем нажми Enter...")

            csrftoken = get_csrftoken_from_context(ctx)
            if not csrftoken:
                raise RuntimeError("Не нашёл csrftoken в cookies контекста")

            photo_id = upload_photo(ctx, csrftoken, FILE_PATH)
            print("photo_id:", photo_id)

            result = create_product(ctx, csrftoken, photo_id)
            print("createdProduct:", result.get("createdProduct"))
            print("errors:", result.get("errors"))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
