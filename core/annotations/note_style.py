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
    stream = _bubble(w, h, fill=rgb, border=_shade(rgb, 0.55), ink=_shade(rgb, 0.5))
    if bx0 or by0:
        stream = f"1 0 0 1 {bx0:.2f} {by0:.2f} cm\n".encode("ascii") + stream
    doc.update_stream(ap, stream)
    document.invalidate_pages()
    return True
