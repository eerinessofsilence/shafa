import _test_path
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import with_playwright


class WithPlaywrightRetryTests(unittest.TestCase):
    @patch("core.with_playwright.handle_retryable_product_failure")
    @patch("core.with_playwright.get_sizes")
    @patch("core.with_playwright.create_product")
    @patch("core.with_playwright.upload_photo")
    @patch("core.with_playwright.ProgressBar")
    @patch("core.with_playwright.verbose_photo_logs_enabled")
    @patch("core.with_playwright.list_media_files")
    @patch("core.with_playwright.save_cookies")
    @patch("core.with_playwright.get_csrftoken_from_context")
    @patch("core.with_playwright.storage_state_has_cookies")
    @patch("core.with_playwright.new_context_with_storage")
    @patch("core.with_playwright.sync_playwright")
    @patch("core.with_playwright.download_product_photos")
    @patch("core.with_playwright.reset_media_dir")
    @patch("core.with_playwright.get_next_product_for_upload")
    @patch("core.with_playwright.init_db")
    def test_registers_retryable_failure_when_size_refresh_fails(
        self,
        _init_db,
        get_next_product_for_upload,
        _reset_media_dir,
        download_product_photos,
        sync_playwright,
        new_context_with_storage,
        storage_state_has_cookies,
        get_csrftoken_from_context,
        _save_cookies,
        list_media_files,
        verbose_photo_logs_enabled,
        progress_bar,
        upload_photo,
        create_product,
        get_sizes,
        handle_failure,
    ):
        get_next_product_for_upload.return_value = {
            "channel_id": 9,
            "message_id": 11543,
            "parsed_data": {"name": "Новинка", "price": "2500", "size": "41"},
            "product_raw_data": {
                "name": "Новинка",
                "price": 2500,
                "size": 41,
                "brand": 77,
                "category": "obuv/krossovki",
            },
        }
        download_product_photos.return_value = 1
        storage_state_has_cookies.return_value = True
        get_csrftoken_from_context.return_value = "token"
        verbose_photo_logs_enabled.return_value = False
        upload_photo.return_value = "photo-1"
        create_product.return_value = {"errors": [{"field": "size"}]}
        get_sizes.side_effect = RuntimeError("size refresh failed")

        playwright = Mock()
        browser = Mock()
        page = Mock()
        ctx = Mock()
        playwright.chromium.launch.return_value = browser
        ctx.new_page.return_value = page
        ctx.cookies.return_value = []
        new_context_with_storage.return_value = ctx

        manager = Mock()
        manager.__enter__ = Mock(return_value=playwright)
        manager.__exit__ = Mock(return_value=None)
        sync_playwright.return_value = manager

        progress = Mock()
        progress_manager = Mock()
        progress_manager.__enter__ = Mock(return_value=progress)
        progress_manager.__exit__ = Mock(return_value=None)
        progress_bar.return_value = progress_manager

        with tempfile.TemporaryDirectory() as tmpdir:
            photo_path = Path(tmpdir) / "shoe.jpg"
            photo_path.write_bytes(b"jpg")
            list_media_files.return_value = [photo_path]

            with_playwright.main()

        handle_failure.assert_called_once_with(
            message_id=11543,
            channel_id=9,
            failure_reason="SIZE_REFRESH_FAILED",
            detail_message="Не удалось обновить размеры: size refresh failed",
        )
