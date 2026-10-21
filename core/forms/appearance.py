"""Text-field appearances for values MuPDF's built-in generator cannot draw well.

MuPDF draws a field with one base-14 font (Helvetica, Times or Courier) and falls back to an
unembedded CJK font for kanji. That breaks for:

* full-width letters and digits (ＡＢＣ１２３) — drawn as "······";
* ordinary digits and letters after Japanese text — drawn with fixed 1 em spacing;
* bold and italic — the base-14 field fonts have no variants in /DA.

For those fields this module writes the /AP appearance stream itself: Latin text uses the
matching base-14 variant (regular / bold / italic / bold italic), every other character
uses an embedded subset of a Unicode CJK font (Droid Sans Fallback, built into MuPDF) that
covers kanji, kana, half- and full-width forms. Text stays selectable and searchable.
The field value itself (/V) is never changed.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import fitz

_BASE = {"Helv": ("helv", "hebo", "heit", "hebi"), "TiRo": ("tiro", "tibo", "tiit", "tibi"), "Cour": ("cour", "cobo", "coit", "cobi")}
_CJK_FAMILY = re.compile(r"mincho|gothic|meiryo|yu |yugoth|yumin|kozuka|koz|heisei|ms[ -]?p?(mincho|gothic)|noto.*(cjk|jp)|源|明朝|ゴシック", re.I)
_ITALIC_SKEW = 0.21  # ~12°, like an oblique font


def is_cjk_family(family: str) -> bool:
    return bool(_CJK_FAMILY.search(family or ""))


def needs_custom_appearance(field: Any) -> bool:
    """True when MuPDF's own appearance would be wrong for this value or style."""
    value = str(getattr(field, "value", "") or "")
    if not value:
        return False
    if getattr(field, "runs", None):
        return True  # mixed fonts / sizes / styles inside the entry
    from core.editing import system_fonts

    family = str(getattr(field, "font_family", "") or "")
    if family and system_fonts.find_font_file(family, bool(getattr(field, "bold", False)), bool(getattr(field, "italic", False))):
        return True  # an installed font that can be embedded: MuPDF's own appearance only knows base-14
    if bool(getattr(field, "bold", False) or getattr(field, "italic", False)) or any(ord(c) > 0xFF for c in value):
        return True
    # MuPDF draws one line centred and wrapped text from the top; any other position is ours
    natural = "top" if getattr(field, "multiline", False) else "middle"
    chosen = str(getattr(field, "valign", "") or "")
    if chosen in ("top", "middle", "bottom") and chosen != natural:
        return True
    if getattr(field, "align", "") == "justify" and getattr(field, "multiline", False):
        return True  # PDF fields have no justify (/Q is left / centre / right) — we draw it
    return _auto_text_too_wide(field, value)


def _auto_text_too_wide(field: Any, value: str) -> bool:
    """Auto size on one line: MuPDF sizes by height only and cuts long entries off. Acrobat
    shrinks the text to fit the width — so do we (the field stays "Auto" in the PDF)."""
    if float(getattr(field, "font_size", 0) or 0) > 0 or getattr(field, "multiline", False):
        return False
    rect = getattr(field, "rect", None)
    w, h = float(getattr(rect, "w", 0) or 0), float(getattr(rect, "h", 0) or 0)
    if w <= 4 or h <= 4:
        return False
    try:
        size = max(4.0, min(h * 0.72, 24.0))
        return fitz.Font("helv").text_length(value, fontsize=size) > w - 4
    except Exception:  # noqa: BLE001
        return False


def _latin_font(family: str, bold: bool, italic: bool) -> fitz.Font:
    """The font for a family: the installed font itself when it may be embedded, else the closest base-14 face."""
    from core.editing import system_fonts
    from core.forms.acroform import pdf_base_font

    installed = system_fonts.load(family, bold, italic)
    if installed is not None:
        return installed
    names = _BASE.get(pdf_base_font(family), _BASE["Helv"])
    return fitz.Font(names[(1 if bold else 0) + (2 if italic else 0)])


