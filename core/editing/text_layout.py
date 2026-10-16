"""Text wrapping, auto-height, shrink-to-fit, overflow detection."""

from __future__ import annotations

from dataclasses import dataclass

from core.editing.font_resolver import measure_text_width, resolve_font
from core.editing.text_box import SizeMode, TextBox, WritingMode


@dataclass
class LayoutLine:
    text: str
    width: float


@dataclass
class LayoutResult:
    lines: list[LayoutLine]
    content_height: float
    font_size: float
    resolved_font: str
    font_substituted: bool
    overflow: bool
    rect_h: float
    rect_w: float = 0.0


def _split_preserve_breaks(text: str) -> list[str]:
    """Split on manual line breaks; keep empty lines."""
    return (text or "").split("\n")


def wrap_paragraph(
    paragraph: str,
    max_width: float,
    family: str,
    size: float,
    bold: bool,
    italic: bool,
    tracking: float,
) -> list[LayoutLine]:
    if max_width <= 1:
        return [LayoutLine(paragraph, measure_text_width(paragraph, family, size, bold, italic))]
    if not paragraph:
        return [LayoutLine("", 0.0)]

    # Prefer break on spaces for Latin; for CJK allow break between chars.
    tokens: list[str] = []
    buf = ""
    for ch in paragraph:
        if ch.isspace():
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        elif "\u3040" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        else:
            buf += ch
    if buf:
        tokens.append(buf)

    lines: list[LayoutLine] = []
    current = ""
    for tok in tokens:
        trial = current + tok
        width = measure_text_width(trial, family, size, bold, italic) + tracking * max(
            0, len(trial) - 1
        )
        if current and width > max_width:
            lines.append(
                LayoutLine(
                    current,
                    measure_text_width(current, family, size, bold, italic)
                    + tracking * max(0, len(current) - 1),
                )
            )
            current = tok.lstrip(" ") if tok.startswith(" ") else tok
        else:
            current = trial
    if current or not lines:
        lines.append(
            LayoutLine(
                current,
                measure_text_width(current, family, size, bold, italic)
                + tracking * max(0, len(current) - 1),
            )
        )
    return lines


def layout_text_box(box: TextBox) -> LayoutResult:
    """Compute wrapped lines and overflow; may suggest height for AUTO_HEIGHT."""
    # Vertical writing: architectural stub — still layout horizontally for now
    # but flag writing_mode for future glyph rotation path.
    _ = box.writing_mode == WritingMode.VERTICAL_RL

    style = box.style
    res = resolve_font(style.font_family, box.text)
    family = res.resolved
    size = style.font_size
    pad = style.padding
    inner_w = max(1.0, box.rect.w - 2 * pad)
    inner_h = max(1.0, box.rect.h - 2 * pad)
    line_h = size * style.line_spacing

    def build(sz: float) -> tuple[list[LayoutLine], float]:
        lines: list[LayoutLine] = []
        for para in _split_preserve_breaks(box.text):
            lines.extend(
                wrap_paragraph(
                    para,
                    inner_w,
                    family,
                    sz,
                    style.bold,
                    style.italic,
                    style.character_spacing,
                )
            )
        height = max(line_h, len(lines) * (sz * style.line_spacing))
        return lines, height

    overflow = False
    rect_w = box.rect.w
    rect_h = box.rect.h
    min_fit = 6.0  # never auto-shrink below readable threshold without warning
    wrap = bool(getattr(style, "wrap", True))

    if box.size_mode == SizeMode.AUTO_SIZE:
        # Grow width+height; honor newlines; optional soft wrap at a generous max.
        lines = []
        soft_max = max(inner_w, 360.0) if wrap else 1e9
        for para in _split_preserve_breaks(box.text):
            if wrap and para:
                lines.extend(
                    wrap_paragraph(
                        para, soft_max, family, size, style.bold, style.italic, style.character_spacing
                    )
                )
            else:
                w = measure_text_width(para, family, size, style.bold, style.italic) + style.character_spacing * max(
                    0, len(para) - 1
                )
                lines.append(LayoutLine(para, w))
        max_line_w = max((ln.width for ln in lines), default=0.0)
        content_h = max(line_h, len(lines) * (size * style.line_spacing))
        rect_w = max(box.rect.w, max_line_w + 2 * pad + 2.0)
        rect_h = content_h + 2 * pad
        overflow = False
    elif box.size_mode == SizeMode.SHRINK_TO_FIT:
        lo, hi = min_fit, size
        best = size
        lines, content_h = build(size)
        if content_h > inner_h or any(ln.width > inner_w + 0.5 for ln in lines):
            for _ in range(12):
                mid = (lo + hi) / 2.0
                lines, content_h = build(mid)
                fits = content_h <= inner_h + 0.5 and all(ln.width <= inner_w + 0.5 for ln in lines)
                if fits:
                    best = mid
                    lo = mid
                else:
                    hi = mid
            size = max(min_fit, best)
            lines, content_h = build(size)
            overflow = content_h > inner_h + 0.5 or size <= min_fit + 0.01
        rect_h = box.rect.h
    else:
        lines, content_h = build(size)
        if box.size_mode == SizeMode.FIXED:
            overflow = content_h > inner_h + 0.5
            rect_h = box.rect.h
        else:  # AUTO_HEIGHT — wrap + grow height
            overflow = False
            rect_h = content_h + 2 * pad

    return LayoutResult(
        lines=lines,
        content_height=content_h,
        font_size=size,
        resolved_font=family,
        font_substituted=res.substituted,
        overflow=overflow,
        rect_h=rect_h,
        rect_w=rect_w,
    )


def apply_layout_to_box(box: TextBox) -> TextBox:
    """Update overflow / font resolution / auto-height on a copy-like mutation."""
    result = layout_text_box(box)
    box.overflow = result.overflow
    box.font_substituted = result.font_substituted
    box.resolved_font = result.resolved_font
    if box.size_mode == SizeMode.AUTO_HEIGHT:
        box.rect = box.rect.with_size(box.rect.w, result.rect_h)
    elif box.size_mode == SizeMode.AUTO_SIZE:
        box.rect = box.rect.with_size(max(box.rect.w, result.rect_w), result.rect_h)
    if box.size_mode == SizeMode.SHRINK_TO_FIT and result.font_size >= 6.0:
        box.style.font_size = result.font_size
    return box
