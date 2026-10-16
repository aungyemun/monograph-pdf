"""Split a PDF into multiple files — source preserved."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

import fitz

from core.document import InvalidPdfError, PdfDocument
from core.organize.page_ops import _doc, parse_page_ranges
from core.organize.temputil import cleanup_dir, move_into_place, organize_temp_dir
from core.safe_paths import safe_child

ProgressCb = Callable[[int, int, str], None]
CancelCb = Callable[[], bool]


class SplitMode(str, Enum):
    RANGES = "ranges"  # user-specified ranges → one file per range
    SELECTED = "selected"  # one file with selected pages
    EVERY_PAGE = "every_page"
    EVERY_N = "every_n"
    BOOKMARKS = "bookmarks"


@dataclass
class SplitPlan:
    mode: SplitMode
    """Each group is a list of 0-based page indices for one output file."""
    groups: list[list[int]] = field(default_factory=list)
    output_names: list[str] = field(default_factory=list)


def plan_split(
    document: PdfDocument,
    mode: SplitMode,
    *,
    range_spec: str = "",
    selected_pages: list[int] | None = None,
    every_n: int = 1,
) -> SplitPlan:
    n = document.page_count
    if n <= 0:
        raise InvalidPdfError("Document has no pages")

    if mode == SplitMode.RANGES:
        # Comma-separated ranges each become a file: "1-2,3-5"
        groups: list[list[int]] = []
        names: list[str] = []
        parts = [p.strip() for p in (range_spec or "").split(",") if p.strip()]
        if not parts:
            raise ValueError("Provide at least one page range")
        for part in parts:
            pages = parse_page_ranges(part, n)
            if not pages:
                continue
            groups.append(pages)
            names.append(f"pages_{pages[0] + 1}-{pages[-1] + 1}.pdf")
        return SplitPlan(mode=mode, groups=groups, output_names=names)

    if mode == SplitMode.SELECTED:
        pages = sorted(set(selected_pages or []))
        if not pages:
            raise ValueError("No pages selected")
        for p in pages:
            if p < 0 or p >= n:
                raise IndexError(f"page out of range: {p}")
        return SplitPlan(
            mode=mode,
            groups=[pages],
            output_names=[f"selected_{len(pages)}_pages.pdf"],
        )

    if mode == SplitMode.EVERY_PAGE:
        groups = [[i] for i in range(n)]
        names = [f"page_{i + 1:04d}.pdf" for i in range(n)]
        return SplitPlan(mode=mode, groups=groups, output_names=names)

    if mode == SplitMode.EVERY_N:
        if every_n < 1:
            raise ValueError("every_n must be >= 1")
        groups = []
        names = []
        for start in range(0, n, every_n):
            chunk = list(range(start, min(n, start + every_n)))
            groups.append(chunk)
            names.append(f"pages_{chunk[0] + 1}-{chunk[-1] + 1}.pdf")
        return SplitPlan(mode=mode, groups=groups, output_names=names)

    if mode == SplitMode.BOOKMARKS:
        groups, names = _groups_from_bookmarks(document)
        if not groups:
            # Fall back: whole document as one file with a note name
            groups = [list(range(n))]
            names = ["full_document_no_bookmarks.pdf"]
        return SplitPlan(mode=mode, groups=groups, output_names=names)

    raise ValueError(f"Unknown split mode: {mode}")


def run_split(
    document: PdfDocument,
    plan: SplitPlan,
    output_dir: Path,
    *,
    name_prefix: str = "",
    progress: ProgressCb | None = None,
    cancel: CancelCb | None = None,
) -> list[Path]:
    """Write split outputs under output_dir. Source file on disk is never modified."""
    if not plan.groups:
        raise InvalidPdfError("Split plan is empty")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    src = _doc(document)
    staging = organize_temp_dir(prefix="split")
    written: list[Path] = []
    total = len(plan.groups)
    try:
        for gi, pages in enumerate(plan.groups):
            if cancel and cancel():
                raise InterruptedError("Split cancelled")
            name = plan.output_names[gi] if gi < len(plan.output_names) else f"part_{gi + 1}.pdf"
            if name_prefix:
                name = f"{name_prefix}_{name}"
            # Names come from bookmarks and the document name: one plain file inside the chosen
            # folder, never replacing a file already there
            dest = safe_child(output_dir, name)
            tmp_out = staging / dest.name
            out = fitz.open()
            try:
                for p in pages:
                    out.insert_pdf(src, from_page=p, to_page=p)
                out.save(tmp_out.as_posix(), garbage=3, deflate=True)
            finally:
                out.close()
            move_into_place(tmp_out, dest)
            written.append(dest)
            if progress:
                progress(gi + 1, total, f"Wrote {dest.name}")
    except Exception:
        cleanup_dir(staging)
        raise
    cleanup_dir(staging)
    return written


def _groups_from_bookmarks(document: PdfDocument) -> tuple[list[list[int]], list[str]]:
    d = _doc(document)
    n = d.page_count
    toc = []
    try:
        toc = d.get_toc(simple=True) or []
    except Exception:  # noqa: BLE001
        toc = []
    # Collect top-level bookmark page starts (1-based in TOC → 0-based)
    starts: list[tuple[int, str]] = []
    for entry in toc:
        if not entry or len(entry) < 3:
            continue
        level, title, page1 = entry[0], str(entry[1] or "section"), int(entry[2])
        if level != 1:
            continue
        page0 = max(0, min(n - 1, page1 - 1))
        starts.append((page0, title))
    if not starts:
        return [], []
    # Unique sorted starts
    starts.sort(key=lambda t: t[0])
    uniq: list[tuple[int, str]] = []
    seen: set[int] = set()
    for p, title in starts:
        if p in seen:
            continue
        seen.add(p)
        uniq.append((p, title))
    groups: list[list[int]] = []
    names: list[str] = []
    for i, (start, title) in enumerate(uniq):
        end = (uniq[i + 1][0] - 1) if i + 1 < len(uniq) else (n - 1)
        groups.append(list(range(start, end + 1)))
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40] or f"part{i+1}"
        names.append(f"{i + 1:02d}_{safe}.pdf")
    return groups, names
