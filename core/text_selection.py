"""Selecting and copying the existing text of PDF pages (0.6.0).

Pure model, no Qt: the canvas turns mouse positions into display-space points and paints the
rectangles returned here; the window puts :meth:`TextSelection.text` on the system clipboard.

Text comes from MuPDF's ``rawdict`` extraction (one bounding box per character) and is kept in
**display space** (the page as shown after ``/Rotate``, see ``core.page_space``), the space the
viewer and every tool use, so selection rectangles line up with the rendered glyphs at any zoom and
rotation.

Reading order (0.6.0 RC2): the lines MuPDF extracts are put into **visual reading order** for
horizontal text, independent of the order in which the PDF stores them (see :func:`visual_order`):
lines are grouped into rows, rows into regions, a region whose lines are cut by a common vertical gap
(a column gutter) and that holds running text is read column by column, everything else row by row,
top to bottom and left to right. Characters inside a line keep MuPDF's order. Pages whose lines do not
all run in one direction (vertical Japanese mixed with horizontal text, for example) keep the stored
order — a documented fallback, not a layout guess. A drag selects every character between the two ends
in this order, also across pages (page order).

Characters are grouped into *clusters* before anything else: a combining mark, a variation
selector, an emoji modifier, a zero-width joiner and the character after it belong to the character
they follow, so a selection boundary never splits them. (A simplified form of Unicode grapheme
clusters: Hangul jamo sequences and regional-indicator pairs are not joined.)

Spaces: only the spaces in the PDF are copied, plus one synthesized space between two clusters of
the same line separated by a clear gap when neither is CJK (many PDFs position words without space
characters). No space is ever inserted next to Japanese / Chinese / Korean text. Lines are separated
by a line break; two parts of one visual line (side by side) by a space; pages by a blank line.

Nothing here changes the document: extraction reads the page only.
"""

from __future__ import annotations

import math
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field

import fitz

from core.page_space import rect_to_display

# rawdict without MuPDF's own space synthesis (it can put spaces between Japanese characters that
# are spaced apart); whitespace in the PDF is kept; ligatures are split into their letters
_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP | fitz.TEXT_INHIBIT_SPACES

# a gap wider than this share of the font size between two clusters of one line is a word space
_SPACE_GAP = 0.22


