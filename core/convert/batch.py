"""Batch conversion: many files, one output format, one output folder.

Each file is converted with the same converters as the single-file commands. Output is written under
a temporary ``.part`` name next to its final name and renamed only when complete, so a failed or
cancelled file leaves nothing behind; an existing file is never overwritten (``name (1).docx``).
Files are converted one at a time: PyMuPDF must not run on several threads at once, and the Office
and OCR back ends start external programs — one at a time keeps memory and processes bounded. The
GUI runs a batch on a worker thread and can cancel between files and between OCR pages.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
OFFICE_EXTS = {".doc", ".docx", ".rtf", ".odt", ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".odp"}


@dataclass(frozen=True)
class OutputFormat:
    key: str
    label: str
    inputs: frozenset[str]
    suffix: str
    uses_pages: bool = True
    needs: str = ""  # "office" | "ocr" | ""


FORMATS: tuple[OutputFormat, ...] = (
    OutputFormat("docx", "Word document (.docx)", frozenset(PDF_EXTS), ".docx"),
    OutputFormat("xlsx", "Excel workbook — detected tables (.xlsx)", frozenset(PDF_EXTS), ".xlsx"),
    OutputFormat("pptx", "PowerPoint presentation (.pptx)", frozenset(PDF_EXTS), ".pptx"),
    OutputFormat("txt", "Plain text (.txt)", frozenset(PDF_EXTS), ".txt"),
    OutputFormat("png", "PNG pictures, one per page", frozenset(PDF_EXTS), ".png"),
    OutputFormat("jpeg", "JPEG pictures, one per page", frozenset(PDF_EXTS), ".jpg"),
    OutputFormat("searchable", "Searchable PDF (OCR)", frozenset(PDF_EXTS), ".pdf", needs="ocr"),
    OutputFormat("ocr_docx", "Word document from scanned pages (OCR)", frozenset(PDF_EXTS), ".docx", needs="ocr"),
    OutputFormat("image_pdf", "PDF from pictures (one PDF per picture)", frozenset(IMAGE_EXTS), ".pdf", uses_pages=False),
    OutputFormat("office_pdf", "PDF from Office files (needs Microsoft Office or LibreOffice)",
                 frozenset(OFFICE_EXTS), ".pdf", uses_pages=False, needs="office"),
)
FORMAT_BY_KEY = {f.key: f for f in FORMATS}


class BatchCancelled(Exception):
    pass


@dataclass
class BatchItem:
    source: Path
    status: str = "waiting"  # waiting | running | done | failed | skipped | cancelled
    message: str = ""
    outputs: list[Path] = field(default_factory=list)


@dataclass
class BatchOptions:
    format_key: str
    output_dir: Path
    page_range: str = ""  # "" = all pages; "1-3, 5"
    dpi: int = 150
    ocr_languages: str = "eng+jpn"
    password: Callable[[Path], str | None] | None = None  # asked for a protected PDF; None = skip it


def parse_page_range(text: str, page_count: int) -> list[int] | None:
    """'1-3, 5, 8-' -> 0-based pages; '' -> None (all). Raises ValueError for an invalid range."""
    text = (text or "").strip()
    if not text:
        return None
    pages: list[int] = []
    for part in re.split(r"[,;\s]+", text):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)?\s*-\s*(\d+)?|(\d+)", part)
        if not m:
            raise ValueError(f"“{part}” is not a page or a range such as 2-5")
        if m.group(3):
            a = b = int(m.group(3))
        else:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else page_count
        if a < 1 or b < a:
            raise ValueError(f"“{part}” is not a valid range")
        for p in range(a, min(b, page_count) + 1):
            if p - 1 not in pages:
                pages.append(p - 1)
    if not pages:
        raise ValueError(f"no page of “{text}” exists (the document has {page_count})")
    return pages


def unique_path(path: Path, taken: set[Path] | None = None) -> Path:
    """``path`` or ``name (1).ext``, ``name (2).ext`` … — never an existing file or one already planned."""
    taken = taken or set()
    candidate = path
    n = 1
    while candidate.exists() or candidate in taken or candidate.with_name(candidate.name + ".part").exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def accepted(paths: list[Path], format_key: str) -> list[Path]:
    fmt = FORMAT_BY_KEY[format_key]
    return [p for p in paths if p.suffix.lower() in fmt.inputs]


class BatchRunner:
    """Converts ``items`` one after another; ``on_update(index, item)`` after each change."""

    def __init__(self, items: list[BatchItem], options: BatchOptions,
                 on_update: Callable[[int, BatchItem], None] | None = None) -> None:
        self.items = items
        self.options = options
        self.on_update = on_update or (lambda i, it: None)
        self._cancel = False
        self._planned: set[Path] = set()

    def cancel(self) -> None:
        self._cancel = True

    @property
    def cancelled(self) -> bool:
        return self._cancel

    def run(self) -> None:
        fmt = FORMAT_BY_KEY[self.options.format_key]
        Path(self.options.output_dir).mkdir(parents=True, exist_ok=True)
        for i, item in enumerate(self.items):
            if self._cancel:
                item.status, item.message = "cancelled", "not converted (cancelled)"
                self.on_update(i, item)
                continue
            if item.source.suffix.lower() not in fmt.inputs:
                item.status, item.message = "skipped", f"{item.source.suffix or 'this file type'} cannot be converted to {fmt.label}"
                self.on_update(i, item)
                continue
            item.status, item.message = "running", "converting…"
            self.on_update(i, item)
            work = Path(tempfile.mkdtemp(prefix="monographpdf-batch-"))
            try:
                produced = self._convert(item.source, fmt, work)
                item.outputs = self._publish(produced, item.source, fmt)
                item.status = "done"
                item.message = ", ".join(p.name for p in item.outputs[:3]) + (f" … ({len(item.outputs)} files)" if len(item.outputs) > 3 else "")
            except BatchCancelled:
                item.status, item.message = "cancelled", "cancelled — no output kept"
            except Exception as exc:  # noqa: BLE001 — one bad file must not stop the batch
                item.status, item.message = "failed", _message(exc)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            self.on_update(i, item)

    # -- conversion into a private work folder --------------------------------------------------------

    def _check(self) -> None:
        if self._cancel:
            raise BatchCancelled()

    def _open(self, source: Path):
        from core.document import PasswordRequiredError, open_document

        try:
            return open_document(source)
        except PasswordRequiredError:
            pw = self.options.password(source) if self.options.password else None
            if not pw:
                raise PermissionError("password-protected — skipped") from None
            return open_document(source, password=pw)

    def _convert(self, source: Path, fmt: OutputFormat, work: Path) -> list[Path]:
        stem = source.stem
        if fmt.key == "image_pdf":
            from core.convert.images_to_pdf import images_to_pdf

            return [images_to_pdf([source], work / f"{stem}.pdf")]
        if fmt.key == "office_pdf":
            from core.convert.office_to_pdf import office_to_pdf

            return [office_to_pdf(source, work / f"{stem}.pdf")]
        pdf = self._open(source)
        try:
            pages = parse_page_range(self.options.page_range, pdf.page_count)
            self._check()
            if fmt.key == "docx":
                from core.convert.pdf_to_docx import pdf_to_docx

                return [pdf_to_docx(pdf, work / f"{stem}.docx", pages=pages)]
            if fmt.key == "xlsx":
                from core.convert.tables_to_xlsx import tables_to_xlsx

                return [tables_to_xlsx(pdf, work / f"{stem}.xlsx", pages=pages)]
            if fmt.key == "pptx":
                from core.convert.pdf_to_pptx import pdf_to_pptx

                return [pdf_to_pptx(pdf, work / f"{stem}.pptx", pages=pages)]
            if fmt.key == "txt":
                from core.convert.pdf_to_text import pdf_to_plain_text

                text = pdf_to_plain_text(pdf, None, pages=pages)
                out = work / f"{stem}.txt"
                out.write_text(text, encoding="utf-8-sig", newline="\r\n")
                return [out]
            if fmt.key in ("png", "jpeg"):
                from core.convert.pdf_to_images import pdf_pages_to_images

                return pdf_pages_to_images(pdf, work, pages=pages, fmt=fmt.key, dpi=self.options.dpi, name_prefix=stem)
            if fmt.key in ("searchable", "ocr_docx"):
                from core.ocr.pipeline import OcrCancelled, OcrOptions, run_ocr

                searchable = fmt.key == "searchable"
                out = work / f"{stem}{fmt.suffix}"
                try:
                    res = run_ocr(pdf, OcrOptions(languages=self.options.ocr_languages, pages=pages,
                                                  make_searchable=searchable, skip_native_text=searchable),
                                  cancel=lambda: self._cancel, destination=out if searchable else None)
                except OcrCancelled:
                    raise BatchCancelled() from None
                if searchable:
                    if res.output_path is None:
                        raise RuntimeError("no pages needed OCR")
                    return [out]
                from core.ocr.text_export import write_docx

                done = [p for p in res.pages if p.words]
                if not done:
                    raise RuntimeError("no text was recognized")
                from core.convert.office_metadata import document_metadata

                return [write_docx(done, out, title=stem, metadata=document_metadata(pdf))]
            raise ValueError(f"unknown output format {fmt.key}")
        finally:
            pdf.close()

    def _publish(self, produced: list[Path], source: Path, fmt: OutputFormat) -> list[Path]:
        """Move finished files from the work folder into the output folder under unique names."""
        self._check()
        out_dir = Path(self.options.output_dir)
        final: list[Path] = []
        moved: list[Path] = []
        try:
            for f in produced:
                target = unique_path(out_dir / f.name, self._planned)
                self._planned.add(target)
                part = target.with_name(target.name + ".part")
                shutil.copyfile(f, part)
                moved.append(part)
                final.append(target)
            for part, target in zip(moved, final):
                part.replace(target)
        except BaseException:
            for part in moved:
                part.unlink(missing_ok=True)
            raise
        return final


def _message(exc: Exception) -> str:
    text = str(exc) or type(exc).__name__
    return text.splitlines()[0][:300]
