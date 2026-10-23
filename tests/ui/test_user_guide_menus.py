"""The User Guide's menu paths (**Menu ▸ Item**) exist in the app, and --user-guide shows the guide."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "USER_GUIDE.md"
# Paths whose last part is not a menu item: About dialog tab
NOT_MENU_LEAF = {("help", "about monograph pdf", "office integration"), ("file", "settings", "updates")}  # dialog tabs


def _norm(text: str) -> str:
    return text.replace("…", "").replace("...", "").strip().rstrip(":").strip().lower()


def _menu_text(text: str) -> str:
    """Menu label as shown: '&&' is a literal '&', a single '&' marks the access key."""
    return _norm(text.replace("&&", "\0").replace("&", "").replace("\0", "&"))


def _menu_tree(win) -> dict:
    from PySide6.QtWidgets import QWidgetAction

    def walk(menu):
        out = {}
        for act in menu.actions():
            if act.isSeparator() or not act.text():
                continue
            # Section labels (QWidgetAction + QLabel) show their text literally
            key = _norm(act.text()) if isinstance(act, QWidgetAction) else _menu_text(act.text())
            out[key] = walk(act.menu()) if act.menu() is not None else None
        return out

    return {_menu_text(a.text()): walk(a.menu()) for a in win.menuBar().actions() if a.menu() is not None}


@pytest.fixture
def window(qtbot):
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-guide-test"])
    win = MainWindow()
    qtbot.addWidget(win)
    yield win
    win.close_document(save_session=False)
    win.close()


def test_every_menu_path_in_the_user_guide_exists(window):
    tree = _menu_tree(window)
    paths = re.findall(r"\*\*([^*]+?▸[^*]+?)\*\*", GUIDE.read_text(encoding="utf-8"))
    checked, missing = 0, []
    for raw in paths:
        parts = [_norm(p) for p in raw.split("▸")]
        if parts[0] not in tree:
            continue  # Windows paths such as Settings ▸ Apps, Open with ▸ Monograph PDF
        if tuple(parts) in NOT_MENU_LEAF:
            parts = parts[:-1]
        node = tree
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                missing.append(raw)
                break
            node = node[part]
        checked += 1
    assert checked >= 40, checked
    assert not missing, missing


def test_markdown_heading_slug_matches_github_ids():
    from ui.app_dialogs import markdown_heading_slug

    assert markdown_heading_slug("OCR (text recognition)") == "ocr-text-recognition"
    assert markdown_heading_slug("Forms, tables and layout") == "forms-tables-and-layout"
    assert markdown_heading_slug("Protect, redact and sign") == "protect-redact-and-sign"
    assert markdown_heading_slug("Password-protected PDFs") == "password-protected-pdfs"


def test_contents_links_scroll_to_their_sections(qtbot):
    """Qt's Markdown reader adds no heading anchors; every in-page link must still reach its heading."""
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QTextBrowser

    from ui.app_dialogs import UserGuideDialog

    dlg = UserGuideDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.waitExposed(dlg)
    view = dlg.findChild(QTextBrowser)
    doc = view.document()

    anchors: dict[str, int] = {}  # anchor name -> block number of its heading
    block = doc.begin()
    while block.isValid():
        for frag in block.textFormats():
            fmt = frag.format.toCharFormat()
            for name in fmt.anchorNames():
                assert block.blockFormat().headingLevel() > 0, (name, block.text())
                anchors[name] = block.blockNumber()
            assert not (fmt.anchorNames() and fmt.anchorHref()), "heading anchors must not become links"
        block = block.next()

    targets = list(dict.fromkeys(re.findall(r"\]\(#([^)\s]+)\)", GUIDE.read_text(encoding="utf-8"))))
    assert len(targets) >= 19, targets
    assert not [t for t in targets if t not in anchors], sorted(set(targets) - set(anchors))

    bar = view.verticalScrollBar()
    for target in ("getting-started", "ocr-text-recognition", "additional-documentation"):
        bar.setValue(0)
        view.setSource(QUrl("#" + target))  # what clicking the link does
        qtbot.waitUntil(lambda: bar.value() > 0, timeout=2000)
        # The heading's top is at the top of the view (or, near the end of the guide, fully in view)
        heading_top = int(doc.documentLayout().blockBoundingRect(doc.findBlockByNumber(anchors[target])).top())
        if bar.value() < bar.maximum():
            assert abs(bar.value() - heading_top) <= 2, (target, bar.value(), heading_top)
        else:
            assert bar.value() <= heading_top <= bar.value() + view.viewport().height(), target


def test_start_menu_user_guide_mode_shows_only_the_guide(qtbot):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMainWindow, QTextBrowser

    import app.bootstrap as bootstrap

    seen: dict = {}

    def inspect_and_close():
        dlg = QApplication.activeModalWidget()
        seen["title"] = dlg.windowTitle() if dlg else None
        if dlg is not None:
            doc = dlg.findChild(QTextBrowser).document()
            seen["headings"] = [
                doc.findBlockByNumber(i).text()
                for i in range(doc.blockCount())
                if doc.findBlockByNumber(i).blockFormat().headingLevel() == 2
            ]
            dlg.reject()

    QTimer.singleShot(800, inspect_and_close)
    assert bootstrap.main(["MonographPDF.exe", "--user-guide"]) == 0
    assert seen["title"] == "Monograph PDF User Guide"
    assert seen["headings"][0] == "Contents" and seen["headings"][-1] == "Additional documentation"
    assert not [w for w in QApplication.topLevelWidgets() if isinstance(w, QMainWindow) and w.isVisible()]