@dataclass(frozen=True)
class Glyph:
    """One cluster: its text and its display-space box."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    line: int
    block: int
    size: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Line:
    block: int
    start: int  # first glyph index
    end: int  # one past the last glyph
    x0: float
    y0: float
    x1: float
    y1: float
    dx: float  # writing direction in display space (unit vector)
    dy: float

    @property
    def vertical(self) -> bool:
        return abs(self.dy) > abs(self.dx)


@dataclass
class PageText:
    """The selectable text of one page."""

    page_index: int
    glyphs: list[Glyph] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.glyphs

    # -- hit testing ---------------------------------------------------------------------------

    def _nearest_line(self, x: float, y: float) -> int | None:
        best, best_d = None, math.inf
        for i, ln in enumerate(self.lines):
            # distance from the point to the line's box, measured mostly across the line
            ddx = max(ln.x0 - x, 0.0, x - ln.x1)
            ddy = max(ln.y0 - y, 0.0, y - ln.y1)
            if ln.vertical:
                d = ddx * 4 + ddy
            else:
                d = ddy * 4 + ddx
            if d < best_d:
                best, best_d = i, d
        return best

    def position_at(self, x: float, y: float) -> int | None:
        """Caret position (0 … number of glyphs) nearest to the display point ``(x, y)``: the
        position before the glyph whose middle lies after the point along its line."""
        li = self._nearest_line(x, y)
        if li is None:
            return None
        ln = self.lines[li]
        for g in range(ln.start, ln.end):
            gl = self.glyphs[g]
            t = (x - gl.cx) * ln.dx + (y - gl.cy) * ln.dy
            if t < 0:
                return g
        return ln.end

    def glyph_at(self, x: float, y: float, *, slack: float = 1.5) -> int | None:
        """Index of the glyph whose box contains the point (or ``None``)."""
        for i, g in enumerate(self.glyphs):
            if g.x0 - slack <= x <= g.x1 + slack and g.y0 - slack <= y <= g.y1 + slack:
                return i
        return None

    def has_text_near(self, x: float, y: float, *, slack: float = 6.0) -> bool:
        return self.glyph_at(x, y, slack=slack) is not None

    # -- ranges ----------------------------------------------------------------------------------

    def word_range(self, index: int) -> tuple[int, int]:
        """The run of glyphs of the same kind (letters/digits of one script, or punctuation, or
        spaces) around ``index`` within its line: a word in English; a run of Kanji, Hiragana or
        Katakana in Japanese (Japanese has no spaces, so this is an approximation of a word)."""
        if not self.glyphs:
            return (0, 0)
        index = max(0, min(index, len(self.glyphs) - 1))
        ln = self.lines[self.glyphs[index].line]
        kind = char_class(self.glyphs[index].text)
        a = index
        while a > ln.start and char_class(self.glyphs[a - 1].text) == kind:
            a -= 1
        b = index + 1
        while b < ln.end and char_class(self.glyphs[b].text) == kind:
            b += 1
        return (a, b)

    def line_range(self, index: int) -> tuple[int, int]:
        ln = self.lines[self.glyphs[max(0, min(index, len(self.glyphs) - 1))].line]
        return (ln.start, ln.end)

    def block_range(self, index: int) -> tuple[int, int]:
        """The paragraph containing ``index``: the neighbouring lines (in reading order) of the same
        MuPDF text block."""
        li = self.glyphs[max(0, min(index, len(self.glyphs) - 1))].line
        block = self.lines[li].block
        a = li
        while a > 0 and self.lines[a - 1].block == block:
            a -= 1
        b = li
        while b + 1 < len(self.lines) and self.lines[b + 1].block == block:
            b += 1
        return (self.lines[a].start, self.lines[b].end)

    # -- output ----------------------------------------------------------------------------------

    def text(self, start: int, end: int) -> str:
        """Plain text of glyphs ``start`` … ``end - 1``."""
        out: list[str] = []
        prev: Glyph | None = None
        for g in self.glyphs[max(0, start):max(0, end)]:
            if prev is not None:
                out.append(self._separator(prev, g))
            out.append(g.text)
            prev = g
        return "".join(out)

    def _separator(self, a: Glyph, b: Glyph) -> str:
        if a.line == b.line:
            ln = self.lines[a.line]
            if a.text.isspace() or b.text.isspace() or is_cjk(a.text) or is_cjk(b.text):
                return ""
            gap = (b.x0 - a.x1) if not ln.vertical else (b.y0 - a.y1)
            if ln.dx < 0 or ln.dy < 0:  # right-to-left or bottom-to-top
                gap = (a.x0 - b.x1) if not ln.vertical else (a.y0 - b.y1)
            return " " if gap > _SPACE_GAP * max(a.size, b.size, 1.0) else ""
        la, lb = self.lines[a.line], self.lines[b.line]
        if not la.vertical and not lb.vertical:
            overlap = min(la.y1, lb.y1) - max(la.y0, lb.y0)
            if overlap > 0.5 * min(la.y1 - la.y0, lb.y1 - lb.y0) and lb.x0 >= la.x1 - 1.0:
                # two pieces of one visual line (e.g. a change of font MuPDF keeps as two lines)
                if a.text.isspace() or b.text.isspace() or is_cjk(a.text) or is_cjk(b.text):
                    return ""
                gap = lb.x0 - la.x1
                return " " if gap > _SPACE_GAP * max(a.size, b.size, 1.0) else ""
        return "\n"

    def rects(self, start: int, end: int) -> list[tuple[float, float, float, float]]:
        """Display-space rectangles covering glyphs ``start`` … ``end - 1``, one per line piece."""
        out: list[tuple[float, float, float, float]] = []
        if start >= end:
            return out
        for ln in self.lines:
            a, b = max(start, ln.start), min(end, ln.end)
            if a >= b:
                continue
            gs = self.glyphs[a:b]
            x0 = min(g.x0 for g in gs)
            y0 = min(g.y0 for g in gs)
            x1 = max(g.x1 for g in gs)
            y1 = max(g.y1 for g in gs)
            out.append((x0, y0, x1, y1))
        return out

    def overlaps(self, start: int, end: int, rects) -> bool:
        """True when any glyph in the range overlaps one of the display-space ``rects``."""
        for g in self.glyphs[start:end]:
            for r in rects:
                if g.x0 < r[2] and r[0] < g.x1 and g.y0 < r[3] and r[1] < g.y1:
                    return True
        return False


# -- characters ------------------------------------------------------------------------------------

def _joins_previous(ch: str, prev: str) -> bool:
    if not ch:
        return False
    cp = ord(ch[0])
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Mc"):
        return True
    if 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF:  # variation selectors
        return True
    if 0x1F3FB <= cp <= 0x1F3FF:  # emoji skin-tone modifiers
        return True
    if cp == 0x200D:  # zero-width joiner joins the previous and the next character
        return True
    if prev.endswith("‍"):
        return True
    if 0xE0020 <= cp <= 0xE007F:  # emoji tag characters
        return True
    return False


def is_cjk(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        if (
            0x3040 <= cp <= 0x30FF  # Hiragana, Katakana
            or 0x31F0 <= cp <= 0x31FF  # Katakana extension
            or 0x3400 <= cp <= 0x4DBF  # CJK extension A
            or 0x4E00 <= cp <= 0x9FFF  # CJK unified ideographs
            or 0xF900 <= cp <= 0xFAFF  # CJK compatibility ideographs
            or 0xFF00 <= cp <= 0xFFEF  # full-width and half-width forms
            or 0x3000 <= cp <= 0x303F  # CJK symbols and punctuation
            or 0xAC00 <= cp <= 0xD7AF  # Hangul syllables
            or 0x20000 <= cp <= 0x2FA1F  # CJK extensions B…
        ):
            return True
    return False


def char_class(text: str) -> str:
    """Kind of a cluster for word selection."""
    if not text:
        return "other"
    ch = text[0]
    if ch.isspace():
        return "space"
    cp = ord(ch)
    if 0x3040 <= cp <= 0x309F:
        return "hiragana"
    if 0x30A0 <= cp <= 0x30FF or 0x31F0 <= cp <= 0x31FF or 0xFF66 <= cp <= 0xFF9F:
        return "katakana"  # includes the long-vowel mark ー
    if 0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF or 0x20000 <= cp <= 0x2FA1F or ch == "々":
        return "han"
    if 0xAC00 <= cp <= 0xD7AF:
        return "hangul"
    cat = unicodedata.category(ch)
    if cat[0] in ("L", "N", "M") or ch in "_'’":
        return "word"
    return "punct:" + ch if cat[0] == "P" else "symbol"


# -- extraction ------------------------------------------------------------------------------------

def _rotate_vector(page: fitz.Page, dx: float, dy: float) -> tuple[float, float]:
    if not page.rotation:
        return dx, dy
    m = page.rotation_matrix
    vx, vy = dx * m.a + dy * m.c, dx * m.b + dy * m.d
    n = math.hypot(vx, vy) or 1.0
    return vx / n, vy / n


def extract_page_text(page: fitz.Page, page_index: int | None = None) -> PageText:
    """The selectable text of ``page`` in visual reading order (reads the page only)."""
    return visual_order(_extract(page, page_index))


def _extract(page: fitz.Page, page_index: int | None = None) -> PageText:
    """The page's text in stored order (MuPDF ``sort=False``)."""
    pt = PageText(page_index=page.number if page_index is None else page_index)
    try:
        raw = page.get_text("rawdict", flags=_FLAGS, sort=False)
    except Exception:  # noqa: BLE001 — a damaged page has no selectable text rather than an error
        return pt
    block_no = 0
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            ldx, ldy = line.get("dir", (1.0, 0.0))
            dx, dy = _rotate_vector(page, float(ldx), float(ldy))
            clusters: list[list] = []  # [text, x0, y0, x1, y1, size]
            for span in line.get("spans", []):
                size = float(span.get("size", 10.0) or 10.0)
                for ch in span.get("chars", []):
                    c = ch.get("c", "")
                    if not c:
                        continue
                    r = rect_to_display(page, ch["bbox"])
                    if clusters and _joins_previous(c, clusters[-1][0]):
                        cl = clusters[-1]
                        cl[0] += c
                        cl[1], cl[2] = min(cl[1], r.x0), min(cl[2], r.y0)
                        cl[3], cl[4] = max(cl[3], r.x1), max(cl[4], r.y1)
                        continue
                    clusters.append([c, r.x0, r.y0, r.x1, r.y1, size])
            if not clusters:
                continue
            line_idx = len(pt.lines)
            start = len(pt.glyphs)
            for c, x0, y0, x1, y1, size in clusters:
                pt.glyphs.append(Glyph(c, x0, y0, x1, y1, line_idx, block_no, size))
            gs = pt.glyphs[start:]
            pt.lines.append(Line(
                block=block_no, start=start, end=len(pt.glyphs),
                x0=min(g.x0 for g in gs), y0=min(g.y0 for g in gs),
                x1=max(g.x1 for g in gs), y1=max(g.y1 for g in gs), dx=dx, dy=dy))
        block_no += 1
    return pt


