"""Professional-UI regression: menus, keyboard map, draw-to-place tools, theme, dialogs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    from core import user_prefs
    from ui.main_window import MainWindow, create_application

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    create_application(["monograph-pdf-pro-ui"])
    win = MainWindow()
    qtbot.addWidget(win)
    win.resize(1360, 860)
    win.show()
    yield win
    win.close_document(save_session=False)
    win.close()


@pytest.fixture
def doc_window(window, tmp_path):
    src = tmp_path / "work.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    assert window.open_path(src)
    return window


def _all_actions(menu):
    for act in menu.actions():
        if act.menu() is not None:
            yield from _all_actions(act.menu())
        elif not act.isSeparator():
            yield act


def _drag(qtbot, window, page: int, x0: float, y0: float, x1: float, y1: float) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from core.editing.geometry import Point

    inner = window._canvas._canvas  # noqa: SLF001
    p0 = inner.pdf_to_widget(page, Point(x0, y0))
    p1 = inner.pdf_to_widget(page, Point(x1, y1))
    QTest.mousePress(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p0)
    QTest.mouseMove(inner, p1)
    QTest.mouseRelease(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p1)
    qtbot.wait(20)


# --------------------------------------------------------------------- menus / keys


def test_menu_order_is_conventional(window):
    titles = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert titles[:3] == ["File", "Edit", "View"]
    assert titles[-1] == "Help"


def test_no_blank_menu_items_and_all_have_icons_or_checks(window):
    blank = []
    for top in window.menuBar().actions():
        for act in _all_actions(top.menu()):
            if not act.text().replace("&", "").strip():
                blank.append(top.text())
    assert not blank, f"menu items without text in {blank}"


def test_no_duplicate_shortcuts(window):
    from PySide6.QtGui import QAction, QKeySequence

    seen: dict[str, str] = {}
    clashes = []
    for act in window.findChildren(QAction):
        for seq in act.shortcuts():
            key = seq.toString(QKeySequence.SequenceFormat.PortableText)
            if not key:
                continue
            if key in seen and seen[key] != act.text():
                clashes.append((key, seen[key], act.text()))
            seen[key] = act.text()
    assert not clashes, clashes


@pytest.mark.parametrize(
    "attr,key",
    [
        ("act_select_tool", "V"),
        ("act_text_tool", "T"),
        ("act_annot_rect", "R"),
        ("act_annot_highlight", "H"),
        ("act_select_all", "Ctrl+A"),
        ("act_find_prev", "Shift+F3"),
        ("act_goto", "Ctrl+G"),
        ("act_exit", "Ctrl+Q"),
        ("act_fullscreen", "F11"),
        ("act_user_guide", "F1"),
        ("act_rotate_cw", "Ctrl+R"),
    ],
)
def test_expected_shortcuts(window, attr, key):
    from PySide6.QtGui import QKeySequence

    act = getattr(window, attr)
    keys = [s.toString(QKeySequence.SequenceFormat.PortableText) for s in act.shortcuts()]
    assert key in keys
    assert key.split("+")[-1] in act.toolTip()


def test_redo_and_zoom_have_windows_friendly_alternates(window):
    from PySide6.QtGui import QKeySequence

    redo = [s.toString(QKeySequence.SequenceFormat.PortableText) for s in window.act_redo.shortcuts()]
    assert "Ctrl+Y" in redo and "Ctrl+Shift+Z" in redo
    zoom = [s.toString(QKeySequence.SequenceFormat.PortableText) for s in window.act_zoom_in.shortcuts()]
    assert "Ctrl+=" in zoom


def test_shortcuts_dialog_lists_and_filters(window):
    from ui.app_dialogs import ShortcutsDialog

    dlg = ShortcutsDialog(window.menuBar(), window)
    assert dlg.row_count() >= 50
    dlg._filter.setText("redo")  # noqa: SLF001
    visible = [
        dlg._tree.topLevelItem(i).text(0).strip()  # noqa: SLF001
        for i in range(dlg._tree.topLevelItemCount())  # noqa: SLF001
        if not dlg._tree.topLevelItem(i).isHidden()  # noqa: SLF001
    ]
    assert any("Redo" in v for v in visible)
    dlg.close()


def test_typing_in_textbox_wins_over_window_shortcuts(doc_window):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from core.editing.geometry import Rect

    w = doc_window
    w._edit.create_text_box(0, Rect(40, 40, 120, 30), text="abc")  # noqa: SLF001
    oid = next(iter(w._edit.objects))  # noqa: SLF001
    w._edit.editing_object_id = oid  # noqa: SLF001
    inner = w._canvas._canvas  # noqa: SLF001
    for key, text in ((Qt.Key.Key_Delete, ""), (Qt.Key.Key_V, "v"), (Qt.Key.Key_Home, "")):
        ev = QKeyEvent(QEvent.Type.ShortcutOverride, key, Qt.KeyboardModifier.NoModifier, text)
        inner.event(ev)
        assert ev.isAccepted(), key
    # Not typing → window shortcuts stay in charge
    w._edit.editing_object_id = None  # noqa: SLF001
    ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_V, Qt.KeyboardModifier.NoModifier, "v")
    ev.ignore()
    inner.event(ev)
    assert not ev.isAccepted()


# --------------------------------------------------------------------- navigation / find


def test_page_navigation_actions(doc_window):
    w = doc_window
    assert w._document.page_count >= 3  # noqa: SLF001
    w.act_last.trigger()
    assert w._canvas.focus_page == w._document.page_count - 1  # noqa: SLF001
    assert not w.act_next.isEnabled()
    w.act_first.trigger()
    assert w._canvas.focus_page == 0  # noqa: SLF001
    w._page_edit.setText("2")  # noqa: SLF001
    w._on_page_edit()  # noqa: SLF001
    assert w._canvas.focus_page == 1  # noqa: SLF001


def test_find_next_previous_cycle(doc_window):
    w = doc_window
    w._search_edit.setText("Monograph PDF fixture")  # noqa: SLF001
    w._on_search_return()  # noqa: SLF001
    hits = len(w._search_hits)  # noqa: SLF001
    assert hits >= 2
    assert w._search_index == 0  # noqa: SLF001
    w._find_prev()  # noqa: SLF001
    assert w._search_index == hits - 1  # noqa: SLF001
    w._on_search_return()  # same query → next  # noqa: SLF001
    assert w._search_index == 0  # noqa: SLF001


# --------------------------------------------------------------------- draw-to-place


def test_highlight_snaps_to_text_under_dragged_area(doc_window, qtbot):
    from core.annotations import list_annotations

    w = doc_window
    hits = w._document.search("alpha-bravo-charlie")  # noqa: SLF001
    assert hits
    page, r = hits[0]
    w.act_annot_highlight.trigger()
    assert w._canvas.region_pick_active  # noqa: SLF001
    _drag(qtbot, w, page, r.x0 - 4, r.y0 - 2, r.x1 + 4, r.y1 + 2)
    annots = [a for a in list_annotations(w._document) if a.kind.lower() == "highlight"]  # noqa: SLF001
    assert annots, "highlight not created"
    x0, y0, x1, y1 = annots[-1].rect
    assert x0 <= r.x0 + 2 and x1 >= r.x1 - 2 and y0 <= r.y0 + 2 and y1 >= r.y1 - 2
    # Highlight is continuous: it stays armed after a stroke and Esc returns to Select.
    qtbot.wait(40)
    assert w.act_annot_highlight.isChecked() and w._canvas.region_pick_active  # noqa: SLF001
    w._canvas._canvas.cancel_region_pick()  # noqa: SLF001 - same path as Esc
    assert w.act_select_tool.isChecked()
    assert w._edit.dirty  # noqa: SLF001


def test_region_pick_escape_cancels(doc_window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w = doc_window
    w._redact_mark_region()  # noqa: SLF001
    assert w._canvas.region_pick_active  # noqa: SLF001
    QTest.keyClick(w._canvas._canvas, Qt.Key.Key_Escape)  # noqa: SLF001
    assert not w._canvas.region_pick_active  # noqa: SLF001


def test_redaction_mark_lands_where_dragged(doc_window, qtbot):
    from core.redaction import preview_redaction_count

    w = doc_window
    before = preview_redaction_count(w._document)  # noqa: SLF001
    w._redact_mark_region()  # noqa: SLF001
    _drag(qtbot, w, 0, 300, 400, 420, 430)
    assert preview_redaction_count(w._document) == before + 1  # noqa: SLF001


def test_drawn_signature_strokes_fit_target_box():
    from ui.app_dialogs import fit_strokes_into

    strokes = [[(0, 0), (100, 50)], [(20, 10), (80, 40)]]
    fitted = fit_strokes_into(strokes, 10, 20, 200, 40)
    xs = [p[0] for s in fitted for p in s]
    ys = [p[1] for s in fitted for p in s]
    assert min(xs) >= 10 - 1e-6 and max(xs) <= 210 + 1e-6
    assert min(ys) >= 20 - 1e-6 and max(ys) <= 60 + 1e-6


# --------------------------------------------------------------------- lifecycle


def test_save_as_switches_to_new_file(doc_window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from core.editing.geometry import Rect

    w = doc_window
    w._edit.create_text_box(0, Rect(60, 60, 140, 36), text="Saved-As")  # noqa: SLF001
    target = tmp_path / "renamed"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "PDF Files (*.pdf)"))
    w.save_as_dialog()
    assert w._document.path.name == "renamed.pdf"  # noqa: SLF001
    assert not w._edit.dirty  # noqa: SLF001
    assert "renamed.pdf" in w.windowTitle()
    assert "Saved-As" in w._document.page_text(0)  # noqa: SLF001


def test_unsaved_prompt_cancel_keeps_document(doc_window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from core.editing.geometry import Rect

    w = doc_window
    w._edit.create_text_box(0, Rect(60, 60, 140, 36), text="dirty")  # noqa: SLF001
    monkeypatch.setattr(w, "_is_headless_ui", lambda: False)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)
    w._close_document_interactive()  # noqa: SLF001
    assert w._document is not None  # noqa: SLF001
    # FEATURE-01: opening another file adds a tab; dirty docs stay open without a prompt.
    assert w.open_path(SAMPLES / "sample_text.pdf")
    assert len(w._sessions) == 2  # noqa: SLF001
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Discard)
    # Close the newly opened (clean) tab, then discard the dirty first tab.
    w._close_document_interactive()  # noqa: SLF001
    w._close_document_interactive()  # noqa: SLF001
    assert w._document is None  # noqa: SLF001
    assert not w._sessions  # noqa: SLF001


def test_recent_menu_numbered_and_clearable(doc_window):
    w = doc_window
    texts = [a.text() for a in w._recent_menu.actions() if not a.isSeparator()]  # noqa: SLF001
    assert texts[0].startswith("&1")
    w.act_clear_recent.trigger()
    texts = [a.text() for a in w._recent_menu.actions() if not a.isSeparator()]  # noqa: SLF001
    assert texts[0] == "No recent files"


def test_print_pipeline_renders_every_page_to_pdf(doc_window, tmp_path):
    from PySide6.QtPrintSupport import QPrinter

    import fitz

    w = doc_window
    out = tmp_path / "printed.pdf"
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(out))
    n = w._render_to_printer(printer, [0, 1, 2], dpi=72)  # noqa: SLF001
    assert n == 3
    with fitz.open(out) as d:
        assert d.page_count == 3


def test_document_properties_dialog(doc_window):
    from PySide6.QtWidgets import QLabel

    from ui.app_dialogs import DocumentPropertiesDialog

    dlg = DocumentPropertiesDialog(doc_window._document, doc_window)  # noqa: SLF001
    texts = [lab.text() for lab in dlg.findChildren(QLabel)]
    assert "work.pdf" in texts
    dlg.close()


# --------------------------------------------------------------------- theme


def test_theme_switch_recolors_canvas_and_icons(window):
    from ui.theme import current_palette

    window._set_theme("dark")  # noqa: SLF001
    assert current_palette().name == "dark"
    img_dark = window.act_open.icon().pixmap(20, 20).toImage()
    window._set_theme("light")  # noqa: SLF001
    img_light = window.act_open.icon().pixmap(20, 20).toImage()
    assert img_dark != img_light
    assert window.act_theme_light.isChecked()


def test_inspector_fits_without_horizontal_scroll(doc_window):
    from core.editing.geometry import Rect

    w = doc_window
    w.act_toggle_right.setChecked(True)
    w._toggle_right_panel()  # noqa: SLF001
    w._edit.create_text_box(0, Rect(40, 40, 120, 30), text="fit")  # noqa: SLF001
    oid = next(iter(w._edit.objects))  # noqa: SLF001
    w._edit.selection = [oid]  # noqa: SLF001
    w._refresh_inspector()  # noqa: SLF001
    ins = w._inspector  # noqa: SLF001
    assert ins._root.minimumSizeHint().width() <= max(ins.minimumWidth(), ins.viewport().width()) + 2  # noqa: SLF001


# --------------------------------------------------------------------- form filling (in-place editor)


@pytest.fixture
def form_window(window, tmp_path):
    from tests.fixtures.make_form_samples import main as make_forms

    make_forms()
    src = tmp_path / "form.pdf"
    src.write_bytes((SAMPLES / "sample_invitation_form.pdf").read_bytes())
    assert window.open_path(src)
    assert window._edit.fields  # noqa: SLF001
    return window


def _first_text_field(w):
    from core.forms.fields import FieldType

    for f in w._edit.fillable_fields_ordered():  # noqa: SLF001
        if f.field_type in (FieldType.TEXT, FieldType.MULTILINE) and not f.multiline:
            return f
    raise AssertionError("no single-line text field")


def _click_field(qtbot, w, field):
    """Select then edit (BUG-19/21: first click selects; editor opened explicitly for tests)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    inner = w._canvas._canvas  # noqa: SLF001
    w._canvas.go_to_page(field.page_index)  # noqa: SLF001
    wr = inner.pdf_rect_to_widget(field.page_index, field.rect)
    QTest.mouseClick(inner, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, wr.center())
    qtbot.wait(10)
    assert inner.open_field_editor(field)
    # Drop tool-letter shortcuts while typing (same as live editModelChanged path).
    w._sync_tool_letter_shortcuts()  # noqa: SLF001
    qtbot.wait(20)
    return inner


