"""PDF document model — open never modifies the source file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from core.page_info import PageContentKind, PageInfo


class DocumentError(Exception):
    """Base document error."""


class PasswordRequiredError(DocumentError):
    """Raised when the PDF needs a password and none/incorrect was supplied."""


class InvalidPdfError(DocumentError):
    """Raised for malformed or unreadable PDF data."""


class PermissionError_(DocumentError):
    """Raised when an operation is forbidden by PDF permissions."""


@dataclass(frozen=True)
class DocumentMetadata:
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    creator: str = ""
    producer: str = ""
    creation_date: str = ""
    mod_date: str = ""
    page_count: int = 0
    encrypted: bool = False
    needs_password: bool = False
    permissions: dict[str, bool] = field(default_factory=dict)
    has_acroform: bool = False
    has_digital_signatures: bool = False
    format: str = "PDF"


@dataclass
class DocumentDiagnostics:
    text_pages: int = 0
    image_scanned_pages: int = 0
    mixed_pages: int = 0
    empty_pages: int = 0


class PdfDocument:
    """High-level document handle. Delegates I/O to the MuPDF backend."""

    def __init__(self, backend: Any, path: Path, password_used: bool = False) -> None:
        self._backend = backend
        self.path = Path(path)
        self.password_used = password_used
        self._pages: list[PageInfo] | None = None
        self._closed = False

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def page_count(self) -> int:
        self._ensure_open()
        return int(self._backend.page_count)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def metadata(self) -> DocumentMetadata:
        self._ensure_open()
        return self._backend.read_metadata()

    def diagnostics(self) -> DocumentDiagnostics:
        pages = self.pages()
        diag = DocumentDiagnostics()
        for page in pages:
            if page.content_kind == PageContentKind.TEXT:
                diag.text_pages += 1
            elif page.content_kind == PageContentKind.IMAGE_SCANNED:
                diag.image_scanned_pages += 1
            elif page.content_kind == PageContentKind.MIXED:
                diag.mixed_pages += 1
            else:
                diag.empty_pages += 1
        return diag

    def pages(self) -> list[PageInfo]:
        self._ensure_open()
        if self._pages is None:
            self._pages = [self._backend.analyze_page(i) for i in range(self.page_count)]
        return self._pages

    def invalidate_pages(self) -> None:
        """Clear cached PageInfo after structural page operations."""
        self._pages = None

    def page(self, index: int) -> PageInfo:
        pages = self.pages()
        if index < 0 or index >= len(pages):
            raise IndexError(f"page index out of range: {index}")
        return pages[index]

    def iter_pages(self) -> Iterator[PageInfo]:
        yield from self.pages()

    def search(self, query: str, *, case_sensitive: bool = False) -> list[tuple[int, Any]]:
        """Return list of (page_index, rect_in_pdf_points) hits."""
        self._ensure_open()
        if not query:
            return []
        return self._backend.search(query, case_sensitive=case_sensitive)

    def page_text(self, index: int) -> str:
        self._ensure_open()
        return self._backend.page_text(index)

    def render_pixmap_png(
        self,
        page_index: int,
        *,
        zoom: float,
        dpr: float = 1.0,
        alpha: bool = False,
    ) -> bytes:
        """Render page to PNG bytes at display zoom * DPR (PDF coords stay independent)."""
        self._ensure_open()
        return self._backend.render_png(page_index, zoom=zoom, dpr=dpr, alpha=alpha)

    def render_thumbnail_png(self, page_index: int, max_edge_px: int = 160) -> bytes:
        self._ensure_open()
        return self._backend.render_thumbnail_png(page_index, max_edge_px=max_edge_px)

    def can_save(self) -> bool:
        self._ensure_open()
        return bool(self._backend.can_save())

    def save_as(self, destination: Path) -> None:
        """Write a copy to destination. Never overwrites source via this API's open path."""
        self._ensure_open()
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            # Explicit Save As to same path still goes through backend save; caller must
            # intend overwrite. Prefer distinct paths for safety in UI.
            pass
        if not self._backend.can_save():
            raise PermissionError_("Saving is not permitted by this document's security settings.")
        self._backend.save_as(destination)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._pages = None
        try:
            self._backend.close()
        finally:
            self._backend = None

    def _ensure_open(self) -> None:
        if self._closed or self._backend is None:
            raise DocumentError("Document is closed")


def open_document(path: str | Path, password: str | None = None) -> PdfDocument:
    """Open a local PDF without modifying the source file."""
    from engines.mupdf_backend import MuPdfBackend

    path = Path(path)
    if not path.is_file():
        raise InvalidPdfError(f"File not found: {path}")
    try:
        backend = MuPdfBackend.open(path, password=password)
    except PasswordRequiredError:
        raise
    except DocumentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InvalidPdfError(str(exc)) from exc
    return PdfDocument(backend, path, password_used=bool(password))
