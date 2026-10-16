"""Cached font family list for fast searchable dropdowns (no disk scan per click)."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def cached_font_families() -> tuple[str, ...]:
    """Installed + bundled families, sorted, unique."""
    families: set[str] = set()
    try:
        from core.editing.font_inventory import list_system_families, load_bundled_fonts

        for name in list_system_families() or []:
            if name:
                families.add(str(name))
        for bf in load_bundled_fonts() or []:
            fam = getattr(bf, "family", None) or getattr(bf, "name", None)
            if fam:
                families.add(str(fam))
    except Exception:  # noqa: BLE001
        pass
    if not families:
        families.update({"Segoe UI", "Arial", "Yu Gothic", "MS PGothic", "Noto Sans CJK JP"})
    return tuple(sorted(families, key=lambda s: s.lower()))


def recently_used_fonts(limit: int = 8) -> list[str]:
    """Recent fonts from user prefs (best-effort)."""
    try:
        from core.user_prefs import UserPreferences

        prefs = UserPreferences.load()
        recent = list(getattr(prefs, "recent_fonts", []) or [])
        return [str(x) for x in recent[:limit] if x]
    except Exception:  # noqa: BLE001
        return []


def remember_font(family: str) -> None:
    family = (family or "").strip()
    if not family:
        return
    try:
        from core.user_prefs import UserPreferences

        prefs = UserPreferences.load()
        recent = [family] + [f for f in (getattr(prefs, "recent_fonts", []) or []) if f != family]
        prefs.recent_fonts = recent[:12]
        prefs.save()
        # Clear lru only if we ever cache prefs-derived lists separately
    except Exception:  # noqa: BLE001
        pass