def _space_safe(font: fitz.Font) -> bool:
    """False for an installed font whose space and no-break space share one glyph: MuPDF then writes the
    text's spaces as U+00A0, so copied or searched text from other viewers would not contain real spaces."""
    from core.editing.system_fonts import is_system_font, roundtrips

    return not is_system_font(font) or roundtrips(font, " ")


def _latin_has(font: fitz.Font, ch: str) -> bool:
    """Latin, punctuation and symbols the base-14 font draws (– — “ ” € …); never CJK forms.
    An embedded installed font draws every character it has a glyph for."""
    from core.editing.system_fonts import is_system_font, roundtrips

    cp = ord(ch)
    if is_system_font(font):
        if ch in " 	":
            return True
        return bool(font.has_glyph(cp)) and roundtrips(font, ch)
    if cp <= 0xFF:
        return bool(font.has_glyph(cp)) or ch in " \t"
    return cp < 0x2E80 and bool(font.has_glyph(cp))


def _runs(text: str, latin: fitz.Font | None, cjk: fitz.Font) -> list[tuple[str, fitz.Font]]:
    out: list[tuple[str, fitz.Font]] = []
    for ch in text:
        font = latin if (latin is not None and _latin_has(latin, ch)) else cjk
        if ch == " " and out and out[-1][1].has_glyph(32) and _space_safe(out[-1][1]):
            font = out[-1][1]  # a space stays with the word before it (copy / search keep it)
        if out and out[-1][1] is font:
            out[-1] = (out[-1][0] + ch, font)
        else:
            out.append((ch, font))
    return out


def _width(runs: list[tuple[str, fitz.Font]], size: float) -> float:
    return sum(f.text_length(t, fontsize=size) for t, f in runs)


def _wrap(text: str, latin: fitz.Font | None, cjk: fitz.Font, size: float, max_w: float) -> list[str]:
    """Greedy wrap: break at spaces for Latin, between any two CJK characters."""
    return [line for line, _last in _wrap_marked(text, latin, cjk, size, max_w)]


def _wrap_marked(
    text: str, latin: fitz.Font | None, cjk: fitz.Font, size: float, max_w: float
) -> list[tuple[str, bool]]:
    """Wrapped lines, each with True when it ends a paragraph (such lines are not justified)."""
    lines: list[tuple[str, bool]] = []
    for para in text.replace("\r\n", "\n").split("\n"):
        tokens = re.findall(r"[　-鿿豈-￯]|\s+|[^\s　-鿿豈-￯]+", para) or [""]
        line = ""
        for tok in tokens:
            cand = line + tok
            if line and _width(_runs(cand.rstrip(), latin, cjk), size) > max_w:
                lines.append((line.rstrip(), False))
                line = tok.lstrip()
            else:
                line = cand
        lines.append((line.rstrip(), True))
    return lines


def _hex_rgb(color: str) -> tuple[float, float, float]:
    c = (color or "#000000").lstrip("#")[-6:].rjust(6, "0")
    return int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255


def _border_and_background(widget: Any, w: float, h: float) -> bytes:
    """The field's own background (/MK /BG) and border (/MK /BC, width), like Acrobat draws them."""
    out = []
    fill = getattr(widget, "fill_color", None)
    if fill and len(fill) in (1, 3, 4):
        op = {1: "g", 3: "rg", 4: "k"}[len(fill)]
        out.append(f"{' '.join(f'{v:.3f}' for v in fill)} {op} 0 0 {w:.3f} {h:.3f} re f")
    stroke = getattr(widget, "border_color", None)
    try:
        bw = float(getattr(widget, "border_width", 0) or 0)
    except (TypeError, ValueError):
        bw = 0.0
    if stroke and len(stroke) in (1, 3, 4) and bw > 0:
        op = {1: "G", 3: "RG", 4: "K"}[len(stroke)]
        out.append(
            f"{bw:.3f} w {' '.join(f'{v:.3f}' for v in stroke)} {op} "
            f"{bw / 2:.3f} {bw / 2:.3f} {w - bw:.3f} {h - bw:.3f} re S"
        )
    return ("q\n" + "\n".join(out) + "\nQ\n").encode() if out else b""


