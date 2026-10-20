"""Installed fonts that may be embedded into a saved PDF (text boxes and form entries).

A font is embedded only when all of these hold; otherwise the text is saved with the closest built-in PDF
face and the caller is told (``take_notes``):

* the family (and bold / italic variant) is installed as a single-face TrueType / OpenType file
  (collections ``.ttc`` are not embedded);
* the font's OS/2 ``fsType`` allows embedding: installable (0) or editable (8). Restricted-license (2),
  preview-and-print only (4), bitmap-only (0x200) and no-subsetting (0x100) fonts are never embedded;
* the font file can be read.

Only a subset of the glyphs actually used goes into the user's PDF (done by the caller with
``Document.subset_fonts``). No font file is copied anywhere else, shipped or redistributed.
Windows only (font files are found through the registry); elsewhere nothing is embedded.
"""

from __future__ import annotations

import os
import re
import sys
from functools import lru_cache
from pathlib import Path

import fitz

_ALLOWED_FSTYPE = {0, 8}
_NOTES: dict[str, str] = {}

_GENERIC = {"sans-serif", "serif", "monospace", "helvetica", "helv", "times", "times-roman", "tiro", "courier", "cour"}


def note_fallback(family: str, reason: str) -> None:
    """Remember that ``family`` could not be embedded (shown to the user after a save)."""
    if family and family.strip().lower() not in _GENERIC:
        _NOTES.setdefault(family, reason)


def take_notes() -> dict[str, str]:
    """Return and clear the fallbacks recorded since the last call: {family: reason}."""
    out = dict(_NOTES)
    _NOTES.clear()
    return out


@lru_cache(maxsize=1)
def _registry_fonts() -> dict[str, Path]:
    """Lower-case face name (``arial bold``) → file, from the Windows font registry."""
    found: dict[str, Path] = {}
    if not sys.platform.startswith("win"):
        return found
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return found
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(hive, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            continue
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            path = Path(value)
            if not path.is_absolute():
                path = fonts_dir / value
            name = re.sub(r"\s*\((truetype|opentype)\);?\s*$", "", name, flags=re.I)
            for alias in name.split(" & "):  # "Meiryo & Meiryo UI" lists several faces for one file
                found.setdefault(alias.strip().lower(), path)
    return found


def _candidates(family: str, bold: bool, italic: bool) -> list[str]:
    fam = family.strip().lower()
    if bold and italic:
        return [f"{fam} bold italic", f"{fam} bold oblique"]
    if bold:
        return [f"{fam} bold", f"{fam} demibold", f"{fam} semibold"]
    if italic:
        return [f"{fam} italic", f"{fam} oblique"]
    return [fam, f"{fam} regular", f"{fam} medium"]


def find_font_file(family: str, bold: bool = False, italic: bool = False) -> Path | None:
    reg = _registry_fonts()
    for name in _candidates(family, bold, italic):
        path = reg.get(name)
        if path is not None and path.is_file():
            return path
    return None


@lru_cache(maxsize=256)
def embedding_verdict(path: str) -> tuple[bool, str]:
    """(allowed, reason) from the file type and OS/2 fsType."""
    if path.lower().endswith((".ttc", ".otc")):
        return False, "font collections (.ttc) are not embedded"
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path, lazy=True, fontNumber=0)
        try:
            fs = int(font["OS/2"].fsType) if "OS/2" in font else 0
        finally:
            font.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"the font file could not be read ({type(exc).__name__})"
    if fs & 0x0200:
        return False, "the font only allows bitmap embedding"
    if fs & 0x0100:
        return False, "the font forbids subsetting"
    if (fs & 0x000F) not in _ALLOWED_FSTYPE:
        return False, f"the font's license does not allow embedding (fsType {fs & 0xF})"
    return True, ""


_SYSTEM_IDS: set[int] = set()


@lru_cache(maxsize=256)
def _load(path: str) -> fitz.Font:
    font = fitz.Font(fontfile=path)
    _SYSTEM_IDS.add(id(font))  # cached for the process lifetime, so the id stays valid
    return font


def load(family: str, bold: bool = False, italic: bool = False) -> fitz.Font | None:
    """The installed font as a MuPDF font when it may be embedded; otherwise None and a note is recorded."""
    if not family or family.strip().lower() in _GENERIC:
        return None
    path = find_font_file(family, bold, italic)
    if path is None:
        regular = find_font_file(family, False, False)
        if regular is None:
            note_fallback(family, "this font is not installed on this computer")
        else:
            note_fallback(family, "no matching bold / italic file is installed")
        return None
    ok, reason = embedding_verdict(str(path))
    if not ok:
        note_fallback(family, reason)
        return None
    try:
        return _load(str(path))
    except Exception as exc:  # noqa: BLE001
        note_fallback(family, f"the font file could not be loaded ({type(exc).__name__})")
        return None


def is_system_font(font: fitz.Font) -> bool:
    """True for a font returned by :func:`load` (its glyph coverage is the font's own, any script)."""
    return id(font) in _SYSTEM_IDS


_ROUNDTRIP: dict[tuple[int, str], bool] = {}


def roundtrips(font: fitz.Font, ch: str) -> bool:
    """True when ``ch`` written with ``font`` (subset, saved, reopened) is extracted as ``ch``.

    Some installed fonts give two code points one glyph (space and U+00A0, "(" and U+FD3E, "-" and U+2011);
    MuPDF may then record the wrong one in the file's ToUnicode map, which would break copy and search in
    other viewers. Such characters are drawn with the built-in font instead. Checked once per font and
    character by really writing and reading back a one-character page.
    """
    key = (id(font), ch)
    if key not in _ROUNDTRIP:
        ok = False
        try:
            doc = fitz.open()
            page = doc.new_page(width=80, height=40)
            tw = fitz.TextWriter(page.rect)
            tw.append((10, 25), ch if ch != " " else "a a", font=font, fontsize=12)
            tw.write_text(page)
            doc.subset_fonts()
            back = fitz.open("pdf", doc.tobytes())
            got = back[0].get_text().replace(chr(10), "")
            want = ch if ch != " " else "a a"
            ok = got.strip() == want.strip() and (ch != " " or " " in got)
            back.close()
            doc.close()
        except Exception:  # noqa: BLE001
            ok = False
        _ROUNDTRIP[key] = ok
    return _ROUNDTRIP[key]
