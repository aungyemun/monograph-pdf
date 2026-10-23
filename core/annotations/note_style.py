"""A clean, readable look for sticky notes (PDF /Text annotations).

MuPDF's built-in note icons are a hard square with a thick black frame whatever the colour. This
writes the note's own appearance instead — a rounded speech bubble with a soft fill, a thin border in
a darker shade of the same colour and faint text lines — into the PDF, so other PDF apps show the
same note. The note keeps its type, colour (/C), text, author and pop-up; only its picture changes.
"""

from __future__ import annotations

from core.document import PdfDocument

DEFAULT_NOTE_COLOR = "#ffd966"  # soft yellow: reads as a note without shouting


def _shade(rgb, k: float) -> tuple[float, float, float]:
    return tuple(max(0.0, min(1.0, c * k)) for c in rgb)


def _bubble(w: float, h: float, fill, border, ink) -> bytes:
    """Rounded speech bubble filling a w × h box (PDF units, origin bottom-left)."""
    r = min(w, h) * 0.2
    x0, y0, x1, y1 = 0.9, h * 0.24, w - 0.9, h - 0.9  # body; the tail hangs below
    k = 0.5523 * r
    path = [
        f"{x0 + r:.2f} {y1:.2f} m",
        f"{x1 - r:.2f} {y1:.2f} l",
        f"{x1 - r + k:.2f} {y1:.2f} {x1:.2f} {y1 - r + k:.2f} {x1:.2f} {y1 - r:.2f} c",
        f"{x1:.2f} {y0 + r:.2f} l",
        f"{x1:.2f} {y0 + r - k:.2f} {x1 - r + k:.2f} {y0:.2f} {x1 - r:.2f} {y0:.2f} c",
        f"{w * 0.46:.2f} {y0:.2f} l",
        f"{w * 0.22:.2f} 0.9 l",  # tail tip
        f"{w * 0.30:.2f} {y0:.2f} l",
        f"{x0 + r:.2f} {y0:.2f} l",
        f"{x0 + r - k:.2f} {y0:.2f} {x0:.2f} {y0 + r - k:.2f} {x0:.2f} {y0 + r:.2f} c",
        f"{x0:.2f} {y1 - r:.2f} l",
        f"{x0:.2f} {y1 - r + k:.2f} {x0 + r - k:.2f} {y1:.2f} {x0 + r:.2f} {y1:.2f} c",
        "h",
    ]
    lines = []
    body_h = y1 - y0
    for i, frac in enumerate((0.72, 0.5, 0.28)):
        y = y0 + body_h * frac
        right = x1 - w * (0.22 if i == 2 else 0.16)
        lines.append(f"{x0 + w * 0.16:.2f} {y:.2f} m {right:.2f} {y:.2f} l")
    ops = [
        "q",
        "{:.3f} {:.3f} {:.3f} rg".format(*fill),
        "{:.3f} {:.3f} {:.3f} RG".format(*border),
        "0.8 w 1 j",
        *path,
        "B",
        "{:.3f} {:.3f} {:.3f} RG".format(*ink),
        "0.8 w 1 J",
        *lines,
        "S",
        "Q",
    ]
    return ("\n".join(ops) + "\n").encode("ascii")


# Note icons offered in Monograph PDF: (PDF /Name, label). The names are the standard ones (ISO 32000
# and Acrobat), so another PDF app that redraws the note picks a similar icon; the appearance written
# here is what every app shows.
NOTE_ICONS: list[tuple[str, str]] = [
    ("Comment", "Speech bubble"),
    ("Note", "Note page"),
    ("Help", "Question"),
    ("Insert", "Insert text"),
    ("Key", "Key point"),
    ("Paragraph", "Paragraph"),
    ("Check", "Check mark"),
    ("Star", "Star"),
]
NOTE_ICON_NAMES = {name for name, _ in NOTE_ICONS}

# Ready-made note colours: soft, readable, distinct from highlight yellow-green
NOTE_COLORS: list[tuple[str, str]] = [
    ("Yellow", "#fbbf24"), ("Soft yellow", "#ffd966"), ("Orange", "#fb923c"), ("Red", "#f87171"),
    ("Pink", "#f472b6"), ("Purple", "#a78bfa"), ("Blue", "#60a5fa"), ("Teal", "#2dd4bf"),
    ("Green", "#4ade80"), ("Gray", "#9ca3af"),
]


def _rounded_rect(x0: float, y0: float, x1: float, y1: float, r: float) -> list[str]:
    k = 0.5523 * r
    return [
        f"{x0 + r:.2f} {y1:.2f} m", f"{x1 - r:.2f} {y1:.2f} l",
        f"{x1 - r + k:.2f} {y1:.2f} {x1:.2f} {y1 - r + k:.2f} {x1:.2f} {y1 - r:.2f} c",
        f"{x1:.2f} {y0 + r:.2f} l",
        f"{x1:.2f} {y0 + r - k:.2f} {x1 - r + k:.2f} {y0:.2f} {x1 - r:.2f} {y0:.2f} c",
        f"{x0 + r:.2f} {y0:.2f} l",
        f"{x0 + r - k:.2f} {y0:.2f} {x0:.2f} {y0 + r - k:.2f} {x0:.2f} {y0 + r:.2f} c",
        f"{x0:.2f} {y1 - r:.2f} l",
        f"{x0:.2f} {y1 - r + k:.2f} {x0 + r - k:.2f} {y1:.2f} {x0 + r:.2f} {y1:.2f} c", "h",
    ]


