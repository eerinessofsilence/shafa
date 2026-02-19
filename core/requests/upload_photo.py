import json
from pathlib import Path

from playwright.sync_api import BrowserContext

from core.core import base_headers, read_response_json
from data.const import API_URL, UPLOAD_PHOTO_MUTATION


def upload_photo(ctx: BrowserContext, csrftoken: str, file_path: Path) -> str:
    file_bytes = file_path.read_bytes()
    resp = ctx.request.post(
        API_URL,
        headers={
            **base_headers(csrftoken),
            "Accept": "application/json, text/plain, */*",
        },
        multipart={
            "operationName": "UploadPhoto",
            "query": UPLOAD_PHOTO_MUTATION,
            "variables": json.dumps({"file": "file"}),
            "file": {
                "name": file_path.name,
                "mimeType": "image/jpeg",
                "buffer": file_bytes,
            },
        },
    )

    data = read_response_json(resp)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    upload = data.get("data", {}).get("uploadPhoto") or {}
    if upload.get("errors"):
        raise RuntimeError(f"Upload errors: {upload['errors']}")

    photo_id = upload.get("idStr")
    if not photo_id:
        raise RuntimeError("Upload response missing idStr")

    return photo_id
