import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import no_playwright


class NoPlaywrightPhotoRetryTests(unittest.TestCase):
    @patch("core.no_playwright.create_product")
    @patch("core.no_playwright.handle_retryable_product_failure")
    @patch("core.no_playwright.list_media_files")
    @patch("core.no_playwright.download_product_photos")
    @patch("core.no_playwright.reset_media_dir")
    @patch("core.no_playwright._get_csrftoken_from_cookies")
    @patch("core.no_playwright._load_shafa_cookies")
    @patch("core.no_playwright.get_next_product_for_upload")
    @patch("core.no_playwright.init_db")
    def test_skips_create_request_when_no_uploadable_photos(
        self,
        _init_db,
        get_next_product_for_upload,
        load_cookies,
        get_csrftoken,
        _reset_media_dir,
        download_product_photos,
        list_media_files,
        handle_failure,
        create_product,
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
        load_cookies.return_value = [{"name": "csrftoken", "value": "token"}]
        get_csrftoken.return_value = "token"
        download_product_photos.return_value = 0
        list_media_files.return_value = []

        no_playwright.main()

        handle_failure.assert_called_once_with(
            message_id=11543,
            channel_id=9,
            failure_reason="NO_UPLOADABLE_PHOTOS",
            detail_message="Не удалось подготовить ни одной фотографии для загрузки.",
            detail_level="WARN",
        )
        create_product.assert_not_called()

    @patch("core.no_playwright.create_product")
    @patch("core.no_playwright.upload_photo")
    @patch("core.no_playwright.handle_retryable_product_failure")
    @patch("core.no_playwright.download_product_photos")
    @patch("core.no_playwright.reset_media_dir")
    @patch("core.no_playwright._get_csrftoken_from_cookies")
    @patch("core.no_playwright._load_shafa_cookies")
    @patch("core.no_playwright.get_next_product_for_upload")
    @patch("core.no_playwright.init_db")
    def test_registers_retryable_failure_when_pipeline_raises(
        self,
        _init_db,
        get_next_product_for_upload,
        load_cookies,
        get_csrftoken,
        _reset_media_dir,
        download_product_photos,
        handle_failure,
        upload_photo,
        create_product,
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
        load_cookies.return_value = [{"name": "csrftoken", "value": "token"}]
        get_csrftoken.return_value = "token"
        download_product_photos.return_value = 1
        upload_photo.return_value = "photo-1"
        create_product.side_effect = RuntimeError("GraphQL errors: brand")

        with tempfile.TemporaryDirectory() as tmpdir:
            photo_path = Path(tmpdir) / "shoe.jpg"
            photo_path.write_bytes(b"jpg")
            with patch("core.no_playwright.list_media_files", return_value=[photo_path]):
                no_playwright.main()

        handle_failure.assert_called_once_with(
            message_id=11543,
            channel_id=9,
            failure_reason="PRODUCT_PIPELINE_EXCEPTION: GraphQL errors: brand",
            detail_message="Не удалось обработать товар: GraphQL errors: brand",
        )

    @patch("core.no_playwright.handle_retryable_product_failure")
    @patch("core.no_playwright.download_product_photos")
    @patch("core.no_playwright.reset_media_dir")
    @patch("core.no_playwright._get_csrftoken_from_cookies")
    @patch("core.no_playwright._load_shafa_cookies")
    @patch("core.no_playwright.get_next_product_for_upload")
    @patch("core.no_playwright.init_db")
    def test_registers_retryable_failure_when_media_prep_raises(
        self,
        _init_db,
        get_next_product_for_upload,
        load_cookies,
        get_csrftoken,
        _reset_media_dir,
        download_product_photos,
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
        load_cookies.return_value = [{"name": "csrftoken", "value": "token"}]
        get_csrftoken.return_value = "token"
        download_product_photos.side_effect = RuntimeError("telegram down")

        no_playwright.main()

        handle_failure.assert_called_once_with(
            message_id=11543,
            channel_id=9,
            failure_reason="PRODUCT_PIPELINE_EXCEPTION: telegram down",
            detail_message="Не удалось обработать товар: telegram down",
        )
