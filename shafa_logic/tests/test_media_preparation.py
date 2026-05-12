import _test_path  # noqa: F401
import tempfile
import unittest
from pathlib import Path

from utils.media import (
    PreparedMediaStage,
    PreparedMediaUpload,
    describe_prepared_media_sizes,
    prepare_media_batch_for_upload,
    prepare_media_for_upload,
)


class MediaPreparationTests(unittest.TestCase):
    def test_returns_original_non_image_without_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "photo.bin"
            file_path.write_bytes(b"0" * 128)

            prepared = prepare_media_for_upload(file_path, 256)

        self.assertEqual(prepared.preparation, "original")
        self.assertEqual(prepared.upload_path, file_path)
        self.assertIsNone(prepared.cleanup_path)
        self.assertEqual(prepared.size_bytes, 128)

    def test_jpeg_stays_original_without_recompression(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "photo.jpg"
            file_path.write_bytes(b"0" * 100)

            prepared = prepare_media_for_upload(file_path, 100)

        self.assertEqual(prepared.preparation, "original")
        self.assertEqual(prepared.upload_path, file_path)
        self.assertEqual(prepared.size_bytes, 100)

    def test_png_stays_original_without_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "photo.png"
            file_path.write_bytes(b"png")

            prepared = prepare_media_for_upload(file_path, file_path.stat().st_size)
        self.assertEqual(prepared.preparation, "original")
        self.assertEqual(prepared.upload_path, file_path)
        self.assertIsNone(prepared.cleanup_path)
        self.assertEqual(prepared.size_bytes, 3)
        self.assertEqual(
            prepared.stages,
            (
                PreparedMediaStage("downloaded", 3),
                PreparedMediaStage("original", 3),
            ),
        )

    def test_batch_keeps_png_and_jpeg_original(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = Path(tmpdir) / "a.png"
            jpg_path = Path(tmpdir) / "b.jpg"
            png_path.write_bytes(b"png")
            jpg_path.write_bytes(b"jpg")

            batch = prepare_media_batch_for_upload(
                [png_path, jpg_path],
                10 * 1024 * 1024,
            )
        self.assertTrue(batch.within_budget)
        self.assertEqual(len(batch.items), 2)
        self.assertEqual(
            [item.preparation for item in batch.items],
            ["original", "original"],
        )

    def test_describe_prepared_media_sizes_lists_original_stage(self):
        item = PreparedMediaUpload(
            source_path=Path("photo.png"),
            upload_path=Path("photo.png"),
            cleanup_path=None,
            preparation="original",
            size_bytes=524288,
            stages=(
                PreparedMediaStage("downloaded", 524288),
                PreparedMediaStage("original", 524288),
            ),
        )

        lines = describe_prepared_media_sizes([item])

        self.assertEqual(
            lines,
            [
                "Фото photo.png этапы: Telegram 0.50 MB -> без изменений 0.50 MB."
            ],
        )
