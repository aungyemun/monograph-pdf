"""Mixed formatting inside one form field ("rich text" fields, PDF 1.5 /RV).

A field's text can carry *runs*: stretches of text with their own font, size, bold, italic and
colour. A run property of ``None`` means "use the field's own setting", so changing the whole
field still reaches every run that was not given its own value. ``"".join(run text)`` always
equals the field's plain value (/V).

Saved as: /V plain text (what every reader understands), /RV XHTML rich value with the
RichText field flag (what Acrobat reads back), and an appearance drawn by
``core.forms.appearance`` (what every reader shows).
"""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from typing import Any

STYLE_KEYS = ("family", "size", "bold", "italic", "color")
RICH_TEXT_FLAG = 1 << 25  # PDF text field flag bit 26: RichText


def make_run(text: str, **style: Any) -> dict:
    run = {"text": text}
    for key in STYLE_KEYS:
        run[key] = style.get(key)
    return run


def _style(run: dict) -> tuple:
    return tuple(run.get(k) for k in STYLE_KEYS)


def normalize_runs(runs: list[dict] | None) -> list[dict]:
    """Merge neighbours with the same style and drop empty runs; [] when nothing is styled."""
    out: list[dict] = []
    for run in runs or []:
        text = str(run.get("text") or "")
        if not text:
            continue
        clean = make_run(text, **{k: run.get(k) for k in STYLE_KEYS})
        if out and _style(out[-1]) == _style(clean):
            out[-1]["text"] += text
        else:
            out.append(clean)
    if all(all(r[k] is None for k in STYLE_KEYS) for r in out):
        return []
    return out


def char_styles(runs: list[dict], text: str) -> list[tuple]:
    """One style tuple per character of ``text`` (all-None when there are no runs)."""
    styles: list[tuple] = []
    for run in runs or []:
        styles.extend([_style(run)] * len(run.get("text") or ""))
    if len(styles) != len(text):
        return [(None,) * len(STYLE_KEYS)] * len(text)
    return styles


def runs_from_char_styles(text: str, styles: list[tuple]) -> list[dict]:
    runs = [make_run(ch, **dict(zip(STYLE_KEYS, st))) for ch, st in zip(text, styles)]
    return normalize_runs(runs)


def reconcile_runs(runs: list[dict], old_text: str, new_text: str) -> list[dict]:
    """Keep the formatting when the text is edited as plain text (Properties box, case change).

    Unchanged start and end keep their styles; new characters take the style of the character
    before them. Same-length edits (UPPER/lower) keep every character's style.
    """
    if not runs or old_text == new_text:
        return normalize_runs(runs) if runs else []
    old = char_styles(runs, old_text)
    if len(old_text) == len(new_text):
        return runs_from_char_styles(new_text, old)
    p = 0
    while p < min(len(old_text), len(new_text)) and old_text[p] == new_text[p]:
        p += 1
    s = 0
    while (
        s < min(len(old_text), len(new_text)) - p
        and old_text[len(old_text) - 1 - s] == new_text[len(new_text) - 1 - s]
    ):
        s += 1
    middle_len = len(new_text) - p - s
    if old:
        fill = old[p - 1] if p > 0 else old[min(p, len(old) - 1)]
    else:
        fill = (None,) * len(STYLE_KEYS)
    styles = old[:p] + [fill] * middle_len + (old[len(old) - s:] if s else [])
    return runs_from_char_styles(new_text, styles)


def apply_to_all(runs: list[dict], **change: Any) -> list[dict]:
    """A whole-field change: the property follows the field again in every run.

    ``size_delta`` instead grows / shrinks every run that has its own size (A+ / A−), keeping
    the differences between them.
    """
    out = []
    delta = change.pop("size_delta", None)
    for run in runs or []:
        r = dict(run)
        for key in change:
            if key in STYLE_KEYS:
                r[key] = None
        if delta is not None and r.get("size") is not None:
            r["size"] = max(4.0, min(200.0, float(r["size"]) + delta))
        out.append(r)
    return normalize_runs(out)


def resolve(run: dict, field: Any) -> dict:
    """A run's effective style: its own values, else the field's."""
    return {
        "family": run.get("family") or str(getattr(field, "font_family", "") or "Helvetica"),
        "size": float(run.get("size") or 0) or float(getattr(field, "font_size", 0) or 0),
        "bold": bool(getattr(field, "bold", False)) if run.get("bold") is None else bool(run["bold"]),
        "italic": bool(getattr(field, "italic", False)) if run.get("italic") is None else bool(run["italic"]),
        "color": run.get("color") or str(getattr(field, "text_color", "") or "#000000"),
    }


# --- /RV (XHTML rich value) ------------------------------------------------------------------


def _css(style: dict) -> str:
    fam = str(style["family"]).replace('"', "'")
    parts = [f"font-family:{fam}"]
    if style["size"]:
        parts.append(f"font-size:{style['size']:g}pt")
    parts.append(f"font-weight:{'bold' if style['bold'] else 'normal'}")
    parts.append(f"font-style:{'italic' if style['italic'] else 'normal'}")
    parts.append(f"color:{style['color']}")
    return ";".join(parts)