_ROTATION_MATRIX = {90: "[0 1 -1 0 0 0]", 180: "[-1 0 0 -1 0 0]", 270: "[0 -1 1 0 0 0]"}


def _widget_rotation(doc: fitz.Document, xref: int) -> int:
    try:
        kind, val = doc.xref_get_key(xref, "MK/R")
        return int(float(val)) % 360 if kind in ("int", "real") else 0
    except Exception:  # noqa: BLE001
        return 0


class _Layout:
    """The entry as styled characters: font, size and look per character, plus widths."""

    def __init__(self, field: Any, *, multiline: bool) -> None:
        from core.forms.rich_text import STYLE_KEYS, char_styles, resolve

        text = str(getattr(field, "value", "") or "")
        if not multiline:
            text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        self.text = text
        self.cjk = fitz.Font("cjk")
        self._latin: dict[tuple, fitz.Font | None] = {}
        styles = char_styles(list(getattr(field, "runs", None) or []), text)
        self._styles = [resolve(dict(zip(STYLE_KEYS, st)), field) for st in styles]
        self.items: list[tuple[fitz.Font, float, dict]] = []
        self.widths: list[float] = []
        # Letter spacing (text boxes): extra advance after every character, in points
        self.tracking = float(getattr(field, "character_spacing", 0.0) or 0.0)

    def _font(self, ch: str, style: dict) -> fitz.Font:
        key = (style["family"], style["bold"], style["italic"])
        if key not in self._latin:
            if is_cjk_family(style["family"]):
                from core.editing import system_fonts

                self._latin[key] = system_fonts.load(*key)  # an embeddable Japanese system font, else the built-in CJK font
            else:
                self._latin[key] = _latin_font(*key)
        latin = self._latin[key]
        if ch == " " and latin is not None and not _space_safe(latin):
            return self.cjk  # spaces from a font that maps them to U+00A0 come from the built-in font
        return latin if (latin is not None and _latin_has(latin, ch)) else self.cjk

    def set_base(self, base: float) -> None:
        """Lay the characters out with ``base`` as the size of text without its own size."""
        self.items, self.widths = [], []
        for ch, style in zip(self.text, self._styles):
            size = float(style["size"] or 0) or base
            font = self._font(ch, style)
            if ch == " " and self.items and self.items[-1][1] == size and self.items[-1][0].has_glyph(32)                     and _space_safe(self.items[-1][0]):
                font = self.items[-1][0]  # a space stays with the word before it (copy / search keep it)
            look = {"bold": style["bold"], "italic": style["italic"], "color": style["color"]}
            self.items.append((font, size, look))
            self.widths.append(font.text_length(ch, fontsize=size) + self.tracking if ch not in "\r\n" else 0.0)
        self.base = base

    def width(self, a: int, b: int) -> float:
        while b > a and self.text[b - 1] in " \t":
            b -= 1
        return sum(self.widths[a:b])

    def line_size(self, a: int, b: int) -> float:
        return max((self.items[k][1] for k in range(a, b)), default=self.base)

    def block_height(self, lines: list[tuple[int, int, bool]]) -> float:
        return sum(self.line_size(a, b) * 1.15 for a, b, _e in lines)

    def wrap(self, max_w: float) -> list[tuple[int, int, bool]]:
        """(start, end, ends paragraph) per line: breaks at spaces, between Japanese characters."""
        lines: list[tuple[int, int, bool]] = []
        text = self.text.replace("\r\n", "\n").replace("\r", "\n") if "\r" in self.text else self.text
        pos = 0
        for para in text.split("\n"):
            pa, pb = pos, pos + len(para)
            pos = pb + 1
            toks = [(pa + m.start(), pa + m.end()) for m in _TOKEN.finditer(para)]
            ls = le = None
            wrapped = False
            for s, e in toks:
                if ls is None:
                    if wrapped and self.text[s].isspace():
                        continue
                    ls, le = s, e
                    continue
                if self.width(ls, e) > max_w and self.width(ls, le) > 0:
                    lines.append((ls, _rstrip(self.text, ls, le), False))
                    wrapped = True
                    if self.text[s].isspace():
                        ls = None
                        continue
                    ls, le = s, e
                else:
                    le = e
            if ls is None:
                lines.append((pb, pb, True))
            else:
                lines.append((ls, _rstrip(self.text, ls, le), True))
        return lines


