"""Font fallback resolver for English / Japanese / Unicode text (lazy, offline)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from pathlib import Path

from core.editing.font_inventory import (
    bundled_fonts_dir,
    glyph_coverage_missing,
    list_system_families,
    load_bundled_fonts,
    normalize_family_name,
    strip_subset_prefix,
)

# Preferred stacks (logical names → OS-typical faces). Exact availability varies.
_LATIN_STACK = ("Segoe UI", "Arial", "Helvetica", "Noto Sans", "DejaVu Sans", "sans-serif")
_JP_STACK = (
    "Yu Gothic UI",
    "Yu Gothic",
    "Meiryo",
    "MS Gothic",
    "MS PGothic",
    "Noto Sans CJK JP",
    "Noto Sans JP",
    "Source Han Sans",
    "sans-serif",
)
_SERIF_JP_STACK = (
    "Yu Mincho",
    "MS Mincho",
    "MS PMincho",
    "Noto Serif CJK JP",
    "Noto Serif JP",
    "serif",
)
_GENERIC = {
    "sans-serif": _LATIN_STACK,
    "serif": ("Times New Roman", "Georgia", "Noto Serif", "Cambria", "serif"),
    "monospace": ("Consolas", "Courier New", "Noto Sans Mono", "monospace"),
}

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_SERIF_HINT_RE = re.compile(r"mincho|serif|times|georgia|cambria|明朝", re.I)


@dataclass(frozen=True)
class FontResolution:
    requested: str
    resolved: str
    substituted: bool
    reason: str = ""
    original_pdf_font: str = ""
    source: str = "system"  # system | bundled | generic | embedded-name


def text_needs_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _qt_app_ready() -> bool:
    try:
        from PySide6.QtWidgets import QApplication

        return QApplication.instance() is not None
    except Exception:  # noqa: BLE001
        return False


@lru_cache(maxsize=1)
def _bundled_family_map() -> dict[str, str]:
    """family.lower() → font file path for bundled OFL fonts."""
    mapping: dict[str, str] = {}
    directory = bundled_fonts_dir()
    if not directory.is_dir():
        return mapping
    try:
        for item in load_bundled_fonts(directory):
            mapping[item.family.lower()] = item.path
            mapping[Path(item.path).stem.lower().replace("-", " ")] = item.path
    except Exception:  # noqa: BLE001
        pass
    return mapping


def _available_families() -> set[str]:
    """Best-effort installed family list — lazy via font inventory cache."""
    families = list_system_families(force_refresh=False)
    if families:
        return {f.lower() for f in families}
    return set()


def _match(name: str, available: set[str]) -> str | None:
    if not name:
        return None
    low = name.lower()
    # Bundled fonts register by family name even if not in QFontDatabase yet
    bundled = _bundled_family_map()
    if low in bundled:
        return name
    if not available:
        return name
    if not _qt_app_ready():
        return name if low in available else None
    from PySide6.QtGui import QFontDatabase

    families = list(QFontDatabase.families())
    for real in families:
        if real.lower() == low:
            return real
    for real in families:
        rl = real.lower()
        if rl.startswith(low) or low.startswith(rl):
            return real
    # Match normalized forms (MS-Mincho vs MS Mincho)
    norm = normalize_family_name(name).lower()
    for real in families:
        if normalize_family_name(real).lower() == norm:
            return real
    return None


def _register_bundled_with_qt() -> None:
    """Ensure bundled TTF/OTF are visible to QFontDatabase (idempotent, lazy)."""
    if not _qt_app_ready():
        return
    try:
        from PySide6.QtGui import QFontDatabase

        for path in _bundled_family_map().values():
            try:
                QFontDatabase.addApplicationFont(path)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass


def resolve_font(requested: str, sample_text: str = "") -> FontResolution:
    """Resolve a font family with Latin/CJK-aware fallbacks; expose substitution."""
    original = (requested or "sans-serif").strip()
    # Strip subset prefix for matching only (ABCDEE+MS-Mincho → MS Mincho)
    stripped = strip_subset_prefix(original)
    family_guess = normalize_family_name(stripped) if stripped else "sans-serif"
    requested_key = family_guess or "sans-serif"

    _register_bundled_with_qt()
    available = _available_families()
    serifish = bool(_SERIF_HINT_RE.search(original) or _SERIF_HINT_RE.search(requested_key))

    stack: list[str] = []
    if requested_key in _GENERIC:
        stack.extend(_GENERIC[requested_key])
    else:
        stack.append(requested_key)
        # Also try original stripped BaseFont token
        if stripped and stripped != requested_key:
            stack.append(stripped.replace("-", " "))
        stack.extend(_GENERIC.get("serif" if serifish else "sans-serif", _LATIN_STACK))

    if text_needs_cjk(sample_text):
        jp = list(_SERIF_JP_STACK if serifish else _JP_STACK)
        stack = jp + stack

    # Prefer bundled Noto when present
    bundled = _bundled_family_map()
    for bname in ("noto sans cjk jp", "noto sans jp", "noto serif cjk jp", "noto sans", "noto serif"):
        if bname in bundled:
            stack.append(bundled_family_label(bname))

    seen: set[str] = set()
    for cand in stack:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        if cand in ("sans-serif", "serif", "monospace"):
            continue
        hit = _match(cand, available)
        if hit:
            source = "bundled" if cand.lower() in bundled or hit.lower() in bundled else "system"
            substituted = normalize_family_name(hit).lower() != normalize_family_name(requested_key).lower()
            if requested_key in _GENERIC:
                substituted = True
            reason = ""
            if substituted:
                reason = f"Exact font '{original}' unavailable; using '{hit}'."
            elif requested_key in _GENERIC:
                reason = f"Generic '{requested_key}' resolved to '{hit}'."
            return FontResolution(
                requested=original,
                resolved=hit,
                substituted=substituted,
                reason=reason,
                original_pdf_font=original if "+" in original else "",
                source=source,
            )

    fallback = "sans-serif"
    return FontResolution(
        requested=original,
        resolved=fallback,
        substituted=True,
        reason=f"Exact font '{original}' unavailable; using generic fallback.",
        original_pdf_font=original if "+" in original else "",
        source="generic",
    )


def bundled_family_label(key: str) -> str:
    # Map lower keys back to display labels
    labels = {
        "noto sans cjk jp": "Noto Sans CJK JP",
        "noto sans jp": "Noto Sans JP",
        "noto serif cjk jp": "Noto Serif CJK JP",
        "noto sans": "Noto Sans",
        "noto serif": "Noto Serif",
    }
    return labels.get(key, key)


def resolve_font_for_text(requested: str, text: str) -> FontResolution:
    """Resolve font and, if glyphs are missing, pick a covering fallback."""
    res = resolve_font(requested, text)
    missing = glyph_coverage_missing(res.resolved, text)
    if not missing:
        return res
    # Retry with CJK-aware stack
    retry = resolve_font("sans-serif", text)
    missing2 = glyph_coverage_missing(retry.resolved, text)
    if len(missing2) < len(missing):
        return FontResolution(
            requested=requested,
            resolved=retry.resolved,
            substituted=True,
            reason=(
                f"Font '{res.resolved}' missing {len(missing)} glyph(s); "
                f"using '{retry.resolved}'."
            ),
            original_pdf_font=res.original_pdf_font,
            source=retry.source,
        )
    return FontResolution(
        requested=requested,
        resolved=res.resolved,
        substituted=True,
        reason=(
            f"Font '{res.resolved}' may miss glyphs: "
            + "".join(missing[:12])
            + ("…" if len(missing) > 12 else "")
        ),
        original_pdf_font=res.original_pdf_font,
        source=res.source,
    )


def measure_text_width(text: str, family: str, size: float, bold: bool = False, italic: bool = False) -> float:
    """Approximate advance width in PDF points (Qt metrics when a QApplication exists)."""
    if not text:
        return 0.0
    if _qt_app_ready():
        try:
            from PySide6.QtGui import QFont, QFontMetricsF

            qf = QFont(family or "sans-serif")
            qf.setPointSizeF(max(1.0, size))
            qf.setBold(bold)
            qf.setItalic(italic)
            return float(QFontMetricsF(qf).horizontalAdvance(text))
        except Exception:  # noqa: BLE001
            pass
    # Headless / no Qt app: CJK ≈ full em, Latin ≈ 0.5em
    _ = family
    w = 0.0
    for ch in text:
        w += size if _CJK_RE.match(ch) else size * 0.5
    return w
