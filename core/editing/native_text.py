"""Extract native PDF text spans; safe replace vs redaction+reinsertion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.editing.geometry import Rect
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
    safe_direct: bool  # True when single-line simple span replacement is considered safe


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
            line_spans = line.get("spans") or []
            for sp in line_spans:
                text = sp.get("text") or ""
                if not text.strip():
                    continue
                bbox = sp.get("bbox") or (0, 0, 0, 0)
                font = str(sp.get("font") or "")
                size = float(sp.get("size") or 12)
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
                    )
                )
                n += 1
    return spans


def span_to_textbox(span: NativeSpan) -> TextBox:
    """Create an overlay TextBox bound to a native span (replacement workflow)."""
    return TextBox(
        page_index=span.page_index,
        rect=span.rect.inflate(1.0),
        text=span.text,
        style=TextStyle(font_family=span.font or "sans-serif", font_size=span.size),
        replaces_native=True,
        native_span_id=span.span_id,
    )


def plan_replacement(span: NativeSpan, new_text: str) -> dict[str, Any]:
    """
    Decide workflow:
    - safe_direct: replace text in-place when backend supports it
    - redaction_reinsert: white-out/redact original area and insert overlay (undoable)
    Never silently corrupt — always returns explicit mode.
    """
    if span.safe_direct and len(new_text) <= max(8, int(len(span.text) * 1.5)):
        return {"mode": "safe_direct", "span_id": span.span_id, "new_text": new_text}
    return {
        "mode": "redaction_reinsert",
        "span_id": span.span_id,
        "rect": span.rect.as_tuple(),
        "new_text": new_text,
        "note": "True rewriting unsafe; use controlled redaction + reinsertion (undoable).",
    }
