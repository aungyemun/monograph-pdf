"""Theme application — light / dark / system (portable).

One palette per theme drives *everything* that has colour: the Qt stylesheet,
drawn toolbar/menu icons, the PDF canvas backdrop, thumbnails, and the small
indicator images (check marks, chevrons) the stylesheet references.

Edit colours in ``PALETTES``; ``python -m ui.theme`` regenerates the reference
``resources/styles/{light,dark}.qss`` files from the same template.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template

from PySide6.QtCore import QDir, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from app.paths import CACHE_DIR, RESOURCES_DIR
from core import app_env


# --------------------------------------------------------------------------- palette


@dataclass(frozen=True)
class Palette:
    name: str
    window: str  # app chrome background
    surface: str  # menus, toolbars, panels, inputs
    surface_alt: str  # secondary chrome (context bar, headers)
    hover: str  # neutral hover fill
    pressed: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_subtle: str  # readable secondary labels (≥ 4.5:1)
    text_faint: str  # disabled controls only
    accent: str  # brand teal for focus rings, checked states, links
    accent_hover: str
    accent_pressed: str
    accent_text: str  # accent used as text on surface
    on_accent: str  # text on accent fills
    accent_soft: str  # subtle selected fill
    accent_soft_strong: str
    selection: str  # text selection in inputs
    danger: str
    warning: str
    success: str
    canvas: str  # workspace behind PDF pages
    page_border: str
    page_shadow: str  # rgba
    icon: str  # monochrome icon ink
    icon_disabled: str
    tooltip_bg: str
    tooltip_text: str
    scroll_handle: str
    scroll_handle_hover: str


PALETTES: dict[str, Palette] = {
    "light": Palette(
        name="light",
        window="#f3f4f6",
        surface="#ffffff",
        surface_alt="#f8f9fb",
        hover="#eef1f4",
        pressed="#e3e7ec",
        border="#e2e5ea",
        border_strong="#cbd1d9",
        text="#1f2937",
        text_muted="#5f6b7a",
        text_subtle="#667080",
        text_faint="#868f9b",
        accent="#0f766e",
        accent_hover="#0d8a80",
        accent_pressed="#115e59",
        accent_text="#0f766e",
        on_accent="#ffffff",
        accent_soft="#e7f4f2",
        accent_soft_strong="#cde9e4",
        selection="#b9e1db",
        danger="#b91c1c",
        warning="#b45309",
        success="#15803d",
        canvas="#dde1e7",
        page_border="#c3c9d2",
        page_shadow="rgba(15, 23, 42, 46)",
        icon="#3b4654",
        icon_disabled="#b4bcc6",
        tooltip_bg="#1f2937",
        tooltip_text="#f9fafb",
        scroll_handle="#c5ccd5",
        scroll_handle_hover="#9fa9b5",
    ),
    "dark": Palette(
        name="dark",
        window="#15181d",
        surface="#1c2027",
        surface_alt="#20252d",
        hover="#2a3039",
        pressed="#333a45",
        border="#2c323b",
        border_strong="#3c444f",
        text="#e6e9ed",
        text_muted="#9ba5b1",
        text_subtle="#8a94a0",
        text_faint="#737c88",
        accent="#2bb3a5",
        accent_hover="#35c6b7",
        accent_pressed="#22958a",
        accent_text="#5eead4",
        on_accent="#0b1514",
        accent_soft="#163632",
        accent_soft_strong="#1d4a44",
        selection="#1f5d55",
        danger="#f87171",
        warning="#fbbf24",
        success="#4ade80",
        canvas="#0e1014",
        page_border="#363d47",
        page_shadow="rgba(0, 0, 0, 140)",
        icon="#c9d0d8",
        icon_disabled="#4f5763",
        tooltip_bg="#e6e9ed",
        tooltip_text="#111827",
        scroll_handle="#3a414c",
        scroll_handle_hover="#525b68",
    ),
}

_current: Palette = PALETTES["light"]
_ASSET_PREFIX = "monographpdftheme"


def current_palette() -> Palette:
    """Palette of the theme applied most recently (light before first apply)."""
    return _current


# --------------------------------------------------------------------------- detection


def detect_system_dark() -> bool:
    """Best-effort OS dark preference without extra deps."""
    if sys.platform.startswith("win"):
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return int(value) == 0
        except Exception:  # noqa: BLE001
            pass
    if sys.platform == "darwin":
        return app_env.get("FORCE_DARK") == "1"
    # Qt 6.5+: platform colour scheme
    try:
        hints = QGuiApplication.styleHints()
        if hints is not None and hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
    except Exception:  # noqa: BLE001
        pass
    app = QApplication.instance()
    if app is not None:
        return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return False


def resolve_theme(preference: str) -> str:
    pref = (preference or "system").lower()
    if pref == "system":
        return "dark" if detect_system_dark() else "light"
    if pref in ("light", "dark"):
        return pref
    return "light"


# --------------------------------------------------------------------------- assets


def _asset_dir(theme: str) -> Path:
    """runtime/cache/theme/<name>; falls back to the OS temp dir when the install folder is read-only."""
    preferred = CACHE_DIR / "theme" / theme
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        probe = preferred / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
        return preferred
    except OSError:
        import tempfile

        return Path(tempfile.gettempdir()) / "monograph-pdf-theme" / theme


def _draw(path: Path, size: int, painter_fn) -> None:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter_fn(p, size)
    p.end()
    pm.save(str(path), "PNG")


def ensure_theme_assets(pal: Palette) -> Path:
    """Render indicator images (2x) for the stylesheet into runtime/cache/theme/<name>."""
    out = _asset_dir(pal.name)
    out.mkdir(parents=True, exist_ok=True)
    s = 32

    def check(color: str):
        def fn(p: QPainter, n: int) -> None:
            pen = QPen(QColor(color), n * 0.12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            path = QPainterPath(QPointF(n * 0.24, n * 0.52))
            path.lineTo(QPointF(n * 0.43, n * 0.70))
            path.lineTo(QPointF(n * 0.77, n * 0.32))
            p.drawPath(path)

        return fn

    def dash(color: str):
        def fn(p: QPainter, n: int) -> None:
            p.setPen(QPen(QColor(color), n * 0.12, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(n * 0.28, n * 0.5), QPointF(n * 0.72, n * 0.5))

        return fn

    def chevron(color: str, direction: str):
        def fn(p: QPainter, n: int) -> None:
            pen = QPen(QColor(color), n * 0.09, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            a, b, c = 0.30, 0.50, 0.70
            if direction == "down":
                pts = [(a, 0.40), (b, 0.60), (c, 0.40)]
            elif direction == "up":
                pts = [(a, 0.60), (b, 0.40), (c, 0.60)]
            elif direction == "right":
                pts = [(0.40, a), (0.60, b), (0.40, c)]
            else:
                pts = [(0.60, a), (0.40, b), (0.60, c)]
            path = QPainterPath(QPointF(pts[0][0] * n, pts[0][1] * n))
            for x, y in pts[1:]:
                path.lineTo(QPointF(x * n, y * n))
            p.drawPath(path)

        return fn

    def dot(color: str):
        def fn(p: QPainter, n: int) -> None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            r = n * 0.20
            p.drawEllipse(QRectF(n / 2 - r, n / 2 - r, 2 * r, 2 * r))

        return fn

    specs = {
        "check.png": check(pal.on_accent),
        "partial.png": dash(pal.on_accent),
        "radio.png": dot(pal.on_accent),
        "chevron-down.png": chevron(pal.text_muted, "down"),
        "chevron-up.png": chevron(pal.text_muted, "up"),
        "chevron-right.png": chevron(pal.text_muted, "right"),
        "chevron-down-disabled.png": chevron(pal.text_faint, "down"),
        "chevron-up-disabled.png": chevron(pal.text_faint, "up"),
        "menu-check.png": check(pal.accent_text),
    }
    for name, fn in specs.items():
        target = out / name
        try:
            _draw(target, s, fn)
        except Exception:  # noqa: BLE001
            pass
    QDir.setSearchPaths(_ASSET_PREFIX, [str(out)])
    return out


# --------------------------------------------------------------------------- stylesheet

_QSS = Template(
    r"""
