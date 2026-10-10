"""Files the operator places in data/local. Paths outside that folder are rejected."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings

ALLOWED_SUFFIXES = {".xlsx", ".csv", ".pdf", ".docx", ".txt", ".md"}


def local_folder() -> Path:
    path = get_settings().resolved_data_dir() / "local"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def list_local_files() -> list[dict]:
    root = local_folder()
    items = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        items.append({"name": path.name, "size_bytes": path.stat().st_size, "suffix": path.suffix.lower()})
    return items


def read_local_file(name: str) -> tuple[str, bytes]:
    if not name or name != Path(name).name or ".." in name or name.startswith("."):
        raise ValueError("Choose a file name from the local folder, not a path.")
    root = local_folder()
    path = (root / name).resolve()
    if path.parent != root or path.suffix.lower() not in ALLOWED_SUFFIXES or not path.is_file():
        raise LookupError("That file is not in the local folder.")
    content = path.read_bytes()
    limit = get_settings().upload_max_mb * 1024 * 1024
    if len(content) > limit:
        raise ValueError(f"The file exceeds the {get_settings().upload_max_mb} MB limit.")
    return path.name, content
