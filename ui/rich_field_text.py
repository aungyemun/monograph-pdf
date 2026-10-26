"""Qt side of mixed formatting in form fields: runs ⇄ QTextDocument character formats.

Only a run's *own* settings go into a character format (stored as user properties so they can
be read back exactly); everything else follows the editor's base font, so a whole-field change
of font or size still reaches the words that were not given their own.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat

from core.forms.rich_text import STYLE_KEYS, char_styles, normalize_runs, runs_from_char_styles

_P = {key: int(QTextFormat.Property.UserProperty) + 101 + i for i, key in enumerate(STYLE_KEYS)}


def char_format(style: tuple, px_per_pt: float) -> QTextCharFormat:
    """Character format for one style tuple (family, size, bold, italic, color); None = inherit."""
    family, size, bold, italic, color = style
    fmt = QTextCharFormat()
    fmt.setProperty(_P["family"], family or "")
    fmt.setProperty(_P["size"], float(size or 0))
    fmt.setProperty(_P["bold"], -1 if bold is None else int(bool(bold)))
    fmt.setProperty(_P["italic"], -1 if italic is None else int(bool(italic)))
    fmt.setProperty(_P["color"], color or "")
    font = QFont()
    specified = False
    if family:
        font.setFamilies([family])
        specified = True
    if size:
        font.setPixelSize(max(1, int(round(float(size) * px_per_pt))))
        specified = True
    if bold is not None:
        font.setBold(bool(bold))
        specified = True
    if italic is not None:
        font.setItalic(bool(italic))
        specified = True
    if specified:
        fmt.setFont(font, QTextCharFormat.FontPropertiesInheritanceBehavior.FontPropertiesSpecifiedOnly)
    if color:
        fmt.setForeground(QColor(color))
    return fmt


def style_of(fmt: QTextCharFormat) -> tuple:
    def prop(key):
        return fmt.property(_P[key])

    family = prop("family") or None
    size = float(prop("size") or 0) or None
    b, i = prop("bold"), prop("italic")
    bold = None if b in (None, -1) else bool(b)
    italic = None if i in (None, -1) else bool(i)
    color = prop("color") or None
    return (family, size, bold, italic, color)


def runs_from_document(doc: QTextDocument) -> tuple[str, list[dict]]:
    """(plain text, runs) of a document; paragraphs are joined with "\\n"."""
    plain = (None,) * len(STYLE_KEYS)
    pieces: list[tuple[str, tuple]] = []  # (text, style) per fragment, "\n" between paragraphs
    block = doc.begin()
    first = True
    styled = False
    while block.isValid():
        if not first:
            pieces.append(("\n", pieces[-1][1] if pieces else plain))
        first = False
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                st = style_of(frag.charFormat())
                styled = styled or st != plain
                pieces.append((frag.text(), st))
            it += 1
        block = block.next()
    text = "".join(t for t, _ in pieces)
    if not styled:
        return text, []  # one style throughout (typing plain text: no per-character work)
    styles: list[tuple] = []
    for t, st in pieces:
        styles.extend([st] * len(t))
    return text, runs_from_char_styles(text, styles)


def apply_runs(doc: QTextDocument, runs: list[dict], px_per_pt: float) -> None:
    """Give every character of ``doc`` the format of its run (no runs = plain base font)."""
    text = doc.toPlainText()
    styles = char_styles(normalize_runs(runs), text)
    cur = QTextCursor(doc)
    cur.beginEditBlock()
    start = 0
    while start < len(text):
        end = start + 1
        while end < len(text) and styles[end] == styles[start]:
            end += 1
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cur.setCharFormat(char_format(styles[start], px_per_pt))
        start = end
    cur.endEditBlock()


def restyle_range(
    doc: QTextDocument,
    start: int,
    end: int,
    px_per_pt: float,
    base_pt: Callable[[], float],
    **change: Any,
) -> None:
    """Change the look of characters ``start``–``end`` only (the selected words).

    ``family`` / ``size`` / ``bold`` / ``italic`` / ``color`` set the value (``size=None`` =
    follow the field again); ``size_delta`` grows / shrinks each selected character from its
    current size (A+ / A−).
    """
    text, runs = runs_from_document(doc)
    styles = char_styles(runs, text)
    keys = list(STYLE_KEYS)
    delta = change.pop("size_delta", None)
    for k in range(max(0, start), min(end, len(text))):
        st = list(styles[k])
        for key, value in change.items():
            if key in keys:
                st[keys.index(key)] = value
        if delta is not None:
            current = st[1] or base_pt()
            st[1] = max(4.0, min(200.0, float(current) + delta))
        styles[k] = tuple(st)
    apply_runs(doc, runs_from_char_styles(text, styles), px_per_pt)


def style_at(doc: QTextDocument, position: int) -> tuple:
    """Own style of the character after ``position`` (or before it at the end)."""
    text, runs = runs_from_document(doc)
    styles = char_styles(runs, text)
    if not styles:
        return (None,) * len(STYLE_KEYS)
    return styles[min(max(0, position), len(styles) - 1)]


def insert_html_fragment(editor, html: str, px_per_pt: float, base_pt: float) -> bool:
    """Paste HTML into a field editor, mapping bold/italic/font/size/colour onto run styles.

    Returns False when the fragment has no usable text (caller should fall back to plain paste).
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextCursor

    probe = QTextDocument()
    probe.setHtml(html or "")
    plain = probe.toPlainText()
    if not plain:
        return False

    styles: list[tuple] = []
    block = probe.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                font = fmt.font()
                families = font.families() or ([font.family()] if font.family() else [])
                family = families[0] if families else None
                px, pt = font.pixelSize(), font.pointSizeF()
                size = None
                if px > 0 and px_per_pt > 0:
                    size = round(px / px_per_pt, 1)
                elif pt > 0:
                    size = float(pt)
                if size is not None and abs(size - float(base_pt or 0)) < 0.3:
                    size = None
                brush = fmt.foreground()
                color = None
                if brush.style() != Qt.BrushStyle.NoBrush:
                    name = brush.color().name()
                    if name.lower() not in ("#000000", "#000"):
                        color = name
                st = (
                    family if family and family.lower() not in ("sans-serif", "serif", "monospace") else None,
                    size,
                    True if font.bold() else None,
                    True if font.italic() else None,
                    color,
                )
                styles.extend([st] * len(frag.text()))
            it += 1
        block = block.next()
        if block.isValid():
            styles.append(styles[-1] if styles else (None,) * len(STYLE_KEYS))
    if not styles or all(s == (None,) * len(STYLE_KEYS) for s in styles):
        return False
    runs = runs_from_char_styles(plain, styles)

    cur: QTextCursor = editor.textCursor()
    cur.beginEditBlock()
    start = cur.selectionStart() if cur.hasSelection() else cur.position()
    if cur.hasSelection():
        cur.removeSelectedText()
    cur.insertText(plain)
    end = start + len(plain)
    live = editor.document()
    full_text, existing = runs_from_document(live)
    full_styles = char_styles(existing, full_text)
    paste_styles = char_styles(normalize_runs(runs), plain)
    for i, st in enumerate(paste_styles):
        idx = start + i
        if idx < len(full_styles):
            full_styles[idx] = st
    apply_runs(live, runs_from_char_styles(full_text, full_styles), px_per_pt)
    cur.setPosition(end)
    editor.setTextCursor(cur)
    cur.endEditBlock()
    return True


def paint_runs(painter, field, rect, px_per_pt: float, base_font: QFont, h_align, valign: str, multiline: bool) -> None:
    """Draw a field's entry with its word formats inside ``rect`` (widget pixels)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QAbstractTextDocumentLayout, QPalette, QTextOption

    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setDefaultFont(base_font)
    opt = QTextOption(h_align)
    opt.setWrapMode(QTextOption.WrapMode.WordWrap if multiline else QTextOption.WrapMode.NoWrap)
    doc.setDefaultTextOption(opt)
    doc.setPlainText(str(field.value or ""))
    apply_runs(doc, list(field.runs or []), px_per_pt)
    doc.setTextWidth(rect.width())
    content_h = doc.size().height()
    off = {"middle": (rect.height() - content_h) / 2, "bottom": rect.height() - content_h}.get(valign, 0.0)
    off = max(0.0, off) if content_h <= rect.height() else 0.0
    painter.save()
    painter.translate(rect.x(), rect.y() + off)
    painter.setClipRect(QRectF(0, -off, rect.width(), rect.height()))
    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.palette.setColor(QPalette.ColorRole.Text, QColor(getattr(field, "text_color", "") or "#000000"))
    doc.documentLayout().draw(painter, ctx)
    painter.restore()
