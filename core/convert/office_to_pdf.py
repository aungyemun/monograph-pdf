"""Word / Excel / PowerPoint (and RTF / OpenDocument) → PDF.

Uses the office suite already installed on this computer (Microsoft Office or
LibreOffice) via its native PDF export or print path to preserve layout as closely
as that application normally does. No suite is bundled or downloaded.
"""

from __future__ import annotations

from pathlib import Path

from core.convert.capabilities import UnsupportedConversionError
from core.convert.office_bridge import (
    OFFICE_EXTS,
    convert_office_file_to_pdf,
    office_availability,
    unavailable_message,
)

FIDELITY_NOTICE = (
    "Converted by the office application installed on this computer using its native PDF "
    "export or print path, preserving layout as closely as that application normally does."
)


def office_to_pdf_supported(ext: str | None = None) -> bool:
    avail = office_availability()
    if ext is None:
        return avail.any
    return avail.can_convert(ext)


def office_to_pdf(source: Path, destination: Path) -> Path:
    source = Path(source)
    ext = source.suffix.lower()
    if ext not in OFFICE_EXTS:
        raise UnsupportedConversionError(f"“{source.name}” is not a Word, Excel or PowerPoint file.")
    if not office_to_pdf_supported(ext):
        raise UnsupportedConversionError(unavailable_message(ext))
    return convert_office_file_to_pdf(source, Path(destination))
