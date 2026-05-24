import json

from data.const import ORIGIN_URL, STORAGE_STATE_PATH
from data.db import load_cookies

try:
    from shafa_logic.utils.proxy import (
        build_playwright_proxy_settings,
        load_runtime_proxy_config,
    )
except ImportError:  # pragma: no cover - runtime script path fallback
    from utils.proxy import (  # type: ignore[no-redef]
        build_playwright_proxy_settings,
        load_runtime_proxy_config,
    )


def new_context_with_storage(browser):
    if STORAGE_STATE_PATH.exists():
        return browser.new_context(storage_state=str(STORAGE_STATE_PATH))
    ctx = browser.new_context()
    saved_cookies = load_cookies(ORIGIN_URL)
    if saved_cookies:
        ctx.add_cookies(saved_cookies)
    return ctx


def storage_state_has_cookies(path=STORAGE_STATE_PATH) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    cookies = data.get("cookies")
    return isinstance(cookies, list) and bool(cookies)


def browser_launch_kwargs(*, headless: bool) -> dict:
    launch_kwargs = {"headless": headless}
    proxy_settings = build_playwright_proxy_settings(load_runtime_proxy_config())
    if proxy_settings is not None:
        launch_kwargs["proxy"] = proxy_settings
    return launch_kwargs