/* $name theme — generated from ui/theme.py (edit PALETTES there) */
QMainWindow, QDialog { background: $window; color: $text; font-size: 13px; }
QWidget { color: $text; selection-background-color: $selection; selection-color: $text; }
QDialog QLabel { color: $text; }
QLabel:disabled { color: $text_faint; }

/* ---------- Menu bar & menus ---------- */
QMenuBar { background: $surface; border-bottom: 1px solid $border; padding: 2px 6px; spacing: 1px; }
QMenuBar::item { padding: 5px 10px; border-radius: 5px; background: transparent; color: $text; }
QMenuBar::item:selected { background: $hover; }
QMenuBar::item:pressed { background: $accent_soft; color: $accent_text; }
QMenu { background: $surface; border: 1px solid $border_strong; padding: 5px; }
QMenu::item { padding: 6px 30px 6px 8px; border-radius: 5px; color: $text; background: transparent; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::item:disabled { color: $text_faint; background: transparent; }
QMenu::icon { padding-left: 8px; }
QMenu::separator { height: 1px; background: $border; margin: 5px 6px; }
QMenu::indicator { width: 16px; height: 16px; margin-left: 6px; }
QMenu::indicator:checked { image: url($asset_prefix:menu-check.png); }
QMenu::right-arrow { image: url($asset_prefix:chevron-right.png); width: 14px; height: 14px; margin-right: 6px; }
QMenu QLabel#MenuSection { color: $text_subtle; font-size: 11px; font-weight: 600; padding: 6px 10px 2px 10px; }

/* ---------- Toolbars ---------- */
QToolBar { background: $surface; border: none; border-bottom: 1px solid $border; spacing: 2px; padding: 4px 8px; }
QToolBar#ContextToolbar { background: $surface_alt; padding: 3px 8px; }
QToolBar::separator { background: $border; width: 1px; margin: 6px 6px; }
QToolBar QToolButton { padding: 5px 7px; border-radius: 6px; color: $text; border: 1px solid transparent; background: transparent; }
QToolBar QToolButton:hover { background: $hover; }
QToolBar QToolButton:pressed { background: $pressed; }
QToolBar QToolButton:checked { background: $accent_soft; border-color: $accent_soft_strong; color: $accent_text; }
QToolBar QToolButton:checked:hover { background: $accent_soft_strong; }
QToolBar QToolButton:disabled { color: $text_faint; background: transparent; }
QToolBar QToolButton:checked:disabled { color: $text_faint; background: transparent; border-color: transparent; }
QToolBar QToolButton:focus { border: 1px solid $accent; }
QToolButton[popupMode="1"] { padding-right: 18px; }
QToolButton::menu-button { border: none; border-left: 1px solid transparent; width: 16px; border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
QToolButton::menu-button:hover { border-left-color: $border; background: $pressed; }
QToolButton::menu-arrow { image: url($asset_prefix:chevron-down.png); width: 12px; height: 12px; }
QToolButton::menu-indicator { image: url($asset_prefix:chevron-down.png); width: 10px; height: 10px; subcontrol-position: right center; subcontrol-origin: padding; right: 2px; }
QToolButton::menu-arrow:disabled, QToolButton::menu-indicator:disabled { image: url($asset_prefix:chevron-down-disabled.png); }
QToolButton#FormatButton { min-width: 18px; font-weight: 600; }

QLabel#ContextHint { color: $text_muted; padding: 2px 8px; }
QLabel#ContextTitle { color: $text_muted; font-weight: 600; padding: 0 10px 0 4px; }
QLabel#ToolbarPageTotal { color: $text_muted; padding: 0 6px 0 2px; }
QLineEdit#ToolbarPageEdit { min-width: 34px; max-width: 46px; padding: 2px 4px; qproperty-alignment: AlignCenter; }
QComboBox#ToolbarZoomValue { min-width: 64px; }
QPushButton#StepButton { padding: 0; min-width: 26px; max-width: 26px; font-weight: 600; }
QLineEdit#ToolbarSearch { border-radius: 14px; padding: 4px 10px; background: $window; }
QLineEdit#ToolbarSearch:focus { background: $surface; }

/* ---------- Tooltips ---------- */
QToolTip { background: $tooltip_bg; color: $tooltip_text; border: none; padding: 5px 8px; border-radius: 4px; }

/* ---------- Status bar ---------- */
QStatusBar { background: $surface; border-top: 1px solid $border; color: $text_muted; min-height: 26px; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $text_muted; padding: 0 4px; }
QLabel#StatusCopyright { color: $text_subtle; background: transparent; padding: 0 6px; }
QLabel#StatusLeft, QLabel#StatusRight, QLabel#StatusSep { color: $text_muted; }
QLabel#StatusDirty[state="modified"] { color: $warning; font-weight: 600; }
QLabel#StatusDirty[state="saved"] { color: $success; }

/* ---------- Splitters, tabs, panels ---------- */
QSplitter::handle { background: $border; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:hover { background: $accent; }
QTabWidget::pane { border: none; background: $surface; }
QTabWidget#LeftRail { background: $surface; }
QTabBar { background: $surface; }
QTabBar::tab { background: transparent; color: $text_muted; padding: 8px 3px; margin: 0; border: none; border-bottom: 2px solid transparent; min-width: 24px; }
QTabBar::tab:selected { color: $accent_text; border-bottom: 2px solid $accent; font-weight: 600; }
QTabBar::tab:hover:!selected { color: $text; background: $hover; }
QTabBar QToolButton { background: $surface; border: none; color: $text; }
QTabBar QToolButton:hover { background: $hover; }
QTabBar QToolButton:disabled { color: $text_faint; }

QScrollArea { background: $canvas; border: none; }
QScrollArea#InspectorPanel { background: $surface; border: none; border-left: 1px solid $border; }
QWidget#InspectorRoot { background: $surface; }
QLabel#InspectorSection { color: $text_subtle; font-size: 11px; font-weight: 700; padding-top: 10px; letter-spacing: 1px; }
QLabel#InspectorTitle { color: $text; font-size: 14px; font-weight: 600; }
QLabel#InspectorWarn { color: $warning; }
QLabel#InspectorError { color: $danger; font-weight: 600; }

/* ---------- Inputs ---------- */
QLineEdit, QComboBox, QAbstractSpinBox, QTextEdit, QPlainTextEdit, QTextBrowser, QDateEdit {
    background: $surface; color: $text; border: 1px solid $border_strong; border-radius: 6px; padding: 3px 7px;
}
QLineEdit, QComboBox, QAbstractSpinBox { min-height: 22px; }
QLineEdit:hover, QComboBox:hover, QAbstractSpinBox:hover { border-color: $text_faint; }
QLineEdit:focus, QComboBox:focus, QAbstractSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus { border: 1px solid $accent; }
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled, QTextEdit:disabled { color: $text_faint; background: $surface_alt; border-color: $border; }
QLineEdit:read-only { background: $surface_alt; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 22px; border: none; }
QComboBox::down-arrow { image: url($asset_prefix:chevron-down.png); width: 12px; height: 12px; }
QComboBox::down-arrow:disabled { image: url($asset_prefix:chevron-down-disabled.png); }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border_strong; border-radius: 6px; padding: 4px; outline: none; selection-background-color: $accent_soft; selection-color: $text; }
QAbstractSpinBox { padding-right: 20px; }
QAbstractSpinBox QLineEdit { padding: 0; border: none; background: transparent; min-height: 0; }
QColorDialog QAbstractSpinBox { min-width: 70px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { subcontrol-origin: border; width: 18px; border: none; background: transparent; }
QAbstractSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 6px; }
QAbstractSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 6px; }
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background: $hover; }
QAbstractSpinBox::up-arrow { image: url($asset_prefix:chevron-up.png); width: 10px; height: 10px; }
QAbstractSpinBox::down-arrow { image: url($asset_prefix:chevron-down.png); width: 10px; height: 10px; }
QAbstractSpinBox::up-arrow:disabled { image: url($asset_prefix:chevron-up-disabled.png); }
QAbstractSpinBox::down-arrow:disabled { image: url($asset_prefix:chevron-down-disabled.png); }

