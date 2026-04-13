import shutil
from pathlib import Path


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
