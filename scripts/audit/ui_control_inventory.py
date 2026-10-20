"""Inventory of every menu, submenu, toolbar control and shortcut in the main window.

Usage: python scripts/audit/ui_control_inventory.py [out.json]

Runs offscreen with isolated settings, builds ``MainWindow`` with and without a document,
and reports:
* each menu item (path, text, shortcut, icon present, tooltip, enabled, checkable, visible)
* toolbar controls (actions and widgets with tooltips)
* duplicate mnemonics inside one menu, duplicate shortcuts across the window,
  menu items without icons (informational), actions without tooltips.
Exit code 1 when a duplicate mnemonic or shortcut conflict is found.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _mnemonic(text: str) -> str | None:
    t = text.replace("&&", "")
    i = t.find("&")
    if i < 0 or i + 1 >= len(t):
        return None
    return t[i + 1].lower()


def inventory(win) -> dict:
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QToolBar, QToolButton, QWidgetAction

    menus_by_action = getattr(win, "_menus_by_action", {})
    items: list[dict] = []
    conflicts: list[str] = []

    def walk(menu, path: str) -> None:
        win._sync_submenus(menu)  # noqa: SLF001
        seen: dict[str, list[str]] = defaultdict(list)
        for a in menu.actions():
            if a.isSeparator() or isinstance(a, QWidgetAction):
                continue
            text = a.text()
            sub = menus_by_action.get(a)
            m = _mnemonic(text)
            if a.isVisible() and m:
                seen[m].append(text)
            entry = {
                "path": f"{path} > {text.replace('&&', '&').replace('&', '')}" if path else text.replace("&", ""),
                "text": text,
                "shortcuts": [s.toString(QKeySequence.SequenceFormat.PortableText) for s in a.shortcuts()],
                "icon": not a.icon().isNull(),
                "tooltip": a.toolTip(),
                "enabled": a.isEnabled(),
                "checkable": a.isCheckable(),
                "visible": a.isVisible(),
                "submenu": sub is not None,
            }
            items.append(entry)
            if sub is not None:
                walk(sub, entry["path"])
        for key, texts in seen.items():
            if len(texts) > 1:
                conflicts.append(f"duplicate mnemonic '{key}' in {path or 'menu bar'}: {texts}")

    bar_seen: dict[str, list[str]] = defaultdict(list)
    for a in win.menuBar().actions():
        m = _mnemonic(a.text())
        if m:
            bar_seen[m].append(a.text())
        sub = menus_by_action.get(a)
        if sub is not None:
            walk(sub, a.text().replace("&", ""))
    for key, texts in bar_seen.items():
        if len(texts) > 1:
            conflicts.append(f"duplicate mnemonic '{key}' in menu bar: {texts}")

    shortcut_owner: dict[str, list[str]] = defaultdict(list)
    from PySide6.QtGui import QAction
    for a in win.findChildren(QAction):
        for s in a.shortcuts():
            k = s.toString(QKeySequence.SequenceFormat.PortableText)
            if k:
                shortcut_owner[k].append(a.text().replace("&", "") or a.objectName())
    for k, owners in shortcut_owner.items():
        uniq = sorted(set(owners))
        if len(uniq) > 1:
            conflicts.append(f"shortcut {k} used by {uniq}")

    toolbar: list[dict] = []
    for tb in win.findChildren(QToolBar):
        for a in tb.actions():
            if a.isSeparator():
                continue
            w = tb.widgetForAction(a)
            if isinstance(a, QWidgetAction) or (w is not None and not isinstance(w, QToolButton)):
                wid = w or a.defaultWidget()
                toolbar.append({"toolbar": tb.objectName(), "widget": type(wid).__name__ if wid else "",
                                "name": wid.objectName() if wid else "", "tooltip": wid.toolTip() if wid else "",
                                "visible": a.isVisible()})
                continue
            if isinstance(w, QToolButton) and w.defaultAction() is not a and w.defaultAction() is not None:
                a = w.defaultAction()
            toolbar.append({"toolbar": tb.objectName(), "text": a.text().replace("&", ""), "icon": not a.icon().isNull(),
                            "tooltip": a.toolTip(), "enabled": a.isEnabled(), "visible": a.isVisible()})

    no_icon = [i["path"] for i in items if not i["icon"] and not i["submenu"] and i["visible"]
               and not i["checkable"]]
    no_tip = [i["path"] for i in items if i["visible"] and not i["tooltip"].strip()]
    return {"menu_items": items, "toolbar": toolbar, "conflicts": conflicts,
            "menu_items_without_icon": no_icon, "items_without_tooltip": no_tip}


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    tmp = tempfile.mkdtemp(prefix="monograph_inventory_")
    os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = str(Path(tmp) / "userdata")
    os.environ["MONOGRAPH_PDF_RUNTIME_DIR"] = str(Path(tmp) / "runtime")
    from PySide6.QtWidgets import QApplication

    import fitz
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    no_doc = inventory(win)
    pdf = Path(tmp) / "inventory.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "Inventory")
    d.new_page()
    d.save(pdf)
    d.close()
    win.open_path(pdf)
    app.processEvents()
    with_doc = inventory(win)
    result = {"without_document": no_doc, "with_document": with_doc}
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"menu items: {len(with_doc['menu_items'])}  toolbar controls: {len(with_doc['toolbar'])}")
    for c in with_doc["conflicts"]:
        print("CONFLICT:", c)
    print("menu items without icon:", len(with_doc["menu_items_without_icon"]))
    for p in with_doc["menu_items_without_icon"]:
        print("   ", p)
    print("items without tooltip:", len(with_doc["items_without_tooltip"]))
    for p in with_doc["items_without_tooltip"]:
        print("   ", p)
    disabled = [i["path"] for i in with_doc["menu_items"] if not i["enabled"] and i["visible"]]
    print("disabled with a document open:", len(disabled))
    for p in disabled:
        print("   ", p)
    win.close()
    return 1 if with_doc["conflicts"] else 0


if __name__ == "__main__":
    sys.exit(main())
