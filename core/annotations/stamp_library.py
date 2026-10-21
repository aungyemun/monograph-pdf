"""The user's own stamps (custom text stamps and picture stamps), kept in the user-data folder.

``stamps/library.json`` lists them; pictures are stored as PNG copies (``stamps/<sha256>.png``) so a
stamp keeps working after the original picture file is moved or deleted. An optional clean-up turns a
near-white background transparent (for scanned stamps and signatures). Nothing is uploaded.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from core.editing.image_box import SAFE_IMAGE_FORMATS

MAX_PICTURE_SIDE = 2000  # pixels; larger pictures are scaled down when imported
MAX_ENTRIES = 200


@dataclass
class LibraryEntry:
    kind: str  # "text" | "picture"
    text: str = ""
    color: str = "#1d4ed8"
    picture: str = ""  # file name inside the stamps folder


def library_dir() -> Path:
    from core.user_prefs import user_data_dir

    return user_data_dir() / "stamps"


def _index_path() -> Path:
    return library_dir() / "library.json"


def load_entries() -> list[LibraryEntry]:
    try:
        data = json.loads(_index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for item in data.get("entries", [])[:MAX_ENTRIES] if isinstance(data, dict) else []:
        if not isinstance(item, dict) or item.get("kind") not in ("text", "picture"):
            continue
        entry = LibraryEntry(kind=item["kind"], text=str(item.get("text", ""))[:200],
                             color=str(item.get("color", "#1d4ed8"))[:9], picture=Path(str(item.get("picture", ""))).name)
        if entry.kind == "picture" and not (library_dir() / entry.picture).is_file():
            continue
        out.append(entry)
    return out


def save_entries(entries: list[LibraryEntry]) -> None:
    folder = library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    tmp = _index_path().with_suffix(".tmp")
    tmp.write_text(json.dumps({"schema": 1, "entries": [asdict(e) for e in entries[:MAX_ENTRIES]]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_index_path())


def picture_path(entry: LibraryEntry) -> Path:
    return library_dir() / entry.picture


def make_transparent(pil_image, threshold: int = 235):
    """Pixels lighter than ``threshold`` in every channel become transparent, with a soft edge."""
    import numpy as np
    from PIL import Image

    arr = np.asarray(pil_image.convert("RGBA")).copy()
    m = arr[..., :3].min(axis=2).astype(np.int32)
    soft = 20
    alpha = arr[..., 3].astype(np.int32)
    fade = np.clip((threshold - m) * 255 // soft, 0, 255)
    alpha = np.where(m >= threshold, 0, np.where(m >= threshold - soft, alpha * fade // 255, alpha))
    arr[..., 3] = alpha.astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def import_picture(source: Path, *, remove_white: bool = False) -> Path:
    """Copy a picture into the stamps folder as PNG (everyday raster formats only). Returns its path."""
    from PIL import Image

    with Image.open(Path(source).as_posix(), formats=SAFE_IMAGE_FORMATS) as im:
        im.load()
        pic = im.convert("RGBA")
    if max(pic.size) > MAX_PICTURE_SIDE:
        pic.thumbnail((MAX_PICTURE_SIDE, MAX_PICTURE_SIDE))
    if remove_white:
        pic = make_transparent(pic)
    buf = io.BytesIO()
    pic.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    folder = library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (hashlib.sha256(data).hexdigest()[:32] + ".png")
    if not target.is_file():
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
    return target


def png_bytes_to_library(data: bytes) -> Path:
    """Store generated PNG bytes (a typed or drawn signature) in the stamps folder; returns the path."""
    folder = library_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (hashlib.sha256(data).hexdigest()[:32] + ".png")
    if not target.is_file():
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
    return target