def _circle(cx: float, cy: float, r: float) -> list[str]:
    k = 0.5523 * r
    return [
        f"{cx + r:.2f} {cy:.2f} m",
        f"{cx + r:.2f} {cy + k:.2f} {cx + k:.2f} {cy + r:.2f} {cx:.2f} {cy + r:.2f} c",
        f"{cx - k:.2f} {cy + r:.2f} {cx - r:.2f} {cy + k:.2f} {cx - r:.2f} {cy:.2f} c",
        f"{cx - r:.2f} {cy - k:.2f} {cx - k:.2f} {cy - r:.2f} {cx:.2f} {cy - r:.2f} c",
        f"{cx + k:.2f} {cy - r:.2f} {cx + r:.2f} {cy - k:.2f} {cx + r:.2f} {cy:.2f} c", "h",
    ]


def _wrap(fill, border, ink, body: list[str], marks: list[str], *, mark_width: float = 0.8,
          fill_marks: bool = False) -> bytes:
    ops = ["q", "{:.3f} {:.3f} {:.3f} rg".format(*fill), "{:.3f} {:.3f} {:.3f} RG".format(*border),
           "0.8 w 1 j 1 J", *body, "B"]
    if marks:
        ops += ["{:.3f} {:.3f} {:.3f} RG".format(*ink), "{:.3f} {:.3f} {:.3f} rg".format(*ink),
                f"{mark_width} w", *marks, "f" if fill_marks else "S"]
    ops.append("Q")
    return ("\n".join(ops) + "\n").encode("ascii")


def _icon_stream(name: str, w: float, h: float, fill, border, ink) -> bytes:
    """Appearance of a note icon *name* filling a w × h box (unknown names: the speech bubble)."""
    m = 0.9
    if name == "Note":  # a page with a folded corner and text lines
        f = min(w, h) * 0.3
        body = [f"{m:.2f} {m:.2f} m", f"{m:.2f} {h - m:.2f} l", f"{w - m - f:.2f} {h - m:.2f} l",
                f"{w - m:.2f} {h - m - f:.2f} l", f"{w - m:.2f} {m:.2f} l", "h"]
        marks = [f"{w - m - f:.2f} {h - m:.2f} m {w - m - f:.2f} {h - m - f:.2f} l {w - m:.2f} {h - m - f:.2f} l"]
        for frac in (0.62, 0.44, 0.26):
            marks.append(f"{w * 0.2:.2f} {h * frac:.2f} m {w * 0.8:.2f} {h * frac:.2f} l")
        return _wrap(fill, border, ink, body, marks)
    if name in ("Help", "Check", "Star", "Key", "Insert", "Paragraph"):
        r = min(w, h) / 2 - m
        cx, cy = w / 2, h / 2
        body = _circle(cx, cy, r) if name in ("Help", "Check") else _rounded_rect(m, m, w - m, h - m, min(w, h) * 0.2)
        if name == "Help":  # question mark
            s = r / 7
            marks = [f"{cx - 2.2 * s:.2f} {cy + 2.0 * s:.2f} m",
                     f"{cx - 2.2 * s:.2f} {cy + 4.6 * s:.2f} {cx + 2.6 * s:.2f} {cy + 4.8 * s:.2f} {cx + 2.6 * s:.2f} {cy + 2.0 * s:.2f} c",
                     f"{cx + 2.6 * s:.2f} {cy + 0.2 * s:.2f} {cx:.2f} {cy - 0.2 * s:.2f} {cx:.2f} {cy - 1.8 * s:.2f} c",
                     f"{cx:.2f} {cy - 3.6 * s:.2f} m {cx:.2f} {cy - 4.2 * s:.2f} l"]
            return _wrap(fill, border, ink, body, marks, mark_width=max(1.0, r / 5))
        if name == "Check":
            marks = [f"{cx - r * 0.5:.2f} {cy:.2f} m {cx - r * 0.12:.2f} {cy - r * 0.4:.2f} l "
                     f"{cx + r * 0.55:.2f} {cy + r * 0.45:.2f} l"]
            return _wrap(fill, border, ink, body, marks, mark_width=max(1.2, r / 4.5))
        if name == "Star":  # five-pointed star inside the rounded square
            import math

            ro, ri = min(w, h) * 0.36, min(w, h) * 0.15
            pts = []
            for i in range(10):
                a = math.pi / 2 + i * math.pi / 5
                rr = ro if i % 2 == 0 else ri
                pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
            marks = [f"{pts[0][0]:.2f} {pts[0][1]:.2f} m"] + [f"{x:.2f} {y:.2f} l" for x, y in pts[1:]] + ["h"]
            return _wrap(fill, border, ink, body, marks, fill_marks=True)
        if name == "Key":  # a key: ring and bit
            kr = min(w, h) * 0.17
            kx, ky = w * 0.32, h * 0.62
            marks = _circle(kx, ky, kr)[:-1] + ["h",
                f"{kx + kr * 0.7:.2f} {ky - kr * 0.7:.2f} m {w * 0.76:.2f} {h * 0.2:.2f} l",
                f"{w * 0.62:.2f} {h * 0.34:.2f} m {w * 0.7:.2f} {h * 0.42:.2f} l",
                f"{w * 0.7:.2f} {h * 0.26:.2f} m {w * 0.78:.2f} {h * 0.34:.2f} l"]
            return _wrap(fill, border, ink, body, marks, mark_width=max(1.0, min(w, h) / 12))
        if name == "Insert":  # caret ^
            marks = [f"{w * 0.25:.2f} {h * 0.28:.2f} m {w * 0.5:.2f} {h * 0.74:.2f} l {w * 0.75:.2f} {h * 0.28:.2f} l"]
            return _wrap(fill, border, ink, body, marks, mark_width=max(1.2, min(w, h) / 10))
        # Paragraph mark ¶
        top, bot = h * 0.78, h * 0.2
        marks = [f"{w * 0.52:.2f} {top:.2f} m {w * 0.52:.2f} {bot:.2f} l",
                 f"{w * 0.66:.2f} {top:.2f} m {w * 0.66:.2f} {bot:.2f} l",
                 f"{w * 0.72:.2f} {top:.2f} m {w * 0.4:.2f} {top:.2f} l",
                 f"{w * 0.4:.2f} {top:.2f} m {w * 0.24:.2f} {top:.2f} {w * 0.24:.2f} {h * 0.5:.2f} {w * 0.4:.2f} {h * 0.5:.2f} c "
                 f"{w * 0.52:.2f} {h * 0.5:.2f} l"]
        return _wrap(fill, border, ink, body, marks, mark_width=max(1.0, min(w, h) / 12))
    return _bubble(w, h, fill=fill, border=border, ink=ink)


