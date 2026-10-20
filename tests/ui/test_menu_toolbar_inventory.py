"""Every menu and toolbar control, inventoried from the real window (scripts/audit/ui_control_inventory.py):
one Alt-letter per item in each menu, no shortcut used twice, an icon on every command, a tooltip
on every control, and menu ↔ toolbar commands are the same actions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import fitz
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "audit"))


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-inventory"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


def _open(win, tmp_path):
    d = fitz.open()
    d.new_page().insert_text((72, 72), "Inventory")
    d.new_page()
    d.save(tmp_path / "inv.pdf")
    d.close()
    assert win.open_path(tmp_path / "inv.pdf")


@pytest.mark.parametrize("with_document", [False, True])
def test_no_mnemonic_or_shortcut_conflicts(window, tmp_path, with_document):
    from ui_control_inventory import inventory

    if with_document:
        _open(window, tmp_path)
    inv = inventory(window)
    assert inv["conflicts"] == []
    assert inv["items_without_tooltip"] == []
    missing = [p for p in inv["menu_items_without_icon"] if not p.startswith("File > Open Recent >")]
    assert missing == []
    no_letter = [i["path"] for i in inv["menu_items"]
                 if i["visible"] and "&" not in i["text"].replace("&&", "") and "Open Recent >" not in i["path"]]
    assert no_letter == []


def test_toolbar_controls_have_tooltips_and_are_menu_commands(window, tmp_path):
    from PySide6.QtWidgets import QToolBar

    from ui_control_inventory import inventory

    _open(window, tmp_path)
    inv = inventory(window)
    assert all(c.get("tooltip", "").strip() for c in inv["toolbar"] if c.get("visible", True)
               and c.get("widget") not in ("QWidget", "QLabel"))
    menu_actions = set()
    for m in window._menus_by_action.values():  # noqa: SLF001
        menu_actions.update(a for a in m.actions() if not a.isSeparator())
    bar = window.findChild(QToolBar, "MainToolbar")
    commands = [a for a in bar.actions() if not a.isSeparator() and bar.widgetForAction(a) is not None
                and a.text() and type(bar.widgetForAction(a)).__name__ == "QToolButton"]
    not_in_menus = [a.text() for a in commands if a not in menu_actions]
    assert not_in_menus == []


def test_new_commands_are_reachable_from_menus(window):
    texts = set()
    for m in window._menus_by_action.values():  # noqa: SLF001
        texts.update(a.text().replace("&&", "&").replace("&", "") for a in m.actions())
    for wanted in ("Bookmark for This Page…", "Remove Hidden Information…", "Copy Page as Picture"):
        assert wanted in texts