_TOKEN = re.compile(r"[\u3000-\u9fff\uf900-\uffef]|\s+|[^\s\u3000-\u9fff\uf900-\uffef]+")


def _rstrip(text: str, a: int, b: int) -> int:
    while b > a and text[b - 1] in " \t":
        b -= 1
    return b


def _set_base_size(layout: _Layout, field: Any, w: float, h: float, pad: float, multiline: bool,
                   line_factor: float) -> None:
    """The field's size, or for Auto (0) the size Acrobat would pick: fill the height and
    shrink until the entry fits (down to 4 pt)."""
    avail_w = max(1.0, w - 2 * pad)
    base = float(getattr(field, "font_size", 0) or 0)
    if base <= 0:
        base = min(12.0, max(4.0, (h - 2 * pad) * 0.72)) if multiline else max(4.0, min(h * 0.72, h - 2 * pad, 24.0))
        while base > 4:
            layout.set_base(base)
            if multiline:
                if layout.block_height(layout.wrap(avail_w)) * line_factor / 1.15 <= h - 2 * pad:
                    break
            elif layout.width(0, len(layout.text)) <= avail_w:
                break
            base -= 0.5
    layout.set_base(base)


def _line_fits(top: float, size: float, h: float, pad: float) -> bool:
    """A wrapped line is drawn only when it fits inside the box: no half-cut glyphs at the edge."""
    return top + size * 1.12 <= h - pad / 2 + 0.5


_OVERFLOW_CACHE: dict = {}


def entry_overflows(field: Any, text: str | None = None, *, line_factor: float = 1.15) -> bool:
    """True when part of the entry cannot be shown in the field's box at its font size, so it
    would be hidden on screen, in the saved PDF and on paper (same layout as ``draw_text``)."""
    content = str(getattr(field, "value", "") or "") if text is None else text
    rect = getattr(field, "rect", None)
    if not content or rect is None:
        return False
    w, h = float(rect.w), float(rect.h)
    if w < 2 or h < 2:
        return False
    multiline = bool(getattr(field, "multiline", False))
    key = (content, w, h, multiline, getattr(field, "font_family", ""), float(getattr(field, "font_size", 0) or 0),
           bool(getattr(field, "bold", False)), bool(getattr(field, "italic", False)),
           repr(getattr(field, "runs", None)), float(getattr(field, "border_width", 0) or 0))
    if key in _OVERFLOW_CACHE:
        return _OVERFLOW_CACHE[key]
    pad = 2.0 + (float(getattr(field, "border_width", 0) or 0) if getattr(field, "border_color", "") else 0.0)
    avail_w = max(1.0, w - 2 * pad)
    try:
        probe = copy.copy(field)
        probe.value = content
        if getattr(probe, "runs", None) and "".join(r.get("text", "") for r in probe.runs) != content:
            probe.runs = []
        layout = _Layout(probe, multiline=multiline)
        _set_base_size(layout, probe, w, h, pad, multiline, line_factor)
        if multiline:
            lines = layout.wrap(avail_w)
            top, result = pad, False
            for a, b, _e in lines:
                size = layout.line_size(a, b)
                if not _line_fits(top, size, h, pad):
                    result = True
                    break
                top += size * line_factor
        else:
            result = layout.width(0, len(layout.text)) > avail_w + 0.5
    except Exception:  # noqa: BLE001
        result = False
    if len(_OVERFLOW_CACHE) > 512:
        _OVERFLOW_CACHE.clear()
    _OVERFLOW_CACHE[key] = result
    return result