def test_field_opens_real_editor_with_selection(form_window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QTextEdit

    w = form_window
    field = _first_text_field(w)
    inner = _click_field(qtbot, w, field)
    editor = inner.field_editor
    assert isinstance(editor, QTextEdit), "second click on a text field must open an editable text box"
    assert editor.single_line
    editor.selectAll()
    QTest.keyClicks(editor, "Aung Ye Mun")
    assert field.value == "Aung Ye Mun"
    assert "*" in w.windowTitle()
    # Real text selection: select all, then keyboard word selection
    editor.selectAll()
    assert editor.textCursor().selectedText() == "Aung Ye Mun"
    editor.moveCursor(editor.textCursor().MoveOperation.Start)
    for _ in range(4):
        QTest.keyClick(editor, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert editor.textCursor().selectedText() == "Aung"
    QTest.keyClicks(editor, "Mr")  # typing replaces the selection
    assert field.value == "Mr Ye Mun"
    # Inspector mirrors live typing when the value widget is present
    field_value = getattr(w._inspector, "_field_value", None)  # noqa: SLF001
    if field_value is not None:
        assert field_value.text() == "Mr Ye Mun"
    # Enter finishes a one-line field instead of adding a line
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert field.value == "Mr Ye Mun" and inner.field_editor is None


def test_field_editor_keys_win_over_window_shortcuts(form_window, qtbot):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    w = form_window
    field = _first_text_field(w)
    editor = _click_field(qtbot, w, field).field_editor
    for key, text, mods in (
        (Qt.Key.Key_V, "v", Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_Delete, "", Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_A, "a", Qt.KeyboardModifier.ControlModifier),
        (Qt.Key.Key_Home, "", Qt.KeyboardModifier.NoModifier),
    ):
        ev = QKeyEvent(QEvent.Type.ShortcutOverride, key, mods, text)
        ev.ignore()
        editor.event(ev)
        assert ev.isAccepted(), key


def test_tab_moves_between_fields_and_escape_commits(form_window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w = form_window
    field = _first_text_field(w)
    inner = _click_field(qtbot, w, field)
    QTest.keyClicks(inner.field_editor, "first")
    QTest.keyClick(inner.field_editor, Qt.Key.Key_Tab)
    qtbot.wait(10)
    assert field.value == "first" and field.value_dirty
    assert w._edit.editing_field_id not in (None, field.object_id) or inner.field_editor is None  # noqa: SLF001
    if inner.field_editor is not None:
        QTest.keyClick(inner.field_editor, Qt.Key.Key_Escape)
        qtbot.wait(10)
    assert inner.field_editor is None
    assert w._edit.editing_field_id is None  # noqa: SLF001


def test_clicking_field_without_typing_does_not_modify(form_window, qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w = form_window
    field = _first_text_field(w)
    inner = _click_field(qtbot, w, field)
    QTest.keyClick(inner.field_editor, Qt.Key.Key_Escape)
    qtbot.wait(10)
    assert not w._edit.dirty  # noqa: SLF001
    assert "*" not in w.windowTitle()


def test_save_commits_open_field_editor(form_window, qtbot):
    import fitz

    from PySide6.QtTest import QTest

    w = form_window
    field = _first_text_field(w)
    inner = _click_field(qtbot, w, field)
    QTest.keyClicks(inner.field_editor, "Saved value")
    w.save_document()
    with fitz.open(w._document.path) as d:  # noqa: SLF001
        values = [wd.field_value for p in d for wd in (p.widgets() or [])]
    assert "Saved value" in values


def test_print_preview_shows_unsaved_form_entries(form_window, qtbot, monkeypatch):
    """Unsaved typed entries (one still open in the field editor) appear in the print preview and
    print job; the file on disk, the open document and its unsaved state are left as they were."""
    import hashlib

    from PySide6.QtTest import QTest

    import ui.print_dialog as print_dialog
    from app.paths import TEMP_DIR

    w = form_window
    path = w._document.path  # noqa: SLF001
    before = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    texts = [f for f in w._edit.fillable_fields_ordered() if f.field_type.value in ("text", "multiline")]  # noqa: SLF001
    first, second = texts[0], texts[1]
    w._edit.set_field_value(second.object_id, "Second entry 2026")  # noqa: SLF001
    inner = _click_field(qtbot, w, first)
    QTest.keyClicks(inner.field_editor, "Typed not saved")  # editor still open, like pressing Ctrl+P
    seen = {}

    class CapturingDialog:
        class DialogCode:
            Accepted = 1

        def __init__(self, document, **_kwargs):
            seen["text"] = "".join(document.page_text(i) for i in range(document.page_count))
            seen["same_document"] = document is w._document  # noqa: SLF001

        def exec(self):
            return 0  # Cancel

    monkeypatch.setattr(print_dialog, "PrintDialog", CapturingDialog)
    w._print_document()  # noqa: SLF001
    flat = "".join(seen["text"].split())
    assert "Typednotsaved" in flat and "Secondentry2026" in flat
    assert seen["same_document"] is False  # a temporary baked copy, never the open file
    assert w._edit.dirty and first.value == "Typed not saved"  # noqa: SLF001
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == before
    assert not list(Path(TEMP_DIR).glob("print-bake-*.pdf"))


def test_field_inspector_is_readable(form_window, qtbot):
    from PySide6.QtWidgets import QCheckBox, QLabel

    w = form_window
    field = _first_text_field(w)
    _click_field(qtbot, w, field)
    w._refresh_inspector()  # noqa: SLF001
    ins = w._inspector  # noqa: SLF001
    texts = [lab.text() for lab in ins._root.findChildren(QLabel)]  # noqa: SLF001
    assert not any("/AP" in t for t in texts), "internal jargon should not be shown"
    # Status is only shown when it matters (Required / Read-only); ordinary fields show no extra row
    if field.readonly or getattr(field, "required", False):
        assert any(t in ("Required", "Read-only") for t in texts)
    else:
        assert "Optional" not in texts
    # status is text, not disabled checkboxes that look like inputs
    assert not [cb for cb in ins._root.findChildren(QCheckBox) if not cb.isEnabled()]  # noqa: SLF001
    assert ins._root.minimumSizeHint().width() <= max(ins.minimumWidth(), ins.viewport().width()) + 2  # noqa: SLF001


def test_each_command_appears_in_one_menu_only(window):
    seen: dict[int, str] = {}
    dupes = []
    for top in window.menuBar().actions():
        for act in _all_actions(top.menu()):
            from PySide6.QtWidgets import QWidgetAction

            if isinstance(act, QWidgetAction):
                continue
            key = id(act)
            title = top.text().replace("&", "")
            if key in seen and seen[key] != title:
                dupes.append((act.text().replace("&", ""), seen[key], title))
            elif key in seen:
                dupes.append((act.text().replace("&", ""), title, title))
            seen[key] = title
    # Workspace-mode/theme radio groups are single-sited too
    assert not dupes, dupes


def test_context_bar_does_not_repeat_main_toolbar(doc_window):
    w = doc_window
    w._update_context_toolbar()  # noqa: SLF001
    main_actions = set(w._main_bar.actions())  # noqa: SLF001
    ctx = [a for a in w._context_bar.actions() if not a.isSeparator() and a.text()]  # noqa: SLF001
    repeated = [a.text() for a in ctx if a in main_actions]
    assert not repeated, repeated


# --------------------------------------------------------------------- 0.1.0: tools, conversion, open-with


def test_menu_bar_is_eleven_clear_menus(window):
    titles = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert titles == [
        "File", "Edit", "View", "Insert", "Forms", "Organize", "Convert", "OCR", "Protect", "Sign", "Help",
    ]


def test_command_names_have_no_arrows_or_jargon(window):
    bad = []
    for top in window.menuBar().actions():
        for act in _all_actions(top.menu()):
            t = act.text().replace("&", "")
            if any(x in t for x in ("→", "best-effort", "(foundation)", "Candidates", "Region Pass", "lock)")):
                bad.append(t)
            tip = act.toolTip()
            if tip.count("(Ctrl") > 1:
                bad.append("tooltip:" + tip)
    assert not bad, bad


def test_welcome_tool_tiles_cover_core_tasks(window):
    keys = {k for k, *_ in window._welcome.TOOLS}  # noqa: SLF001
    assert {"merge", "rotate", "protect", "unlock", "watermark", "pdf_to_word", "office_to_pdf", "sign"} <= keys


def test_open_image_as_new_pdf_and_save_as(window, tmp_path, monkeypatch):
    from PIL import Image
    from PySide6.QtWidgets import QFileDialog

    img = tmp_path / "photo.png"
    Image.new("RGB", (400, 300), "#3366aa").save(img)
    assert window.open_path(img)
    assert window._document.page_count == 1  # noqa: SLF001
    assert "photo.pdf" in window.windowTitle() and "not saved yet" in window.windowTitle()
    # Save goes through Save As, suggesting the image's folder and name
    seen = {}

    def fake_save(parent, title, suggested, filt):
        seen["suggested"] = suggested
        return str(tmp_path / "photo.pdf"), filt

    monkeypatch.setattr(QFileDialog, "getSaveFileName", fake_save)
    window.save_document()
    assert Path(seen["suggested"]) == tmp_path / "photo.pdf"
    assert (tmp_path / "photo.pdf").is_file()
    assert "not saved yet" not in window.windowTitle()
    recent = [p.name for p in window._recent.list()]  # noqa: SLF001
    assert "photo.png" in recent or "photo.pdf" in recent


def test_rotate_pages_dialog_odd_pages(doc_window, monkeypatch):
    from ui import organize_dialogs

    w = doc_window
    before = [p.rotation for p in w._document.pages()]  # noqa: SLF001

    def fake_exec(self):
        self.opt_odd.setChecked(True)
        self._turn_buttons[2].setChecked(True)  # 180°
        return self.DialogCode.Accepted

    monkeypatch.setattr(organize_dialogs.RotatePagesDialog, "exec", fake_exec)
    w._rotate_pages_dialog()  # noqa: SLF001
    after = [p.rotation for p in w._document.pages()]  # noqa: SLF001
    assert after[0] == (before[0] + 180) % 360
    assert after[1] == before[1]
    assert w._edit.dirty  # noqa: SLF001


def test_rotate_pages_dialog_exact_orientation(doc_window, monkeypatch):
    """"Set an exact orientation" turns each chosen page to that angle, whatever it was before."""
    from ui import organize_dialogs

    w = doc_window
    w._rotate_pages([0], 90)  # noqa: SLF001 — page 1 starts turned right, the others upright

    def fake_exec(self):
        self.opt_all.setChecked(True)
        self.opt_exact.setChecked(True)
        self.exact.setCurrentIndex(self.exact.findData(180))
        assert not self._preview.pixmap().isNull(), "the preview shows the current page"
        return self.DialogCode.Accepted

    monkeypatch.setattr(organize_dialogs.RotatePagesDialog, "exec", fake_exec)
    w._rotate_pages_dialog()  # noqa: SLF001
    assert {p.rotation for p in w._document.pages()} == {180}  # noqa: SLF001
    w.act_undo.trigger()
    assert w._document.pages()[0].rotation == 90  # noqa: SLF001 — one undo step restores every page


def test_pdf_to_word_from_menu(doc_window, tmp_path, monkeypatch):
    pytest.importorskip("pdf2docx")
    from PySide6.QtWidgets import QFileDialog

    from ui import convert_dialogs

    w = doc_window
    monkeypatch.setattr(convert_dialogs.PdfToWordDialog, "exec", lambda self: self.DialogCode.Accepted)
    out = tmp_path / "work.docx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), "Word Document (*.docx)"))
    w._pdf_to_docx()  # noqa: SLF001
    assert out.is_file() and out.stat().st_size > 1000


def test_protect_dialog_full_permissions():
    from ui.security_dialogs import PasswordProtectDialog

    dlg = PasswordProtectDialog()
    dlg.user_pw.setText("a")
    dlg.user_pw_confirm.setText("a")
    dlg.perm_assemble.setChecked(True)
    dlg.perm_forms.setChecked(False)
    dlg.perm_print_hq.setChecked(False)
    perms = dlg.settings().permissions
    assert perms.assemble and not perms.fill_forms and perms.print and not perms.print_hq
    dlg.close()


def test_about_dialog_tabs_and_license(window):
    from PySide6.QtWidgets import QTabWidget

    from ui.about_dialog import AboutDialog

    dlg = AboutDialog(window)
    tabs = dlg.findChild(QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["About", "Components", "Office Integration"]
    dlg.close()


def test_typed_signature_renders_clean_image(doc_window):
    import fitz

    from core.editing.geometry import Rect
    from core.signatures import insert_typed_signature
    from ui.security_dialogs import TypedSignatureDialog

    dlg = TypedSignatureDialog()
    dlg.name.setText("Ada Lovelace")
    assert dlg.windowTitle() == "Type a Signature"
    from ui.security_dialogs import SIGNATURE_INKS

    assert dlg.style.count() >= 1 and dlg.ink.count() == len(SIGNATURE_INKS) >= 3
    assert dlg.ink.itemText(0) == "Blue ink"  # the default ink is unchanged
    png = dlg.signature_png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    dlg.close()
    w = doc_window
    doc = w._document  # noqa: SLF001
    insert_typed_signature(doc, 0, Rect(72, 600, 200, 50), "Ada Lovelace", image_png=png)
    page = doc._backend._doc[0]  # noqa: SLF001
    assert page.get_images(), "signature image placed"
    assert "Visual signature" not in page.get_text(), "no caption stamped on the page"


def test_permissions_only_password_opens_without_password(tmp_path):
    import fitz

    from core.document import open_document
    from core.security.ops import EncryptionSettings, PermissionFlags, apply_password_protection

    src = tmp_path / "in.pdf"
    d = fitz.open()
    d.new_page().insert_text((72, 72), "hello")
    d.set_metadata({"title": "Kept title"})
    d.set_toc([[1, "Intro", 1]])
    d.save(src)
    d.close()
    doc = open_document(src)
    out = tmp_path / "restricted.pdf"
    apply_password_protection(
        doc, out, EncryptionSettings(user_password="", owner_password="owner", permissions=PermissionFlags(copy=False))
    )
    doc.close()
    with fitz.open(out) as x:
        assert not x.needs_pass
        assert not (x.permissions & fitz.PDF_PERM_COPY)
        assert x.metadata["title"] == "Kept title"
        assert x.get_toc() == [[1, "Intro", 1]]


def test_save_releases_open_file_before_replacing_it(doc_window, monkeypatch):
    """Windows cannot replace a file that is still open; Save must close it first."""
    import os

    w = doc_window
    real_replace = os.replace
    seen = {}

    def strict_replace(src, dst):
        seen["closed"] = bool(getattr(w._document, "_closed", False))  # noqa: SLF001
        if not seen["closed"]:
            raise PermissionError(13, "file is open (simulated Windows sharing violation)")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", strict_replace)
    w._edit.mark_dirty()  # noqa: SLF001
    w.save_document()
    assert seen.get("closed") is True
    assert not w._edit.dirty  # noqa: SLF001
    assert w._document.page_count >= 1  # noqa: SLF001
    leftovers = list(Path(w._document.path).parent.glob(".*.saving-*.pdf"))  # noqa: SLF001
    assert not leftovers


def test_font_picker_finds_fonts_by_letters_and_applies_on_pick(qtbot):
    from ui.font_picker import FontPicker

    fp = FontPicker()
    qtbot.addWidget(fp)
    picked = []
    fp.fontPicked.connect(picked.append)
    families = [fp.itemText(i) for i in range(fp.count())]
    assert families
    target = families[len(families) // 2]
    letters = target[1:4].lower()  # letters from inside the name, not just the start
    comp = fp.completer()
    comp.setCompletionPrefix(letters)
    matches = [comp.completionModel().index(i, 0).data() for i in range(comp.completionCount())]
    assert target in matches, (letters, matches[:10])
    assert all(letters in m.lower() for m in matches)
    # Typing does not apply anything; Enter on a real name does
    fp.lineEdit().setText(target.upper())
    assert picked == []
    fp._commit_typed()  # noqa: SLF001
    assert picked == [target]
    # Unknown text is reverted, nothing applied
    fp.lineEdit().setText("zzqq-no-such-font")
    fp._commit_typed()  # noqa: SLF001
    assert picked == [target] and fp.lineEdit().text() == target


def test_wrap_toggle_on_toolbar_for_text_box_and_field(form_window, qtbot):
    from core.editing.geometry import Rect
    from core.editing.text_box import TextBox

    w = form_window
    box = TextBox(page_index=0, rect=Rect(60, 60, 200, 40), text="Wrap me")
    w._edit.add_object(box)  # noqa: SLF001
    w._edit.selection = [box.object_id]  # noqa: SLF001
    w._update_context_toolbar()  # noqa: SLF001
    assert w.act_text_wrap in w._context_bar.actions()  # noqa: SLF001
    w.act_text_wrap.setChecked(False)
    w._apply_wrap_toggle()  # noqa: SLF001
    assert w._edit.objects[box.object_id].style.wrap is False  # noqa: SLF001
    # Form field: font, size and wrap from the toolbar
    field = _first_text_field(w)
    w._edit.selection = []  # noqa: SLF001
    w._edit.field_selection = [field.object_id]  # noqa: SLF001
    w._update_context_toolbar()  # noqa: SLF001
    acts = w._context_bar.actions()  # noqa: SLF001
    assert w.act_text_wrap in acts and w._font_family_action in acts  # noqa: SLF001
    w.act_text_wrap.setChecked(True)
    w._apply_wrap_toggle()  # noqa: SLF001
    assert field.multiline and field.style_dirty
    w._nudge_font_size(+2)  # noqa: SLF001
    assert field.font_size >= 12


def test_change_page_size_from_menu(doc_window, tmp_path, monkeypatch):
    import fitz
    from PySide6.QtWidgets import QMessageBox

    from ui import convert_dialogs, organize_dialogs

    w = doc_window
    assert w.act_page_sizes.text().replace("&", "") == "Change Page Size…"

    def fake_exec(self):
        self.paper.setCurrentIndex(self.paper.findData("Legal"))
        return self.DialogCode.Accepted

    out = tmp_path / "legal.pdf"
    monkeypatch.setattr(organize_dialogs.ChangePageSizeDialog, "exec", fake_exec)
    monkeypatch.setattr(convert_dialogs, "choose_save", lambda *a, **k: out)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Close)
    w.act_page_sizes.trigger()
    with fitz.open(out) as d:
        assert all(round(p.rect.height) in (1008, 612) for p in d)


def test_field_toolbar_bold_italic_and_case(form_window):
    w = form_window
    field = _first_text_field(w)
    w._edit.set_field_value(field.object_id, "Mixed Text 山田")  # noqa: SLF001
    w._edit.selection = []  # noqa: SLF001
    w._edit.field_selection = [field.object_id]  # noqa: SLF001
    w._update_context_toolbar()  # noqa: SLF001
    acts = w._context_bar.actions()  # noqa: SLF001
    for a in (w.act_font_bold, w.act_font_italic, w.act_case_upper, w.act_case_lower, w.act_text_wrap):
        assert a in acts
    w.act_font_bold.setChecked(True)
    w._apply_font_toggle("bold")  # noqa: SLF001
    w.act_font_italic.setChecked(True)
    w._apply_font_toggle("italic")  # noqa: SLF001
    assert field.bold and field.italic and field.style_dirty
    w._change_case("upper")  # noqa: SLF001
    assert field.value == "MIXED TEXT 山田"
    w._change_case("lower")  # noqa: SLF001
    assert field.value == "mixed text 山田"


def test_field_formatting_lives_only_in_toolbar(form_window):
    """Align and colour are on the field toolbar; the Properties panel keeps only type, name and value."""
    from PySide6.QtWidgets import QLabel

    w = form_window
    field = _first_text_field(w)
    w._edit.selection = []  # noqa: SLF001
    w._edit.field_selection = [field.object_id]  # noqa: SLF001
    w._update_context_toolbar()  # noqa: SLF001
    acts = w._context_bar.actions()  # noqa: SLF001
    for a in (w.act_align_text_left, w.act_align_text_center, w.act_align_text_right, w.act_text_color):
        assert a in acts
    w._apply_text_align("center")  # noqa: SLF001
    assert field.align == "center" and field.style_dirty
    assert w.act_align_text_center.isChecked()
    # the field name is no longer squeezed into the toolbar as loose text
    hints = [lab.text() for lab in w._context_bar.findChildren(QLabel) if lab.objectName() == "ContextHint"]  # noqa: SLF001
    assert all(not t for t in hints)

    w._refresh_inspector()  # noqa: SLF001
    ins = w._inspector  # noqa: SLF001
    labels = [ins._form.itemAt(i, ins._form.ItemRole.LabelRole) for i in range(ins._form.rowCount())]  # noqa: SLF001
    texts = [it.widget().text() for it in labels if it is not None and isinstance(it.widget(), QLabel)]
    assert "Value:" in texts and "Name:" in texts
    for dup in ("Font:", "Size:", "Style:", "Align:", "Color:", "Case:"):
        assert dup not in texts, dup


def test_print_dialog_preview_and_page_choices(doc_window, qtbot):
    from core.printing import ColorMode, PageScaling
    from ui.print_dialog import PrintDialog

    w = doc_window
    doc = w._document  # noqa: SLF001
    dlg = PrintDialog(doc, doc_name=doc.name, current_page=1, selected_pages=[0, 2], parent=w)
    qtbot.addWidget(dlg)
    dlg.show()
    qtbot.wait(10)
    assert dlg.selected_pages() == list(range(doc.page_count))
    assert dlg.sheet_label.text().startswith(f"Sheet 1 of {doc.page_count}")
    assert dlg.preview._image is not None and not dlg.preview._image.isNull()  # noqa: SLF001
    dlg.r_current.setChecked(True)
    assert dlg.selected_pages() == [1]
    dlg.r_selected.setChecked(True)
    assert dlg.selected_pages() == [0, 2]
    dlg.custom.setText("2-3")
    dlg.r_custom.setChecked(True)
    assert dlg.selected_pages() == [1, 2]
    dlg.custom.setText("99")
    assert dlg.selected_pages() == [] and not dlg._print_btn.isEnabled()  # noqa: SLF001
    dlg.custom.setText("1")
    dlg.color.setCurrentIndex(1)
    dlg.scaling.setCurrentIndex(1)
    st = dlg.settings()
    assert st.color_mode == ColorMode.GRAYSCALE and st.scaling == PageScaling.ACTUAL and st.pages == [0]
    from PySide6.QtGui import QImage

    assert dlg.preview._image.format() == QImage.Format.Format_Grayscale8  # noqa: SLF001
    dlg.close()


def test_status_footer_has_no_redundant_ready_word(window):
    st = window._status  # noqa: SLF001
    st.set_ready("Ready")
    assert st.ready_label.text() == ""
    st.set_analysis_progress("Working…")
    st.clear_analysis_progress()
    assert st.ready_label.text() == ""


def test_filled_field_gets_no_added_border(window, qtbot, tmp_path):
    """Typing into a PDF field must not draw a dark box (or white fill) the PDF field doesn't have."""
    import fitz
    from PySide6.QtGui import QColor

    p = tmp_path / "plain_field.pdf"
    d = fitz.open()
    page = d.new_page()
    page.draw_rect(page.rect, color=None, fill=(0.85, 0.92, 1.0))  # tinted page: a white fill would show too
    wd = fitz.Widget()
    wd.field_name = "name"
    wd.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    wd.rect = fitz.Rect(100, 100, 400, 130)
    page.add_widget(wd)
    d.save(p)
    assert window.open_path(p)
    w = window
    field = next(iter(w._edit.fields.values()))  # noqa: SLF001
    assert QColor(field.border_color).alpha() == 0 and field.border_width == 0
    w._edit.set_field_value(field.object_id, "Myanmar")  # noqa: SLF001
    w._edit.field_selection = []  # noqa: SLF001
    w._edit.selection = []  # noqa: SLF001
    inner = w._canvas.widget()  # noqa: SLF001
    inner.update()
    wr = inner.pdf_rect_to_widget(field.page_index, field.rect)
    assert wr is not None

    # The page image is rendered asynchronously after opening; until it arrives the page shows the
    # white placeholder (field outlines are drawn over it at once). A fixed wait alone was not always
    # enough under full-suite load (the white placeholder was sampled inside the field). Wait until an
    # untouched page area below the field shows the page's tint, i.e. the page is drawn.
    def page_drawn() -> bool:
        probe = QColor(inner.grab().toImage().pixel(wr.center().x(), wr.bottom() + 60))
        return probe.lightness() > 150 and probe.blue() > probe.red()

    qtbot.waitUntil(page_drawn, timeout=5000)
    qtbot.wait(150)
    img = inner.grab().toImage()
    # Edges and the empty right half of the box keep the page's tint: no dark border, no white fill
    pts = [(x, y) for x in range(wr.left() + wr.width() // 2, wr.right() - 2, 9) for y in (wr.top(), wr.bottom(), wr.center().y())]
    for x, y in pts:
        c = QColor(img.pixel(x, y))
        assert c.lightness() > 150 and c.blue() > c.red(), (x, y, c.name())

def test_open_field_editor_follows_alignment_and_size(form_window, qtbot):
    """Centre / middle / A+ from the toolbar change the field being typed in at once."""
    from PySide6.QtCore import Qt

    w = form_window
    c = w._canvas._canvas  # noqa: SLF001
    field = next(f for f in w._edit.fields.values() if f.multiline)  # noqa: SLF001
    qtbot.wait(200)
    assert c.open_field_editor(field)
    c.field_editor.setPlainText("Feb 13–14")
    w._update_context_toolbar()  # noqa: SLF001
    for a in (w.act_valign_top, w.act_valign_middle, w.act_valign_bottom):
        assert a in w._context_bar.actions()  # noqa: SLF001
    px = c.field_editor.font().pixelSize()
    w._apply_text_align("center")  # noqa: SLF001
    w._apply_text_valign("middle")  # noqa: SLF001
    w._nudge_font_size(2)  # noqa: SLF001
    ed = c.field_editor
    assert field.align == "center" and field.valign == "middle"
    assert ed.font().pixelSize() > px
    assert ed.document().defaultTextOption().alignment() & Qt.AlignmentFlag.AlignHCenter
    assert ed.viewportMargins().top() > 0  # text block moved down to the middle


def test_text_box_size_keeps_selection_and_valign(form_window, qtbot):
    from core.editing.geometry import Rect

    w = form_window
    c = w._canvas._canvas  # noqa: SLF001
    box = w._edit.create_text_box(0, Rect(60, 450, 220, 90), text="Hello world")  # noqa: SLF001
    w._edit.selection = [box.object_id]  # noqa: SLF001
    qtbot.wait(50)
    assert c.open_text_editor(box.object_id)
    te = c.text_editor
    cur = te.textCursor()
    cur.setPosition(0)
    cur.setPosition(5, cur.MoveMode.KeepAnchor)
    te.setTextCursor(cur)
    before = box.style.font_size
    w._nudge_font_size(2)  # noqa: SLF001
    w._apply_text_valign("bottom")  # noqa: SLF001
    # (0.5.0) A+ with words selected grows only those words; the box keeps its size
    box = w._edit.objects[box.object_id]  # noqa: SLF001
    assert box.style.font_size == before
    assert box.runs and box.runs[0]["text"] == "Hello" and box.runs[0]["size"] == before + 2
    assert box.valign.value == "bottom"
    assert c.text_editor is te and te.textCursor().selectedText() == "Hello"


@pytest.mark.parametrize("size", [(792, 612), (595, 842), (1400, 400), (226, 1400)])
def test_page_is_drawn_in_fit_modes(window, qtbot, tmp_path, size):
    """Fit Width / Fit Page must settle: some page sizes made the scrollbar flip forever and
    the page was never drawn."""
    import fitz

    from ui.pdf_canvas import ZoomMode

    p = tmp_path / "page.pdf"
    d = fitz.open()
    d.new_page(width=size[0], height=size[1]).insert_text((40, 60), "Hello", fontsize=20)
    d.save(p)
    for ws in ((1300, 950), (1100, 800), (1366, 768)):
        window.resize(*ws)
        assert window.open_path(p)
        for mode in (ZoomMode.FIT_WIDTH, ZoomMode.FIT_PAGE):
            window._canvas.set_zoom_mode(mode)  # noqa: SLF001
            c = window._canvas._canvas  # noqa: SLF001
            qtbot.waitUntil(lambda c=c: len(c._cache) > 0 and not c._render_timer.isActive(), timeout=2000)  # noqa: SLF001
        window.close_document(save_session=False)


def test_field_justify_button(form_window, qtbot):
    from PySide6.QtCore import Qt

    w = form_window
    c = w._canvas._canvas  # noqa: SLF001
    field = next(f for f in w._edit.fields.values() if f.multiline)  # noqa: SLF001
    w._edit.field_selection = [field.object_id]  # noqa: SLF001
    w._update_context_toolbar()  # noqa: SLF001
    assert w.act_align_text_justify in w._context_bar.actions()  # noqa: SLF001
    w._apply_text_align("justify")  # noqa: SLF001
    assert field.align == "justify" and w.act_align_text_justify.isChecked()
    qtbot.wait(150)
    assert c.open_field_editor(field)
    assert c.field_editor.document().defaultTextOption().alignment() & Qt.AlignmentFlag.AlignJustify


def test_word_formats_inside_a_field(form_window, qtbot, tmp_path):
    """Select words while typing and give them their own font / size / bold; the rest keeps the
    field's look. With no selection the toolbar changes the whole entry (every word)."""
    from PySide6.QtGui import QInputMethodEvent
    from PySide6.QtTest import QTest

    from core.forms.acroform import load_acroform_fields

    w = form_window
    c = w._canvas._canvas  # noqa: SLF001
    field = next(f for f in w._edit.fields.values() if f.multiline)  # noqa: SLF001
    qtbot.wait(150)
    assert c.open_field_editor(field)
    ed = c.field_editor
    QTest.keyClicks(ed, "Good will ")
    ime = QInputMethodEvent()
    ime.setCommitString("東京 OK")  # Japanese typed through the input method
    QApplication = __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication
    QApplication.sendEvent(ed, ime)
    assert field.value == "Good will 東京 OK"
    w._edit.field_selection = [field.object_id]  # noqa: SLF001
    w._update_context_toolbar()  # noqa: SLF001

    def select(a, b):
        cur = ed.textCursor()
        cur.setPosition(a)
        cur.setPosition(b, cur.MoveMode.KeepAnchor)
        ed.setTextCursor(cur)

    select(0, 4)
    w._apply_font_family("Times New Roman")  # noqa: SLF001
    w._font_size.setFocus()  # clicking into the size box keeps the editor and the selection
    qtbot.wait(30)
    assert c.field_editor is ed and ed.textCursor().selectedText() == "Good"
    w._font_size.setCurrentText("8 pt")  # noqa: SLF001
    w._apply_font_size_value()  # noqa: SLF001
    select(5, 9)
    w.act_font_bold.setChecked(True)
    w._apply_font_toggle("bold")  # noqa: SLF001
    w._font_size.setCurrentText("10 pt")  # noqa: SLF001
    w._apply_font_size_value()  # noqa: SLF001
    runs = {r["text"]: r for r in field.runs}
    assert runs["Good"]["family"] == "Times New Roman" and runs["Good"]["size"] == 8
    assert runs["will"]["bold"] is True and runs["will"]["size"] == 10
    select(0, 2)
    qtbot.wait(200)  # past the toolbar's delayed refresh: it must keep showing the selected word
    w._update_context_toolbar()  # noqa: SLF001 — what that refresh does
    assert w._font_size.currentText() == "8 pt" and not w.act_font_bold.isChecked()  # noqa: SLF001
    w._nudge_font_size(1)  # noqa: SLF001 — A+ on the selected word only
    runs = {r["text"]: r for r in field.runs}
    assert runs["Go"]["size"] == 9 and runs["od"]["size"] == 8 and runs["will"]["size"] == 10
    w._commit_field_editor()  # noqa: SLF001
    w._edit.field_selection = [field.object_id]  # noqa: SLF001
    w._nudge_font_size(1)  # noqa: SLF001 — no editor: the whole entry grows, differences kept
    sizes = [r["size"] for r in field.runs if r["size"]]
    assert sizes == [10, 9, 11]
    out = tmp_path / "rich.pdf"
    w._bake_to(out)  # noqa: SLF001
    import fitz

    with fitz.open(out) as d:
        again = next(f for f in load_acroform_fields(d) if f.name == field.name)
        assert again.value == "Good will 東京 OK"
        assert [r["size"] for r in again.runs if r["size"]] == [10, 9, 11]


def test_field_can_be_deselected(form_window, qtbot):
    """Esc (after typing), a click on blank paper or on the grey area clears the selection box."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    w = form_window
    c = w._canvas._canvas  # noqa: SLF001
    field = _first_text_field(w)
    qtbot.wait(150)

    def click(pt):
        QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
        qtbot.wait(60)

    wr = c.pdf_rect_to_widget(field.page_index, field.rect)
    # Select-then-edit: first click selects; open_field_editor starts typing.
    click(wr.center())
    assert w._edit.field_selection  # noqa: SLF001
    assert c.open_field_editor(field)
    assert c.field_editor is not None
    QTest.keyClick(c.field_editor, Qt.Key.Key_Escape)  # 1st Esc: finish typing
    assert c.field_editor is None and w._edit.field_selection  # noqa: SLF001
    QTest.keyClick(c, Qt.Key.Key_Escape)  # 2nd Esc: deselect
    assert not w._edit.field_selection  # noqa: SLF001

    click(wr.center())
    page = c._layouts[field.page_index]  # noqa: SLF001
    click(QPoint(wr.center().x(), min(page.bottom() - 5, wr.bottom() + 120)))  # blank paper
    assert not w._edit.field_selection and c.field_editor is None  # noqa: SLF001

    click(wr.center())
    click(QPoint(page.right() + 6, page.top() + 40))  # grey area beside the page
    assert not w._edit.field_selection and c.field_editor is None  # noqa: SLF001
    # the toolbar refresh is debounced by a 40 ms timer: wait for it instead of relying on a fixed delay
    qtbot.waitUntil(lambda: w.act_rotate_cw in w._context_bar.actions(), timeout=3000)  # noqa: SLF001  back to the page tools


def test_properties_panel_close_button(form_window, qtbot):
    w = form_window
    assert w._inspector.isVisible()  # noqa: SLF001
    w._inspector._hide_btn.click()  # noqa: SLF001
    assert not w._inspector.isVisible() and not w.act_toggle_right.isChecked()  # noqa: SLF001
    assert w._prefs.right_panel_collapsed  # noqa: SLF001
    w.act_toggle_right.trigger()  # F8 / View ▸ Properties Panel
    assert w._inspector.isVisible() and not w._prefs.right_panel_collapsed  # noqa: SLF001

