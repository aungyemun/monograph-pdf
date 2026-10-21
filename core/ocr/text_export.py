"""Recognised text as plain text, and as a Word document with paragraphs and headings.

Tesseract groups words into blocks, paragraphs and lines in reading order (its page segmentation
also separates columns). Words of a line are joined with spaces, except between Japanese/Chinese
characters, which are written without spaces. This is a reconstruction: layout, fonts and tables are
not reproduced, and recognition errors stay until corrected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x3000 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF
            or 0xFF00 <= o <= 0xFFEF or 0xAC00 <= o <= 0xD7AF)


def join_words(words: Iterable[str]) -> str:
    out = ""
    for w in words:
        if out and not (_is_cjk(out[-1]) and _is_cjk(w[0])):
            out += " "
        out += w
    return out


def paragraphs(words) -> list[dict]:
    """[{"lines": [text, ...], "height": median word height}, ...] in Tesseract's reading order."""
    paras: dict[tuple[int, int], dict] = {}
    order: list[tuple[int, int]] = []
    for w in words:
        key = (w.block, w.par)
        if key not in paras:
            paras[key] = {"lines": {}, "heights": []}
            order.append(key)
        paras[key]["lines"].setdefault(w.line, []).append(w.text)
        paras[key]["heights"].append(w.rect.h)
    out = []
    for key in order:
        p = paras[key]
        hs = sorted(p["heights"])
        out.append({"lines": [join_words(ws) for _n, ws in sorted(p["lines"].items())],
                    "height": hs[len(hs) // 2] if hs else 0.0})
    return out


def page_text(words) -> str:
    """Plain text of one page: lines of a paragraph on separate lines, a blank line between paragraphs."""
    return "\n\n".join("\n".join(p["lines"]) for p in paragraphs(words))


def document_text(pages) -> str:
    """Plain text of several OCR page results, each page headed by its number."""
    parts = []
    for pr in pages:
        if pr.skipped and not pr.words:
            continue
        parts.append(f"--- Page {pr.page_index + 1} ---\n{pr.full_text or page_text(pr.words)}")
    return "\n\n".join(parts).strip() + "\n"


def _merge_lines(lines: list[str]) -> str:
    """Lines of a paragraph as one paragraph (hyphenation at a line end is joined)."""
    text = ""
    for line in lines:
        if not text:
            text = line
        elif text.endswith("-") and line[:1].islower():
            text = text[:-1] + line
        elif _is_cjk(text[-1]) and line and _is_cjk(line[0]):
            text += line
        else:
            text += " " + line
    return text


def write_docx(pages, destination: Path, *, title: str = "", page_images: list[bytes | None] | None = None,
               edited_text: str | None = None, metadata: dict | None = None) -> Path:
    """A Word document of OCR results: paragraphs in reading order; a paragraph clearly taller than the
    page's body text (at most two lines) becomes a heading; a page break between pages. ``edited_text``
    (the user's corrected text, pages separated by "--- Page n ---") replaces the recognised text.
    ``page_images`` optionally adds each page's picture after its text."""
    import io
    import re

    from docx import Document
    from docx.shared import Inches

    from core.convert.office_metadata import apply_core_properties, pdf_properties

    doc = Document()
    props = pdf_properties(metadata)
    if not props["title"] and title:
        props["title"] = title
    apply_core_properties(doc.core_properties, props)
    edited_pages: dict[int, str] = {}
    if edited_text is not None:
        chunks = re.split(r"^--- Page (\d+) ---\s*$", edited_text, flags=re.MULTILINE)
        if len(chunks) > 1:
            for i in range(1, len(chunks) - 1, 2):
                edited_pages[int(chunks[i]) - 1] = chunks[i + 1].strip("\n")
        else:
            edited_pages[-1] = edited_text
    first = True
    for n, pr in enumerate(pages):
        if not first:
            doc.add_page_break()
        first = False
        text_override = edited_pages.get(pr.page_index, edited_pages.get(-1) if n == 0 else None)
        if text_override is not None:
            for para in re.split(r"\n\s*\n", text_override.strip()):
                if para.strip():
                    doc.add_paragraph(_merge_lines(para.splitlines()))
        else:
            paras = paragraphs(pr.words)
            body = sorted(p["height"] for p in paras if p["height"] > 0)
            median = body[len(body) // 2] if body else 0.0
            for p in paras:
                text = _merge_lines(p["lines"])
                if not text.strip():
                    continue
                if median and p["height"] >= median * 1.35 and len(p["lines"]) <= 2 and len(text) <= 120:
                    doc.add_heading(text, level=1 if p["height"] >= median * 1.8 else 2)
                else:
                    doc.add_paragraph(text)
        if page_images and n < len(page_images) and page_images[n]:
            doc.add_picture(io.BytesIO(page_images[n]), width=Inches(6.0))
    destination = Path(destination)
    tmp = destination.with_name(destination.name + ".part")
    doc.save(tmp.as_posix())
    tmp.replace(destination)
    return destination


def write_text(text: str, destination: Path) -> Path:
    """UTF-8 text file (with a byte-order mark so Windows Notepad and Excel detect the encoding)."""
    destination = Path(destination)
    tmp = destination.with_name(destination.name + ".part")
    tmp.write_text(text, encoding="utf-8-sig", newline="\r\n")
    tmp.replace(destination)
    return destination
