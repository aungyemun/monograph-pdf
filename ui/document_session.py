"""Per-document editing session for the multi-tab MainWindow (FEATURE-01)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.document import PdfDocument
from core.editing.edit_model import EditableDocument
from ui.pdf_canvas import ZoomMode


def canonical_doc_path(path: str | Path | None) -> Path | None:
    """Stable path key for tab dedupe (same file opened twice focuses the existing tab)."""
    if path is None:
        return None
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path)


@dataclass
class DocumentSession:
    document: PdfDocument
    edit: EditableDocument
    page_index: int = 0
    zoom: float = 1.0
    zoom_mode: ZoomMode = ZoomMode.FIT_WIDTH
    converted_from: Path | None = None
    search_hits: list[tuple[int, object]] = field(default_factory=list)
    search_index: int = -1
    last_query: str | None = None

    def path_key(self) -> Path | None:
        return canonical_doc_path(getattr(self.document, "path", None))

    def tab_title(self) -> str:
        mark = " *" if self.edit.dirty else ""
        src = self.converted_from
        if src is not None:
            return f"{src.stem}.pdf{mark}"
        return f"{self.document.name}{mark}"
