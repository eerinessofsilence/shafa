from dataclasses import dataclass
import mimetypes
import shutil
import tempfile
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - optional at import time for tests
    Image = None
    ImageOps = None


@dataclass(frozen=True)
class PreparedMediaStage:
    name: str
    size_bytes: Optional[int]


@dataclass(frozen=True)
class PreparedMediaUpload:
    source_path: Path
    upload_path: Optional[Path]
    cleanup_path: Optional[Path]
    preparation: str
    size_bytes: Optional[int] = None
    stages: tuple[PreparedMediaStage, ...] = ()


@dataclass(frozen=True)
class PreparedMediaBatch:
    items: list[PreparedMediaUpload]
    total_size_bytes: int
    within_budget: bool
    notes: tuple[str, ...] = ()


_PREPARATION_STAGE_LABELS = {
    "downloaded": "Telegram",
    "original": "без изменений",
    "png_to_jpg": "PNG -> JPG",
}


def reset_media_dir(media_dir: Path) -> None:
    if media_dir.exists():
        for item in media_dir.iterdir():
            if item.is_file():
                item.unlink()
            else:
                shutil.rmtree(item)
    else:
        media_dir.mkdir(parents=True, exist_ok=True)


def list_media_files(media_dir: Path) -> list[Path]:
    if not media_dir.is_dir():
        return []
    return sorted(
        [path for path in media_dir.iterdir() if path.is_file()],
        key=lambda path: path.name,
    )


def total_media_size_bytes(file_paths: list[Path]) -> int:
    total = 0
    for file_path in file_paths:
        size_bytes = _safe_file_size(file_path)
        if size_bytes is None:
            continue
        total += size_bytes
    return total


def detect_media_mime_type(file_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(file_path.name)
    if mime_type and mime_type.startswith("image/"):
        return mime_type
    return "image/jpeg"


def cleanup_prepared_media_uploads(items: list[PreparedMediaUpload]) -> None:
    seen: set[Path] = set()
    for item in items:
        cleanup_path = item.cleanup_path
        if cleanup_path is None or cleanup_path in seen:
            continue
        seen.add(cleanup_path)
        shutil.rmtree(cleanup_path, ignore_errors=True)


def format_size_mb(size_bytes: Optional[int]) -> str:
    if size_bytes is None:
        return "?"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def describe_downloaded_media_sizes(file_paths: list[Path]) -> list[str]:
    return [
        f"Фото {file_path.name} после скачивания из Telegram: {format_size_mb(_safe_file_size(file_path))}."
        for file_path in file_paths
    ]


def describe_prepared_media_sizes(items: list[PreparedMediaUpload]) -> list[str]:
    lines: list[str] = []
    for item in items:
        if not item.stages:
            lines.append(
                f"Фото {item.source_path.name} итоговый размер: {format_size_mb(item.size_bytes)}."
            )
            continue
        stage_parts = []
        for stage in item.stages:
            label = _PREPARATION_STAGE_LABELS.get(stage.name, stage.name)
            stage_parts.append(f"{label} {format_size_mb(stage.size_bytes)}")
        lines.append(f"Фото {item.source_path.name} этапы: " + " -> ".join(stage_parts) + ".")
    return lines


def _safe_file_size(file_path: Path) -> Optional[int]:
    try:
        return file_path.stat().st_size
    except OSError:
        return None


def _open_image(file_path: Path):
    if Image is None:
        return None
    try:
        with Image.open(file_path) as img:
            if ImageOps is not None:
                exif_transpose = getattr(ImageOps, "exif_transpose", None)
                if exif_transpose:
                    img = exif_transpose(img)
            img.load()
            return img.copy()
    except Exception:
        return None


def _build_original_prepared_upload(file_path: Path) -> PreparedMediaUpload:
    source_size = _safe_file_size(file_path)
    if source_size is None:
        return PreparedMediaUpload(
            source_path=file_path,
            upload_path=None,
            cleanup_path=None,
            preparation="stat_failed",
        )
    return PreparedMediaUpload(
        source_path=file_path,
        upload_path=file_path,
        cleanup_path=None,
        preparation="original",
        size_bytes=source_size,
        stages=(
            PreparedMediaStage("downloaded", source_size),
            PreparedMediaStage("original", source_size),
        ),
    )


def _flatten_image_for_jpeg(image):
    if Image is None:
        return image
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in getattr(image, "info", {})
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _write_png_to_jpg_candidate(
    source_path: Path,
    work_dir: Path,
    source_size: Optional[int] = None,
) -> Optional[PreparedMediaUpload]:
    image = _open_image(source_path)
    if image is None:
        return None

    image = _flatten_image_for_jpeg(image)
    target_path = work_dir / f"{source_path.stem}_png_to_jpg.jpg"
    save_kwargs = {
        "format": "JPEG",
        "quality": 100,
        "subsampling": 0,
        "optimize": False,
        "progressive": False,
    }
    icc_profile = getattr(image, "info", {}).get("icc_profile")
    if icc_profile:
        save_kwargs["icc_profile"] = icc_profile

    try:
        image.save(target_path, **save_kwargs)
    except Exception:
        return None

    size_bytes = _safe_file_size(target_path)
    if size_bytes is None:
        return None
    return PreparedMediaUpload(
        source_path=source_path,
        upload_path=target_path,
        cleanup_path=work_dir,
        preparation="png_to_jpg",
        size_bytes=size_bytes,
        stages=(
            PreparedMediaStage("downloaded", source_size),
            PreparedMediaStage("png_to_jpg", size_bytes),
        ),
    )


def _build_prepared_batch(
    items: list[PreparedMediaUpload],
    total_max_bytes: int,
    notes: tuple[str, ...] = (),
) -> PreparedMediaBatch:
    total_size_bytes = sum(item.size_bytes or 0 for item in items)
    return PreparedMediaBatch(
        items=items,
        total_size_bytes=total_size_bytes,
        within_budget=total_size_bytes <= total_max_bytes,
        notes=notes,
    )


def prepare_media_for_upload(file_path: Path, max_bytes: int) -> PreparedMediaUpload:
    del max_bytes

    mime_type = detect_media_mime_type(file_path)
    if mime_type != "image/png":
        return _build_original_prepared_upload(file_path)

    source_size = _safe_file_size(file_path)
    if source_size is None:
        return PreparedMediaUpload(
            source_path=file_path,
            upload_path=None,
            cleanup_path=None,
            preparation="stat_failed",
        )

    work_dir = Path(tempfile.mkdtemp(prefix="shafa_upload_"))
    candidate = _write_png_to_jpg_candidate(file_path, work_dir, source_size=source_size)
    if candidate is not None:
        return candidate

    shutil.rmtree(work_dir, ignore_errors=True)
    return _build_original_prepared_upload(file_path)


def prepare_media_batch_for_upload(
    file_paths: list[Path],
    total_max_bytes: int,
) -> PreparedMediaBatch:
    if not file_paths:
        return PreparedMediaBatch(items=[], total_size_bytes=0, within_budget=True)

    items = [
        item
        for item in (
            prepare_media_for_upload(file_path, total_max_bytes) for file_path in file_paths
        )
        if item.upload_path is not None and item.size_bytes is not None
    ]
    return _build_prepared_batch(items, total_max_bytes)
