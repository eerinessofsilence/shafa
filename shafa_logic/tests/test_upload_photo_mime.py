import _test_path
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import no_playwright
import core.requests.upload_photo as playwright_upload_photo


class UploadPhotoMimeTests(unittest.TestCase):
    @patch("core.no_playwright._request_json")
    @patch("core.no_playwright._encode_multipart")
    def test_no_playwright_preserves_png_mime_type(
        self,
        encode_multipart,
        request_json,
    ):
        encode_multipart.return_value = (b"body", "boundary")
        request_json.return_value = {"data": {"uploadPhoto": {"idStr": "photo-1"}}}

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "photo.png"
            file_path.write_bytes(b"png")

            photo_id = no_playwright.upload_photo("token", [], file_path)

        self.assertEqual(photo_id, "photo-1")
        files = encode_multipart.call_args.args[1]
        self.assertEqual(files["file"][1], "image/png")

    @patch("core.requests.upload_photo.read_response_json")
    def test_playwright_upload_preserves_webp_mime_type(self, read_response_json):
        read_response_json.return_value = {"data": {"uploadPhoto": {"idStr": "photo-2"}}}
        ctx = Mock()
        ctx.request.post.return_value = object()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "photo.webp"
            file_path.write_bytes(b"webp")

            photo_id = playwright_upload_photo.upload_photo(ctx, "token", file_path)

        self.assertEqual(photo_id, "photo-2")
        multipart = ctx.request.post.call_args.kwargs["multipart"]
        self.assertEqual(multipart["file"]["mimeType"], "image/webp")
