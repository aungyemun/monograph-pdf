"""Page box helpers and nominal paper-size labeling (PDF points remain authoritative)."""

from __future__ import annotations

from dataclasses import dataclass

# 1 PDF point = 1/72 inch
_PT_PER_IN = 72.0
_PT_PER_MM = _PT_PER_IN / 25.4

# (name, width_pt, height_pt) portrait; landscape matched by swap
_STANDARDS: list[tuple[str, float, float, str]] = [
    ("A0", 2383.94, 3370.39, "mm"),
    ("A1", 1683.78, 2383.94, "mm"),
    ("A2", 1190.55, 1683.78, "mm"),
    ("A3", 841.89, 1190.55, "mm"),
    ("A4", 595.28, 841.89, "mm"),
    ("A5", 419.53, 595.28, "mm"),
    ("A6", 297.64, 419.53, "mm"),
    ("Letter", 612.0, 792.0, "in"),
    ("Legal", 612.0, 1008.0, "in"),
    ("Tabloid", 792.0, 1224.0, "in"),
    ("Ledger", 1224.0, 792.0, "in"),
    ("Executive", 522.0, 756.0, "in"),
]


@dataclass(frozen=True)
class PaperLabel:
    name: str  # e.g. A4, Letter, Custom
    width_pt: float
    height_pt: float
    orientation: str  # portrait | landscape
    display: str  # "A4 — 210 × 297 mm"
    matched: bool


def _fmt_mm(w_pt: float, h_pt: float) -> str:
    return f"{w_pt / _PT_PER_MM:.0f} × {h_pt / _PT_PER_MM:.0f} mm"


def _fmt_in(w_pt: float, h_pt: float) -> str:
    return f"{w_pt / _PT_PER_IN:.2f} × {h_pt / _PT_PER_IN:.2f} in"


def label_page_size(width_pt: float, height_pt: float, *, tolerance_pt: float = 3.0) -> PaperLabel:
    """Match MediaBox/display size to a nominal standard within tolerance."""
    w, h = float(width_pt), float(height_pt)
    orientation = "landscape" if w > h else "portrait"
    for name, sw, sh, unit in _STANDARDS:
        if (abs(w - sw) <= tolerance_pt and abs(h - sh) <= tolerance_pt) or (
            abs(w - sh) <= tolerance_pt and abs(h - sw) <= tolerance_pt
        ):
            # Prefer portrait dimensions in the label text
            pw, ph = (sw, sh) if sw <= sh else (sh, sw)
            if orientation == "landscape":
                pw, ph = ph, pw
            dim = _fmt_mm(pw, ph) if unit == "mm" else _fmt_in(pw, ph)
            return PaperLabel(
                name=name,
                width_pt=w,
                height_pt=h,
                orientation=orientation,
                display=f"{name} — {dim}",
                matched=True,
            )
    return PaperLabel(
        name="Custom",
        width_pt=w,
        height_pt=h,
        orientation=orientation,
        display=f"Custom — {_fmt_mm(w, h)} ({_fmt_in(w, h)})",
        matched=False,
    )
