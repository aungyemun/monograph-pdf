"""Branding UI: icon, About, exact copyright, window-centered footer."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from core.product_meta import COPYRIGHT_DISPLAY, PRODUCT_NAME, get_product_identity


@pytest.fixture
def window(qtbot):
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-branding-test"])
    win = MainWindow()
    qtbot.addWidget(win)
    yield win
    win.close_document(save_session=False)
    win.close()


def test_window_icon_and_title(window):
    assert not window.windowIcon().isNull()
    assert window.windowTitle() == PRODUCT_NAME


def test_footer_copyright_exact_and_centered(window, qtbot):
    status = window._status  # noqa: SLF001
    assert status.copyright_label.text() == COPYRIGHT_DISPLAY
    window.resize(1100, 700)
    status.resize(1100, status.height() or 24)
    status._position_copyright()  # noqa: SLF001
    bar_w = status.width()
    lab = status.copyright_label
    center_label = lab.x() + lab.width() / 2
    center_bar = bar_w / 2
    assert abs(center_label - center_bar) <= 3


def test_footer_narrow_preserves_copyright_owner(window, qtbot):
    status = window._status  # noqa: SLF001
    window.resize(500, 600)
    status.resize(480, status.height() or 24)
    status._position_copyright()  # noqa: SLF001
    text = status.copyright_label.text()
    assert "Aung Ye Mun" in text
    assert "©" in text


def test_about_dialog_branding(window, qtbot):
    from pathlib import Path

    from PySide6.QtWidgets import QLabel, QTreeWidget

    from ui.about_dialog import AboutDialog
    from ui.app_dialogs import find_user_guide

    dlg = AboutDialog(window)
    qtbot.addWidget(dlg)
    identity = get_product_identity()
    assert dlg.windowTitle() == identity.about_title
    logos = [w for w in dlg.findChildren(QLabel) if w.objectName() == "AboutLogo"]
    assert logos and logos[0].pixmap() is not None and not logos[0].pixmap().isNull()
    copies = [w for w in dlg.findChildren(QLabel) if w.objectName() == "AboutCopyright"]
    assert copies and copies[0].text() == COPYRIGHT_DISPLAY
    versions = [w for w in dlg.findChildren(QLabel) if w.objectName() == "AboutVersion"]
    assert versions and identity.version in versions[0].text()

    trees = [w for w in dlg.findChildren(QTreeWidget) if w.objectName() == "AboutComponents"]
    assert trees and trees[0].columnCount() == 4
    statuses, names = [], []
    for i in range(trees[0].topLevelItemCount()):
        item = trees[0].topLevelItem(i)
        statuses.append(item.text(2))
        names.append(item.text(0))
        # Normal About must not expose absolute development paths.
        for col in range(4):
            assert ":\\" not in item.text(col)
            assert "/Users/" not in item.text(col)
    assert any(s == "Bundled" for s in statuses)
    # Only components shipped inside Monograph PDF: Office suites have their own tab, build tools are not listed.
    assert not any(n in ("Microsoft Office", "LibreOffice", "Inno Setup", "qpdf") for n in names), names
    assert not any("Build-time" in s for s in statuses)

    guide = find_user_guide()
    assert guide is not None and guide.name == "USER_GUIDE.md"
    assert "user_guide" not in Path(guide).as_posix().split("/")[-2:]
    dlg.close()


def test_theme_copyright_visible_light_dark(window):
    from PySide6.QtWidgets import QApplication

    from ui.theme import apply_theme

    app = QApplication.instance()
    assert app is not None
    for theme in ("light", "dark"):
        apply_theme(app, theme)
        label = window._status.copyright_label  # noqa: SLF001
        assert not label.isHidden()
        assert COPYRIGHT_DISPLAY in label.text() or "Aung Ye Mun" in label.text()


def test_about_shows_monograph_pdf_identity_without_product_history(window, qtbot):
    from PySide6.QtWidgets import QLabel, QPushButton, QTabWidget

    from core.product_meta import PRODUCT_DESCRIPTION
    from ui.about_dialog import AboutDialog

    dlg = AboutDialog(window)
    qtbot.addWidget(dlg)
    labels = {w.objectName(): w.text() for w in dlg.findChildren(QLabel) if w.objectName()}
    assert labels["AboutTitle"] == "Monograph PDF"
    assert labels["AboutVersion"] == f"Version {get_product_identity().version}"
    assert labels["AboutTagline"] == PRODUCT_DESCRIPTION
    assert "AboutHistory" not in labels
    shown = " ".join(w.text() for w in dlg.findChildren(QLabel))
    for banned in ("PDF Editor", "succeeds", "formerly", "previously known", "final release"):
        assert banned not in shown, banned
    tabs = dlg.findChildren(QTabWidget)[0]
    names = [tabs.tabText(i) for i in range(tabs.count())]
    assert "Components" in names and "Office Integration" in names, names
    buttons = [b.text() for b in dlg.findChildren(QPushButton)]
    assert "View License…" in buttons and "Third-Party Notices…" in buttons, buttons
    # no development paths on the normal About screen
    text = " ".join(labels.values())
    assert "Software" + " testing" not in text and "\\Users\\" not in text


def test_window_and_application_icon_is_the_new_logo(window):
    from PySide6.QtWidgets import QApplication

    from core.product_meta import resolve_app_icon_path

    assert resolve_app_icon_path().name == "monograph_pdf.ico"
    icon = QApplication.instance().windowIcon()
    sizes = {(s.width(), s.height()) for s in icon.availableSizes()}
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes, sizes
