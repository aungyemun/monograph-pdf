"""PyMuPDF backend — read-only open semantics; Save As writes a separate file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from core.document import DocumentMetadata, InvalidPdfError, PasswordRequiredError
from core.page_space import rect_to_display
from core.page_info import PageContentKind, PageInfo

# Heuristic: mostly images + little text => scanned/image page
_SCAN_TEXT_THRESHOLD = 40


class MuPdfBackend:
    def __init__(
        self,
        doc: fitz.Document,
        path: Path,
        *,
        was_encrypted: bool = False,
        needs_password: bool = False,
    ) -> None:
        self._doc = doc
        self._path = path
        self._was_encrypted = was_encrypted
        self._needs_password = needs_password
        # Kept in memory only (never written to disk, logs or session data) so that Save can
        # keep the file's password protection.
        self._password: str | None = None

    @classmethod
    def open(cls, path: Path, password: str | None = None) -> "MuPdfBackend":
        path = Path(path)
        try:
            doc = fitz.open(path)
        except Exception as exc:  # noqa: BLE001
            raise InvalidPdfError(f"Cannot open PDF: {exc}") from exc

        # Opening must never modify the source file on disk (read + in-memory only).
        was_encrypted = bool(doc.is_encrypted)
        needs_password = bool(doc.needs_pass)

        if was_encrypted or needs_password:
            if not password:
                doc.close()
                raise PasswordRequiredError("Password required")
            ok = doc.authenticate(password)
            if not ok:
                doc.close()
                raise PasswordRequiredError("Incorrect password")

        # Reject empty / non-PDF that somehow opened
        if doc.page_count < 0:
            doc.close()
            raise InvalidPdfError("Invalid PDF structure")

        backend = cls(
            doc,
            path,
            was_encrypted=was_encrypted,
            needs_password=needs_password,
        )
        if was_encrypted or needs_password:
            backend._password = password
        return backend

    @property
    def page_count(self) -> int:
        return int(self._doc.page_count)

    def read_metadata(self) -> DocumentMetadata:
        meta = self._doc.metadata or {}
        perms = self._permissions_dict()
        return DocumentMetadata(
            title=str(meta.get("title") or ""),
            author=str(meta.get("author") or ""),
            subject=str(meta.get("subject") or ""),
            keywords=str(meta.get("keywords") or ""),
            creator=str(meta.get("creator") or ""),
            producer=str(meta.get("producer") or ""),
            creation_date=str(meta.get("creationDate") or ""),
            mod_date=str(meta.get("modDate") or ""),
            page_count=self.page_count,
            encrypted=bool(self._was_encrypted or self._doc.is_encrypted),
            needs_password=bool(self._needs_password),
            permissions=perms,
            has_acroform=self._detect_acroform(),
            has_digital_signatures=self._detect_signatures(),
            format="PDF",
        )

    def _permissions_dict(self) -> dict[str, bool]:
        # PyMuPDF exposes permissions bitmask after auth; map common flags.
        # Never bypass — UI must honor these.
        try:
            p = int(self._doc.permissions)
        except Exception:  # noqa: BLE001
            p = -1
        # When not encrypted, treat as fully permitted for local viewing.
        if not self._doc.is_encrypted and p < 0:
            return {
                "print": True,
                "copy": True,
                "edit": True,
                "annotate": True,
                "fill_forms": True,
                "assemble": True,
            }
        # fitz permission bits (PDF spec / MuPDF convention)
        return {
            "print": bool(p & fitz.PDF_PERM_PRINT),
            "copy": bool(p & fitz.PDF_PERM_COPY),
            "edit": bool(p & fitz.PDF_PERM_MODIFY),
            "annotate": bool(p & fitz.PDF_PERM_ANNOTATE),
            "fill_forms": bool(getattr(fitz, "PDF_PERM_FORM", 0) and (p & fitz.PDF_PERM_FORM)),
            "assemble": bool(getattr(fitz, "PDF_PERM_ASSEMBLE", 0) and (p & fitz.PDF_PERM_ASSEMBLE)),
        }

    def _detect_acroform(self) -> bool:
        try:
            if getattr(self._doc, "is_form_pdf", False):
                return True
        except Exception:  # noqa: BLE001
            pass
        try:
            # Fallback: look for widget annotations
            for i in range(min(self.page_count, 50)):
                page = self._doc.load_page(i)
                if page.widgets():
                    return True
        except Exception:  # noqa: BLE001
            pass
        try:
            xref = self._doc.pdf_catalog()
            if xref:
                obj = self._doc.xref_object(xref)
                if obj and "/AcroForm" in obj:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _detect_signatures(self) -> bool:
        try:
            for i in range(min(self.page_count, 100)):
                page = self._doc.load_page(i)
                for widget in page.widgets() or []:
                    field_type = getattr(widget, "field_type", None)
                    # PDF_WIDGET_TYPE_SIGNATURE == 7 in PyMuPDF
                    if field_type == getattr(fitz, "PDF_WIDGET_TYPE_SIGNATURE", 7):
                        return True
                    name = (getattr(widget, "field_name", None) or "").lower()
                    if "signature" in name or "sig" == name:
                        return True
        except Exception:  # noqa: BLE001
            pass
        try:
            # Document-level SigFlags / signature dictionaries
            for xref in range(1, self._doc.xref_length()):
                try:
                    obj = self._doc.xref_object(xref)
                except Exception:  # noqa: BLE001
                    continue
                if obj and "/Type /Sig" in obj.replace(" ", " "):
                    return True
                if obj and "/FT /Sig" in obj:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def analyze_page(self, index: int) -> PageInfo:
        page = self._doc.load_page(index)
        rect = page.rect
        rotation = int(page.rotation)
        text = page.get_text("text") or ""
        char_count = len(text.strip())
        images = page.get_images(full=True) or []
        image_count = len(images)
        has_text = char_count > 0
        has_images = image_count > 0

        if has_text and has_images:
            if char_count < _SCAN_TEXT_THRESHOLD and image_count >= 1:
                kind = PageContentKind.IMAGE_SCANNED
            else:
                kind = PageContentKind.MIXED
        elif has_text:
            kind = PageContentKind.TEXT
        elif has_images:
            kind = PageContentKind.IMAGE_SCANNED
        else:
            kind = PageContentKind.EMPTY

        return PageInfo(
            index=index,
            width_pt=float(rect.width),
            height_pt=float(rect.height),
            rotation=rotation,
            content_kind=kind,
            has_text=has_text,
            has_images=has_images,
            char_count=char_count,
            image_count=image_count,
        )

    def page_text(self, index: int) -> str:
        return self._doc.load_page(index).get_text("text") or ""

    def search(self, query: str, *, case_sensitive: bool = False) -> list[tuple[int, Any]]:
        hits: list[tuple[int, Any]] = []
        for i in range(self.page_count):
            page = self._doc.load_page(i)
            # search_for is case-insensitive by default; optionally require exact casing in page text.
            rects = list(page.search_for(query) or [])
            if case_sensitive and rects:
                text = page.get_text("text") or ""
                if query not in text:
                    rects = []
            for r in rects:
                hits.append((i, rect_to_display(page, r)))
        return hits

    def render_png(
        self,
        page_index: int,
        *,
        zoom: float,
        dpr: float = 1.0,
        alpha: bool = False,
    ) -> bytes:
        page = self._doc.load_page(page_index)
        # PDF points stay independent; matrix scales for display pixels only.
        scale = max(0.05, float(zoom) * max(0.5, float(dpr)))
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=alpha)
        return pix.tobytes("png")

    def render_rgb(
        self,
        page_index: int,
        *,
        scale: float,
        clip: tuple[float, float, float, float] | None = None,
    ) -> tuple[bytes, int, int, int]:
        """RGB samples of the page (or of ``clip``, display space in points) at ``scale`` pixels per
        point: (samples, width, height, stride). No PNG encoding — used for the on-screen view."""
        page = self._doc.load_page(page_index)
        matrix = fitz.Matrix(scale, scale)
        area = fitz.Rect(clip) & page.rect if clip is not None else None
        pix = page.get_pixmap(matrix=matrix, alpha=False, clip=area, colorspace=fitz.csRGB)
        return bytes(pix.samples), pix.width, pix.height, pix.stride

    def render_thumbnail_png(self, page_index: int, max_edge_px: int = 160) -> bytes:
        page = self._doc.load_page(page_index)
        rect = page.rect
        edge = max(rect.width, rect.height) or 1.0
        zoom = max_edge_px / edge
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")

    def can_save(self) -> bool:
        # Authenticated open is required for encrypted docs; never bypass permissions.
        # Save As creates a new file; refuse only when MuPDF cannot write.
        return self._doc is not None and not self._doc.is_closed

    def save_as(self, destination: Path) -> None:
        destination = Path(destination)
        if destination.resolve() == self._path.resolve():
            # Still a deliberate write; incremental=False rewrites destination only.
            pass
        encrypt = (
            fitz.PDF_ENCRYPT_KEEP if self._doc.is_encrypted else fitz.PDF_ENCRYPT_NONE
        )
        # Always write a full new file (not an in-place incremental edit of the source).
        self._doc.save(
            destination.as_posix(),
            garbage=3,
            deflate=True,
            encryption=encrypt,
            incremental=False,
        )

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None  # type: ignore[assignment]


def snapshot_bytes(backend: "MuPdfBackend") -> bytes:
    """The live document as PDF bytes with every object number unchanged (no garbage collection) and
    its encryption kept, for undo of page operations."""
    doc = backend._doc  # noqa: SLF001
    keep = bool(backend._password) and bool((doc.metadata or {}).get("encryption"))  # noqa: SLF001
    return doc.tobytes(garbage=0, deflate=False, encryption=fitz.PDF_ENCRYPT_KEEP if keep else fitz.PDF_ENCRYPT_NONE)


def restore_bytes(backend: "MuPdfBackend", data: bytes) -> None:
    """Replace the live document with ``data`` from ``snapshot_bytes`` (re-unlocked with the same
    password). The previous document object is left to Python to close: a view may still hold it."""
    doc = fitz.open("pdf", data)
    if doc.needs_pass and backend._password:  # noqa: SLF001
        doc.authenticate(backend._password)  # noqa: SLF001
    backend._doc = doc  # noqa: SLF001
