"""Optional OCR languages (Japanese vertical, Chinese, Korean, German, French, Spanish ...).

English and Japanese (and the orientation data) are bundled. ``resources/ocr/language_packs.json``
pins each optional language file (official tesseract-ocr/tessdata_fast release 4.1.0, the same release
as the bundled files; Apache-2.0) by size and SHA-256. A file is accepted only if it matches a pin and
is copied to the user's local app-data folder; it can be used at once. It arrives in one of three ways,
always on the user's request (**OCR ▸ OCR Languages**):

* **Download and Install** — core/ocr/language_download.py fetches the pinned file (this module itself
  never uses the network);
* **Install from File** — a file the user downloaded;
* language files already in the user's Downloads folder are offered for installation.

The pins ship inside each signed release, so a future release adds languages through the normal
(signed) update.

Tesseract reads its language data from one folder. When an installed optional language is used, OCR
runs on a merged folder (the user's language folder plus links to — or, across drives, copies of — the
bundled files).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from app.paths import RESOURCES_DIR
from core import app_env
from core.ocr.paths import tessdata_dir

CATALOG = RESOURCES_DIR / "ocr" / "language_packs.json"
BUNDLED_NAMES = {"eng": "English", "jpn": "Japanese", "osd": "Orientation detection"}


class LanguagePackError(Exception):
    pass


@dataclass(frozen=True)
class LanguagePack:
    code: str
    name: str
    file: str
    size: int
    sha256: str
    url: str


def catalog() -> list[LanguagePack]:
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for p in data.get("packs", []):
        try:
            out.append(LanguagePack(code=str(p["code"]), name=str(p["name"]), file=str(p["file"]), size=int(p["size"]),
                                    sha256=str(p["sha256"]).lower(), url=str(p["url"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def user_language_dir() -> Path:
    """Where installed optional languages are kept (local app data, not the roaming profile)."""
    override = app_env.get("USER_DATA_DIR")
    if override:
        return Path(override) / "ocr-languages"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        from core.product_meta import DATA_FOLDER_NAME

        return Path(base) / DATA_FOLDER_NAME / "OCR Languages"
    from core.user_prefs import user_cache_dir

    return user_cache_dir() / "ocr-languages"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


_VERIFIED: dict[tuple[str, int, int], str] = {}  # (path, size, mtime_ns) -> SHA-256 already computed


def installed() -> list[LanguagePack]:
    """Optional languages installed and still matching their pins (a changed file is not used). A
    file's SHA-256 is computed once per (size, modification time), not every time a list is shown."""
    folder = user_language_dir()
    out = []
    for pack in catalog():
        f = folder / pack.file
        try:
            if not f.is_file():
                continue
            st = f.stat()
            if st.st_size != pack.size:
                continue
            key = (str(f), st.st_size, st.st_mtime_ns)
            digest = _VERIFIED.get(key)
            if digest is None:
                digest = _VERIFIED[key] = _sha256(f)
            if digest == pack.sha256:
                out.append(pack)
        except OSError:
            continue
    return out


def available_languages() -> dict[str, str]:
    """code -> display name of every language OCR can use now (bundled + installed)."""
    langs = {code: name for code, name in BUNDLED_NAMES.items()
             if code != "osd" and (tessdata_dir() / f"{code}.traineddata").is_file()}
    langs.update({p.code: p.name for p in installed()})
    return langs


def install_from_file(path: Path) -> LanguagePack:
    """Install a downloaded language file if it matches a pinned pack (by size and SHA-256)."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LanguagePackError(f"The file cannot be read: {exc.strerror or exc}") from exc
    candidates = [p for p in catalog() if p.size == size]
    digest = _sha256(path) if candidates else ""
    match = next((p for p in candidates if p.sha256 == digest), None)
    if match is None:
        raise LanguagePackError(
            "This file is not one of the supported OCR language files (its size or SHA-256 does not match). "
            "Download the file from the address shown for the language and install it unchanged.")
    folder = user_language_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / match.file
    tmp = target.with_suffix(".part")
    shutil.copyfile(path, tmp)
    if _sha256(tmp) != match.sha256:  # copied bytes are checked again
        tmp.unlink(missing_ok=True)
        raise LanguagePackError("The copied file did not verify; nothing was installed.")
    tmp.replace(target)
    return match


def downloads_folder() -> Path:
    try:
        from core.windows_paths import get_downloads_dir

        return Path(get_downloads_dir())
    except Exception:  # noqa: BLE001
        return Path.home() / "Downloads"


def downloads_found(folder: Path | None = None) -> list[tuple[LanguagePack, Path]]:
    """Pinned language files in the Downloads folder that are not installed yet (matched by name and
    size here; the SHA-256 is checked when they are installed). Only ``*.traineddata`` names are read."""
    folder = folder or downloads_folder()
    have = {p.code for p in installed()}
    out = []
    try:
        for pack in catalog():
            f = folder / pack.file
            if pack.code not in have and f.is_file() and f.stat().st_size == pack.size:
                out.append((pack, f))
    except OSError:
        return out
    return out


def remove(code: str) -> bool:
    pack = next((p for p in catalog() if p.code == code), None)
    if pack is None:
        return False
    f = user_language_dir() / pack.file
    if f.is_file():
        f.unlink()
        return True
    return False


def tessdata_for(languages: str) -> Path:
    """The language folder for an OCR language string ("eng+jpn+kor"): the bundled folder when it has
    everything, otherwise the user's language folder completed with the bundled files."""
    wanted = [c for c in languages.split("+") if c]
    bundled = tessdata_dir()
    if all((bundled / f"{c}.traineddata").is_file() for c in wanted):
        return bundled
    have = {p.code for p in installed()}
    missing = [c for c in wanted if c not in have and not (bundled / f"{c}.traineddata").is_file()]
    if missing:
        raise LanguagePackError(f"OCR language not installed: {', '.join(missing)}")
    folder = user_language_dir()
    for f in bundled.glob("*.traineddata"):
        target = folder / f.name
        try:
            if target.is_file() and target.stat().st_size == f.stat().st_size:
                continue
            target.unlink(missing_ok=True)
            try:
                os.link(f, target)  # same drive: no extra space
            except OSError:
                shutil.copyfile(f, target)
        except OSError as exc:
            raise LanguagePackError(f"The OCR language folder cannot be prepared: {exc.strerror or exc}") from exc
    return folder
