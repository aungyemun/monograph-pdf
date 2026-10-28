"""Offline font inventory — embedded, system, and bundled fallbacks (lazy)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.paths import BUNDLE_ROOT, CACHE_DIR, ROOT

_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")

# Common Windows Japanese / Latin faces the resolver may use when installed.
_WINDOWS_HINTS = (
    "MS Mincho",
    "MS PMincho",
    "MS Gothic",
    "MS PGothic",
    "Yu Mincho",
    "Yu Gothic",
    "Yu Gothic UI",
    "Meiryo",
    "Meiryo UI",
    "Arial",
    "Times New Roman",
    "Calibri",
    "Cambria",
    "Segoe UI",
    "Consolas",
    "Courier New",
)


@dataclass
class BundledFont:
    family: str
    path: str
    style: str = "Regular"
    scripts: list[str] = field(default_factory=list)
    license: str = "OFL-1.1"


@dataclass
class FontInventory:
    embedded: list[str] = field(default_factory=list)
    system_families: list[str] = field(default_factory=list)
    system_hints_present: list[str] = field(default_factory=list)
    bundled: list[BundledFont] = field(default_factory=list)
    substitutions: list[dict[str, str]] = field(default_factory=list)
    unsupported_glyph_warnings: list[str] = field(default_factory=list)
    cache_age_sec: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def strip_subset_prefix(font_name: str) -> str:
    """ABCDEE+MS-Mincho → MS-Mincho (family matching only; embedded resource kept for view)."""
    name = (font_name or "").strip().lstrip("/")
    if _SUBSET_PREFIX_RE.match(name):
        return name.split("+", 1)[1]
    return name


def normalize_family_name(font_name: str) -> str:
    """Normalize BaseFont / subset names toward a human family label."""
    base = strip_subset_prefix(font_name)
    base = base.replace("-", " ").replace("_", " ")
    # Collapse common PostScript style suffixes for matching
    for suffix in (
        " Regular",
        " Bold",
        " Italic",
        " BoldItalic",
        " Oblique",
        " Light",
        " Medium",
        " Heavy",
    ):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return re.sub(r"\s+", " ", base).strip()


def bundled_fonts_dir() -> Path:
    for candidate in (
        BUNDLE_ROOT / "resources" / "fonts",
        ROOT / "resources" / "fonts",
    ):
        if candidate.is_dir():
            return candidate
    return ROOT / "resources" / "fonts"


def load_bundled_fonts(directory: Path | None = None) -> list[BundledFont]:
    directory = directory or bundled_fonts_dir()
    return _load_bundled_manifest(directory)


def _load_bundled_manifest(directory: Path) -> list[BundledFont]:
    manifest = directory / "FONT_MANIFEST.json"
    out: list[BundledFont] = []
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for item in data.get("fonts") or []:
                rel = str(item.get("file") or "")
                path = directory / rel
                if not path.is_file():
                    continue
                out.append(
                    BundledFont(
                        family=str(item.get("family") or path.stem),
                        path=str(path),
                        style=str(item.get("style") or "Regular"),
                        scripts=list(item.get("scripts") or []),
                        license=str(item.get("license") or "OFL-1.1"),
                    )
                )
        except Exception:  # noqa: BLE001
            pass
    if out:
        return out
    # Discover TTF/OTF without manifest
    for path in sorted(directory.glob("*.ttf")) + sorted(directory.glob("*.otf")):
        out.append(
            BundledFont(
                family=path.stem.replace("-", " "),
                path=str(path),
                scripts=["latin"],
                license="OFL-1.1",
            )
        )
    return out


_system_cache: tuple[float, list[str]] | None = None


_MIN_REAL_FAMILIES = 10


def list_system_families(*, force_refresh: bool = False) -> list[str]:
    """Lazy system font family list; cached under runtime/cache and in-process."""
    global _system_cache
    cache_path = CACHE_DIR / "font_families.json"
    now = time.time()
    if not force_refresh and _system_cache is not None:
        return list(_system_cache[1])
    if not force_refresh and cache_path.is_file():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            families = list(data.get("families") or [])
            mtime = float(data.get("mtime") or 0)
            # Refresh at most daily unless forced. A tiny list comes from a headless run
            # (installer self-check, tests) that saw only the bundled fonts — never trust it.
            if len(families) >= _MIN_REAL_FAMILIES and (now - mtime) < 86400:
                _system_cache = (mtime, families)
                return list(families)
        except Exception:  # noqa: BLE001
            pass

    families: list[str] = []
    headless = False
    try:
        from PySide6.QtGui import QFontDatabase, QGuiApplication

        app = QGuiApplication.instance()
        if app is not None:
            # The offscreen / minimal platforms list only application fonts, not the system's.
            headless = QGuiApplication.platformName() in ("offscreen", "minimal")
            if not headless:
                families = sorted(QFontDatabase.families())
    except Exception:  # noqa: BLE001
        families = []

    # Headless: still record Windows Fonts directory basenames as weak hints
    if not families and os.name == "nt" and sys.platform.startswith("win"):
        windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        if windir.is_dir():
            families = sorted({p.stem for p in windir.glob("*.ttf")} | {p.stem for p in windir.glob("*.ttc")})

    if not families and sys.platform == "darwin":
        names: set[str] = set()
        for folder in (
            Path.home() / "Library" / "Fonts",
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts/Supplemental"),
        ):
            if not folder.is_dir():
                continue
            for pattern in ("*.ttf", "*.otf", "*.ttc"):
                names |= {p.stem for p in folder.glob(pattern)}
        families = sorted(names)

    if headless or len(families) < _MIN_REAL_FAMILIES:
        _system_cache = (now, families)
        return list(families)  # usable for this run, but not written to the shared cache
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"mtime": now, "families": families}, indent=2),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass
    _system_cache = (now, families)
    return list(families)


def collect_embedded_fonts(doc: Any) -> list[str]:
    names: list[str] = []
    try:
        for xref in range(1, doc.xref_length()):
            try:
                t = doc.xref_get_key(xref, "Type")
                if not t or "Font" not in str(t[1]):
                    continue
                base = doc.xref_get_key(xref, "BaseFont")
                label = str(base[1]).lstrip("/") if base and base[0] != "null" else f"font@{xref}"
                names.append(label)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def build_font_inventory(doc: Any | None = None, *, force_refresh: bool = False) -> FontInventory:
    """Assemble inventory for diagnostics (not shown during ordinary viewing)."""
    inv = FontInventory()
    if doc is not None:
        inv.embedded = collect_embedded_fonts(doc)
    families = list_system_families(force_refresh=force_refresh)
    inv.system_families = families
    low = {f.lower() for f in families}
    inv.system_hints_present = [h for h in _WINDOWS_HINTS if h.lower() in low]
    inv.bundled = load_bundled_fonts()
    if _system_cache is not None:
        inv.cache_age_sec = max(0.0, time.time() - _system_cache[0])
    return inv


_RAW_FONTS: dict = {}  # family → QRawFont (the coverage check runs while painting)


def glyph_coverage_missing(family: str, text: str) -> list[str]:
    """Return characters in *text* that *family* cannot render (best-effort via Qt)."""
    if not text:
        return []
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont, QFontMetricsF

        if QApplication.instance() is None:
            return []
        qf = QFont(family)
        # The font file itself, asked by code point. PySide6 6.8's one-character str overloads
        # (QFontMetricsF.inFont, QRawFont.supportsCharacter) answer wrongly for non-ASCII characters
        # (Arial "had" ゴ, MS Gothic "lacked" Ｍ and 緑), and inFontUcs4 counts Qt's fallback fonts.
        from PySide6.QtGui import QFontDatabase, QRawFont

        raw = _RAW_FONTS.get(family)
        if raw is None:
            # QRawFont.fromFont crashes Qt when its font database is empty (offscreen platform without
            # a font folder): only ask it when there are fonts; otherwise the old check is used.
            raw = QRawFont.fromFont(qf) if QFontDatabase.families() else QRawFont()
            if len(_RAW_FONTS) > 64:
                _RAW_FONTS.clear()
            _RAW_FONTS[family] = raw
        metrics = None if raw.isValid() else QFontMetricsF(qf)
        missing: list[str] = []
        for ch in text:
            if ch.isspace():
                continue
            try:
                if raw.isValid():
                    if not raw.supportsCharacter(ord(ch)):
                        missing.append(ch)
                elif hasattr(metrics, "inFont") and not metrics.inFont(ch):
                    missing.append(ch)
            except Exception:  # noqa: BLE001
                continue
        # Deduplicate preserving order
        seen: set[str] = set()
        out: list[str] = []
        for ch in missing:
            if ch not in seen:
                seen.add(ch)
                out.append(ch)
        return out
    except Exception:  # noqa: BLE001
        return []
