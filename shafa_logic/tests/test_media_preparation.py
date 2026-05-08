import _test_path  # noqa: F401
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from utils.media import (
    PreparedMediaStage,
    PreparedMediaUpload,
    cleanup_prepared_media_uploads,
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

    def test_png_converts_to_jpg_with_high_quality_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "photo.png"
            image = Image.effect_noise((256, 256), 60).convert("RGB")
            image.save(file_path, format="PNG")

            prepared = prepare_media_for_upload(file_path, file_path.stat().st_size)
            try:
                self.assertEqual(prepared.preparation, "png_to_jpg")
                self.assertIsNotNone(prepared.upload_path)
                self.assertEqual(prepared.upload_path.suffix.lower(), ".jpg")
                self.assertEqual(prepared.upload_path.name, "photo_png_to_jpg.jpg")
                self.assertEqual(prepared.stages[0].name, "downloaded")
                self.assertEqual(prepared.stages[1].name, "png_to_jpg")
                with Image.open(prepared.upload_path) as converted:
                    self.assertEqual(converted.format, "JPEG")
                    self.assertEqual(converted.size, (256, 256))
            finally:
                cleanup_prepared_media_uploads([prepared])

    def test_transparent_png_flattens_to_jpg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "photo.png"
            image = Image.new("RGBA", (32, 32), (255, 0, 0, 0))
            image.putpixel((10, 10), (0, 0, 255, 255))
            image.save(file_path, format="PNG")

            prepared = prepare_media_for_upload(file_path, file_path.stat().st_size)
            try:
                self.assertEqual(prepared.preparation, "png_to_jpg")
                with Image.open(prepared.upload_path) as converted:
                    self.assertEqual(converted.format, "JPEG")
                    self.assertEqual(converted.mode, "RGB")
            finally:
                cleanup_prepared_media_uploads([prepared])

    def test_batch_converts_png_and_keeps_jpeg_original(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            png_path = Path(tmpdir) / "a.png"
            jpg_path = Path(tmpdir) / "b.jpg"
            Image.new("RGB", (64, 64), "red").save(png_path, format="PNG")
            jpg_path.write_bytes(b"jpg")

            batch = prepare_media_batch_for_upload(
                [png_path, jpg_path],
                10 * 1024 * 1024,
            )
            try:
                self.assertTrue(batch.within_budget)
                self.assertEqual(len(batch.items), 2)
                self.assertEqual(
                    [item.preparation for item in batch.items],
                    ["png_to_jpg", "original"],
                )
            finally:
                cleanup_prepared_media_uploads(batch.items)

    def test_describe_prepared_media_sizes_lists_png_conversion_stage(self):
        item = PreparedMediaUpload(
            source_path=Path("photo.png"),
            upload_path=Path("photo_png_to_jpg.jpg"),
            cleanup_path=None,
            preparation="png_to_jpg",
            size_bytes=3145728,
            stages=(
                PreparedMediaStage("downloaded", 524288),
                PreparedMediaStage("png_to_jpg", 3145728),
            ),
        )

        lines = describe_prepared_media_sizes([item])

        self.assertEqual(
            lines,
            [
                "Фото photo.png этапы: Telegram 0.50 MB -> PNG -> JPG 3.00 MB."
            ],
        )
