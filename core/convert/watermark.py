"""Watermark, header/footer, and page-number tools (offline)."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.document import PdfDocument


def _latin_only(text: str) -> bool:
    return all(ord(c) < 0x100 for c in text)


def _text_width(text: str, fontsize: float) -> float:
    """Width with Helvetica for Latin and the embedded Japanese font for everything else."""
    from core.forms.appearance import _runs

    helv, cjk = fitz.Font("helv"), fitz.Font("cjk")
    return sum(f.text_length(t, fontsize=fontsize) for t, f in _runs(text, helv, cjk))


def _place_text(
    page: fitz.Page,
    text: str,
    fontsize: float,
    color: tuple[float, float, float],
    *,
    left: float | None = None,
    center: fitz.Point | None = None,
    baseline: float = 0.0,
    rotate: float = 0.0,
    opacity: float = 1.0,
) -> None:
    """Write one line of text in any script.

    Latin-only text goes straight onto the page in Helvetica. Text with Japanese (or other
    non-Latin) characters is drawn per character — Helvetica for Latin, the embedded CJK font
    for the rest — on a small scratch page whose fonts are cut down to the characters used,
    then placed on the page (still selectable and searchable). PDF base fonts have no CJK
    glyphs ("···"), and the built-in "japan" font spaces Latin letters full-width.
    """
    width = _text_width(text, fontsize)
    if _latin_only(text) and not rotate and opacity >= 0.999:
        x = left if left is not None else center.x - width / 2
        page.insert_text((x, baseline), text, fontsize=fontsize, fontname="helv", color=color)
        return
    from core.forms.appearance import _runs

    h = fontsize * 1.3
    scratch = fitz.open()
    try:
        sp = scratch.new_page(width=width + 2, height=h)
        tw = fitz.TextWriter(sp.rect)
        x = 1.0
        for chunk, font in _runs(text, fitz.Font("helv"), fitz.Font("cjk")):
            tw.append((x, fontsize * 1.0), chunk, font=font, fontsize=fontsize)
            x += font.text_length(chunk, fontsize=fontsize)
        tw.write_text(sp, color=color, opacity=opacity)
        scratch.subset_fonts()
        import math

        w, hh = width + 2, h
        a = math.radians(rotate)
        bw = abs(w * math.cos(a)) + abs(hh * math.sin(a))  # box around the turned text
        bh = abs(w * math.sin(a)) + abs(hh * math.cos(a))
        if center is not None:
            cx, cy = center.x, center.y
        else:
            cx, cy = left + w / 2, baseline - fontsize + hh / 2
        target = fitz.Rect(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
        page.show_pdf_page(target, scratch, 0, rotate=rotate, overlay=True)
    finally:
        scratch.close()


def apply_watermark(
    document: PdfDocument,
    destination: Path,
    *,
    text: str,
    opacity: float = 0.25,
    rotate: float = 45.0,
    fontsize: float = 48.0,
    pages: list[int] | None = None,
    color: tuple[float, float, float] = (0.55, 0.55, 0.55),
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    doc = fitz.open()
    try:
        doc.insert_pdf(src)
        indices = list(range(doc.page_count)) if pages is None else list(pages)
        for i in indices:
            page = doc.load_page(i)
            r = page.rect
            # Centred; long text is made smaller so it stays on the page (85 % of the line it runs along)
            size = fontsize
            tw = _text_width(text, size)
            ang = float(rotate) % 180
            along = (r.width if ang < 1e-6 else r.height if abs(ang - 90) < 1e-6 else (r.width ** 2 + r.height ** 2) ** 0.5)
            if tw > along * 0.85:
                size = size * along * 0.85 / tw
            centre = fitz.Point(r.width / 2, r.height / 2)
            if _latin_only(text):
                # Helvetica straight onto the page (as before)
                tw = _text_width(text, size)
                rot = int(rotate) % 360
                mat = fitz.Matrix(1, 1).prerotate(rotate)
                shape = page.new_shape()
                shape.insert_text(
                    fitz.Point(r.width / 2 - tw / 2, r.height / 2),
                    text,
                    fontsize=size,
                    fontname="helv",
                    color=tuple(color),
                    rotate=rot if rot in (0, 90, 180, 270) else 0,
                    morph=(centre, mat) if int(rotate) % 90 != 0 else None,
                    fill_opacity=opacity,  # the text itself; finish() only covers drawings
                    stroke_opacity=opacity,
                )
                shape.finish(width=0, stroke_opacity=opacity, fill_opacity=opacity)
                shape.commit()
            else:
                _place_text(page, text, size, tuple(color), center=centre, rotate=float(rotate), opacity=opacity)
        doc.save(destination.as_posix(), garbage=3, deflate=True)
    finally:
        doc.close()
    return destination


def apply_headers_footers(
    document: PdfDocument,
    destination: Path,
    *,
    header: str = "",
    footer: str = "",
    fontsize: float = 9.0,
    margin: float = 36.0,
    pages: list[int] | None = None,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    doc = fitz.open()
    try:
        doc.insert_pdf(src)
        indices = list(range(doc.page_count)) if pages is None else list(pages)
        for i in indices:
            page = doc.load_page(i)
            r = page.rect
            if header:
                _place_text(page, header, fontsize, (0.2, 0.2, 0.2), left=margin, baseline=margin)
            if footer:
                _place_text(page, footer, fontsize, (0.2, 0.2, 0.2), left=margin, baseline=r.height - margin * 0.6)
        doc.save(destination.as_posix(), garbage=3, deflate=True)
    finally:
        doc.close()
    return destination


def apply_page_numbers(
    document: PdfDocument,
    destination: Path,
    *,
    fmt: str = "{page} / {total}",
    fontsize: float = 10.0,
    margin: float = 36.0,
    pages: list[int] | None = None,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    doc = fitz.open()
    try:
        doc.insert_pdf(src)
        total = doc.page_count
        indices = list(range(total)) if pages is None else list(pages)
        for i in indices:
            page = doc.load_page(i)
            r = page.rect
            label = fmt.format(page=i + 1, total=total)
            tw = _text_width(label, fontsize)
            _place_text(page, label, fontsize, (0.15, 0.15, 0.15), left=r.width - margin - tw, baseline=r.height - margin * 0.6)
        doc.save(destination.as_posix(), garbage=3, deflate=True)
    finally:
        doc.close()
    return destination
