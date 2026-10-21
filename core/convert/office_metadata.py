"""Document properties of Word, PowerPoint and Excel files made from a PDF.

The libraries that write these files start from templates that carry their own properties (an author
"python-docx", "Steve Canny", "openpyxl", 2013 dates, "generated using python-pptx" comments). None of
that may end up in the user's file. Every Office file Monograph PDF writes gets:

A. preserved directly — title, author, subject, keywords from the PDF's document information;
B. mapped — the PDF's creation and modification dates become the Office "created" / "modified"
   dates (the PDF's Creator/Producer have no Office equivalent and are not copied);
C. not carried over — PDF-only data (XMP extensions, trapping, PDF/A identification, custom keys).

Nothing is invented: a property the PDF does not have is left empty, and no user name, computer name
or path of this computer is written.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Any

_PDF_DATE = re.compile(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?'?")


def parse_pdf_date(value: str | None) -> _dt.datetime | None:
    """'D:20261021093000+09'00'' -> aware UTC datetime (None if absent or malformed)."""
    if not value:
        return None
    m = _PDF_DATE.match(value.strip())
    if not m:
        return None
    y, mo, d, h, mi, s, sign, oh, om = m.groups()
    try:
        dt = _dt.datetime(int(y), int(mo or 1), int(d or 1), int(h or 0), int(mi or 0), int(s or 0))
    except ValueError:
        return None
    offset = _dt.timedelta(0)
    if sign in ("+", "-") and oh:
        offset = _dt.timedelta(hours=int(oh), minutes=int(om or 0))
        if sign == "-":
            offset = -offset
    return (dt - offset).replace(tzinfo=_dt.timezone.utc)


def pdf_properties(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """The PDF properties that have Office equivalents."""
    md = metadata or {}

    def text(key: str) -> str:
        return str(md.get(key) or "").strip()[:1000]

    return {
        "title": text("title"),
        "author": text("author"),
        "subject": text("subject"),
        "keywords": text("keywords"),
        "created": parse_pdf_date(md.get("creationDate")),
        "modified": parse_pdf_date(md.get("modDate")),
    }


def apply_core_properties(core: Any, props: dict[str, Any]) -> None:
    """Set python-docx / python-pptx core properties from ``pdf_properties``; clear template values."""
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    for name in ("title", "author", "subject", "keywords"):
        setattr(core, name, props.get(name) or "")
    for name in ("comments", "category", "last_modified_by", "content_status", "identifier", "language", "version"):
        try:
            setattr(core, name, "")
        except (AttributeError, ValueError):
            pass
    created = props.get("created") or now
    core.created = created.replace(tzinfo=None) if created.tzinfo else created
    modified = props.get("modified") or now
    core.modified = modified.replace(tzinfo=None) if modified.tzinfo else modified
    core.revision = 1
    try:
        core.last_printed = None
    except (AttributeError, ValueError, TypeError):
        pass


def apply_workbook_properties(wb: Any, props: dict[str, Any]) -> None:
    """The same for an openpyxl workbook (openpyxl's default creator "openpyxl" is removed)."""
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0, tzinfo=None)
    p = wb.properties
    p.title = props.get("title") or None
    p.creator = props.get("author") or None
    p.subject = props.get("subject") or None
    p.keywords = props.get("keywords") or None
    p.lastModifiedBy = None
    p.description = None
    p.category = None
    for key, attr in (("created", "created"), ("modified", "modified")):
        value = props.get(key)
        setattr(p, attr, value.replace(tzinfo=None) if value else now)


def document_metadata(document: Any) -> dict[str, Any]:
    """The PDF document information of an open PdfDocument (empty dict if unavailable)."""
    try:
        return dict(document._backend._doc.metadata or {})
    except Exception:  # noqa: BLE001
        return {}


def apply_to_file(path: Path, metadata: dict[str, Any] | None) -> None:
    """Rewrite the document properties of a .docx, .pptx or .xlsx file in place (atomically)."""
    path = Path(path)
    props = pdf_properties(metadata)
    suffix = path.suffix.lower()
    tmp = path.with_name(path.name + ".meta")
    if suffix == ".docx":
        from docx import Document

        doc = Document(path.as_posix())
        apply_core_properties(doc.core_properties, props)
        doc.save(tmp.as_posix())
    elif suffix == ".pptx":
        from pptx import Presentation

        prs = Presentation(path.as_posix())
        apply_core_properties(prs.core_properties, props)
        prs.save(tmp.as_posix())
    elif suffix == ".xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(path.as_posix())
        apply_workbook_properties(wb, props)
        wb.save(tmp.as_posix())
    else:
        raise ValueError(f"not an Office file: {path.name}")
    tmp.replace(path)
