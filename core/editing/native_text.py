"""Extract native PDF text spans and plan their replacement.

Editing existing text is a *controlled reconstruction*: the original span's glyphs are removed from
the page content when the document is saved (a text-only redaction: pictures and drawings under it
are kept) and the edited text is written in their place as new text. While editing, the canvas covers
the original span with the page's background colour. This is not a secure redaction tool and does not
change any other occurrence of the text (bookmarks, metadata, form values).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.editing.geometry import Rect
from core.page_space import rect_to_display
from core.editing.text_box import TextBox
from core.editing.text_style import TextStyle


@dataclass
class NativeSpan:
    span_id: str
    page_index: int
    text: str
    rect: Rect
    font: str
    size: float
    safe_direct: bool  # single simple span (kept for callers; every replacement removes the original)
    color: str = "#000000"
    bold: bool = False
    italic: bool = False


def clean_font_name(name: str) -> str:
    """'ABCDEF+NotoSans-Bold' -> 'NotoSans-Bold' (drop the subset tag of an embedded font)."""
    if len(name) > 7 and name[6] == "+" and name[:6].isalpha() and name[:6].isupper():
        return name[7:]
    return name


def _merge_word_spans(line: dict) -> list[dict]:
    """Join the spans of one horizontal line that are really one run of text: same font, size,
    colour and style, separated by no more than a word space.

    Many PDFs (and text saved by Monograph PDF itself) place every word separately, so each word was a
    span of its own: Edit Text then changed one word, and a longer word was drawn over the next one.
    As one run the whole phrase is edited, removed and redrawn together, so nothing overlaps. Runs in
    another style (a bold word, another colour) stay separate.
    """
    spans = [dict(s) for s in (line.get("spans") or [])]
    direction = line.get("dir") or (1.0, 0.0)
    if len(spans) < 2 or abs(float(direction[0]) - 1.0) > 1e-3 or abs(float(direction[1])) > 1e-3:
        return spans
    # Spaces may come from another font than the words (Monograph PDF draws them from its built-in font
    # when the chosen font would turn them into no-break spaces): they never split a run. Space-only
    # spans were never editable on their own.
    spans = [s for s in spans if (s.get("text") or "").strip()]
    merged: list[dict] = []
    for sp in spans:
        prev = merged[-1] if merged else None
        if prev is not None and (prev.get("text") or "").strip() and (sp.get("text") or "").strip():
            same = (prev.get("font") == sp.get("font") and abs(float(prev.get("size") or 0) - float(sp.get("size") or 0)) < 0.05
                    and prev.get("color") == sp.get("color") and prev.get("flags") == sp.get("flags"))
            pb, sb = prev.get("bbox") or (0, 0, 0, 0), sp.get("bbox") or (0, 0, 0, 0)
            size = float(sp.get("size") or 12)
            gap = float(sb[0]) - float(pb[2])
            same_line = abs(float(sb[1]) - float(pb[1])) < 0.25 * size and abs(float(sb[3]) - float(pb[3])) < 0.25 * size
            if same and same_line and -0.1 * size <= gap <= 0.6 * size:
                sep = "" if gap < 0.12 * size or prev["text"].endswith(" ") or sp["text"].startswith(" ") else " "
                prev["text"] = prev["text"] + sep + sp["text"]
                prev["bbox"] = (min(pb[0], sb[0]), min(pb[1], sb[1]), max(pb[2], sb[2]), max(pb[3], sb[3]))
                continue
        merged.append(sp)
    return merged


def extract_spans(backend: Any, page_index: int) -> list[NativeSpan]:
    """Extract glyph/span geometry via PyMuPDF text dict."""
    page = backend._doc.load_page(page_index)  # noqa: SLF001 — engine-internal
    data = page.get_text("dict") or {}
    spans: list[NativeSpan] = []
    n = 0
    for block in data.get("blocks") or []:
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines") or []:
            line_spans = _merge_word_spans(line)
            for sp in line_spans:
                text = sp.get("text") or ""
                if not text.strip():
                    continue
                bbox = rect_to_display(page, sp.get("bbox") or (0, 0, 0, 0))
                font = str(sp.get("font") or "")
                size = float(sp.get("size") or 12)
                flags = int(sp.get("flags") or 0)
                color = "#%06x" % (int(sp.get("color") or 0) & 0xFFFFFF)
                # Safe direct edit: single span, no complex writing mode flags
                safe = len(line_spans) == 1 and "\n" not in text and len(text) < 200
                spans.append(
                    NativeSpan(
                        span_id=f"p{page_index}-s{n}",
                        page_index=page_index,
                        text=text,
                        rect=Rect(bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]),
                        font=font,
                        size=size,
                        safe_direct=safe,
                        color=color,
                        bold=bool(flags & 16) or "bold" in font.lower(),
                        italic=bool(flags & 2) or "italic" in font.lower() or "oblique" in font.lower(),
                    )
                )
                n += 1
    return spans


def span_to_textbox(span: NativeSpan) -> TextBox:
    """Create an overlay TextBox bound to a native span (replacement workflow).

    No padding, no wrapping and automatic size, so the text starts where the original did and a longer
    replacement grows the box instead of breaking onto a second line."""
    from core.editing.text_box import SizeMode

    family = clean_font_name(span.font) or "sans-serif"
    try:
        # The installed family of the span's PostScript name (MS-Gothic → MS Gothic, YuGothic-Regular →
        # Yu Gothic, TimesNewRomanPSMT → Times New Roman): Save then embeds that font. With the raw
        # name it was "not installed" and the edited text came out in a substitute font.
        from core.editing.font_resolver import resolve_font

        res = resolve_font(family, span.text)
        if not res.substituted and res.resolved not in ("sans-serif", "serif", "monospace"):
            family = res.resolved
    except Exception:  # noqa: BLE001
        pass
    return TextBox(
        page_index=span.page_index,
        rect=span.rect.inflate(0.5),
        text=span.text,
        style=TextStyle(font_family=family, font_size=span.size,
                        text_color=span.color, bold=span.bold, italic=span.italic, padding=0.0,
                        wrap=False, line_spacing=1.0),
        size_mode=SizeMode.AUTO_SIZE,
        replaces_native=True,
        native_span_id=span.span_id,
    )


def plan_replacement(span: NativeSpan, new_text: str, cover: str = "#ffffff") -> dict[str, Any]:
    """The replacement plan for a native span: remove the span's glyphs at Save, reinsert the edited
    text as an overlay (undoable until saved). ``cover`` is the background colour used on screen."""
    return {
        "mode": "redaction_reinsert",
        "span_id": span.span_id,
        "rect": span.rect.as_tuple(),
        "new_text": new_text,
        "original_text": span.text,
        "cover": cover,
        "note": "Text-only removal of the original span at Save; pictures and drawings are kept.",
    }


def removal_rect(rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """The area whose glyphs are removed: the span's box with its top and bottom quarter left out, so
    characters of the lines above and below (whose boxes may overlap) are never caught."""
    x, y, w, h = rect
    inset = h * 0.25
    return (x + 0.2, y + inset, max(0.1, w - 0.4), max(0.1, h - 2 * inset))


def sample_background(page: Any, rect: tuple[float, float, float, float]) -> str:
    """Most common colour on the border of a span's box in the rendered page (``#rrggbb``)."""
    import fitz

    from core.page_space import rect_to_page

    x, y, w, h = rect
    try:
        clip = rect_to_page(page, fitz.Rect(x - 1.5, y - 1.5, x + w + 1.5, y + h + 1.5)) & page.rect
        pix = page.get_pixmap(clip=clip, dpi=72, alpha=False, colorspace=fitz.csRGB)
    except Exception:  # noqa: BLE001
        return "#ffffff"
    counts: dict[tuple[int, int, int], int] = {}
    for yy in range(pix.height):
        for xx in range(pix.width):
            if 0 < yy < pix.height - 1 and 0 < xx < pix.width - 1:
                continue
            c = pix.pixel(xx, yy)[:3]
            counts[c] = counts.get(c, 0) + 1
    if not counts:
        return "#ffffff"
    r, g, b = max(counts.items(), key=lambda kv: kv[1])[0]
    return f"#{r:02x}{g:02x}{b:02x}"
