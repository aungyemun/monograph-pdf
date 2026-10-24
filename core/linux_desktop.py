"""Linux desktop integration: .desktop entry and default PDF handler (XDG)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from core.product_meta import EXECUTABLE_NAME, PRODUCT_NAME, REPOSITORY_NAME, resolve_app_icon_path
from core.safe_paths import linux_tool

DESKTOP_ID = f"{REPOSITORY_NAME}.desktop"


def _applications_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "applications"


def _exec_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" %F'
    root = Path(__file__).resolve().parents[1]
    launch = root / "scripts" / "dev_launch.sh"
    py = root / "env" / "bin" / "python"
    if launch.is_file():
        return f'"{launch}" %F'
    if py.is_file():
        return f'"{py}" -m app %F'
    return f'"{sys.executable}" -m app %F'


def ensure_desktop_entry() -> str:
    """Write ~/.local/share/applications/monograph-pdf.desktop and return its desktop-file id."""
    apps = _applications_dir()
    apps.mkdir(parents=True, exist_ok=True)
    path = apps / DESKTOP_ID
    icon = resolve_app_icon_path()
    icon_field = str(icon) if icon and icon.is_file() else REPOSITORY_NAME
    body = "\n".join(
        [
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            f"Name={PRODUCT_NAME}",
            "Comment=Offline privacy-focused PDF editor",
            f"Exec={_exec_command()}",
            f"Icon={icon_field}",
            "Terminal=false",
            "Categories=Office;Viewer;Graphics;",
            "MimeType=application/pdf;",
            f"StartupWMClass={EXECUTABLE_NAME}",
            "",
        ]
    )
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    path.chmod(path.stat().st_mode | 0o111)
    update = linux_tool("update-desktop-database")
    if update:
        subprocess.run([update, str(apps)], check=False, capture_output=True, timeout=30)
    return DESKTOP_ID


def set_default_pdf_handler(desktop_id: str | None = None) -> tuple[bool, str]:
    """Register as the default handler for application/pdf via xdg-mime."""
    desktop_id = desktop_id or ensure_desktop_entry()
    xdg_mime = linux_tool("xdg-mime")
    if not xdg_mime:
        return False, "xdg-mime was not found. Install xdg-utils, then try again."
    try:
        proc = subprocess.run(
            [xdg_mime, "default", desktop_id, "application/pdf"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"xdg-mime exited {proc.returncode}"
        return False, err
    check = subprocess.run(
        [xdg_mime, "query", "default", "application/pdf"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    current = (check.stdout or "").strip()
    if current == desktop_id:
        return True, f"Default handler is now {desktop_id}."
    return True, f"Registered {desktop_id}. Current default reports as: {current or '(unknown)'}."