"""Font drop-down: the font in use is highlighted, scrolled to, kept in sync and never changed by opening."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402


@pytest.fixture
def picker(qtbot):
    from ui.font_picker import FontPicker
    from ui.main_window import create_application

    create_application(["monograph-pdf-fonts"])
    p = FontPicker()
    qtbot.addWidget(p)
    p.resize(240, 28)
    p.show()
    if p.count() < 3:
        pytest.skip("no installed fonts in this environment")
    return p


def _row_pixel(picker, row: int, x: int = 1) -> QColor:
    view = picker.view()
    rect = view.visualRect(picker.model().index(row, 0))
    img = view.viewport().grab().toImage()
    k = img.devicePixelRatio() or 1.0  # a scaled display (150 %) grabs more pixels than logical points
    return QColor(img.pixel(int(x * k), int(rect.center().y() * k)))


def _installed(picker, name: str) -> bool:
    return picker.findText(name, Qt.MatchFlag.MatchFixedString) >= 0


def test_active_font_is_highlighted_and_scrolled_into_view(picker, qtbot):
    last = picker.count() - 1
    family = picker.itemText(last)  # far down the list: must be scrolled to
    picker.set_family(family)
    assert picker.active_row() == last
    picker.showPopup()
    qtbot.wait(50)
    view = picker.view()
    assert view.currentIndex().row() == last
    rect = view.visualRect(picker.model().index(last, 0))
    assert rect.isValid() and 0 <= rect.top() < view.viewport().height(), "active font not scrolled into view"
    from ui.theme import current_palette

    accent = QColor(current_palette().accent)
    marker = _row_pixel(picker, last, x=1)
    assert (marker.red(), marker.green(), marker.blue()) == (accent.red(), accent.green(), accent.blue())
    picker.hidePopup()


def test_other_rows_are_not_marked(picker, qtbot):
    picker.set_family(picker.itemText(0))
    picker.showPopup()
    qtbot.wait(50)
    from ui.theme import current_palette

    accent = QColor(current_palette().accent)
    other = _row_pixel(picker, 1, x=1)
    assert (other.red(), other.green(), other.blue()) != (accent.red(), accent.green(), accent.blue())
    picker.hidePopup()


def test_opening_the_list_never_emits_or_changes_the_font(picker, qtbot):
    picker.set_family(picker.itemText(2))
    got = []
    picker.fontPicked.connect(got.append)
    for _ in range(3):
        picker.showPopup()
        qtbot.wait(30)
        picker.hidePopup()
    assert got == [] and picker.family() == picker.itemText(2)


def test_choosing_another_font_applies_once_and_reopening_shows_it(picker, qtbot):
    picker.set_family(picker.itemText(0))
    got = []
    picker.fontPicked.connect(got.append)
    target = picker.itemText(4)
    picker._pick(target)  # noqa: SLF001 — same path as clicking a row
    assert got == [target] and picker.active_row() == 4
    picker.showPopup()
    qtbot.wait(30)
    assert picker.view().currentIndex().row() == 4
    picker.hidePopup()


def test_keyboard_navigation_confirms_with_enter(picker, qtbot):
    picker.set_family(picker.itemText(0))
    got = []
    picker.fontPicked.connect(got.append)
    picker.showPopup()
    qtbot.wait(30)
    view = picker.view()
    QTest.keyClick(view, Qt.Key.Key_Down)
    QTest.keyClick(view, Qt.Key.Key_Return)
    qtbot.wait(30)
    assert got == [picker.itemText(1)]
    assert picker.active_row() == 1


def test_unavailable_pdf_font_selects_nothing_else(picker, qtbot):
    picker.set_family("Some-Embedded-Only-Font")
    assert picker.currentText() == "Some-Embedded-Only-Font"
    assert picker.family() == "Some-Embedded-Only-Font"
    assert picker.active_row() == -1
    got = []
    picker.fontPicked.connect(got.append)
    picker.showPopup()
    qtbot.wait(30)
    assert not picker.view().selectionModel().selectedIndexes()
    picker.hidePopup()
    assert got == [] and picker.family() == "Some-Embedded-Only-Font"
    # an installed font afterwards is selected normally
    picker.set_family(picker.itemText(3))
    assert picker.active_row() == 3


def test_helvetica_is_not_silently_shown_as_arial(picker):
    if _installed(picker, "Helvetica"):
        pytest.skip("Helvetica is installed")
    picker.set_family("Helvetica")
    assert picker.currentText() == "Helvetica" and picker.active_row() == -1


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_marker_is_visible_in_both_themes(picker, qtbot, theme):
    from ui import theme as themes

    from PySide6.QtWidgets import QApplication

    themes.apply_theme(QApplication.instance(), theme)
    picker.set_family(picker.itemText(0))
    picker.showPopup()
    qtbot.wait(50)
    acc = QColor(themes.current_palette().accent)
    px = _row_pixel(picker, 0, x=1)
    assert (px.red(), px.green(), px.blue()) == (acc.red(), acc.green(), acc.blue())
    bg = _row_pixel(picker, 1, x=40)
    # the tinted active row differs from a neutral row, and both stay distinguishable from the accent bar
    assert _row_pixel(picker, 0, x=40) != bg
    picker.hidePopup()


def test_toolbar_picker_follows_selected_text_box(qtbot, tmp_path, monkeypatch):
    import fitz

    from core import user_prefs
    from core.editing.geometry import Rect
    from core.editing.text_box import TextBox
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-fonts-sync"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1200, 800)
    win.show()
    src = tmp_path / "a.pdf"
    d = fitz.open()
    d.new_page()
    d.save(src.as_posix())
    d.close()
    assert win.open_path(src)
    try:
        edit = win._edit  # noqa: SLF001
        picker = win._font_family  # noqa: SLF001
        if picker.count() < 3:
            pytest.skip("no installed fonts")
        courier = "Courier New" if _installed(picker, "Courier New") else picker.itemText(5)
        a = TextBox(page_index=0, rect=Rect(50, 50, 150, 30), text="One")
        a.style.font_family = courier
        b = TextBox(page_index=0, rect=Rect(50, 120, 150, 30), text="Two")
        b.style.font_family = "Embedded-Only-Font"
        edit.add_object(a)
        edit.add_object(b)
        edit.select([a.object_id])
        win._update_context_toolbar()  # noqa: SLF001
        assert picker.family() == courier and picker.active_row() == picker.findText(courier, Qt.MatchFlag.MatchFixedString)
        edit.select([b.object_id])
        win._update_context_toolbar()  # noqa: SLF001
        assert picker.family() == "Embedded-Only-Font" and picker.active_row() == -1
        # opening the list leaves both boxes' fonts alone
        picker.showPopup()
        qtbot.wait(30)
        picker.hidePopup()
        assert (a.style.font_family, b.style.font_family) == (courier, "Embedded-Only-Font")
    finally:
        win.close_document(save_session=False)
        win.close()


def test_row_painter_never_raises(picker, qtbot):
    """Regression: an exception in the row painter ended the whole app (font_picker:28). The painter is
    Monograph PDF's own (it no longer wraps Qt's, which Qt may delete) and falls back on any error."""
    from PySide6.QtCore import QModelIndex
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem

    from ui.font_picker import FontRowDelegate

    delegate = picker.itemDelegate()
    assert delegate is picker._font_delegate and isinstance(delegate, FontRowDelegate)  # noqa: SLF001
    img = QImage(200, 30, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    try:
        option = QStyleOptionViewItem()
        option.rect = img.rect()
        for index in (picker.model().index(0, 0), QModelIndex()):  # a real row and an invalid one
            delegate.paint(painter, option, index)
            assert delegate.sizeHint(option, index).height() > 0
        picker.set_family(picker.itemText(0))  # active row path as well
        delegate.paint(painter, option, picker.model().index(0, 0))
        delegate._picker = None  # noqa: SLF001 — picker not reachable
        delegate.paint(painter, option, picker.model().index(0, 0))
    finally:
        painter.end()


def test_one_click_opens_the_list_but_not_while_typing_a_search(picker, qtbot):
    picker.set_family(picker.itemText(1))
    QTest.mouseClick(picker.lineEdit(), Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: picker.view().isVisible(), timeout=2000)
    assert picker.family() == picker.itemText(1), "opening the list must not change the font"
    picker.hidePopup()
    qtbot.waitUntil(lambda: not picker.view().isVisible(), timeout=2000)
    picker.lineEdit().setText("ti")  # the user is typing a search
    QTest.mouseClick(picker.lineEdit(), Qt.MouseButton.LeftButton)
    qtbot.wait(50)
    assert not picker.view().isVisible(), "a click while typing must only place the cursor"


def test_font_list_scrolls_evenly(picker):
    from PySide6.QtWidgets import QAbstractItemView

    view = picker.view()
    assert view.verticalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel
    if hasattr(view, "uniformItemSizes"):
        assert view.uniformItemSizes()

def test_bundled_fonts_are_listed_with_installed_fonts(picker):
    from core.editing.font_resolver import _QT_REGISTERED

    assert _QT_REGISTERED, "bundled fonts were not registered"
    for family in ("Noto Sans", "Noto Serif"):
        assert picker.findText(family, Qt.MatchFlag.MatchFixedString) >= 0, family
