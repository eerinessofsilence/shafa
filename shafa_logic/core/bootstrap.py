from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from core.context import new_context_with_storage, storage_state_has_cookies
from core.core import get_csrftoken_from_context
from core.requests.get_brands import get_brands
from core.requests.get_sizes import get_sizes
from data.const import HEADLESS, REFERER_URL, STORAGE_STATE_PATH
from data.db import init_db, save_cookies

SIZE_CATALOG_SLUGS = ("obuv/krossovki", "zhenskaya-obuv/krossovki")


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
            if not storage_state_has_cookies(STORAGE_STATE_PATH):
                input("Log in in the browser window, then press Enter...")
                ctx.storage_state(path=str(STORAGE_STATE_PATH))

            csrftoken = get_csrftoken_from_context(ctx)
            if not csrftoken:
                raise RuntimeError("csrftoken not found in context cookies")
            save_cookies(ctx.cookies())

            sizes_total = 0
            for catalog_slug in SIZE_CATALOG_SLUGS:
                sizes = get_sizes(ctx, csrftoken, catalog_slug=catalog_slug)
                sizes_total += len(sizes)
                print(f"Saved sizes for {catalog_slug}: {len(sizes)}")
            brands = get_brands(ctx, csrftoken)
            print(f"Saved sizes total: {sizes_total}")
            print(f"Saved brands: {len(brands)}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
