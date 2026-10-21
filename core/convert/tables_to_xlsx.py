"""Detected tables → XLSX (best-effort)."""

from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook

from core.document import PdfDocument
from core.tables.detect import detect_tables

FIDELITY_NOTICE = (
    "Best-effort: tables are found from the lines drawn on the page. "
    "Merged cells, formatting and tables without ruled lines may be missing. "
    "Plain numbers become Excel numbers; everything else (dates, codes with leading zeros, text) stays text."
)

_PLAIN_NUMBER = re.compile(r"^-?(0|[1-9]\d{0,14})(\.\d{1,10})?$")
_GROUPED_NUMBER = re.compile(r"^-?[1-9]\d{0,2}(,\d{3})+(\.\d{1,10})?$")


def cell_value(text: str):
    """A plain number as int/float, anything else unchanged. Leading zeros (codes, phone numbers),
    dates, percentages and long digit strings are kept as text so no information is changed."""
    t = (text or "").strip()
    if _PLAIN_NUMBER.match(t) or _GROUPED_NUMBER.match(t):
        t = t.replace(",", "")
        return float(t) if "." in t else int(t)
    return text


def tables_to_xlsx(
    document: PdfDocument,
    destination: Path,
    *,
    page_index: int | None = None,
    pages: list[int] | None = None,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    backend_doc = document._backend._doc  # noqa: SLF001
    if pages is not None:
        tables = [t for p in pages for t in detect_tables(backend_doc, p)]
    else:
        tables = detect_tables(backend_doc, page_index)
    wb = Workbook()
    # Remove default sheet after we create content
    default = wb.active
    default.title = "Info"
    default["A1"] = FIDELITY_NOTICE
    if not tables:
        default["A2"] = "No tables detected."
    for ti, table in enumerate(tables):
        ws = wb.create_sheet(title=f"Table{ti + 1}_p{table.page_index + 1}"[:31])
        for r in range(table.nrows):
            for c in range(table.ncols):
                cell = table.cells.get((r, c))
                value = cell.text if cell else ""
                ws.cell(row=r + 1, column=c + 1, value=cell_value(value))
    destination.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destination.as_posix())
    return destination