def draw_text(
    page: fitz.Page,
    box: fitz.Rect,
    field: Any,
    *,
    pad: float,
    multiline: bool,
    line_factor: float = 1.15,
    underline: bool = False,
    wrap: bool = True,
    opacity: float = 1.0,
) -> None:
    """Draw an entry (field value or text-box text) inside ``box`` on ``page``.

    Per character: Latin uses the base-14 variant for the family and bold / italic, everything
    else (Japanese, full-width …) the embedded CJK font; mixed formats (``field.runs``), wrap,
    left / centre / right / justify and top / middle / bottom.
    """
    w, h = float(box.width), float(box.height)
    ox, oy = float(box.x0), float(box.y0)
    avail_w = max(1.0, w - 2 * pad)
    layout = _Layout(field, multiline=multiline)
    _set_base_size(layout, field, w, h, pad, multiline, line_factor)
    # multiline + no wrap: only the entry's own line breaks start a new line
    lines = layout.wrap(avail_w if wrap else 1e9) if multiline else [(0, len(layout.text), True)]

    align = str(getattr(field, "align", "left") or "left")
    from core.forms.fields import effective_valign

    valign = effective_valign(field)
    heights = [layout.line_size(a, b) * line_factor for a, b, _e in lines]
    if multiline:
        block_h = sum(heights)
        top = {"top": pad, "middle": (h - block_h) / 2, "bottom": h - pad - block_h}[valign]
        top = max(pad, top) if block_h <= h - 2 * pad else pad

    # Text goes out in reading order (one writer per stretch of the same look) so copy and
    # search give the words in order. "bold" = Japanese without a bold face (fill + outline),
    # "italic" = Japanese slanted; Latin uses the real bold / italic variants.
    segments: list[tuple[tuple, fitz.TextWriter, tuple | None]] = []
    underlines: list[tuple[float, float, float, float, str]] = []

    def emit(text: str, font: fitz.Font, size: float, style: dict, x: float, y: float) -> None:
        cjk_font = font is layout.cjk
        slant = cjk_font and style["italic"]  # Japanese has no italic face: slant it
        key = (bool(cjk_font and style["bold"]), style["color"])  # no bold face: fill + outline
        morph = (fitz.Point(ox + x, oy + y), fitz.Matrix(1, 0, _ITALIC_SKEW, 1, 0, 0)) if slant else None
        if morph is None and segments and segments[-1][0] == key and segments[-1][2] is None:
            tw = segments[-1][1]
        else:
            tw = fitz.TextWriter(page.rect)
            segments.append((key, tw, morph))
        tw.append((ox + x, oy + y), text, font=font, fontsize=size)
        if underline:
            underlines.append((ox + x, oy + y + size * 0.12, font.text_length(text, fontsize=size), size, style["color"]))

    line_top = top if multiline else 0.0
    for index, ((a, b, para_end), lh) in enumerate(zip(lines, heights)):
        size_max = lh / line_factor
        lw = layout.width(a, b)
        if multiline:
            if index and not _line_fits(line_top, size_max, h, pad):
                break  # the rest does not fit the box; never print half-cut lines
            y = line_top + size_max * 0.92
            line_top += lh
        elif valign == "top":
            y = pad + size_max * 0.92
        elif valign == "bottom":
            y = h - pad - size_max * 0.22
        else:
            y = (h + size_max * 0.70) / 2  # optical vertical centre (cap height ~0.7 em)
        x = pad if align in ("left", "justify") else (w - pad - lw if align == "right" else (w - lw) / 2)
        extra, spaced = 0.0, False
        if align == "justify" and multiline and not para_end and lw < avail_w and b - a > 1:
            # Justify: widen the spaces (Latin) or the gaps between characters (Japanese); a
            # paragraph's last line stays left, as in Word.
            spaces = sum(1 for k in range(a, b) if layout.text[k] == " ")
            spaced = spaces > 0
            gaps = spaces if spaced else (b - a - 1)
            extra = (avail_w - lw) / gaps if gaps > 0 else 0.0
        k = a
        while k < b:
            font, size, style = layout.items[k]
            j = k + 1
            if not extra and not layout.tracking:  # group characters that look the same
                while j < b and layout.items[j][0] is font and layout.items[j][1] == size and layout.items[j][2] == style:
                    j += 1
            chunk = layout.text[k:j]
            emit(chunk, font, size, style, x, y)
            x += sum(layout.widths[k:j])
            if layout.tracking and underline:
                underlines[-1] = (*underlines[-1][:2], layout.widths[k], *underlines[-1][3:])
            if extra and ((layout.text[k] == " ") if spaced else (k < b - 1)):
                x += extra
            k = j
    for (fake_bold, color), tw, morph in segments:
        if tw.text_rect is None or tw.text_rect.is_empty:
            continue
        tw.write_text(page, color=_hex_rgb(color), morph=morph, render_mode=2 if fake_bold else 0,
                      opacity=-1 if opacity >= 0.999 else max(0.0, opacity))
    for x, y, length, size, color in underlines:
        page.draw_line(fitz.Point(x, y), fitz.Point(x + length, y), color=_hex_rgb(color), width=max(0.5, size * 0.06),
                       stroke_opacity=1.0 if opacity >= 0.999 else max(0.0, opacity))