/* ---------- Buttons ---------- */
QPushButton { background: $surface; color: $text; border: 1px solid $border_strong; border-radius: 6px; padding: 6px 14px; min-height: 18px; }
QPushButton:hover { background: $hover; }
QPushButton:pressed { background: $pressed; }
QPushButton:focus { border-color: $accent; }
QPushButton:disabled { color: $text_faint; background: $surface_alt; border-color: $border; }
QPushButton:default, QPushButton[primary="true"] { background: $accent; color: $on_accent; border: 1px solid $accent; font-weight: 600; }
QPushButton:default:hover, QPushButton[primary="true"]:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton:default:pressed, QPushButton[primary="true"]:pressed { background: $accent_pressed; }
QPushButton[danger="true"] { background: $danger; color: #ffffff; border-color: $danger; font-weight: 600; }
QPushButton[flat="true"], QPushButton:flat { background: transparent; border-color: transparent; }
QDialogButtonBox QPushButton { min-width: 76px; }
QToolButton { color: $text; }
QToolButton#ColorSwatch { border: 1px solid $border_strong; border-radius: 5px; padding: 3px 8px 3px 4px; background: $surface; color: $text; font-size: 12px; min-height: 20px; }
QToolButton#ColorSwatch:hover { border-color: $accent; }
QToolButton#FormatToggle { border: 1px solid $border; border-radius: 5px; background: $surface; color: $text; padding: 0; }
QToolButton#FormatToggle:hover { border-color: $accent_soft_strong; background: $accent_soft; }
QToolButton#FormatToggle:checked { background: $accent_soft_strong; border-color: $accent; color: $accent_text; }

/* ---------- Check / radio ---------- */
QCheckBox, QRadioButton { spacing: 8px; color: $text; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QCheckBox::indicator { border: 1px solid $border_strong; border-radius: 4px; background: $surface; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($asset_prefix:check.png); }
QCheckBox::indicator:indeterminate { background: $accent; border-color: $accent; image: url($asset_prefix:partial.png); }
QCheckBox::indicator:disabled { background: $surface_alt; border-color: $border; }
QCheckBox::indicator:checked:disabled { background: $text_faint; border-color: $text_faint; }
QRadioButton::indicator { border: 1px solid $border_strong; border-radius: 8px; background: $surface; }
QRadioButton::indicator:checked { background: $accent; border-color: $accent; image: url($asset_prefix:radio.png); }

/* ---------- Lists, trees, tables ---------- */
QListView, QListWidget, QTreeView, QTreeWidget, QTableView, QTableWidget {
    background: $surface; color: $text; border: 1px solid $border; border-radius: 6px; outline: none; padding: 2px;
    alternate-background-color: $surface_alt;
}
QListView::item, QTreeView::item { padding: 4px 6px; border-radius: 4px; }
QListView::item:hover, QTreeView::item:hover { background: $hover; }
QListView::item:selected, QTreeView::item:selected, QTableView::item:selected { background: $accent_soft; color: $text; }
QListWidget#Thumbnails { border: none; background: $surface; padding: 6px 2px; }
QListWidget#Thumbnails::item, QListWidget#Thumbnails::item:hover, QListWidget#Thumbnails::item:selected { background: transparent; border: none; }
QHeaderView::section { background: $surface_alt; color: $text_muted; border: none; border-bottom: 1px solid $border; padding: 5px 8px; font-weight: 600; }

/* ---------- Group boxes, progress, sliders ---------- */
QGroupBox { border: 1px solid $border; border-radius: 8px; margin-top: 14px; padding: 12px 10px 8px 10px; background: transparent; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 4px; color: $text_muted; font-weight: 600; }
QProgressBar { border: 1px solid $border; border-radius: 6px; background: $surface_alt; text-align: center; color: $text; min-height: 14px; }
QProgressBar::chunk { background: $accent; border-radius: 5px; }
QSlider::groove:horizontal { height: 4px; background: $border_strong; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; background: $surface; border: 1px solid $border_strong; }
QSlider::handle:horizontal:hover { border-color: $accent; }

/* ---------- Scroll bars ---------- */
QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:vertical { background: $scroll_handle; min-height: 32px; border-radius: 4px; margin: 2px 3px; }
QScrollBar::handle:horizontal { background: $scroll_handle; min-width: 32px; border-radius: 4px; margin: 3px 2px; }
QScrollBar::handle:hover { background: $scroll_handle_hover; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QAbstractScrollArea::corner { background: transparent; }

/* ---------- Message boxes & dialogs ---------- */
QMessageBox { background: $surface; }
QMessageBox QLabel { color: $text; }
QLabel#DialogTitle { color: $text; font-size: 15px; font-weight: 600; }
QLabel#DialogSection { color: $text; font-weight: 600; }
QLabel#DialogHint, QLabel#ContextHintDialog { color: $text_muted; }
QLabel#DialogWarning { color: $warning; }
QLabel#DialogError { color: $danger; }
QLabel#ShortcutKey { color: $text_muted; font-family: "Consolas", "Cascadia Mono", monospace; }
QFrame#DialogBanner { background: $accent_soft; border: 1px solid $accent_soft_strong; border-radius: 6px; }
QFrame#WarningBanner { background: transparent; border: 1px solid $warning; border-radius: 6px; }
QWidget#SignaturePad { background: #ffffff; border: 1px dashed $border_strong; border-radius: 6px; }

/* ---------- About ---------- */
QLabel#AboutTitle { color: $text; }
QLabel#AboutVersion { color: $text_muted; }
QLabel#AboutTagline { color: $text_muted; }
QLabel#AboutCopyright { color: $text_muted; }
QLabel#AboutSectionTitle { color: $text; font-weight: 600; margin-top: 2px; }
QLabel#AboutDescription, QLabel#AboutBody, QLabel#AboutPrivacy, QLabel#AboutLicenseNote {
    color: $text;
}
QLabel#AboutFeatures { color: $text; }
QTextBrowser#LegalDocumentBrowser {
    background: $surface;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px;
    color: $text;
}

/* ---------- Welcome empty state ---------- */
QWidget#WelcomePage { background: $window; }
QScrollArea#WelcomeScroll, QWidget#WelcomeContent { background: transparent; border: none; }
QFrame#WelcomeCard { background: $surface; border: 1px solid $border; border-radius: 14px; }
QLabel#WelcomeTitle { color: $text; }
QLabel#WelcomeSubtitle { color: $text_muted; }
QLabel#WelcomeDropHint { color: $text_subtle; }
QLabel#WelcomeSection { color: $text_subtle; font-size: 11px; font-weight: 700; letter-spacing: 1px; margin-top: 6px; }
QPushButton#WelcomePrimary { background: $accent; color: $on_accent; border: none; border-radius: 8px; font-weight: 600; padding: 9px 18px; }
QPushButton#WelcomePrimary:hover { background: $accent_hover; }
QPushButton#WelcomePrimary:pressed { background: $accent_pressed; }
QPushButton#WelcomeSecondary { background: $surface_alt; color: $text; border: 1px solid $border; border-radius: 8px; padding: 8px 10px; text-align: left; }
QPushButton#WelcomeSecondary:hover { background: $hover; border-color: $border_strong; }
QListWidget#WelcomeRecent { border: 1px solid $border; border-radius: 8px; background: $surface; }
QToolButton#ToolTile { background: $surface_alt; border: 1px solid $border; border-radius: 10px; padding: 8px 4px 6px 4px; color: $text; font-size: 12px; }
QToolButton#ToolTile:hover { background: $accent_soft; border-color: $accent_soft_strong; color: $accent_text; }
QToolButton#ToolTile:pressed { background: $accent_soft_strong; }
QToolButton#ToolTile:focus { border-color: $accent; }
QListWidget#WelcomeRecent::item { padding: 0; border-radius: 6px; margin: 1px 3px; }
QListWidget#WelcomeRecent::item:hover { background: $hover; }
QListWidget#WelcomeRecent::item:selected { background: $accent_soft; color: $text; }
"""
)


def stylesheet_for(theme: str) -> str:
    pal = PALETTES.get(theme, PALETTES["light"])
    values = {k: getattr(pal, k) for k in pal.__dataclass_fields__}
    values["asset_prefix"] = _ASSET_PREFIX
    return _QSS.substitute(values).strip() + "\n"


def apply_theme(app: QApplication, preference: str = "system") -> str:
    global _current
    theme = resolve_theme(preference)
    pal = PALETTES[theme]
    _current = pal
    try:
        ensure_theme_assets(pal)
    except Exception:  # noqa: BLE001 — indicators fall back to plain boxes
        pass
    # Fusion renders QSS consistently on every OS (Windows native style ignores parts of it)
    try:
        if app.style().objectName().lower() != "fusion":
            app.setStyle("Fusion")
    except Exception:  # noqa: BLE001
        pass
    qpal = app.palette()
    for role, value in (
        (QPalette.ColorRole.Window, pal.window),
        (QPalette.ColorRole.WindowText, pal.text),
        (QPalette.ColorRole.Base, pal.surface),
        (QPalette.ColorRole.AlternateBase, pal.surface_alt),
        (QPalette.ColorRole.Text, pal.text),
        (QPalette.ColorRole.Button, pal.surface),
        (QPalette.ColorRole.ButtonText, pal.text),
        (QPalette.ColorRole.Highlight, pal.accent),
        (QPalette.ColorRole.HighlightedText, pal.on_accent),
        (QPalette.ColorRole.ToolTipBase, pal.tooltip_bg),
        (QPalette.ColorRole.ToolTipText, pal.tooltip_text),
        (QPalette.ColorRole.PlaceholderText, pal.text_subtle),
        (QPalette.ColorRole.Link, pal.accent_text),
    ):
        qpal.setColor(role, QColor(value))
    qpal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(pal.text_faint))
    qpal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(pal.text_faint))
    qpal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(pal.text_faint))
    app.setPalette(qpal)
    app.setStyleSheet(stylesheet_for(theme))
    app.setProperty("monograph_pdf_theme", theme)
    return theme


def write_reference_stylesheets() -> list[Path]:
    """Regenerate resources/styles/*.qss from the template (reference copies)."""
    written = []
    for name in PALETTES:
        path = RESOURCES_DIR / "styles" / f"{name}.qss"
        path.write_text(stylesheet_for(name), encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":  # pragma: no cover
    for p in write_reference_stylesheets():
        print(p)
