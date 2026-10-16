"""Merge / Combine workspace — builds a new PDF; never modifies source files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import fitz

from core.document import InvalidPdfError, PasswordRequiredError
from core.organize.page_ops import _open_external, parse_page_ranges
from core.organize.temputil import cleanup_dir, move_into_place, organize_temp_dir

ProgressCb = Callable[[int, int, str], None]
CancelCb = Callable[[], bool]


@dataclass
class MergeSource:
    path: Path
    password: str | None = None
    """None = include all pages; else 0-based included indices in source order."""
    included_pages: list[int] | None = None
    display_name: str = ""
    page_count: int = 0
    encrypted: bool = False
    has_signatures: bool = False
    open_error: str | None = None

    def effective_pages(self) -> list[int]:
        if self.included_pages is None:
            return list(range(self.page_count))
        return list(self.included_pages)


@dataclass
class MergeJob:
    sources: list[MergeSource] = field(default_factory=list)

    def add_path(self, path: Path, *, password: str | None = None) -> MergeSource:
        path = Path(path)
        src = MergeSource(path=path, password=password, display_name=path.name)
        try:
            doc = _open_external(path, password=password)
            try:
                src.page_count = doc.page_count
                src.encrypted = bool(doc.is_encrypted or doc.needs_pass)
                src.has_signatures = _detect_sigs(doc)
                src.included_pages = list(range(src.page_count))
            finally:
                doc.close()
        except PasswordRequiredError as exc:
            src.open_error = str(exc)
            src.encrypted = True
        except Exception as exc:  # noqa: BLE001
            src.open_error = str(exc)
        self.sources.append(src)
        return src

    def remove_at(self, index: int) -> None:
        del self.sources[index]

    def reorder_sources(self, new_order: list[int]) -> None:
        if sorted(new_order) != list(range(len(self.sources))):
            raise ValueError("invalid source order")
        self.sources = [self.sources[i] for i in new_order]

    def set_included_pages(self, source_index: int, pages: list[int] | None) -> None:
        src = self.sources[source_index]
        if pages is None:
            src.included_pages = list(range(src.page_count))
        else:
            for p in pages:
                if p < 0 or p >= src.page_count:
                    raise IndexError(f"page out of range: {p}")
            src.included_pages = sorted(set(pages))

    def set_included_from_range_spec(self, source_index: int, spec: str) -> None:
        src = self.sources[source_index]
        pages = parse_page_ranges(spec, src.page_count)
        self.set_included_pages(source_index, pages)

    def total_output_pages(self) -> int:
        return sum(len(s.effective_pages()) for s in self.sources if not s.open_error)

    def signature_warning(self) -> str | None:
        named = [s.display_name for s in self.sources if s.has_signatures]
        if not named:
            return None
        return (
            "One or more inputs contain digital signatures ("
            + ", ".join(named[:5])
            + "). Combining pages into a new PDF will break those signatures. "
            "Source files are not modified."
        )


def combine_to_pdf(
    job: MergeJob,
    destination: Path,
    *,
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
) -> Path:
    """
    Write a new combined PDF. Source files on disk are never modified.
    Uses a temp staging file under runtime/temp/organize then moves to destination.
    """
    ready = [s for s in job.sources if not s.open_error and s.page_count > 0]
    if not ready:
        raise InvalidPdfError("No readable PDF sources to combine")
    if job.total_output_pages() <= 0:
        raise InvalidPdfError("No pages selected for combine")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = organize_temp_dir(prefix="merge")
    staging = staging_dir / "combined.pdf"
    out = fitz.open()
    try:
        total = job.total_output_pages()
        done = 0
        for src in ready:
            if cancel and cancel():
                raise InterruptedError("Combine cancelled")
            doc = _open_external(src.path, password=src.password)
            try:
                for p in src.effective_pages():
                    if cancel and cancel():
                        raise InterruptedError("Combine cancelled")
                    out.insert_pdf(doc, from_page=p, to_page=p)
                    done += 1
                    if progress:
                        progress(done, total, f"Adding {src.display_name} page {p + 1}")
            finally:
                doc.close()
        out.save(staging.as_posix(), garbage=3, deflate=True)
    except Exception:
        out.close()
        cleanup_dir(staging_dir)
        raise
    out.close()

    # Into place — also when the destination is on another drive than the working folder
    move_into_place(staging, destination)
    cleanup_dir(staging_dir)
    if progress:
        progress(total, total, "Combine complete")
    return destination


def _detect_sigs(doc: fitz.Document) -> bool:
    try:
        for i in range(min(doc.page_count, 50)):
            page = doc.load_page(i)
            for widget in page.widgets() or []:
                if getattr(widget, "field_type", None) == getattr(fitz, "PDF_WIDGET_TYPE_SIGNATURE", 7):
                    return True
    except Exception:  # noqa: BLE001
        pass
    return False