def extract_page_text_stored(page: fitz.Page, page_index: int | None = None) -> PageText:
    """Like :func:`extract_page_text` but in the order the PDF stores the text (no reordering)."""
    return _extract(page, page_index)


# -- visual reading order ----------------------------------------------------------------------------

# a vertical gap at least this many line heights wide (and at least _GUTTER_MIN points) between the
# lines of two or more rows is a column gutter
_GUTTER_EM = 0.8
_GUTTER_MIN = 4.0
# a region holds running text (read column by column) when the median line of each of its columns
# has at least this many characters; shorter cells (tables, forms, labels) are read row by row
_RUNNING_TEXT_CHARS = 12
# rows further apart than this many line heights start a new region (a header above columns)
_REGION_BREAK = 3.0


@dataclass
class _Item:
    index: int  # line index in stored order
    u0: float  # along the writing direction
    v0: float  # across it, downwards in reading order
    u1: float
    v1: float
    chars: int

    @property
    def h(self) -> float:
        return max(self.v1 - self.v0, 0.1)


def _frame(lines: list[Line]) -> tuple[float, float, float, float] | None:
    """(dx, dy, nx, ny): the common writing direction and the direction in which lines follow each
    other, or ``None`` when the lines do not all run the same way (then stored order is kept)."""
    if not lines:
        return None
    longest = max(lines, key=lambda ln: ln.end - ln.start)
    dx, dy = longest.dx, longest.dy
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    for ln in lines:
        m = math.hypot(ln.dx, ln.dy) or 1.0
        if (ln.dx * dx + ln.dy * dy) / m < 0.97:  # more than ~14° apart, or opposite
            return None
    # the next line follows "below" the writing direction: (1, 0) -> (0, 1); turned pages likewise
    return dx, dy, -dy, dx


