"""Find text that is cut off: labels, buttons, check boxes, radio buttons and combo boxes whose text
does not fit, in the main window and in every dialog the menus open.

Usage: python scripts/audit/clipped_text_audit.py [--out tests/outputs/logs/clipped_text.json]
       [--width 1366 --height 768] [--scale 1.0]

Runs offscreen with temporary settings and a generated document (your own files and settings are
never touched). Every menu command is triggered once; dialogs are shown, checked and closed without
doing anything (file pickers, message boxes and input boxes are answered with "Cancel"). Commands that
would contact the network, open other programs or quit are skipped. Exit code 1 when clipped text is
found.

A widget counts as clipped when it is visible and narrower than the width its text needs
(``sizeHint``); a combo box when its current text is wider than the box minus its arrow. Word-wrapped
labels and elided-by-design widgets (file paths in the status bar) are not reported.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SKIP_WORDS = ("exit", "quit", "update", "report", "website", "releases", "issues", "github", "privacy policy",
              "default pdf app", "open containing", "show in folder", "user guide", "license", "close")
ELIDED_BY_DESIGN = {"ToolbarPageTotal", "StatusPath", "DocStateLabel"}


def clipped_widgets(root) -> list[dict]:
    from PySide6.QtWidgets import QAbstractButton, QCheckBox, QComboBox, QLabel, QRadioButton, QToolButton

    found: list[dict] = []
    for w in root.findChildren(QLabel) + root.findChildren(QAbstractButton) + root.findChildren(QComboBox):
        try:
            if not w.isVisibleTo(root) or not w.isVisible() or w.visibleRegion().isEmpty():
                continue
            if w.objectName() in ELIDED_BY_DESIGN:
                continue
            text = ""
            if isinstance(w, QLabel):
                if w.wordWrap() or w.pixmap() is not None and not w.pixmap().isNull() or not w.text().strip():
                    continue
                if w.textFormat() == w.textFormat().RichText or "<" in w.text():
                    continue
                text = w.text()
                need = w.sizeHint().width()
            elif isinstance(w, QComboBox):
                text = w.currentText()
                if not text or w.isEditable():
                    continue
                need = w.fontMetrics().horizontalAdvance(text) + 34  # frame, padding and the arrow
            elif isinstance(w, (QCheckBox, QRadioButton)) or isinstance(w, QAbstractButton):
                text = w.text().replace("&&", "\0").replace("&", "").replace("\0", "&")
                if not text.strip():
                    continue
                if isinstance(w, QToolButton) and w.toolButtonStyle() == w.toolButtonStyle().ToolButtonIconOnly:
                    continue
                need = w.sizeHint().width()
            else:
                continue
            if w.width() + 1 < need:
                found.append({
                    "class": type(w).__name__, "name": w.objectName(), "text": text[:80],
                    "width": w.width(), "needs": need, "window": root.windowTitle() or type(root).__name__,
                })
        except RuntimeError:
            continue
    return found


def _inspector_states(win, app) -> list[dict]:
    """The Properties panel for a text box, each kind of shape and a sticky note: nothing may be wider
    than the panel (a too-wide row pushes every row past the panel's right edge)."""
    from core.editing.geometry import Rect

    found: list[dict] = []
    edit = win._edit  # noqa: SLF001
    if edit is None:
        return found
    objs = [("text box", edit.create_text_box(0, Rect(60, 60, 200, 40), text="Audit text"))]
    for kind in ("rectangle", "ellipse", "line", "arrow"):
        objs.append((kind, edit.create_shape(0, Rect(80, 200, 120, 60), kind, x0=80, y0=260, x1=200, y1=200)))
    for label, obj in objs:
        edit.select([obj.object_id])
        edit.editing_object_id = None
        win._flush_chrome_refresh()  # noqa: SLF001
        for _ in range(3):
            app.processEvents()
        panel = win._inspector  # noqa: SLF001
        need = panel.widget().minimumSizeHint().width()
        have = panel.viewport().width()
        if need > have + 1:
            found.append({"class": "InspectorPanel", "text": f"properties of a {label}", "width": have,
                          "needs": need, "window": "Properties panel"})
        found.extend(clipped_widgets(panel))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="")
    parser.add_argument("--width", type=int, default=1366)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--scale", default="1")
    args = parser.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
    tmp = Path(tempfile.mkdtemp(prefix="monograph-clip-audit-"))

    import fitz

    from core import user_prefs

    user_prefs.user_data_dir = lambda: tmp / "appdata"
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

    from ui.main_window import MainWindow, create_application

    report: list[dict] = []
    seen_dialogs: list[str] = []

    def check_dialog(self, *a, **k):
        try:
            self.show()
            from PySide6.QtWidgets import QApplication

            for _ in range(3):
                QApplication.processEvents()
            title = self.windowTitle() or type(self).__name__
            seen_dialogs.append(title)
            report.extend(clipped_widgets(self))
        finally:
            self.hide()
        return QDialog.DialogCode.Rejected

    QDialog.exec = check_dialog
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
    QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
    for name in ("information", "warning", "critical", "question"):
        setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))
    QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
    QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("", False))
    QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
    QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
    QDesktopServices.openUrl = staticmethod(lambda *a, **k: False)

    app = create_application(["clip-audit"])
    win = MainWindow()
    win.resize(args.width, args.height)
    win.show()
    src = tmp / "audit.pdf"
    d = fitz.open()
    for i in range(4):
        d.new_page().insert_text((72, 100), f"Audit page {i + 1}", fontsize=18)
    d.save(src)
    d.close()
    win.open_path(str(src))
    for _ in range(5):
        app.processEvents()
    report.extend(clipped_widgets(win))

    for menu_action in win.menuBar().actions():
        menu = menu_action.menu()
        if menu is None:
            continue
        stack = [menu]
        while stack:
            m = stack.pop()
            try:
                actions = list(m.actions())
            except RuntimeError:  # a menu that was rebuilt meanwhile (recent files)
                continue
            for act in actions:
                try:
                    if act.menu() is not None:
                        stack.append(act.menu())
                        continue
                    label = act.text().replace("&", "").lower()
                    skip = act.isSeparator() or not act.isEnabled() or any(w in label for w in SKIP_WORDS)
                except RuntimeError:  # deleted when its menu was rebuilt
                    continue
                if skip:
                    continue
                try:
                    act.trigger()
                    for _ in range(2):
                        app.processEvents()
                except Exception as exc:  # noqa: BLE001
                    report.append({"class": "error", "text": f"{label}: {exc}"})
                if win._document is None:  # noqa: SLF001 — a command closed it: open again
                    win.open_path(str(src))
    report.extend(clipped_widgets(win))
    report.extend(_inspector_states(win, app))
    unique = {json.dumps(r, sort_keys=True): r for r in report}
    result = {"dialogs_checked": sorted(set(seen_dialogs)), "clipped": list(unique.values())}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    win.close_document(save_session=False)
    win.close()
    return 1 if result["clipped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