def note_icon_name(document: PdfDocument, xref: int) -> str:
    """The note's icon (/Name); "Comment" when missing."""
    doc = document._backend._doc  # noqa: SLF001
    kind, value = doc.xref_get_key(int(xref), "Name")
    return value.lstrip("/") if kind == "name" else "Comment"


def set_note_style(document: PdfDocument, page_index: int, xref: int, *,
                   color: tuple[float, float, float] | None = None, icon: str | None = None) -> bool:
    """Change a sticky note's colour and/or icon and redraw it. False when it is not a sticky note."""
    doc = document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    annot = next((a for a in page.annots() or [] if int(a.xref) == int(xref)), None)
    if annot is None or annot.type[1] != "Text":
        return False
    if icon is not None:
        doc.xref_set_key(int(xref), "Name", f"/{icon if icon in NOTE_ICON_NAMES else 'Comment'}")
    if color is not None:
        doc.xref_set_key(int(xref), "C", "[{:.4f} {:.4f} {:.4f}]".format(*color))
    return style_sticky_note(document, page_index, xref)


def style_sticky_note(document: PdfDocument, page_index: int, xref: int) -> bool:
    """Give the sticky note ``xref`` the clean look; False when it is not a sticky note."""
    doc = document._backend._doc  # noqa: SLF001
    page = doc.load_page(page_index)
    annot = next((a for a in page.annots() or [] if int(a.xref) == int(xref)), None)
    if annot is None or annot.type[1] != "Text":
        return False
    kind, value = doc.xref_get_key(int(xref), "AP/N")
    if kind != "xref":
        annot.update()
        kind, value = doc.xref_get_key(int(xref), "AP/N")
        if kind != "xref":
            return False
    ap = int(value.split()[0])
    bbox = doc.xref_get_key(ap, "BBox")[1].strip("[] ").split()
    try:
        bx0, by0, bx1, by1 = (float(v) for v in bbox)
    except ValueError:
        bx0, by0, bx1, by1 = 0.0, 0.0, 16.0, 16.0
    w, h = bx1 - bx0, by1 - by0
    rgb = tuple(float(c) for c in ((annot.colors or {}).get("stroke") or (1.0, 0.85, 0.4))[:3])
    kind_n, name = doc.xref_get_key(int(xref), "Name")
    icon = name.lstrip("/") if kind_n == "name" else "Comment"
    stream = _icon_stream(icon, w, h, fill=rgb, border=_shade(rgb, 0.55), ink=_shade(rgb, 0.45))
    if bx0 or by0:
        stream = f"1 0 0 1 {bx0:.2f} {by0:.2f} cm\n".encode("ascii") + stream
    doc.update_stream(ap, stream)
    document.invalidate_pages()
    return True