def _items(lines: list[Line], frame) -> list[_Item]:
    dx, dy, nx, ny = frame
    out = []
    for i, ln in enumerate(lines):
        us = [x * dx + y * dy for x in (ln.x0, ln.x1) for y in (ln.y0, ln.y1)]
        vs = [x * nx + y * ny for x in (ln.x0, ln.x1) for y in (ln.y0, ln.y1)]
        out.append(_Item(i, min(us), min(vs), max(us), max(vs), ln.end - ln.start))
    return out


def _rows(items: list[_Item]) -> list[list[_Item]]:
    """Group lines into rows: lines whose middle halves overlap across the writing direction."""
    rows: list[list[_Item]] = []
    lo = hi = 0.0
    for it in sorted(items, key=lambda t: (t.v0 + t.h * 0.25, t.u0, t.index)):
        c0, c1 = it.v0 + it.h * 0.25, it.v1 - it.h * 0.25
        if rows and c0 < hi:
            rows[-1].append(it)
            hi = max(hi, c1)
        else:
            rows.append([it])
            lo, hi = c0, c1
    _ = lo
    return rows


def _gaps(items: list[_Item], width: float) -> list[tuple[float, float]]:
    """Intervals along the writing direction that no item covers and that are at least ``width``."""
    out = []
    spans = sorted((t.u0, t.u1) for t in items)
    reach = spans[0][1]
    for a, b in spans[1:]:
        if a - reach >= width:
            out.append((reach, a))
        reach = max(reach, b)
    return out