def to_xhtml(field: Any) -> str:
    """The /RV rich value Acrobat writes for formatted text fields."""
    align = {"center": "center", "right": "right", "justify": "justify"}.get(str(getattr(field, "align", "")), "left")
    runs = getattr(field, "runs", None) or [make_run(str(getattr(field, "value", "") or ""))]
    paragraphs: list[list[str]] = [[]]
    for run in runs:
        css = _css(resolve(run, field))
        pieces = str(run["text"]).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for i, piece in enumerate(pieces):
            if i:
                paragraphs.append([])
            if piece:
                paragraphs[-1].append(f'<span style="{escape(css)}">{escape(piece, quote=False)}</span>')
    body = "".join(f'<p dir="ltr" style="text-align:{align}">{"".join(p)}</p>' for p in paragraphs)
    return (
        '<?xml version="1.0"?><body xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/" xfa:APIVersion="Acroform:2.7.0.0" '
        f'xfa:spec="2.1">{body}</body>'
    )


def default_style(field: Any) -> str:
    """/DS — the field's default style string."""
    return _css(resolve({}, field)).replace("font-weight:normal;", "").replace("font-style:normal;", "")


def _parse_css(text: str) -> dict:
    out: dict = {}
    for decl in (text or "").split(";"):
        if ":" not in decl:
            continue
        key, val = (s.strip() for s in decl.split(":", 1))
        key = key.lower()
        if key == "font-family":
            out["family"] = val.split(",")[0].strip().strip("'\"") or None
        elif key == "font-size":
            m = re.match(r"([\d.]+)\s*(pt|px)?", val)
            if m:
                size = float(m.group(1)) * (0.75 if m.group(2) == "px" else 1.0)
                out["size"] = size if size > 0 else None
        elif key == "font-weight":
            out["bold"] = val.lower() in ("bold", "bolder") or (val.isdigit() and int(val) >= 600)
        elif key == "font-style":
            out["italic"] = val.lower() in ("italic", "oblique")
        elif key == "color":
            m = re.match(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", val)
            if m:
                h = m.group(1)
                out["color"] = "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h).lower()
            else:
                m = re.match(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", val)
                if m:
                    out["color"] = "#" + "".join(f"{min(255, int(v)):02x}" for v in m.groups())
        elif key == "font":  # shorthand: [style] [weight] size[/line] family
            m = re.search(r"([\d.]+)pt\S*\s+(.+)$", val)
            if m:
                out["size"] = float(m.group(1))
                out["family"] = m.group(2).split(",")[0].strip().strip("'\"")
            low = val.lower()
            if "bold" in low:
                out["bold"] = True
            if "italic" in low:
                out["italic"] = True
    return out


class _RVParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict] = [{}]
        self.runs: list[dict] = []
        self.paragraphs = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower().split(":")[-1]
        a = {k.lower(): (v or "") for k, v in attrs}
        style = dict(self.stack[-1])
        if tag == "b" or tag == "strong":
            style["bold"] = True
        if tag == "i" or tag == "em":
            style["italic"] = True
        if tag == "font":
            if a.get("face"):
                style["family"] = a["face"].split(",")[0].strip()
            if a.get("color"):
                style.update(_parse_css("color:" + a["color"]))
        style.update(_parse_css(a.get("style", "")))
        if tag == "p":
            if self.paragraphs:
                self._text("\n", style)
            self.paragraphs += 1
        if tag == "br":
            self._text("\n", style)
            return
        self.stack.append(style)

    def handle_startendtag(self, tag, attrs):
        if tag.lower().split(":")[-1] == "br":
            self._text("\n", self.stack[-1])

    def handle_endtag(self, tag):
        if tag.lower().split(":")[-1] == "br":
            return
        if len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data):
        self._text(data, self.stack[-1])

    def _text(self, text, style):
        if text:
            self.runs.append(make_run(text, **{k: style.get(k) for k in STYLE_KEYS}))


def parse_xhtml(rv: str) -> tuple[str, list[dict]]:
    """(plain text, runs) from an /RV rich value. Never raises; ([], '') on garbage."""
    try:
        rv = re.sub(r"<\?xml[^>]*\?>", "", rv or "")
        p = _RVParser()
        p.feed(rv)
        p.close()
        runs = [r for r in p.runs if r["text"]]
        text = "".join(r["text"] for r in runs)
        return text, runs
    except Exception:  # noqa: BLE001
        return "", []


def runs_for_value(rv: str, value: str, field: Any) -> list[dict]:
    """Runs from /RV when its text matches /V. Run values equal to the field's own become None."""
    text, runs = parse_xhtml(rv)
    norm = lambda s: s.replace("\r\n", "\n").replace("\r", "\n")  # noqa: E731
    if not runs or norm(text).strip() != norm(value).strip():
        return []
    if norm(text) != norm(value):  # only surrounding whitespace differs: keep text = /V
        return []
    base = resolve({}, field)
    out = []
    for run in runs:
        r = dict(run)
        for key in STYLE_KEYS:
            if r.get(key) is not None and _same(key, r[key], base[key]):
                r[key] = None
        out.append(r)
    return normalize_runs(out)


def _same(key: str, a: Any, b: Any) -> bool:
    if key == "family":
        return str(a).replace(" ", "").lower() == str(b).replace(" ", "").lower()
    if key == "size":
        return b and abs(float(a) - float(b)) < 0.05
    if key == "color":
        return str(a).lower() == str(b).lower()
    return bool(a) == bool(b)
