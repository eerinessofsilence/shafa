import json
from typing import Optional
from data.const import ORIGIN_URL, REFERER_URL, APP_PLATFORM, APP_VERSION
from playwright.sync_api import BrowserContext

def base_headers(csrftoken: str) -> dict:
    return {
        "Origin": ORIGIN_URL,
        "Referer": REFERER_URL,
        "X-CSRFToken": csrftoken,
        "x-app-platform": APP_PLATFORM,
        "x-app-version": APP_VERSION,
    }


def get_csrftoken_from_context(ctx: BrowserContext) -> Optional[str]:
    cookies = ctx.cookies(ORIGIN_URL)
    return next((c["value"] for c in cookies if c["name"] == "csrftoken"), None)


def read_response_json(resp, preview: int = 2000) -> dict:
    text = resp.text()
    print(text[:preview])
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Response is not valid JSON") from exc