def _median(values: list[float]) -> float:
    vs = sorted(values)
    return vs[len(vs) // 2] if vs else 0.0


def _row_major(rows: list[list[_Item]]) -> list[_Item]:
    return [it for row in rows for it in sorted(row, key=lambda t: (t.u0, t.v0, t.index))]


def _arrange(items: list[_Item], line_h: float) -> list[_Item]:
    if len(items) <= 1:
        return list(items)
    rows = _rows(items)
    if len(rows) == 1:
        return _row_major(rows)
    width = max(_GUTTER_EM * line_h, _GUTTER_MIN)
    row_gaps = [_gaps(r, width) if len(r) > 1 else [] for r in rows]
    # the gutter shared by most rows (at least two)
    best, best_support = None, 1
    for gaps in row_gaps:
        for g in gaps:
            common, support = g, 0
            for other in row_gaps:
                hit = next((o for o in other if o[0] < common[1] and common[0] < o[1]), None)
                if hit is not None:
                    common = (max(common[0], hit[0]), min(common[1], hit[1]))
                    support += 1
            if support > best_support or (support == best_support and best is not None and common[0] < best[0]):
                best, best_support = common, support
    if best is None:
        return _row_major(rows)
    g0, g1 = best

    def crosses(row: list[_Item]) -> bool:
        return any(t.u0 < g1 - 0.5 and t.u1 > g0 + 0.5 for t in row)

    out: list[_Item] = []
    run: list[list[_Item]] = []

    def flush() -> None:
        if not run:
            return
        members = [t for r in run for t in r]
        left = [t for t in members if t.u1 <= g0 + 0.5]
        right = [t for t in members if t.u0 >= g1 - 0.5]
        li, ri = {t.index for t in left}, {t.index for t in right}
        two_sided = sum(1 for r in run if any(t.index in li for t in r) and any(t.index in ri for t in r))
        running = (left and right and _median([t.chars for t in left]) >= _RUNNING_TEXT_CHARS
                   and _median([t.chars for t in right]) >= _RUNNING_TEXT_CHARS)
        if two_sided >= 2 and running:
            out.extend(_arrange(left, line_h) + _arrange(right, line_h))  # column by column
        elif len(members) < len(items):
            out.extend(_arrange(members, line_h))
        else:
            out.extend(_row_major(run))
        run.clear()

    prev_bottom = None
    for row in rows:
        top = min(t.v0 for t in row)
        if crosses(row):
            flush()
            out.extend(_row_major([row]))
        else:
            if run and prev_bottom is not None and top - prev_bottom > _REGION_BREAK * line_h:
                flush()
            run.append(row)
        prev_bottom = max(t.v1 for t in row)
    flush()
    return out


def visual_order(pt: PageText) -> PageText:
    """``pt`` with its lines in visual reading order (see the module docstring). Characters inside a
    line keep their order; pages whose lines run in different directions are returned unchanged."""
    if len(pt.lines) < 2:
        return pt
    frame = _frame(pt.lines)
    if frame is None:
        return pt
    items = _items(pt.lines, frame)
    line_h = _median([t.h for t in items]) or 10.0
    order = [t.index for t in _arrange(items, line_h)]
    if order == list(range(len(pt.lines))):
        return pt
    out = PageText(page_index=pt.page_index)
    for new_li, old_li in enumerate(order):
        ln = pt.lines[old_li]
        start = len(out.glyphs)
        for g in pt.glyphs[ln.start:ln.end]:
            out.glyphs.append(Glyph(g.text, g.x0, g.y0, g.x1, g.y1, new_li, g.block, g.size))
        out.lines.append(Line(block=ln.block, start=start, end=len(out.glyphs), x0=ln.x0, y0=ln.y0,
                              x1=ln.x1, y1=ln.y1, dx=ln.dx, dy=ln.dy))
    return out


def compose(base: PageText, removals, extra: list[PageText]) -> PageText:
    """``base`` (stored order) without the characters that overlap a display-space rectangle of
    ``removals`` (x0, y0, x1, y1), followed by the lines of ``extra``: the text a page shows while
    replacements of existing text are not saved yet (see ``engines/visible_text.py``)."""
    out = PageText(page_index=base.page_index)
    rects = [tuple(r) for r in removals]

    def hidden(g: Glyph) -> bool:
        return any(g.x0 < r[2] and r[0] < g.x1 and g.y0 < r[3] and r[1] < g.y1 for r in rects)

    def add(lines_glyphs, block, dx, dy) -> None:
        if not lines_glyphs:
            return
        li, start = len(out.lines), len(out.glyphs)
        for g in lines_glyphs:
            out.glyphs.append(Glyph(g.text, g.x0, g.y0, g.x1, g.y1, li, block, g.size))
        gs = out.glyphs[start:]
        out.lines.append(Line(block=block, start=start, end=len(out.glyphs), x0=min(g.x0 for g in gs),
                              y0=min(g.y0 for g in gs), x1=max(g.x1 for g in gs), y1=max(g.y1 for g in gs),
                              dx=dx, dy=dy))

    top = -1
    for ln in base.lines:
        add([g for g in base.glyphs[ln.start:ln.end] if not hidden(g)], ln.block, ln.dx, ln.dy)
        top = max(top, ln.block)
    for part in extra:
        offset = top + 1
        for ln in part.lines:
            add(part.glyphs[ln.start:ln.end], offset + ln.block, ln.dx, ln.dy)
            top = max(top, offset + ln.block)
    return out


class PageTextCache:
    """Per-page text, extracted only when a page is selected on and kept for the most recent
    ``max_pages`` pages. Keyed by page index, the page object's xref and its rotation, so a moved,
    rotated or replaced page is extracted again; :meth:`invalidate` forgets pages whose content
    changed.

    ``overlay`` (optional) supplies unsaved edits that change what a page shows (replaced existing
    text): ``overlay.signature(doc, page)`` is cheap and ``None`` when the page has none;
    ``overlay.contribution(doc, page)`` returns ``(removal_rects, [PageText, …])``. The page is read
    from the PDF once; only the composition is rebuilt when the signature changes. ``version`` and
    :meth:`changed_since` let a selection notice that the text under it changed."""

    def __init__(self, max_pages: int = 24) -> None:
        self.max_pages = max_pages
        # page -> (key, signature, stored-order text, text as shown in reading order)
        self._items: OrderedDict[int, tuple[tuple, object, PageText, PageText]] = OrderedDict()
        self.extractions = 0  # for tests and measurements
        self.overlay = None
        self.version = 0
        self._changed: dict[int, int] = {}

    def get(self, doc: fitz.Document, page_index: int) -> PageText:
        page = doc.load_page(page_index)
        key = (int(doc.page_xref(page_index)), int(page.rotation))
        sig = None
        if self.overlay is not None:
            try:
                sig = self.overlay.signature(doc, page_index)
            except Exception:  # noqa: BLE001 — never stands in the way of selecting the page's own text
                sig = None
        hit = self._items.get(page_index)
        if hit is not None and hit[0] == key and hit[1] == sig:
            self._items.move_to_end(page_index)
            return hit[3]
        if hit is not None and hit[0] == key:
            raw = hit[2]
        else:
            raw = _extract(page, page_index)
            self.extractions += 1
        shown = raw
        if sig is not None:
            try:
                removals, extra = self.overlay.contribution(doc, page_index)
                shown = compose(raw, removals, extra)
            except Exception:  # noqa: BLE001
                shown = raw
        shown = visual_order(shown)
        if hit is not None:  # the text of a page already read changed (an edit, Undo, Redo)
            self.version += 1
            self._changed[page_index] = self.version
        self._items[page_index] = (key, sig, raw, shown)
        self._items.move_to_end(page_index)
        while len(self._items) > self.max_pages:
            self._items.popitem(last=False)
        return shown

    def changed_since(self, version: int, first: int, last: int) -> bool:
        return any(first <= p <= last and v > version for p, v in self._changed.items())

    def invalidate(self, pages=None) -> None:
        if pages is None:
            self._items.clear()
            return
        for p in pages:
            self._items.pop(int(p), None)

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True)
class TextPosition:
    page: int
    pos: int

    def __lt__(self, other: "TextPosition") -> bool:
        return (self.page, self.pos) < (other.page, other.pos)

    def __le__(self, other: "TextPosition") -> bool:
        return (self.page, self.pos) <= (other.page, other.pos)