def write_text_appearance(doc: fitz.Document, widget: Any, field: Any) -> bool:
    """Replace the widget's normal appearance with one drawn by us. Returns True on success."""
    xref = int(getattr(widget, "xref", 0) or 0)
    if not xref:
        return False
    kind, ap = doc.xref_get_key(xref, "AP/N")
    if kind != "xref":
        return False
    ap_xref = int(ap.split()[0])
    rect = widget.rect
    rotation = _widget_rotation(doc, xref)
    w, h = float(rect.width), float(rect.height)
    if rotation in (90, 270):  # text runs along the other side of the box
        w, h = h, w
    if w < 2 or h < 2:
        return False
    flags = int(getattr(widget, "field_flags", 0) or 0)
    if flags & (1 << 24):  # comb fields: leave to MuPDF
        return False

    multiline = bool(getattr(field, "multiline", False))
    bw = 0.0
    try:
        if getattr(widget, "border_color", None):
            bw = float(getattr(widget, "border_width", 0) or 0)
    except (TypeError, ValueError):
        bw = 0.0
    pad = 2.0 + bw

    scratch = fitz.open()
    pages_before = doc.page_count
    try:
        page = scratch.new_page(width=w, height=h)
        draw_text(page, fitz.Rect(0, 0, w, h), field, pad=pad, multiline=multiline)
        scratch.subset_fonts()

        # The appearance is drawn on a temporary page appended to the user's document (so fonts and
        # resources land in this file); it must be removed again even if a later step fails, or the
        # saved PDF would gain an extra page (the caller keeps saving after an exception).
        doc.insert_pdf(scratch)
        temp_index = doc.page_count - 1
        temp = doc[temp_index]
        body = b"".join(doc.xref_stream(x) or b"" for x in temp.get_contents())
        res_kind, res = doc.xref_get_key(temp.xref, "Resources")
        if res_kind == "xref":
            res = doc.xref_object(int(res.split()[0]), compressed=True)

        old = doc.xref_stream(ap_xref) or b""
        background = old.split(b"/Tx BMC", 1)[0] if b"/Tx BMC" in old else b""
        if not background.strip():  # MuPDF draws the box inside /Tx BMC — draw it ourselves
            background = _border_and_background(widget, w, h)
        clip = f"q {pad / 2:.2f} {pad / 2:.2f} {w - pad:.2f} {h - pad:.2f} re W n\n".encode()
        matrix = _ROTATION_MATRIX.get(rotation, "null")
        doc.update_stream(ap_xref, background + b"/Tx BMC\n" + clip + body + b"\nQ\nEMC\n")
        doc.xref_set_key(ap_xref, "Resources", res)
        doc.xref_set_key(ap_xref, "BBox", f"[0 0 {w:.4f} {h:.4f}]")
        doc.xref_set_key(ap_xref, "Matrix", matrix)
    finally:
        while doc.page_count > pages_before:
            doc.delete_page(doc.page_count - 1)
        scratch.close()
    return True
