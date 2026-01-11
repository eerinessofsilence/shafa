from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from core.context import new_context_with_storage
from core.core import get_csrftoken_from_context
from core.get_brands import get_brands
from core.get_sizes import get_sizes
from data.const import HEADLESS, REFERER_URL, STORAGE_STATE_PATH
from data.db import init_db, save_cookies


def main() -> None:
    init_db()
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
                input("Log in in the browser window, then press Enter...")
                ctx.storage_state(path=str(STORAGE_STATE_PATH))

            csrftoken = get_csrftoken_from_context(ctx)
            if not csrftoken:
                raise RuntimeError("csrftoken not found in context cookies")
            save_cookies(ctx.cookies())

            sizes = get_sizes(ctx, csrftoken)
            brands = get_brands(ctx, csrftoken)
            print(f"Saved sizes: {len(sizes)}")
            print(f"Saved brands: {len(brands)}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