class TextSelection:
    """A selection of existing page text from ``anchor`` to ``focus`` (either order), across pages.

    Holds positions only; the text of a page is read through the cache when it is needed."""

    def __init__(self, cache: PageTextCache) -> None:
        self.cache = cache
        self.anchor: TextPosition | None = None
        self._focus: TextPosition | None = None
        self._version = cache.version

    @property
    def focus(self) -> TextPosition | None:
        return self._focus

    @focus.setter
    def focus(self, value: TextPosition | None) -> None:
        self._focus = value
        self._version = self.cache.version

    def clear(self) -> None:
        self.anchor = self.focus = None

    @property
    def empty(self) -> bool:
        return self.anchor is None or self.focus is None or self.anchor == self.focus

    def bounds(self) -> tuple[TextPosition, TextPosition] | None:
        if self.anchor is None or self.focus is None:
            return None
        a, b = self.anchor, self.focus
        lo, hi = (a, b) if a <= b else (b, a)
        if self.cache.changed_since(self._version, lo.page, hi.page):
            # the text under the selection changed (an unsaved edit, Undo or Redo): its positions
            # no longer mean the same characters, so the selection is dropped rather than shifted
            self.clear()
            return None
        return lo, hi

    def set(self, anchor: TextPosition, focus: TextPosition) -> None:
        self.anchor = anchor
        self.focus = focus

    def page_range(self, doc: fitz.Document, page_index: int) -> tuple[int, int] | None:
        """Selected glyph range on one page (``None`` when nothing on it is selected)."""
        b = self.bounds()
        if b is None or self.empty:
            return None
        lo, hi = b
        if page_index < lo.page or page_index > hi.page:
            return None
        n = len(self.cache.get(doc, page_index).glyphs)
        if self.bounds() is None:  # reading the page just showed that its text changed
            return None
        start = min(lo.pos, n) if page_index == lo.page else 0
        end = min(hi.pos, n) if page_index == hi.page else n
        return (start, end) if start < end else None

    def text(self, doc: fitz.Document) -> str:
        b = self.bounds()
        if b is None or self.empty:
            return ""
        lo, hi = b
        parts: list[str] = []
        for p in range(lo.page, hi.page + 1):
            rng = self.page_range(doc, p)
            if rng is None:
                continue
            chunk = self.cache.get(doc, p).text(*rng)
            if chunk:
                parts.append(chunk)
        return "\n\n".join(parts)

    def pages(self) -> range:
        b = self.bounds()
        return range(0) if b is None else range(b[0].page, b[1].page + 1)
