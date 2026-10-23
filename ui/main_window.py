"""Main application window — consolidated desktop shell (portable UI)."""

from __future__ import annotations

import html
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QImage, QIntValidator, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QWidgetAction,
    QComboBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from app.qt_app import create_application
from core.document import (
    InvalidPdfError,
    PasswordRequiredError,
    PdfDocument,
    open_document,
)
from core.editing.edit_model import EditableDocument, EditTool, WorkspaceMode
from core.editing.session_store import clear_session, read_session, write_session
from core.layout.ops import LayoutPolicy
from core.product_meta import PRODUCT_NAME
from core.recent_files import RecentFiles
from core.user_prefs import UserPreferences
from ui.about_dialog import AboutDialog
from core.diagnostics import EventId, diagnostics
from ui.branding import apply_application_icon, load_app_icon
from ui.inspector_panel import InspectorPanel
from ui.left_rail import LeftRail
from ui.password_dialog import PasswordDialog
from ui.pdf_canvas import PdfCanvas, ZoomMode
from ui.status_footer import AppStatusBar
from ui.theme import apply_theme
from ui.toolbar_icons import apply_toolbar_icons, refresh_registered_icons, set_action_icon
from ui.welcome_page import WelcomePage

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp")


def is_openable(path: str) -> bool:
    """PDF, images (opened as a new PDF) and Office documents (via the installed suite)."""
    from core.convert.office_bridge import OFFICE_EXTS

    ext = Path(path).suffix.lower()
    return ext == ".pdf" or ext in IMAGE_EXTS or ext in OFFICE_EXTS


# Re-export for callers that historically imported create_application from here.
__all__ = ("MainWindow", "create_application")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumSize(900, 600)
        self.setAccessibleName("Monograph PDF main window")
        self._prefs = UserPreferences.load()
        from ui.update_dialogs import UpdateController

        self._updates = UpdateController(self)
        self.resize(self._prefs.window_width, self._prefs.window_height)
        if self._prefs.window_x is not None and self._prefs.window_y is not None:
            self.move(self._prefs.window_x, self._prefs.window_y)

        self._document: PdfDocument | None = None
        self._edit: EditableDocument | None = None
        self._recent = RecentFiles(limit=self._prefs.recent_limit)
        self._search_hits: list[tuple[int, object]] = []
        self._search_index = -1
        self._autosave = QTimer(self)
        self._autosave.setInterval(5000)
        self._autosave.timeout.connect(self._autosave_session)

        self._left = LeftRail()
        self._thumbs = self._left.thumbs  # compat for page ops
        self._canvas = PdfCanvas()
        self._canvas.setAccessibleName("PDF canvas")
        self._welcome = WelcomePage()
        self._center_stack = QStackedWidget()
        self._center_stack.addWidget(self._welcome)
        self._center_stack.addWidget(self._canvas)
        self._center_stack.setCurrentWidget(self._welcome)
        self._inspector = InspectorPanel()
        self._inspector.setAccessibleName("Properties inspector")
        self._status = AppStatusBar()
        self._page_label = self._status.page_label
        self._zoom_label = self._status.zoom_label
        self._dirty_label = self._status.dirty_label
        self._doc_state_label = self._status.doc_state_label
        self._progress_label = self._status.progress_label
        self._toolbar_zoom = QComboBox()
        self._toolbar_zoom.setObjectName("ToolbarZoomValue")
        self._toolbar_zoom.setEditable(True)
        self._toolbar_zoom.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for z in (25, 50, 67, 75, 80, 90, 100, 110, 125, 150, 175, 200, 300, 400):
            self._toolbar_zoom.addItem(f"{z}%", z)
        self._toolbar_zoom.setCurrentText("100%")
        self._toolbar_zoom.setMinimumWidth(78)
        self._toolbar_zoom.setMaximumWidth(96)
        self._toolbar_zoom.setAccessibleName("Zoom level")
        self._toolbar_zoom.setToolTip("Current zoom — choose or type a percentage")
        self._toolbar_zoom.activated.connect(self._on_toolbar_zoom_chosen)
        self._toolbar_zoom.lineEdit().editingFinished.connect(self._on_toolbar_zoom_typed)
        self._fit_button = QToolButton()
        self._fit_button.setObjectName("ToolbarFitButton")
        self._fit_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._fit_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._page_indicator = QLabel("")
        self._page_indicator.setObjectName("ToolbarPageTotal")
        self._page_edit = QLineEdit()
        self._page_edit.setObjectName("ToolbarPageEdit")
        self._page_edit.setValidator(QIntValidator(1, 99999, self))
        self._page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_edit.setToolTip("Current page — type a number and press Enter  (Ctrl+G)")
        self._page_edit.setAccessibleName("Page number")
        self._page_edit.returnPressed.connect(self._on_page_edit)
        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("ToolbarSearch")
        self._search_edit.setPlaceholderText("Find in document…")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setToolTip("Find text  (Ctrl+F) — Enter: next · Shift+Enter: previous · Esc: clear")
        self._search_edit.setAccessibleName("Find in document")
        self._search_edit.setMaximumWidth(240)
        self._search_edit.setMinimumWidth(130)
        self._search_edit.returnPressed.connect(self._on_search_return)
        self._search_edit.installEventFilter(self)
        self._last_query: str | None = None
        from ui.font_picker import FontPicker

        self._font_family = FontPicker()
        self._font_family.setMinimumWidth(150)
        self._font_family.setMaximumWidth(210)
        self._font_size = QComboBox()
        self._font_size.setEditable(True)
        self._font_size.setMinimumWidth(84)  # "72 pt" stays readable when the context bar is crowded
        for s in (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48, 72):
            self._font_size.addItem(f"{s} pt", s)
        self._font_size.setCurrentText("11 pt")
        self._font_size.setToolTip("Font size")
        self._font_size.setMaximumWidth(92)
        self._font_controls_wired = False
        self._chrome_timer = QTimer(self)
        self._chrome_timer.setSingleShot(True)
        self._chrome_timer.setInterval(40)
        self._chrome_timer.timeout.connect(self._flush_chrome_refresh)

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._prefs.theme)
            refresh_registered_icons()  # widgets created above (start page tiles) follow the theme
            apply_application_icon(app)
        self.setWindowIcon(load_app_icon())

        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_status()
        self._connect_signals()
        self._update_title()
        self._set_document_actions_enabled(False)
        self._update_context_toolbar()
        self._update_workspace_chrome()
        self._refresh_welcome_recent()
        self._canvas.refresh_theme()
        self._status.set_ready("Ready")
        if app is not None:
            for arg in app.arguments()[1:]:
                if is_openable(arg) and Path(arg).is_file():
                    QTimer.singleShot(0, lambda p=arg: self.open_path(p))
                    break

    # ------------------------------------------------------------------ memory-saving mode (minimized)
    ECO_DELAY_MS = 3000  # a quick minimize / restore keeps everything as it was

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange:
            return
        self._eco_state()
        if self.isMinimized():
            self._eco_timer.start(self.ECO_DELAY_MS)
        else:
            self._eco_timer.stop()
            if self._eco_active:
                self._leave_memory_saving()

    def _eco_state(self) -> QTimer:
        """The memory-saving timer and flags (made on first use: changeEvent can run during start-up)."""
        if getattr(self, "_eco_timer", None) is None:
            self._eco_timer = QTimer(self)
            self._eco_timer.setSingleShot(True)
            self._eco_timer.timeout.connect(self._enter_memory_saving)
            self._eco_active = False
            self._eco_qos = False
        return self._eco_timer

    def _enter_memory_saving(self) -> None:
        """Minimized for a few seconds: release what can be drawn again and let Windows run the
        program in efficiency mode (unless a background job such as OCR is running)."""
        if not self.isMinimized():
            return
        from core import memory_saver

        self._eco_state()
        self._eco_active = True
        try:
            self._canvas.release_memory()
            self._left.thumbs.release_images()
        except Exception:  # noqa: BLE001
            pass
        memory_saver.release_library_memory()
        if not memory_saver.background_work_running():
            self._eco_qos = memory_saver.set_efficiency_mode(True)
        else:  # try again later: a job may finish while the window stays minimized
            self._eco_timer.start(20000)

    def _leave_memory_saving(self) -> None:
        from core import memory_saver

        self._eco_state()
        self._eco_active = False
        if self._eco_qos:
            memory_saver.set_efficiency_mode(False)
            self._eco_qos = False
        try:
            self._canvas.restore_after_release()
            self._left.thumbs.restore_images()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ second start (single instance)
    def handle_instance_request(self, files: list[str]) -> None:
        """Monograph PDF was started again: come to the front and open the file it was started with
        (one document at a time), or say that it is already running."""
        self.bring_to_front()
        openable = [f for f in files if is_openable(f) and Path(f).is_file()]
        if not openable:
            self._show_already_running()
            return
        self._pending_open = openable[0]
        if len(openable) > 1:
            self.statusBar().showMessage(
                f"Opening {Path(openable[0]).name} — Monograph PDF shows one document at a time", 8000)
        self._open_pending_when_free()

    def _open_pending_when_free(self) -> None:
        """Open the handed-over file once no dialog is waiting for an answer (never inside one)."""
        path = getattr(self, "_pending_open", None)
        if not path:
            return
        if QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None:
            self.statusBar().showMessage(
                f"{Path(path).name} opens when the open dialog is closed", 4000)
            QTimer.singleShot(500, self._open_pending_when_free)
            return
        self._pending_open = None
        self.open_path(path)

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        if sys.platform.startswith("win"):
            try:
                import ctypes

                ctypes.WinDLL("user32").SetForegroundWindow(int(self.winId()))
            except Exception:  # noqa: BLE001
                pass

    def _show_already_running(self) -> None:
        self.statusBar().showMessage("Monograph PDF is already running — this is the open window", 6000)
        box = getattr(self, "_running_box", None)
        if box is not None and box.isVisible():
            box.raise_()
            return
        box = QMessageBox(QMessageBox.Icon.Information, "Monograph PDF",
                          "Monograph PDF is already running.\n\nThis is the open window — "
                          "use File ▸ Open to open another PDF.", QMessageBox.StandardButton.Ok, self)
        box.setWindowModality(Qt.WindowModality.NonModal)
        self._running_box = box
        box.open()
        QTimer.singleShot(8000, box.close)

    def _build_actions(self) -> None:
        self.act_open = QAction("&Open…", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self.open_file_dialog)

        self.act_save = QAction("&Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.save_document)

        self.act_save_as = QAction("Save &As…", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self.save_as_dialog)

        self.act_save_copy = QAction("&Whole Document (Keep Working on This One)…", self)
        self.act_save_copy.setStatusTip("Save the document as it is now to a separate file; the open "
                                        "document and its unsaved changes stay as they are")
        self.act_save_copy.triggered.connect(lambda: self.save_copy_dialog())  # triggered passes "checked"

        self.act_close = QAction("&Close", self)
        self.act_close.setShortcut(QKeySequence.StandardKey.Close)
        self.act_close.triggered.connect(self._close_document_interactive)

        self.act_exit = QAction("E&xit", self)
        self.act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_exit.triggered.connect(self.close)

        self.act_undo = QAction("&Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self._undo)

        self.act_redo = QAction("&Redo", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.triggered.connect(self._redo)

        self.act_cut = QAction("Cu&t", self)
        self.act_cut.setShortcut(QKeySequence.StandardKey.Cut)
        self.act_cut.triggered.connect(self._cut)

        self.act_copy = QAction("&Copy", self)
        self.act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.act_copy.triggered.connect(self._copy)

        self.act_paste = QAction("&Paste", self)
        self.act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self.act_paste.triggered.connect(self._paste)

        self.act_duplicate = QAction("Dupl&icate", self)
        self.act_duplicate.setShortcut(QKeySequence("Ctrl+D"))
        self.act_duplicate.triggered.connect(self._duplicate)

        self.act_delete = QAction("&Delete", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.triggered.connect(self._delete)

        self.act_select_tool = QAction("&Select", self)
        self.act_select_tool.setCheckable(True)
        self.act_select_tool.setChecked(True)
        self.act_select_tool.triggered.connect(lambda: self._set_tool(EditTool.SELECT))

        self.act_text_tool = QAction("&Text Box", self)
        self.act_text_tool.setCheckable(True)
        self.act_text_tool.triggered.connect(lambda: self._set_tool(EditTool.TEXT_BOX))
        self.act_image_tool = QAction("&Image…", self)
        self.act_image_tool.setCheckable(True)
        self.act_image_tool.triggered.connect(self._add_image)
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)
        for act in (self.act_select_tool, self.act_text_tool, self.act_image_tool):
            self._tool_group.addAction(act)

        self.act_mode_edit = QAction("&Edit Mode", self)
        self.act_mode_edit.triggered.connect(lambda: self._set_mode(WorkspaceMode.EDIT))
        self.act_mode_forms = QAction("&Forms Mode", self)
        self.act_mode_forms.triggered.connect(lambda: self._set_mode(WorkspaceMode.FORMS))
        self.act_mode_layout = QAction("&Layout Mode", self)
        self.act_mode_layout.triggered.connect(lambda: self._set_mode(WorkspaceMode.LAYOUT))
        self.act_mode_tables = QAction("Ta&bles Mode", self)
        self.act_mode_tables.triggered.connect(lambda: self._set_mode(WorkspaceMode.TABLES))

        self.act_form_select = QAction("Select &Field", self)
        self.act_form_select.triggered.connect(lambda: self._set_tool(EditTool.FORM_SELECT))
        self.act_form_text = QAction("&Text Field", self)
        self.act_form_text.triggered.connect(lambda: self._set_tool(EditTool.FORM_TEXT))
        self.act_form_multi = QAction("&Multiline Field", self)
        self.act_form_multi.triggered.connect(lambda: self._set_tool(EditTool.FORM_MULTILINE))
        self.act_form_check = QAction("&Checkbox", self)
        self.act_form_check.triggered.connect(lambda: self._set_tool(EditTool.FORM_CHECKBOX))
        self.act_form_radio = QAction("&Radio Button", self)
        self.act_form_radio.triggered.connect(lambda: self._set_tool(EditTool.FORM_RADIO))
        self.act_form_drop = QAction("&Dropdown", self)
        self.act_form_drop.triggered.connect(lambda: self._set_tool(EditTool.FORM_DROPDOWN))
        self.act_form_date = QAction("Da&te Field", self)
        self.act_form_date.triggered.connect(lambda: self._set_tool(EditTool.FORM_DATE))
        self.act_form_sig = QAction("Si&gnature Field", self)
        self.act_form_sig.triggered.connect(lambda: self._set_tool(EditTool.FORM_SIGNATURE))
        self.act_form_detect = QAction("Detect &Fields", self)
        self.act_form_detect.triggered.connect(self._detect_fields)
        self.act_form_accept = QAction("Accept &Candidates", self)
        self.act_form_accept.triggered.connect(self._accept_candidates)
        self.act_form_reject = QAction("Reject Candidates", self)
        self.act_form_reject.triggered.connect(self._reject_candidates)
        self.act_flatten = QAction("Flatten Form on Save", self)
        self.act_flatten.setCheckable(True)
        self.act_flatten.toggled.connect(self._toggle_flatten)

        self.act_detect_tables = QAction("Detect &Tables", self)
        self.act_detect_tables.triggered.connect(self._detect_tables)
        self.act_table_add_row = QAction("Add &Row", self)
        self.act_table_add_row.triggered.connect(lambda: self._table_op("add_row"))
        self.act_table_del_row = QAction("Delete Row", self)
        self.act_table_del_row.triggered.connect(lambda: self._table_op("del_row"))
        self.act_table_add_col = QAction("Add &Column", self)
        self.act_table_add_col.triggered.connect(lambda: self._table_op("add_col"))
        self.act_table_del_col = QAction("Delete Column", self)
        self.act_table_del_col.triggered.connect(lambda: self._table_op("del_col"))

        self.act_align_left = QAction("Align &Left", self)
        self.act_align_left.triggered.connect(lambda: self._align("left"))
        self.act_align_right = QAction("Align &Right", self)
        self.act_align_right.triggered.connect(lambda: self._align("right"))
        self.act_align_top = QAction("Align &Top", self)
        self.act_align_top.triggered.connect(lambda: self._align("top"))
        self.act_align_bottom = QAction("Align &Bottom", self)
        self.act_align_bottom.triggered.connect(lambda: self._align("bottom"))
        self.act_align_ch = QAction("Align Center &H", self)
        self.act_align_ch.triggered.connect(lambda: self._align("center_h"))
        self.act_align_cv = QAction("Align Center &V", self)
        self.act_align_cv.triggered.connect(lambda: self._align("center_v"))
        self.act_dist_h = QAction("Distribute &Horizontally", self)
        self.act_dist_h.triggered.connect(lambda: self._distribute("horizontal"))
        self.act_dist_v = QAction("Distribute &Vertically", self)
        self.act_dist_v.triggered.connect(lambda: self._distribute("vertical"))
        self.act_policy_preserve = QAction("&Preserve Layout", self)
        self.act_policy_preserve.setCheckable(True)
        self.act_policy_preserve.setChecked(True)
        self.act_policy_preserve.triggered.connect(lambda: self._set_layout_policy(LayoutPolicy.PRESERVE))
        self.act_policy_smart = QAction("&Smart Layout (foundation)", self)
        self.act_policy_smart.setCheckable(True)
        self.act_policy_smart.triggered.connect(lambda: self._set_layout_policy(LayoutPolicy.SMART))

        self.act_make_editable = QAction("&Make PDF Editable…", self)
        self.act_make_editable.triggered.connect(self._make_pdf_editable)
        self.act_ocr_document = QAction("OCR &Document", self)
        self.act_ocr_document.triggered.connect(lambda: self._run_ocr(scope="document"))
        self.act_ocr_pages = QAction("OCR Current &Page", self)
        self.act_ocr_pages.triggered.connect(lambda: self._run_ocr(scope="page"))
        self.act_ocr_region = QAction("OCR Page as &Region Pass", self)
        self.act_ocr_region.triggered.connect(lambda: self._run_ocr(scope="region"))
        self.act_ocr_area = QAction("Recognize Text in &Area…", self)
        self.act_ocr_area.setToolTip("Drag a rectangle on a scanned page and read its text (offline OCR)")
        self.act_ocr_area.triggered.connect(self._ocr_area)
        self.act_ocr_extract = QAction("E&xtract Text (OCR)…", self)
        self.act_ocr_extract.setToolTip("Recognize the text of pages and show it to correct, copy or save")
        self.act_ocr_extract.triggered.connect(self._ocr_extract)
        self.act_ocr_languages = QAction("OCR &Languages…", self)
        self.act_ocr_languages.setToolTip("Choose OCR languages; install optional languages from verified files")
        self.act_ocr_languages.triggered.connect(self._ocr_languages)
        self.act_scan_to_word = QAction("Scanned PDF to &Word (OCR)…", self)
        self.act_scan_to_word.setToolTip("Recognize the text of scanned pages and save it as an editable Word document")
        self.act_scan_to_word.triggered.connect(self._scan_to_word)

        # Pages / organize
        self.act_insert_blank = QAction("Insert &Blank Pages…", self)
        self.act_insert_blank.setToolTip("Insert one or more blank pages before or after any page")
        self.act_insert_blank.triggered.connect(lambda: self._insert_blank_page(ask=True))
        self.act_insert_pdf = QAction("Insert Pages from &PDF…", self)
        self.act_insert_pdf.setToolTip("Insert the pages of another PDF before or after any page")
        self.act_insert_pdf.triggered.connect(lambda: self._insert_pdf_pages(ask=True))
        self.act_move_pages = QAction("&Move Pages…", self)
        self.act_move_pages.setToolTip("Move the selected pages before or after any page (or drag them in the page list)")
        self.act_move_pages.triggered.connect(lambda: self._move_selected_pages(ask=True))
        self.act_delete_pages = QAction("&Delete Pages", self)
        self.act_delete_pages.triggered.connect(self._delete_selected_pages)
        self.act_dup_pages = QAction("Du&plicate Pages", self)
        self.act_dup_pages.triggered.connect(self._duplicate_selected_pages)
        self.act_replace_page = QAction("&Replace Page…", self)
        self.act_replace_page.triggered.connect(self._replace_page)
        self.act_rotate_cw = QAction("Rotate &90° CW", self)
        self.act_rotate_cw.triggered.connect(lambda: self._rotate_selected(90))
        self.act_rotate_ccw = QAction("Rotate 90° CC&W", self)
        self.act_rotate_ccw.triggered.connect(lambda: self._rotate_selected(-90))
        self.act_crop_page = QAction("&Crop Page…", self)
        self.act_crop_page.triggered.connect(self._crop_page)
        self.act_extract_pages = QAction("&Extract Pages…", self)
        self.act_extract_pages.triggered.connect(self._extract_pages)
        self.act_copy_to_doc = QAction("Copy Pages to Another PDF…", self)
        self.act_copy_to_doc.triggered.connect(lambda: self._transfer_pages(move=False))
        self.act_move_to_doc = QAction("Move Pages to Another PDF…", self)
        self.act_move_to_doc.triggered.connect(lambda: self._transfer_pages(move=True))
        self.act_page_sizes = QAction("Change Page &Size…", self)
        self.act_page_sizes.triggered.connect(self._change_page_size_dialog)
        self.act_merge = QAction("&Merge / Combine…", self)
        self.act_merge.triggered.connect(self._merge_combine)
        self.act_split = QAction("&Split…", self)
        self.act_split.triggered.connect(self._split_document)

        # Convert / Export
        self.act_images_to_pdf = QAction("Images → &PDF…", self)
        self.act_images_to_pdf.triggered.connect(self._images_to_pdf)
        self.act_pdf_to_images = QAction("PDF Pages → I&mages…", self)
        self.act_pdf_to_images.triggered.connect(self._pdf_to_images)
        self.act_extract_images = QAction("E&xtract Embedded Images…", self)
        self.act_extract_images.triggered.connect(self._extract_images)
        self.act_pdf_to_text = QAction("PDF → Plain &Text…", self)
        self.act_pdf_to_text.triggered.connect(self._pdf_to_text)
        self.act_batch_convert = QAction("&Batch Convert…", self)
        self.act_batch_convert.setToolTip("Convert many files at once: PDF to Word, Excel, PowerPoint, text or pictures, "
                                          "pictures or Office files to PDF, OCR")
        self.act_batch_convert.triggered.connect(self._batch_convert)
        self.act_searchable = QAction("Scanned → &Searchable PDF…", self)
        self.act_searchable.triggered.connect(self._scanned_to_searchable)
        self.act_pages_export = QAction("Selected Pages → P&DF…", self)
        self.act_pages_export.triggered.connect(self._export_selected_pages_pdf)
        self.act_flatten_export = QAction("&Flattened PDF…", self)
        self.act_flatten_export.triggered.connect(self._export_flattened)
        self.act_meta_copy = QAction("Metadata-Preserving &Copy…", self)
        self.act_meta_copy.triggered.connect(self._metadata_copy)
        self.act_pdf_to_docx = QAction("PDF → DOC&X… (best-effort)", self)
        self.act_pdf_to_docx.triggered.connect(self._pdf_to_docx)
        self.act_tables_xlsx = QAction("Tables → XLS&X… (best-effort)", self)
        self.act_tables_xlsx.triggered.connect(self._tables_to_xlsx)
        self.act_pdf_to_pptx = QAction("PDF → PP&TX… (best-effort)", self)
        self.act_pdf_to_pptx.triggered.connect(self._pdf_to_pptx)
        self.act_office_to_pdf = QAction("Office → PDF…", self)
        self.act_office_to_pdf.triggered.connect(self._office_to_pdf)
        self.act_optimize = QAction("&Optimize / Compress…", self)
        self.act_optimize.triggered.connect(self._optimize_pdf)
        self.act_watermark = QAction("&Watermark…", self)
        self.act_watermark.triggered.connect(self._watermark)
        self.act_header_footer = QAction("&Header / Footer / Page Numbers…", self)
        self.act_header_footer.triggered.connect(self._header_footer)
        self.act_background = QAction("&Background…", self)
        self.act_background.triggered.connect(self._background)
        self.act_remove_page_design = QAction("Remove Header, Footer, Watermark or Background…", self)
        self.act_remove_page_design.triggered.connect(self._remove_page_design)
        self.act_convert_caps = QAction("Capabilities && Limitations…", self)
        self.act_convert_caps.triggered.connect(self._show_convert_capabilities)
        self.act_export_image = QAction("Export Selected &Image…", self)
        self.act_export_image.triggered.connect(self._export_selected_image)
        self.act_replace_image = QAction("Replace Selected Image…", self)
        self.act_replace_image.triggered.connect(self._replace_selected_image)
        self.act_export_image.setEnabled(False)  # enabled while an image is selected
        self.act_replace_image.setEnabled(False)

        # Annotations (menu titles finalized in _build_extra_actions)
        self.act_annot_highlight = QAction("&Highlight Text", self)
        self.act_annot_highlight.setCheckable(True)
        self.act_annot_highlight.triggered.connect(self._toggle_highlight_tool)
        self._tool_group.addAction(self.act_annot_highlight)
        self.act_annot_eraser = QAction("&Eraser", self)
        self.act_annot_eraser.setCheckable(True)
        self.act_annot_eraser.triggered.connect(self._toggle_eraser_tool)
        self._tool_group.addAction(self.act_annot_eraser)
        self._markup_sticky = None  # "highlight" while continuous Highlight is armed
        self._eraser_active = False
        self.act_annot_underline = QAction("&Underline Text", self)
        self.act_annot_underline.triggered.connect(lambda: self._annot_markup("underline"))
        self.act_annot_strike = QAction("Stri&kethrough Text", self)
        self.act_annot_strike.triggered.connect(lambda: self._annot_markup("strikeout"))
        self.act_annot_squiggly = QAction("S&quiggly Underline", self)
        self.act_annot_squiggly.setToolTip("Squiggly underline: drag across the text")
        self.act_annot_squiggly.triggered.connect(lambda: self._annot_markup("squiggly"))
        self.act_show_comments = QAction("&Comments Panel", self)
        self.act_show_comments.setToolTip("Show the comments and markup of the document, by page")
        self.act_show_comments.triggered.connect(self._show_comments_panel)
        self.act_annot_comment = QAction("Sticky &Note Comment…", self)
        self.act_annot_comment.triggered.connect(self._annot_comment)
        self.act_annot_callout = QAction("Call&out…", self)
        self.act_annot_callout.triggered.connect(self._annot_callout)
        self.act_annot_ink = QAction("&Freehand Stroke", self)
        self.act_annot_ink.setCheckable(True)
        self.act_annot_ink.triggered.connect(lambda: self._set_tool(EditTool.SHAPE_FREEHAND))
        self._tool_group.addAction(self.act_annot_ink)
        self.act_annot_line = QAction("&Line", self)
        self.act_annot_line.setCheckable(True)
        self.act_annot_line.triggered.connect(lambda: self._set_tool(EditTool.SHAPE_LINE))
        self._tool_group.addAction(self.act_annot_line)
        self.act_annot_arrow = QAction("&Arrow", self)
        self.act_annot_arrow.setCheckable(True)
        self.act_annot_arrow.triggered.connect(lambda: self._set_tool(EditTool.SHAPE_ARROW))
        self._tool_group.addAction(self.act_annot_arrow)
        self.act_annot_rect = QAction("&Rectangle", self)
        self.act_annot_rect.setCheckable(True)
        self.act_annot_rect.triggered.connect(lambda: self._set_tool(EditTool.SHAPE_RECT))
        self._tool_group.addAction(self.act_annot_rect)
        self.act_annot_ellipse = QAction("&Ellipse", self)
        self.act_annot_ellipse.setCheckable(True)
        self.act_annot_ellipse.triggered.connect(lambda: self._set_tool(EditTool.SHAPE_ELLIPSE))
        self._tool_group.addAction(self.act_annot_ellipse)
        self.act_shape_circle = QAction("&Circle (Ellipse + lock)", self)
        self.act_shape_circle.setCheckable(True)
        self.act_shape_circle.triggered.connect(self._start_circle_tool)
        self._tool_group.addAction(self.act_shape_circle)
        self.act_annot_stamp = QAction("S&tamp…", self)
        self.act_annot_stamp.triggered.connect(self._annot_stamp)
        self.act_text_color = QAction("Color", self)
        self.act_text_color.setToolTip("Text color")
        self.act_text_color.triggered.connect(self._pick_text_color)

        # Security / redact / sign / print
        self.act_sec_protect = QAction("&Password Protect…", self)
        self.act_sec_protect.triggered.connect(self._password_protect)
        self.act_sec_remove = QAction("&Remove Protection…", self)
        self.act_sec_remove.triggered.connect(self._remove_protection)
        self.act_sec_perms = QAction("Inspect &Permissions…", self)
        self.act_sec_perms.triggered.connect(self._inspect_permissions)
        self.act_sec_meta = QAction("Inspect &Metadata…", self)
        self.act_sec_meta.triggered.connect(self._inspect_metadata)
        self.act_sec_meta_rm = QAction("Remove Meta&data…", self)
        self.act_sec_meta_rm.triggered.connect(self._remove_metadata)
        self.act_sec_attach = QAction("Inspect A&ttachments…", self)
        self.act_sec_attach.triggered.connect(self._inspect_attachments)
        self.act_redact_mark = QAction("&Mark Region for Redaction", self)
        self.act_redact_mark.triggered.connect(self._redact_mark_region)
        self.act_redact_text = QAction("Mark &Text…", self)
        self.act_redact_text.triggered.connect(self._redact_mark_text)
        self.act_redact_pages = QAction("Mark &Whole Pages for Redaction…", self)
        self.act_redact_pages.triggered.connect(self._redact_mark_pages)
        self.act_redact_preview = QAction("Preview Redaction &Count", self)
        self.act_redact_preview.triggered.connect(self._redact_preview)
        self.act_redact_apply = QAction("&Apply True Redaction…", self)
        self.act_redact_apply.triggered.connect(self._redact_apply)
        self.act_sig_typed = QAction("&Typed Visual Signature…", self)
        self.act_sig_typed.triggered.connect(self._sig_typed)
        self.act_sig_image = QAction("&Image Visual Signature…", self)
        self.act_sig_image.triggered.connect(self._sig_image)
        self.act_sig_drawn = QAction("&Drawn Visual Signature", self)
        self.act_sig_drawn.triggered.connect(self._sig_drawn)
        self.act_print = QAction("&Print…", self)
        self.act_print.setShortcut(QKeySequence.StandardKey.Print)
        self.act_print.triggered.connect(self._print_document)

        self.act_copy_style = QAction("Copy St&yle", self)
        self.act_copy_style.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.act_copy_style.triggered.connect(self._copy_style)

        self.act_paste_style = QAction("Paste Sty&le", self)
        self.act_paste_style.setShortcut(QKeySequence("Ctrl+Shift+V"))
        self.act_paste_style.triggered.connect(self._paste_style)

        self.act_bring_forward = QAction("Bring &Forward", self)
        self.act_bring_forward.triggered.connect(lambda: self._layer("forward"))
        self.act_send_backward = QAction("Send &Backward", self)
        self.act_send_backward.triggered.connect(lambda: self._layer("backward"))
        self.act_bring_front = QAction("Bring to F&ront", self)
        self.act_bring_front.triggered.connect(lambda: self._layer("front"))
        self.act_send_back = QAction("Send to Bac&k", self)
        self.act_send_back.triggered.connect(lambda: self._layer("back"))

        self.act_fit_width = QAction("Fit &Width", self)
        self.act_fit_width.setShortcut(QKeySequence("Ctrl+1"))
        self.act_fit_width.triggered.connect(lambda: self._apply_fit_mode(ZoomMode.FIT_WIDTH))
        self.act_fit_page = QAction("Fit &Page", self)
        self.act_fit_page.setShortcut(QKeySequence("Ctrl+2"))
        self.act_fit_page.triggered.connect(lambda: self._apply_fit_mode(ZoomMode.FIT_PAGE))
        self.act_actual = QAction("&Actual Size", self)
        self.act_actual.setShortcut(QKeySequence("Ctrl+0"))
        self.act_actual.triggered.connect(lambda: self._apply_fit_mode(ZoomMode.ACTUAL_SIZE))
        self.act_zoom_in = QAction("Zoom &In", self)
        self.act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.act_zoom_in.setToolTip("Zoom In (Ctrl+=)")
        self.act_zoom_in.triggered.connect(self._canvas.zoom_in)
        self.act_zoom_out = QAction("Zoom &Out", self)
        self.act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        self.act_zoom_out.triggered.connect(self._canvas.zoom_out)
        self.act_highlight_fields = QAction("&Highlight Fillable Fields", self)
        self.act_highlight_fields.setCheckable(True)
        self.act_highlight_fields.setChecked(bool(self._prefs.highlight_fillable_fields))
        self.act_highlight_fields.setToolTip(
            "UI-only highlight for fillable form fields (never baked into Save/Export)"
        )
        self.act_highlight_fields.toggled.connect(self._toggle_highlight_fillable)
        self.act_font_bold = QAction("B", self)
        self.act_font_bold.setCheckable(True)
        self.act_font_bold.setToolTip("Bold")
        self.act_font_bold.triggered.connect(lambda: self._apply_font_toggle("bold"))
        self.act_font_italic = QAction("I", self)
        self.act_font_italic.setCheckable(True)
        self.act_font_italic.setToolTip("Italic")
        self.act_font_italic.triggered.connect(lambda: self._apply_font_toggle("italic"))
        self.act_font_underline = QAction("U", self)
        self.act_font_underline.setCheckable(True)
        self.act_font_underline.setToolTip("Underline")
        self.act_font_underline.triggered.connect(lambda: self._apply_font_toggle("underline"))
        self.act_font_dec = QAction("−", self)
        self.act_font_dec.setToolTip("Decrease font size")
        self.act_font_dec.triggered.connect(lambda: self._nudge_font_size(-1))
        self.act_font_inc = QAction("+", self)
        self.act_font_inc.setToolTip("Increase font size")
        self.act_font_inc.triggered.connect(lambda: self._nudge_font_size(1))
        # Placeholder — color action created with annotations block; ensure exists early
        if not hasattr(self, "act_text_color"):
            self.act_text_color = QAction("Color", self)
            self.act_text_color.triggered.connect(self._pick_text_color)
        self.act_align_text_left = QAction("Left", self)
        self.act_align_text_left.setToolTip("Align left")
        self.act_align_text_left.triggered.connect(lambda: self._apply_text_align("left"))
        self.act_align_text_center = QAction("Center", self)
        self.act_align_text_center.setToolTip("Align center")
        self.act_align_text_center.triggered.connect(lambda: self._apply_text_align("center"))
        self.act_align_text_right = QAction("Right", self)
        self.act_align_text_right.setToolTip("Align right")
        self.act_align_text_right.triggered.connect(lambda: self._apply_text_align("right"))
        self.act_align_text_justify = QAction("Justify", self)
        self.act_align_text_justify.setToolTip(
            "Justify — wrapped lines reach both edges; a paragraph's last line stays left (turn on Wrap Text)"
        )
        self.act_align_text_justify.triggered.connect(lambda: self._apply_text_align("justify"))
        self._text_align_group = QActionGroup(self)
        for _act in (self.act_align_text_left, self.act_align_text_center, self.act_align_text_right,
                     self.act_align_text_justify):
            _act.setCheckable(True)
            self._text_align_group.addAction(_act)
        self.act_valign_top = QAction("Top", self)
        self.act_valign_top.setToolTip("Text at the top of the box")
        self.act_valign_top.triggered.connect(lambda: self._apply_text_valign("top"))
        self.act_valign_middle = QAction("Middle", self)
        self.act_valign_middle.setToolTip("Text in the middle of the box (vertically centered)")
        self.act_valign_middle.triggered.connect(lambda: self._apply_text_valign("middle"))
        self.act_valign_bottom = QAction("Bottom", self)
        self.act_valign_bottom.setToolTip("Text at the bottom of the box")
        self.act_valign_bottom.triggered.connect(lambda: self._apply_text_valign("bottom"))
        self._text_valign_group = QActionGroup(self)
        for _act in (self.act_valign_top, self.act_valign_middle, self.act_valign_bottom):
            _act.setCheckable(True)
            self._text_valign_group.addAction(_act)
        self.act_case_upper = QAction("UPPERCASE", self)
        self.act_case_upper.setToolTip("Change the text to UPPERCASE")
        self.act_case_upper.triggered.connect(lambda: self._change_case("upper"))
        self.act_case_lower = QAction("lowercase", self)
        self.act_case_lower.setToolTip("Change the text to lowercase")
        self.act_case_lower.triggered.connect(lambda: self._change_case("lower"))
        self.act_text_wrap = QAction("Wrap Text", self)
        self.act_text_wrap.setCheckable(True)
        self.act_text_wrap.setToolTip("Wrap text — long lines continue on the next line inside the box")
        self.act_text_wrap.triggered.connect(self._apply_wrap_toggle)
        self.act_prev = QAction("&Previous Page", self)
        self.act_prev.setShortcut(QKeySequence(Qt.Key.Key_PageUp))
        self.act_prev.triggered.connect(self._prev_page)
        self.act_next = QAction("&Next Page", self)
        self.act_next.setShortcut(QKeySequence(Qt.Key.Key_PageDown))
        self.act_next.triggered.connect(self._next_page)
        self.act_find = QAction("&Find…", self)
        self.act_find.setShortcut(QKeySequence.StandardKey.Find)
        self.act_find.triggered.connect(self._focus_search)
        self.act_find_next = QAction("Find Ne&xt", self)
        self.act_find_next.setShortcut(QKeySequence.StandardKey.FindNext)
        self.act_find_next.triggered.connect(self._find_next)
        self.act_about = QAction("&About", self)
        self.act_about.triggered.connect(self._show_about)
        self.act_check_updates = QAction("Check for &Updates…", self)
        self.act_check_updates.triggered.connect(lambda: self._updates.check(manual=True))
        self.act_settings = QAction("Se&ttings…", self)
        self.act_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.act_settings.triggered.connect(self._show_settings)

        self.act_toggle_left = QAction("Toggle &Left Panel", self)
        self.act_toggle_left.setShortcut(QKeySequence("F9"))
        self.act_toggle_left.setCheckable(True)
        self.act_toggle_left.setChecked(not self._prefs.left_panel_collapsed)
        self.act_toggle_left.triggered.connect(self._toggle_left_panel)
        self.act_toggle_right = QAction("Toggle &Inspector", self)
        self.act_toggle_right.setShortcut(QKeySequence("F8"))
        self.act_toggle_right.setCheckable(True)
        self.act_toggle_right.setChecked(not self._prefs.right_panel_collapsed)
        self.act_toggle_right.triggered.connect(self._toggle_right_panel)

        self.act_theme_system = QAction("&System theme", self)
        self.act_theme_system.setCheckable(True)
        self.act_theme_light = QAction("&Light", self)
        self.act_theme_light.setCheckable(True)
        self.act_theme_dark = QAction("&Dark", self)
        self.act_theme_dark.setCheckable(True)
        self._theme_group = QActionGroup(self)
        for act, key in (
            (self.act_theme_system, "system"),
            (self.act_theme_light, "light"),
            (self.act_theme_dark, "dark"),
        ):
            self._theme_group.addAction(act)
            act.triggered.connect(lambda checked=False, k=key: self._set_theme(k))
        theme_act = {
            "system": self.act_theme_system,
            "light": self.act_theme_light,
            "dark": self.act_theme_dark,
        }.get(self._prefs.theme, self.act_theme_system)
        theme_act.setChecked(True)
        self._build_extra_actions()
        self._assign_action_tooltips()

    def _assign_action_tooltips(self) -> None:
        """Accessible tooltips for non-obvious controls."""
        tips = {
            self.act_make_editable: "Analyze pages and OCR only those that need it",
            self.act_ocr_region: "Run OCR on the current page as an explicit region pass",
            self.act_redact_apply: "Permanently remove marked content (not just cover it)",
            self.act_flatten: "When saving, bake form field values into page content",
            self.act_policy_smart: "Nudge related objects only — never moves unrelated content",
            self.act_sig_typed: "Visual signature only — not a digital certificate",
            self.act_sig_drawn: "Visual signature only — not a digital certificate",
            self.act_sig_image: "Visual signature only — not a digital certificate",
            self.act_searchable: "Create a searchable PDF via local OCR (no cloud)",
            self.act_convert_caps: "What each conversion can and cannot do",
            self.act_theme_system: "Follow Windows / OS light or dark preference",
            self.act_select_tool: "Select and move objects",
            self.act_text_tool: "Add a text box",
            self.act_image_tool: "Place an image on the current page",
            self.act_annot_highlight: "Highlight — click to toggle on/off; draw over text or any blank area; change colour without leaving the tool; Esc cancels a stroke, Esc again exits",
            self.act_annot_eraser: "Eraser — draw over highlights, underlines, strikethroughs or ink to remove them (a click removes everything under the pointer); click again or Esc to exit; Undo restores them",
            self.act_annot_comment: "Add a sticky-note comment",
            self.act_open: "Open a PDF",
            self.act_save: "Save changes",
            self.act_print: "Print",
            self.act_toggle_left: "Show or hide the page thumbnails / search panel",
            self.act_toggle_right: "Show or hide the Properties panel",
            self.act_text_color: "Text color",
            self.act_font_bold: "Bold",
            self.act_font_italic: "Italic",
            self.act_font_underline: "Underline",
            self.act_font_dec: "Decrease font size",
            self.act_font_inc: "Increase font size",
        }
        for act, tip in tips.items():
            act.setToolTip(tip)
            act.setStatusTip(tip)

    def _build_extra_actions(self) -> None:
        """Complete keyboard map + commands a professional editor is expected to have."""

        def keys(act: QAction, *seqs: str) -> None:
            act.setShortcuts([QKeySequence(s) for s in seqs])

        # --- standard keys that were missing / platform-empty on Windows
        keys(self.act_exit, "Ctrl+Q")
        keys(self.act_close, "Ctrl+W", "Ctrl+F4")
        keys(self.act_save_as, "Ctrl+Shift+S")
        keys(self.act_redo, "Ctrl+Y", "Ctrl+Shift+Z")
        keys(self.act_zoom_in, "Ctrl+=", "Ctrl++")
        keys(self.act_zoom_out, "Ctrl+-")
        keys(self.act_find_next, "F3")
        keys(self.act_prev, "PgUp")
        keys(self.act_next, "PgDown")
        # --- tool keys (single letters; in-place typing overrides them)
        keys(self.act_select_tool, "V")
        keys(self.act_text_tool, "T")
        keys(self.act_image_tool, "I")
        keys(self.act_annot_rect, "R")
        keys(self.act_annot_ellipse, "E")
        keys(self.act_annot_line, "L")
        keys(self.act_annot_arrow, "A")
        keys(self.act_annot_ink, "P")
        keys(self.act_annot_highlight, "H")
        keys(self.act_annot_eraser, "Shift+E")
        keys(self.act_annot_underline, "U")
        keys(self.act_annot_strike, "K")
        keys(self.act_annot_comment, "N")
        # --- arrange
        keys(self.act_bring_forward, "Ctrl+]")
        keys(self.act_send_backward, "Ctrl+[")
        keys(self.act_bring_front, "Ctrl+Shift+]")
        keys(self.act_send_back, "Ctrl+Shift+[")
        # --- pages
        keys(self.act_insert_blank, "Ctrl+Shift+N")
        keys(self.act_insert_pdf, "Ctrl+Shift+I")
        keys(self.act_delete_pages, "Ctrl+Shift+Del")
        keys(self.act_rotate_cw, "Ctrl+R")
        keys(self.act_rotate_ccw, "Ctrl+Shift+R")
        keys(self.act_extract_pages, "Ctrl+Shift+E")
        keys(self.act_merge, "Ctrl+Shift+M")
        keys(self.act_highlight_fields, "Ctrl+Shift+H")

        # --- clearer menu wording (toolbar keeps short iconText)
        self.act_annot_highlight.setText("&Highlight Text")
        self.act_annot_underline.setText("&Underline Text")
        self.act_annot_strike.setText("Stri&kethrough Text")
        self.act_annot_comment.setText("Sticky &Note Comment…")
        self.act_annot_callout.setText("Call&out…")
        self.act_annot_stamp.setText("S&tamp…")
        self.act_annot_ink.setText("&Freehand")
        self.act_redact_mark.setText("&Mark Area for Redaction")
        self.act_redact_text.setText("Mark &Text for Redaction…")
        self.act_sig_drawn.setText("&Drawn Visual Signature…")
        self.act_mode_edit.setText("&Edit")
        self.act_mode_forms.setText("&Forms")
        self.act_mode_layout.setText("&Layout")
        self.act_mode_tables.setText("Ta&bles")
        self.act_toggle_left.setText("&Navigation Panel")
        self.act_toggle_right.setText("&Properties Panel")
        self.act_rotate_cw.setText("Rotate &Clockwise")
        self.act_rotate_ccw.setText("Rotate C&ounterclockwise")
        self.act_about.setText(f"&About {PRODUCT_NAME}")
        renames = {
            self.act_images_to_pdf: ("&Images to PDF…", "Create a PDF from one or more images"),
            self.act_office_to_pdf: ("&Word, Excel or PowerPoint to PDF…", "Convert an Office document to PDF with its exact layout"),
            self.act_pdf_to_docx: ("PDF to &Word…", "Editable Word document that keeps fonts, tables and images"),
            self.act_tables_xlsx: ("PDF Tables to &Excel…", "Detected tables as Excel worksheets"),
            self.act_pdf_to_pptx: ("PDF to &PowerPoint…", "Slides at the PDF's page size — layout-preserving or editable text; "
                                   "choose how pages of different sizes are handled"),
            self.act_annot_callout: ("Call&out…", "Add a callout: a text box with a line pointing to a spot on the page"),
            self.act_annot_stamp: ("St&amp…", "Place a stamp — Approved, Draft, Confidential … or your own text or picture"),
            self.act_save_copy: ("&Whole Document (Keep Working on This One)…",
                                 "Save the document as it is now, with unsaved changes, to a separate file; "
                                 "the open document stays as it is"),
            self.act_check_updates: ("&Check for Updates…", "Check whether a newer verified version of Monograph PDF is available"),
            self.act_about: (f"&About {PRODUCT_NAME}", "Version, build, licence and third-party notices"),
            self.act_pdf_to_images: ("PDF to Ima&ges…", "Save pages as PNG, JPEG or TIFF images"),
            self.act_pdf_to_text: ("PDF to &Text…", "Save the text as a .txt file"),
            self.act_extract_images: ("E&xtract Images…", "Save the pictures embedded in the PDF"),
            self.act_convert_caps: ("Conversion &Quality Guide…", "What each conversion keeps and its limits"),
            self.act_searchable: ("Make &Searchable PDF…", "Add an invisible text layer to scanned pages (offline OCR)"),
            self.act_ocr_document: ("OCR &Whole Document…", "Recognize text on every scanned page"),
            self.act_ocr_pages: ("OCR &Current Page…", "Recognize text on the current page"),
            self.act_make_editable: ("&Make PDF Editable…", "Check the document and OCR only the pages that need it"),
            self.act_pages_export: ("Selected &Pages as PDF…", "Save the selected pages as a new PDF"),
            self.act_flatten_export: ("&Flattened PDF…", "Save a copy with form fields and comments merged into the pages"),
            self.act_meta_copy: ("Copy with &Metadata…", "Save an identical copy that keeps the document properties"),
            self.act_optimize: ("Co&mpress PDF…", "Make the file smaller: lossless, balanced, smallest, or an exact maximum size"),
            self.act_export_image: ("Save Selected &Image As…", "Save the selected image object to a file"),
            self.act_replace_image: ("&Replace Selected Image…", "Swap the selected image for another file"),
            self.act_sec_protect: ("&Protect with Password…", "Require a password to open, and restrict printing, copying or editing"),
            self.act_sec_remove: ("&Unlock PDF (Remove Password)…", "Save a copy without a password or restrictions"),
            self.act_sec_perms: ("View &Permissions…", "Show what the document allows (print, copy, edit…)"),
            self.act_sec_meta: ("View &Metadata…", "Show title, author and other document properties"),
            self.act_sec_attach: ("View &Attachments…", "List files embedded in the PDF"),
            self.act_sec_meta_rm: ("&Remove Metadata…", "Save a copy without title, author and other hidden information"),
            self.act_redact_mark: ("Mark &Area for Redaction", "Drag over content to remove"),
            self.act_redact_text: ("Mark &Text for Redaction…", "Find and mark every occurrence of a word or phrase"),
            self.act_redact_pages: ("Mark &Whole Pages for Redaction…", "Mark everything on chosen pages; the pages stay, empty"),
            self.act_redact_preview: ("&Count Marked Redactions", "How many areas are marked and not yet removed"),
            self.act_redact_apply: ("Apply &Redactions…", "Permanently remove the marked content and save a copy"),
            self.act_sig_typed: ("&Type a Signature…", "Type your name and place it as a visual signature"),
            self.act_sig_drawn: ("&Draw a Signature…", "Draw your signature with the mouse or a pen"),
            self.act_sig_image: ("Signature from &Image…", "Place a scanned or photographed signature"),
            self.act_watermark: ("&Watermark…", "Add text such as CONFIDENTIAL across the pages"),
            self.act_header_footer: ("&Header, Footer && Page Numbers…", "Add text and page numbers to the page margins"),
            self.act_background: ("&Background…", "Put a color or picture behind the page content"),
            self.act_remove_page_design: ("&Remove Header, Footer, Watermark or Background…",
                                          "Remove page design added earlier by Monograph PDF"),
            self.act_merge: ("&Merge PDFs…", "Combine several PDFs into one file"),
            self.act_split: ("&Split PDF…", "Split into several files by page ranges or bookmarks"),
            self.act_page_sizes: ("Change Page &Size…", "Convert pages to A4, Letter, Legal, B5 … and fit the content"),
            self.act_crop_page: ("&Crop Page…", "Trim the margins of the current page"),
            self.act_replace_page: ("Re&place Page…", "Replace the current page with a page from another PDF"),
            self.act_copy_to_doc: ("Copy Pages to Another PDF…", "Append the selected pages to another PDF (saved as a new file)"),
            self.act_move_to_doc: ("Move Pages to Another PDF…", "Move the selected pages into another PDF (saved as a new file)"),
            self.act_shape_circle: ("&Circle", "Draw a circle"),
            self.act_policy_smart: ("&Smart Layout", "Move only clearly related objects together — never unrelated content"),
            self.act_align_ch: ("Align Horizontal &Centers", "Line up the centers of the selected objects left-to-right"),
            self.act_align_cv: ("Align &Vertical Centers", "Line up the middles of the selected objects top-to-bottom"),
            self.act_form_accept: ("&Keep Detected Fields", "Turn the suggested fields into real form fields"),
            self.act_form_reject: ("&Discard Detected Fields", "Remove the suggested fields"),
            self.act_form_detect: ("&Detect Fields", "Suggest form fields from boxes and lines on the page"),
            self.act_form_select: ("&Select Fields", "Select, move and resize form fields"),
            self.act_form_multi: ("&Multi-line Text Field", "Add a text field that wraps onto several lines"),
            self.act_form_drop: ("Drop-down &List", "Add a drop-down list field"),
            self.act_theme_system: ("&System", "Follow the Windows light or dark setting"),
            self.act_highlight_fields: ("&Highlight Fillable Fields", "Tint fillable fields on screen (not saved into the PDF)"),
            self.act_flatten: ("&Flatten Form on Save", "When saving, merge field values into the page so they can no longer be edited"),
        }
        for act, (text, tip) in renames.items():
            act.setText(text)
            act.setToolTip(tip)
            act.setStatusTip(tip)
        for act, short in (
            (self.act_open, "Open"),
            (self.act_save, "Save"),
            (self.act_print, "Print"),
            (self.act_undo, "Undo"),
            (self.act_redo, "Redo"),
            (self.act_select_tool, "Select"),
            (self.act_text_tool, "Text"),
            (self.act_image_tool, "Image"),
            (self.act_annot_highlight, "Highlight"),
            (self.act_annot_eraser, "Eraser"),
            (self.act_annot_comment, "Comment"),
            (self.act_fit_width, "Fit Width"),
            (self.act_fit_page, "Fit Page"),
            (self.act_actual, "Actual Size"),
        ):
            act.setIconText(short)

        # --- workspace modes are an exclusive, visible choice
        self._mode_group = QActionGroup(self)
        self._mode_group.setExclusive(True)
        for act in (self.act_mode_edit, self.act_mode_forms, self.act_mode_layout, self.act_mode_tables):
            act.setCheckable(True)
            self._mode_group.addAction(act)
        self.act_mode_edit.setChecked(True)
        self._policy_group = QActionGroup(self)
        self._policy_group.setExclusive(True)
        self._policy_group.addAction(self.act_policy_preserve)
        self._policy_group.addAction(self.act_policy_smart)

        # --- new commands
        def new(text: str, slot, *shortcut: str, tip: str = "", checkable: bool = False) -> QAction:
            act = QAction(text, self)
            if shortcut:
                act.setShortcuts([QKeySequence(s) for s in shortcut])
            if tip:
                act.setToolTip(tip)
                act.setStatusTip(tip)
            act.setCheckable(checkable)
            act.triggered.connect(slot)
            return act

        self.act_field_prev = new("Previous Field", lambda: self._canvas._canvas.tab_to_next_field(reverse=True),  # noqa: SLF001
                                  tip="Previous fillable field (Shift+Tab)")
        self.act_field_next = new("Next Field", lambda: self._canvas._canvas.tab_to_next_field(),  # noqa: SLF001
                                  tip="Next fillable field (Tab)")
        self.act_field_clear = new("Clear Field", self._clear_selected_field, tip="Empty the selected field")
        set_action_icon(self.act_field_prev, "prev")
        set_action_icon(self.act_field_next, "next")
        set_action_icon(self.act_field_clear, "close")
        self.act_rotate_pages = new(
            "&Rotate Pages…", self._rotate_pages_dialog, tip="Rotate all, odd, even, selected or a range of pages"
        )
        set_action_icon(self.act_rotate_pages, "rotate_cw")
        self.act_default_app = new(
            "Make Monograph PDF the Default PDF App…",
            self._make_default_app,
            tip="Open Windows settings to choose Monograph PDF for .pdf files",
        )
        self.act_default_app.setVisible(sys.platform.startswith("win"))
        set_action_icon(self.act_default_app, "default_app")
        self.act_select_all = new("Select &All", self._select_all, "Ctrl+A")
        self.act_deselect = new("D&eselect All", self._deselect_all, "Ctrl+Shift+A")
        self.act_find_prev = new("Find Pre&vious", self._find_prev, "Shift+F3")
        self.act_first = new("&First Page", self._first_page, "Home")
        self.act_last = new("&Last Page", self._last_page, "End")
        self.act_goto = new("&Go to Page…", self._go_to_page_dialog, "Ctrl+G")
        self.act_fullscreen = new("F&ull Screen", self._toggle_fullscreen, "F11", checkable=True)
        self.act_print_preview = new("Print Pre&view…", self._print_preview, "Ctrl+Shift+P")
        self.addAction(self.act_print_preview)  # shortcut only — the Print dialog has the preview
        self.act_doc_props = new(
            "Document &Properties…", self._show_document_properties, "Ctrl+Alt+D",
            tip="Title, author, page size, security and form information",
        )
        self.act_show_in_folder = new(
            "Show in &Folder", self._show_in_folder, tip="Open the folder that contains this PDF"
        )
        self.act_clear_recent = new("&Clear Recent Files", self._clear_recent)
        self.act_add_bookmark = new(
            "&Bookmark for This Page…", lambda: self._bookmark_add(self._left.current_bookmark()), "Ctrl+B",
            tip="Add a bookmark that opens the current page",
        )
        set_action_icon(self.act_add_bookmark, "bookmark_add")
        self.act_remove_hidden = new(
            "Remove &Hidden Information…", self._remove_hidden_info,
            tip="Find and remove metadata, attached files, scripts, comments and other hidden content",
        )
        set_action_icon(self.act_remove_hidden, "sanitize")
        self.act_copy_page_image = new(
            "Copy Page as &Picture", self._copy_page_as_picture, "Ctrl+Alt+C",
            tip="Copy the current page, as shown, to the clipboard as a picture",
        )
        set_action_icon(self.act_copy_page_image, "snapshot")
        self.act_shortcuts = new("&Keyboard Shortcuts", self._show_shortcuts, "Ctrl+/", "F12")
        self.act_user_guide = new("&User Guide", self._show_user_guide, "F1")

        self._doc_actions_extra = (
            self.act_select_all,
            self.act_deselect,
            self.act_find_prev,
            self.act_first,
            self.act_last,
            self.act_goto,
            self.act_print_preview,
            self.act_doc_props,
            self.act_show_in_folder,
            self.act_field_prev,
            self.act_field_next,
            self.act_field_clear,
            self.act_rotate_pages,
            self.act_add_bookmark,
            self.act_remove_hidden,
            self.act_copy_page_image,
        )

    def _assign_icons(self) -> None:
        mapping = {
            "open": self.act_open,
            "save": self.act_save,
            "save_as": self.act_save_as,
            "save_copy": self.act_save_copy,
            "close": self.act_close,
            "print": self.act_print,
            "exit": self.act_exit,
            "undo": self.act_undo,
            "redo": self.act_redo,
            "cut": self.act_cut,
            "copy": self.act_copy,
            "paste": self.act_paste,
            "duplicate": self.act_duplicate,
            "delete": self.act_delete,
            "select_all": self.act_select_all,
            "style_copy": self.act_copy_style,
            "find": self.act_find,
            "select": self.act_select_tool,
            "text": self.act_text_tool,
            "image": self.act_image_tool,
            "rect": self.act_annot_rect,
            "ellipse": self.act_annot_ellipse,
            "circle": self.act_shape_circle,
            "line": self.act_annot_line,
            "arrow": self.act_annot_arrow,
            "freehand": self.act_annot_ink,
            "highlight": self.act_annot_highlight,
            "eraser": self.act_annot_eraser,
            "underline": self.act_annot_underline,
            "strikeout": self.act_annot_strike,
            "squiggly": self.act_annot_squiggly,
            "comments_panel": self.act_show_comments,
            "comment": self.act_annot_comment,
            "callout": self.act_annot_callout,
            "stamp": self.act_annot_stamp,
            "zoom_in": self.act_zoom_in,
            "zoom_out": self.act_zoom_out,
            "fit_width": self.act_fit_width,
            "fit_page": self.act_fit_page,
            "actual_size": self.act_actual,
            "prev": self.act_prev,
            "next": self.act_next,
            "first": self.act_first,
            "last": self.act_last,
            "goto": self.act_goto,
            "panel_left": self.act_toggle_left,
            "panel_right": self.act_toggle_right,
            "fullscreen": self.act_fullscreen,
            "fields": self.act_highlight_fields,
            "info": self.act_doc_props,
            "keyboard": self.act_shortcuts,
            "help": self.act_user_guide,
            "page_add": self.act_insert_blank,
            "page_insert": self.act_insert_pdf,
            "page_delete": self.act_delete_pages,
            "page_duplicate": self.act_dup_pages,
            "page_replace": self.act_replace_page,
            "rotate_cw": self.act_rotate_cw,
            "rotate_ccw": self.act_rotate_ccw,
            "crop": self.act_crop_page,
            "extract": self.act_extract_pages,
            "page_size": self.act_page_sizes,
            "merge": self.act_merge,
            "split": self.act_split,
            "import_images": self.act_images_to_pdf,
            "text_file": self.act_pdf_to_text,
            "pdf_to_word": self.act_pdf_to_docx,
            "table": self.act_tables_xlsx,
            "export": self.act_pages_export,
            "optimize": self.act_optimize,
            "watermark": self.act_watermark,
            "header_footer": self.act_header_footer,
            "capabilities": self.act_convert_caps,
            "magic": self.act_make_editable,
            "ocr": self.act_ocr_document,
            "lock": self.act_sec_protect,
            "unlock": self.act_sec_remove,
            "shield": self.act_sec_perms,
            "metadata": self.act_sec_meta,
            "attachments": self.act_sec_attach,
            "redact": self.act_redact_mark,
            "redact_apply": self.act_redact_apply,
            "sign": self.act_sig_typed,
            "sign_draw": self.act_sig_drawn,
            "sign_image": self.act_sig_image,
            "form": self.act_mode_forms,
            "checkbox": self.act_form_check,
            "radio": self.act_form_radio,
            "dropdown": self.act_form_drop,
            "detect": self.act_form_detect,
            "bring_forward": self.act_bring_forward,
            "send_backward": self.act_send_backward,
            "obj_align_left": self.act_align_left,
            "obj_align_center": self.act_align_ch,
            "distribute": self.act_dist_h,
            "theme": self.act_theme_system,
            "recent": self._recent_menu.menuAction() if hasattr(self, "_recent_menu") else None,
            "bold": self.act_font_bold,
            "italic": self.act_font_italic,
            "underline_fmt": self.act_font_underline,
            "align_left": self.act_align_text_left,
            "align_center": self.act_align_text_center,
            "align_right": self.act_align_text_right,
            "align_justify": self.act_align_text_justify,
            "valign_top": self.act_valign_top,
            "valign_middle": self.act_valign_middle,
            "valign_bottom": self.act_valign_bottom,
            "wrap_text": self.act_text_wrap,
            "case_upper": self.act_case_upper,
            "case_lower": self.act_case_lower,
            "font_smaller": self.act_font_dec,
            "font_larger": self.act_font_inc,
            "color": self.act_text_color,
        }
        apply_toolbar_icons({k: v for k, v in mapping.items() if v is not None})
        for name, act in (
            ("image", self.act_pdf_to_images),
            ("image", self.act_extract_images),
            ("searchable", self.act_searchable),
            ("batch", self.act_batch_convert),
            ("ocr", self.act_ocr_pages),
            ("area_ocr", self.act_ocr_area),
            ("text_extract", self.act_ocr_extract),
            ("language", self.act_ocr_languages),
            ("pages_to_doc", self.act_scan_to_word),
            ("export", self.act_flatten_export),
            ("copy", self.act_meta_copy),
            ("pdf_to_pptx", self.act_pdf_to_pptx),
            ("convert", self.act_office_to_pdf),
            ("image", self.act_export_image),
            ("page_replace", self.act_replace_image),
            ("metadata", self.act_sec_meta_rm),
            ("find", self.act_redact_text),
            ("text", self.act_form_text),
            ("text_file", self.act_form_multi),
            ("sign_draw", self.act_form_sig),
            ("table", self.act_detect_tables),
            ("style_copy", self.act_paste_style),
            ("bring_forward", self.act_bring_front),
            ("send_backward", self.act_send_back),
            ("obj_align_right", self.act_align_right),
            ("obj_align_top", self.act_align_top),
            ("obj_align_middle", self.act_align_cv),
            ("obj_align_bottom", self.act_align_bottom),
            ("distribute_v", self.act_dist_v),
            ("find_next", self.act_find_next),
            ("find_prev", self.act_find_prev),
            ("deselect", self.act_deselect),
            ("folder", self.act_show_in_folder),
            ("clear_list", self.act_clear_recent),
            ("background", self.act_background),
            ("page_design_remove", self.act_remove_page_design),
            ("select_fields", self.act_form_select),
            ("date_field", self.act_form_date),
            ("accept", self.act_form_accept),
            ("reject", self.act_form_reject),
            ("row_add", self.act_table_add_row),
            ("row_delete", self.act_table_del_row),
            ("col_add", self.act_table_add_col),
            ("col_delete", self.act_table_del_col),
            ("pages_to_doc", self.act_copy_to_doc),
            ("pages_move", self.act_move_to_doc),
            ("pages_reorder", self.act_move_pages),
            ("redact_pages", self.act_redact_pages),
            ("count", self.act_redact_preview),
            ("about", self.act_about),
            ("updates", self.act_check_updates),
            ("settings", self.act_settings),
            ("rotate_cw", self.act_rotate_pages),
        ):
            set_action_icon(act, name)

    def _decorate_tooltips(self) -> None:
        """Every action tooltip names its keyboard shortcut (e.g. “Undo (Ctrl+Z)”)."""
        for act in self.findChildren(QAction):
            if act.isSeparator() or act.menu() is not None:
                continue
            base = act.property("baseToolTip")
            if base is None:
                tip = re.sub(r"\s*\((?:Ctrl|Shift|Alt|F\d)[^)]*\)\s*$", "", act.toolTip() or "")
                text = act.text().replace("&&", "\u0000").replace("&", "").replace("\u0000", "&")
                if not tip or tip.replace("&", "") == text.replace("&", ""):
                    tip = text.rstrip("…").strip()
                act.setProperty("baseToolTip", tip)
                base = tip
            seq = act.shortcut()
            if not seq.isEmpty():
                act.setToolTip(f"{base}  ({seq.toString(QKeySequence.SequenceFormat.NativeText)})")
            else:
                act.setToolTip(str(base))

    def _menu_section(self, menu: QMenu, title: str) -> None:
        """Small caps group label inside a menu (Fusion draws addSection() as a bare line)."""
        if menu.actions():
            menu.addSeparator()
        label = QLabel(title.replace("&&", "&").upper())
        label.setObjectName("MenuSection")
        act = QWidgetAction(menu)
        act.setDefaultWidget(label)
        act.setText(title.replace("&&", "&"))
        act.setEnabled(False)
        menu.addAction(act)

    def _build_menu(self) -> None:
        """File · Edit · View · Insert · Forms · Organize · Convert · OCR · Protect · Sign · Export · Help."""
        mb = self.menuBar()

        # ---------------------------------------------------------------- File
        file_menu = mb.addMenu("&File")
        file_menu.addAction(self.act_open)
        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()
        file_menu.addAction(self.act_close)
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        copy_menu = file_menu.addMenu("Save a &Copy")
        set_action_icon(copy_menu.menuAction(), "export")
        for act in (self.act_save_copy, self.act_pages_export, self.act_flatten_export, self.act_meta_copy):
            copy_menu.addAction(act)
        file_menu.addAction(self.act_optimize)
        file_menu.addSeparator()
        file_menu.addAction(self.act_print)
        file_menu.addSeparator()
        file_menu.addAction(self.act_doc_props)
        file_menu.addAction(self.act_show_in_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.act_settings)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        # ---------------------------------------------------------------- Edit
        edit = mb.addMenu("&Edit")
        edit.addAction(self.act_undo)
        edit.addAction(self.act_redo)
        edit.addSeparator()
        edit.addAction(self.act_cut)
        edit.addAction(self.act_copy)
        edit.addAction(self.act_paste)
        edit.addAction(self.act_duplicate)
        edit.addAction(self.act_delete)
        edit.addAction(self.act_copy_page_image)
        edit.addSeparator()
        edit.addAction(self.act_select_tool)
        edit.addAction(self.act_select_all)
        edit.addAction(self.act_deselect)
        edit.addSeparator()
        edit.addAction(self.act_copy_style)
        edit.addAction(self.act_paste_style)
        edit.addSeparator()
        arrange = edit.addMenu("Arra&nge")
        set_action_icon(arrange.menuAction(), "bring_forward")
        for act in (self.act_bring_front, self.act_bring_forward, self.act_send_backward, self.act_send_back):
            arrange.addAction(act)
        align = edit.addMenu("Ali&gn && Distribute")
        set_action_icon(align.menuAction(), "obj_align_left")
        for act in (self.act_align_left, self.act_align_ch, self.act_align_right):
            align.addAction(act)
        align.addSeparator()
        for act in (self.act_align_top, self.act_align_cv, self.act_align_bottom):
            align.addAction(act)
        align.addSeparator()
        align.addAction(self.act_dist_h)
        align.addAction(self.act_dist_v)
        self._menu_section(align, "Layout policy")
        align.addAction(self.act_policy_preserve)
        align.addAction(self.act_policy_smart)
        modes = edit.addMenu("&Workspace Mode")
        set_action_icon(modes.menuAction(), "edit_text")
        for act in (self.act_mode_edit, self.act_mode_forms, self.act_mode_layout, self.act_mode_tables):
            modes.addAction(act)
        image_menu = edit.addMenu("Selected I&mage")
        set_action_icon(image_menu.menuAction(), "image")
        image_menu.addAction(self.act_replace_image)
        image_menu.addAction(self.act_export_image)
        edit.addSeparator()
        edit.addAction(self.act_find)
        edit.addAction(self.act_find_next)
        edit.addAction(self.act_find_prev)

        # ---------------------------------------------------------------- View
        view = mb.addMenu("&View")
        view.addAction(self.act_zoom_in)
        view.addAction(self.act_zoom_out)
        view.addSeparator()
        view.addAction(self.act_actual)
        view.addAction(self.act_fit_width)
        view.addAction(self.act_fit_page)
        view.addSeparator()
        for act in (self.act_first, self.act_prev, self.act_next, self.act_last, self.act_goto):
            view.addAction(act)
        view.addSeparator()
        view.addAction(self.act_toggle_left)
        view.addAction(self.act_show_comments)
        view.addAction(self.act_toggle_right)
        view.addAction(self.act_fullscreen)
        view.addSeparator()
        view.addAction(self.act_highlight_fields)
        view.addSeparator()
        theme_menu = view.addMenu("&Theme")
        set_action_icon(theme_menu.menuAction(), "theme")
        theme_menu.addAction(self.act_theme_system)
        theme_menu.addAction(self.act_theme_light)
        theme_menu.addAction(self.act_theme_dark)

        # ---------------------------------------------------------------- Insert
        insert = mb.addMenu("&Insert")
        insert.addAction(self.act_text_tool)
        insert.addAction(self.act_image_tool)
        shapes = insert.addMenu("&Shapes")
        set_action_icon(shapes.menuAction(), "shapes")
        for act in (
            self.act_annot_rect,
            self.act_annot_ellipse,
            self.act_shape_circle,
            self.act_annot_line,
            self.act_annot_arrow,
            self.act_annot_ink,
        ):
            shapes.addAction(act)
        self._menu_section(insert, "Comments && markup")
        for act in (
            self.act_annot_highlight,
            self.act_annot_eraser,
            self.act_annot_underline,
            self.act_annot_strike,
            self.act_annot_squiggly,
            self.act_annot_comment,
            self.act_annot_callout,
            self.act_annot_stamp,
        ):
            insert.addAction(act)
        self._menu_section(insert, "Navigation")
        insert.addAction(self.act_add_bookmark)
        self._menu_section(insert, "Page design")
        insert.addAction(self.act_watermark)
        insert.addAction(self.act_header_footer)
        insert.addAction(self.act_background)
        insert.addAction(self.act_remove_page_design)

        # ---------------------------------------------------------------- Forms
        forms = mb.addMenu("F&orms")
        forms.addAction(self.act_form_select)
        create = forms.addMenu("&Add Field")
        set_action_icon(create.menuAction(), "form")
        for act in (
            self.act_form_text,
            self.act_form_multi,
            self.act_form_check,
            self.act_form_radio,
            self.act_form_drop,
            self.act_form_date,
            self.act_form_sig,
        ):
            create.addAction(act)
        forms.addSeparator()
        forms.addAction(self.act_form_detect)
        forms.addAction(self.act_form_accept)
        forms.addAction(self.act_form_reject)
        forms.addSeparator()
        forms.addAction(self.act_flatten)
        tables = forms.addMenu("&Tables")
        set_action_icon(tables.menuAction(), "table")
        tables.addAction(self.act_detect_tables)
        tables.addSeparator()
        for act in (self.act_table_add_row, self.act_table_del_row, self.act_table_add_col, self.act_table_del_col):
            tables.addAction(act)

        # ---------------------------------------------------------------- Organize
        organize = mb.addMenu("Or&ganize")
        organize.addAction(self.act_merge)
        organize.addAction(self.act_split)
        organize.addSeparator()
        organize.addAction(self.act_insert_blank)
        organize.addAction(self.act_insert_pdf)
        organize.addAction(self.act_replace_page)
        organize.addAction(self.act_move_pages)
        organize.addSeparator()
        organize.addAction(self.act_dup_pages)
        organize.addAction(self.act_delete_pages)
        organize.addAction(self.act_extract_pages)
        organize.addSeparator()
        organize.addAction(self.act_rotate_pages)
        organize.addAction(self.act_rotate_cw)
        organize.addAction(self.act_rotate_ccw)
        organize.addAction(self.act_crop_page)
        organize.addSeparator()
        organize.addAction(self.act_copy_to_doc)
        organize.addAction(self.act_move_to_doc)
        organize.addAction(self.act_page_sizes)

        # ---------------------------------------------------------------- Convert
        convert = mb.addMenu("&Convert")
        self._menu_section(convert, "Create PDF")
        convert.addAction(self.act_office_to_pdf)
        convert.addAction(self.act_images_to_pdf)
        self._menu_section(convert, "Convert PDF to")
        convert.addAction(self.act_pdf_to_docx)
        convert.addAction(self.act_tables_xlsx)
        convert.addAction(self.act_pdf_to_pptx)
        convert.addAction(self.act_pdf_to_images)
        convert.addAction(self.act_pdf_to_text)
        convert.addSeparator()
        convert.addAction(self.act_batch_convert)
        convert.addSeparator()
        convert.addAction(self.act_extract_images)
        convert.addAction(self.act_convert_caps)

        # ---------------------------------------------------------------- OCR
        ocr = mb.addMenu("OC&R")
        ocr.addAction(self.act_make_editable)
        ocr.addAction(self.act_searchable)
        ocr.addSeparator()
        ocr.addAction(self.act_ocr_area)
        ocr.addAction(self.act_ocr_extract)
        ocr.addAction(self.act_scan_to_word)
        ocr.addSeparator()
        ocr.addAction(self.act_ocr_document)
        ocr.addAction(self.act_ocr_pages)
        ocr.addSeparator()
        ocr.addAction(self.act_ocr_languages)

        # ---------------------------------------------------------------- Protect
        protect = mb.addMenu("&Protect")
        self._menu_section(protect, "Password")
        protect.addAction(self.act_sec_protect)
        protect.addAction(self.act_sec_remove)
        self._menu_section(protect, "Redaction")
        protect.addAction(self.act_redact_mark)
        protect.addAction(self.act_redact_text)
        protect.addAction(self.act_redact_pages)
        protect.addAction(self.act_redact_preview)
        protect.addAction(self.act_redact_apply)
        self._menu_section(protect, "Document information")
        protect.addAction(self.act_sec_perms)
        protect.addAction(self.act_sec_meta)
        protect.addAction(self.act_sec_attach)
        protect.addAction(self.act_sec_meta_rm)
        protect.addAction(self.act_remove_hidden)

        # ---------------------------------------------------------------- Sign
        sign = mb.addMenu("&Sign")
        self._menu_section(sign, "Visual signature (not a digital certificate)")
        sign.addAction(self.act_sig_typed)
        sign.addAction(self.act_sig_drawn)
        sign.addAction(self.act_sig_image)

        # ---------------------------------------------------------------- Help
        help_menu = mb.addMenu("&Help")
        help_menu.addAction(self.act_user_guide)
        help_menu.addAction(self.act_shortcuts)
        help_menu.addSeparator()
        help_menu.addAction(self.act_default_app)
        help_menu.addAction(self.act_check_updates)
        help_menu.addSeparator()
        help_menu.addAction(self.act_about)
        # Python-side references to every menu: QAction.menu() hands out wrappers that may
        # delete the menu when they are garbage-collected, so it is not used for this.
        self._menus_by_action = {m.menuAction(): m for m in self.findChildren(QMenu)}
        for m in mb.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly):
            self._assign_unique_mnemonics(m)
        for m in mb.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly):
            m.aboutToShow.connect(lambda m=m: self._sync_submenus(m))

    def _assign_unique_mnemonics(self, menu: QMenu) -> None:
        """Every item in a menu gets its own Alt-letter. An item keeps its letter when no earlier
        item uses it; otherwise it moves to a free letter (start of a word first, then any letter).
        Runs over submenus too; Open Recent numbers its own entries."""
        if menu is getattr(self, "_recent_menu", None):
            return
        used: set[str] = set()
        pending: list[QAction] = []
        for a in menu.actions():
            if a.isSeparator() or isinstance(a, QWidgetAction):
                continue
            plain = a.text().replace("&&", "\u0000")
            i = plain.find("&")
            letter = plain[i + 1].lower() if 0 <= i < len(plain) - 1 else ""
            if letter and letter.isalnum() and letter not in used:
                used.add(letter)
            else:
                pending.append(a)
        for a in pending:
            plain = a.text().replace("&&", "\u0000").replace("&", "")
            words = [k for k, ch in enumerate(plain) if ch.isalpha() and (k == 0 or not plain[k - 1].isalnum())]
            others = [k for k, ch in enumerate(plain) if ch.isalnum() and k not in words]
            for k in words + others:
                if plain[k].lower() not in used:
                    used.add(plain[k].lower())
                    plain = plain[:k] + "&" + plain[k:]
                    break
            a.setText(plain.replace("\u0000", "&&"))
        for a in menu.actions():
            sub = self._menus_by_action.get(a)
            if sub is not None:
                self._assign_unique_mnemonics(sub)

    def _sync_submenus(self, menu: QMenu | None = None) -> None:
        """A submenu is enabled only when something in it can be used (Open Recent always opens,
        to show “No recent files”)."""
        recent = getattr(self, "_recent_menu", None)
        menus_by_action = getattr(self, "_menus_by_action", {})

        def walk(m: QMenu) -> bool:
            usable = False
            for a in m.actions():
                if a.isSeparator() or not a.isVisible():
                    continue
                sub = menus_by_action.get(a)
                if sub is not None:
                    inner = walk(sub)
                    if sub is recent:
                        inner = True
                    a.setEnabled(inner)
                    usable |= inner
                elif not isinstance(a, QWidgetAction) and a.isEnabled():
                    usable = True
            return usable

        if menu is None:
            bar = self.menuBar().actions()
            menus = [menus_by_action[a] for a in bar if a in menus_by_action]
        else:
            menus = [menu]
        for m in menus:
            walk(m)

    def _build_toolbar(self) -> None:
        self._assign_icons()

        # Fit split button: click = last fit mode; menu = Width / Page / Actual
        fit_menu = QMenu(self)
        fit_menu.addAction(self.act_fit_width)
        fit_menu.addAction(self.act_fit_page)
        fit_menu.addAction(self.act_actual)
        self._fit_button.setMenu(fit_menu)
        self._fit_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        last = getattr(self._prefs, "last_fit_mode", "fit_width")
        self._fit_button.setDefaultAction(
            {"fit_page": self.act_fit_page, "actual_size": self.act_actual}.get(last, self.act_fit_width)
        )

        bar = QToolBar("Main Toolbar")
        bar.setObjectName("MainToolbar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(QSize(20, 20))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        bar.toggleViewAction().setEnabled(False)
        self._main_bar = bar
        self.addToolBar(bar)

        self._labelled_buttons: list[QToolButton] = []
        self._main_bar_full_width = 0

        def labelled(act: QAction) -> None:
            bar.addAction(act)
            btn = bar.widgetForAction(act)
            if isinstance(btn, QToolButton):
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                self._labelled_buttons.append(btn)

        for act in (self.act_open, self.act_save, self.act_print):
            bar.addAction(act)
        bar.addSeparator()
        bar.addAction(self.act_undo)
        bar.addAction(self.act_redo)
        bar.addSeparator()
        labelled(self.act_select_tool)
        labelled(self.act_text_tool)
        bar.addAction(self.act_image_tool)

        # Shape ▾ split button — same actions as Insert ▸ Shapes
        self._shape_button = QToolButton()
        self._shape_button.setObjectName("ShapeButton")
        self._shape_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self._shape_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        shape_menu = QMenu(self)
        for act in (
            self.act_annot_rect,
            self.act_annot_ellipse,
            self.act_shape_circle,
            self.act_annot_line,
            self.act_annot_arrow,
            self.act_annot_ink,
        ):
            shape_menu.addAction(act)
        self._shape_button.setMenu(shape_menu)
        self._shape_button.setDefaultAction(self.act_annot_rect)
        bar.addWidget(self._shape_button)
        labelled(self.act_annot_highlight)
        self._highlight_color_button = self._build_highlight_color_button()
        bar.addWidget(self._highlight_color_button)
        # enabled together with the Highlight tool (no document: shown pale like the other disabled tools)
        self.act_annot_highlight.changed.connect(
            lambda: self._highlight_color_button.setEnabled(self.act_annot_highlight.isEnabled()))
        self._highlight_color_button.setEnabled(self.act_annot_highlight.isEnabled())
        labelled(self.act_annot_eraser)
        bar.addAction(self.act_annot_comment)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)

        bar.addWidget(self._fit_button)
        bar.addAction(self.act_zoom_out)
        bar.addWidget(self._toolbar_zoom)
        bar.addAction(self.act_zoom_in)
        bar.addSeparator()
        bar.addAction(self.act_prev)
        bar.addWidget(self._page_edit)
        bar.addWidget(self._page_indicator)
        bar.addAction(self.act_next)

        spacer2 = QWidget()
        spacer2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer2)
        bar.addWidget(self._search_edit)
        bar.addSeparator()
        bar.addAction(self.act_toggle_left)
        bar.addAction(self.act_toggle_right)

        self.addToolBarBreak()
        self._context_bar = QToolBar("Context")
        # Using the formatting tools keeps a field's in-place editor (and its selected words) open
        self._context_bar.setProperty("keepsInlineEditor", True)
        self._context_bar.setMovable(False)
        self._context_bar.setFloatable(False)
        self._context_bar.setObjectName("ContextToolbar")
        self._context_bar.setIconSize(QSize(18, 18))
        self._context_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._context_bar.toggleViewAction().setEnabled(False)
        self.addToolBar(self._context_bar)
        self._context_hint = QLabel("Select an object for contextual tools")
        self._context_hint.setObjectName("ContextHint")
        self._context_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._context_bar.addWidget(self._context_hint)
        self._font_family_action = QWidgetAction(self)
        self._font_family_action.setDefaultWidget(self._font_family)
        self._font_size_action = QWidgetAction(self)
        self._font_size_action.setDefaultWidget(self._font_size)
        self._decorate_tooltips()

    def _build_central(self) -> None:
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(True)
        self._splitter.addWidget(self._left)
        self._splitter.addWidget(self._center_stack)
        self._splitter.addWidget(self._inspector)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        left_w = 0 if self._prefs.left_panel_collapsed else self._prefs.left_panel_width
        right_w = 0 if self._prefs.right_panel_collapsed else self._prefs.right_panel_width
        # No document: hide inspector by default
        if self._document is None:
            right_w = 0
            self.act_toggle_right.setChecked(False)
        self._splitter.setSizes([left_w, 900, right_w])
        self._left.setVisible(left_w > 0)
        self._inspector.setVisible(right_w > 0)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        self.setCentralWidget(self._splitter)

    def _build_status(self) -> None:
        self.setStatusBar(self._status)

    def _connect_signals(self) -> None:
        self._left.pageActivated.connect(self._canvas.go_to_page)
        self._left.pagesReordered.connect(self._on_thumbs_reordered)
        self._left.searchRequested.connect(self._run_search_query)
        self._left.bookmarkActivated.connect(self._canvas.go_to_page)
        self._left.bookmarkAddRequested.connect(self._bookmark_add)
        self._left.bookmarkRenameRequested.connect(self._bookmark_rename)
        self._left.bookmarkDeleteRequested.connect(self._bookmark_delete)
        self._left.bookmarkMoveRequested.connect(self._bookmark_move)
        self._left.bookmarkRetargetRequested.connect(self._bookmark_retarget)
        self._left.thumbs.set_context_actions([
            self.act_rotate_cw, self.act_rotate_ccw, None,
            self.act_insert_blank, self.act_insert_pdf, self.act_dup_pages, self.act_replace_page,
            self.act_move_pages, None,
            self.act_extract_pages, self.act_copy_to_doc, self.act_move_to_doc, None,
            self.act_crop_page, self.act_page_sizes, None,
            self.act_delete_pages,
        ])
        self._canvas.annotationSelected.connect(lambda page, xref: self._left.comments.select(page, xref))
        self._canvas.annotationMoveRequested.connect(self._annot_move)
        self._canvas.annotationDeleteRequested.connect(lambda page, xref: self._comment_delete(self._annot_ref(page, xref)))
        self._canvas.annotationEditRequested.connect(lambda page, xref: self._comment_edit_text(self._annot_ref(page, xref)))
        self._canvas.imageEditRequested.connect(self._edit_image_object)
        comments = self._left.comments
        comments.commentActivated.connect(self._comment_go_to)
        comments.editTextRequested.connect(self._comment_edit_text)
        comments.colorRequested.connect(self._comment_color)
        comments.opacityRequested.connect(self._comment_opacity)
        comments.deleteRequested.connect(self._comment_delete)
        self._canvas.pageChanged.connect(self._on_page_changed)
        self._canvas.zoomChanged.connect(self._on_zoom_changed)
        self._canvas.selectionChanged.connect(self._on_selection_changed)
        self._canvas.editModelChanged.connect(self._on_edit_changed)
        self._canvas.requestStatus.connect(self.statusBar().showMessage)
        self._canvas._canvas.history_handler = (  # noqa: SLF001
            lambda op: self._undo() if op == "undo" else self._redo()
        )
        self._canvas.regionPickCancelled.connect(self._on_region_pick_cancelled)
        self._canvas.fieldValueEdited.connect(self._on_field_typed)
        self._canvas.fieldEditorFormatChanged.connect(self._on_field_editor_format)
        self._inspector.styleEdited.connect(self._on_edit_changed)
        self._inspector.pageSizeRequested.connect(lambda: self.act_page_sizes.trigger())
        self._inspector.hideRequested.connect(self._hide_right_panel)
        self._welcome.openRequested.connect(self.open_file_dialog)
        self._welcome.openRecentRequested.connect(self.open_path)
        self._welcome.combineRequested.connect(self._merge_combine)
        self._welcome.imagesToPdfRequested.connect(self._images_to_pdf)
        self._welcome.ocrRequested.connect(self._welcome_ocr)
        self._welcome.toolRequested.connect(self._run_welcome_tool)
        self._welcome.removeRecentRequested.connect(self._remove_recent)
        self._welcome.revealRequested.connect(lambda p: self._reveal_file(Path(p)))

    # --- Document lifecycle ----------------------------------------------

    def open_file_dialog(self) -> None:
        from core.convert.office_bridge import OFFICE_EXTS

        images = " ".join(f"*{e}" for e in IMAGE_EXTS)
        office = " ".join(f"*{e}" for e in OFFICE_EXTS)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open",
            self._doc_dir(),
            f"All supported files (*.pdf {images} {office});;PDF files (*.pdf);;Images ({images});;"
            f"Word, Excel and PowerPoint ({office});;All files (*.*)",
        )
        if path:
            self.open_path(path)

    def _welcome_ocr(self) -> None:
        if self._document is None:
            self.open_file_dialog()
        if self._document is not None:
            self._run_ocr(scope="document")

    def open_path(self, path: str | Path, password: str | None = None) -> bool:
        path = Path(path)
        if self._document is not None and not self._confirm_unsaved("opening another file"):
            return False
        diagnostics.record(EventId.PDF_OPEN_STARTED)
        ext = path.suffix.lower()
        if ext != ".pdf" and path.is_file():
            converted = self._convert_for_viewing(path)
            if converted is None:
                return False
            ok = self.open_path(converted)
            if ok:
                self._converted_from = path
                self._recent.remove(converted)
                self._recent.add(path)
                self._rebuild_recent_menu()
                self._refresh_welcome_recent()
                self._update_title()
                self.statusBar().showMessage(
                    f"Opened {path.name} as a new PDF — use Save to keep it as a PDF file", 8000
                )
            return ok
        self._converted_from = None
        try:
            document = open_document(path, password=password)
        except PasswordRequiredError:
            dlg = PasswordDialog(self, filename=path.name)
            while True:
                if dlg.exec() != dlg.DialogCode.Accepted:
                    return False
                # Password kept only for this authenticate attempt — never stored in Recent/session
                try:
                    document = open_document(path, password=dlg.password())
                    break
                except PasswordRequiredError:
                    dlg.set_incorrect()
                    continue
                except InvalidPdfError as exc:
                    self.report_error(
                        "Cannot open PDF",
                        str(exc),
                        hint="Choose a valid local PDF, or unlock it if password-protected.",
                    )
                    return False
            self._load_document(document)
            self._recent.add(path)
            self._rebuild_recent_menu()
            self._refresh_welcome_recent()
            self._maybe_recover_session(path)
            return True
        except InvalidPdfError as exc:
            self.report_error(
                "Cannot open PDF",
                str(exc),
                hint="Choose a valid local PDF, or unlock it if password-protected.",
            )
            return False
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected(
                "Cannot open PDF",
                exc,
                EventId.PDF_OPEN_FAILED,
                hint="Confirm the file is readable and not in use by another program.",
            )
            return False

        self._load_document(document)
        self._recent.add(path)
        self._rebuild_recent_menu()
        self._refresh_welcome_recent()
        self._maybe_recover_session(path)
        return True

    def _load_document(self, document: PdfDocument) -> None:
        self.close_document(save_session=False)
        self._document = document
        self._edit = EditableDocument(document)
        self._edit.highlight_fillable_fields = bool(self._prefs.highlight_fillable_fields)
        has_fields = bool(self._edit.fields)
        # Default ON when the PDF has forms (unless user turned it off permanently)
        if has_fields and self._prefs.highlight_fillable_fields:
            self._edit.highlight_fillable_fields = True
        self.act_highlight_fields.setChecked(bool(self._edit.highlight_fillable_fields))
        self.act_highlight_fields.setEnabled(has_fields)
        self.act_mode_edit.setChecked(True)
        self.act_policy_preserve.setChecked(True)
        self._edit.add_listener(self._on_edit_changed)
        self._canvas.set_document(document)
        self._canvas.set_edit_model(self._edit)
        self._left.set_document(document)
        self._center_stack.setCurrentWidget(self._canvas)
        self._set_document_actions_enabled(True)
        self._update_workspace_chrome()
        self._update_title()
        self._on_page_changed(0)
        self._on_zoom_changed(self._canvas.zoom)
        self._on_edit_changed()
        self._update_context_toolbar()
        self._autosave.start()
        self._doc_state_label.setText(document.name)
        self._status.set_ready("Ready")
        n = document.page_count
        msg = f"Opened {document.name} ({n} page{'' if n == 1 else 's'})"
        if has_fields:
            msg += " — click fields to fill (Forms Mode not required)"
        self.statusBar().showMessage(msg, 5000)

    def _is_headless_ui(self) -> bool:
        """True for offscreen/CI — avoid modal dialogs that block forever."""
        import os

        from core import app_env

        if app_env.is_true("HEADLESS"):
            return True
        app = QApplication.instance()
        if app is not None:
            platform_name = app.platformName().lower()
            if platform_name in ("offscreen", "minimal", "null"):
                return True
        return os.environ.get("QT_QPA_PLATFORM", "").lower() in (
            "offscreen",
            "minimal",
            "null",
        )

    def _maybe_recover_session(self, path: Path) -> None:
        data = read_session(path)
        if not data:
            return
        payload = data.get("payload") or {}
        if not payload.get("dirty") or not payload.get("objects"):
            return
        if self._is_headless_ui():
            # Non-interactive: discard recovery prompt; leave session file for manual debug
            clear_session(path)
            return
        resp = QMessageBox.question(
            self,
            "Recover editing session",
            "Unsaved edits from a previous session were found. Recover them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.Yes and self._edit is not None:
            self._edit.load_objects(payload)
            self.statusBar().showMessage("Recovered unsaved editing session", 5000)
        else:
            clear_session(path)

    def _keeps_recovery_copy(self) -> bool:
        """No recovery copy for a password-protected PDF: the copy is not encrypted, so it would
        keep the unsaved text and form entries readable without the password."""
        return self._document is not None and self._open_password() is None

    def close_document(self, *, save_session: bool = True) -> None:
        if save_session and self._edit is not None and self._document is not None:
            if self._edit.dirty and self._keeps_recovery_copy():
                try:
                    write_session(self._document.path, self._edit.to_dict())
                except Exception:  # noqa: BLE001
                    pass
            else:
                clear_session(self._document.path)
        self._autosave.stop()
        self._markup_sticky = None
        self._eraser_active = False
        if self._canvas.region_pick_active:
            self._canvas.cancel_region_pick(announce=False)
        self.act_select_tool.setChecked(True)
        self._converted_from = None
        self._search_hits = []
        self._search_index = -1
        self._canvas.clear_highlights()
        self._canvas.set_edit_model(None)
        self._canvas.clear_document()
        self._left.clear_document()
        self._inspector.clear()
        self._edit = None
        if self._document is not None:
            self._document.close()
            self._document = None
        self._search_hits.clear()
        self.clear_analysis_progress()
        self._doc_state_label.setText("")
        self._center_stack.setCurrentWidget(self._welcome)
        self._set_document_actions_enabled(False)
        self._update_workspace_chrome()
        self._update_context_toolbar()
        self._update_title()
        self._page_label.setText("No document")
        self._zoom_label.setText("")
        self._toolbar_zoom.setCurrentText("—")
        self._toolbar_zoom.setEnabled(False)
        self._fit_button.setEnabled(False)
        self.act_highlight_fields.setEnabled(False)
        self._page_indicator.setText("")
        self._page_edit.setText("")
        self._search_edit.clear()
        self._last_query = None
        self._dirty_label.setText("")
        self._dirty_label.setProperty("state", "")
        self._status.set_ready("Ready")
        self._refresh_welcome_recent()

    def _open_password(self) -> str | None:
        """Password of the open protected PDF (memory only), to reopen it after saving."""
        backend = getattr(self._document, "_backend", None) if self._document is not None else None
        return getattr(backend, "_password", None)

    def _report_font_notes(self) -> None:
        """After a save: say which fonts could not be embedded (their text was saved with a built-in face)."""
        from core.editing import system_fonts

        notes = system_fonts.take_notes()
        if not notes:
            return
        lines = chr(10).join(f"•  {family}: {reason}" for family, reason in sorted(notes.items()))
        QMessageBox.information(
            self,
            "Fonts in the saved PDF",
            "Some text could not be saved with the font you chose, so a similar built-in font was used. "
            "It looks the same in Monograph PDF now, but other PDF programs will show a similar, not identical, "
            f"typeface.{chr(10)}{chr(10)}{lines}",
        )

    def _bake_to(self, dest: Path) -> bool:
        """Write the edited document to ``dest``.

        Saving over the file that is open goes through a temporary file in the same folder; the
        open document is released before the swap because Windows cannot replace a file that is
        still open. Returns True when the open document was closed (the caller reopens ``dest``).
        """
        import os
        import time
        import uuid

        from core.editing import system_fonts
        from engines.bake_edits import bake_via_backend

        system_fonts.take_notes()  # forget fallbacks noted by earlier temporary bakes (print, export)
        dest = Path(dest)
        password = self._open_password()
        current = Path(self._document.path) if self._document and self._document.path else None
        try:
            same = current is not None and dest.exists() and os.path.samefile(current, dest)
        except OSError:
            same = current is not None and current.resolve() == dest.resolve()
        if not same:
            bake_via_backend(self._edit, dest)
            return False
        tmp = dest.with_name(f".{dest.stem}.saving-{uuid.uuid4().hex[:8]}.pdf")
        try:
            bake_via_backend(self._edit, tmp)
            self._document.close()  # release the file handle before replacing the file
            delays = (0.1, 0.2, 0.4, 0.8, 1.0, 1.0, 1.0)  # ~4.5 s in all, then the user is told
            for attempt in range(len(delays) + 1):
                try:
                    os.replace(tmp, dest)
                    break
                except PermissionError:
                    # Another program (often an antivirus scan or a PDF viewer) has the file open. The lock is
                    # never bypassed: wait a little, then report it and keep the edits.
                    if attempt == len(delays):
                        raise PermissionError(
                            f"“{dest.name}” is open in another program, so it could not be replaced. "
                            "Your changes are still here — close the other program and save again, "
                            "or use Save As."
                        ) from None
                    time.sleep(delays[attempt])
        except Exception:
            if self._document is not None and getattr(self._document, "_closed", False):
                # Keep working on the original so no edits are lost
                try:
                    self._document = open_document(dest, password=password)
                    self._edit.pdf = self._document
                    self._canvas.set_document(self._document)
                    self._left.set_document(self._document)
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        return True

    def save_document(self) -> None:
        self._commit_field_editor()
        if self._document is None or self._edit is None:
            return
        if getattr(self, "_converted_from", None) is not None:
            # A converted image/Office file has no PDF on disk yet — choose where to save it
            self.save_as_dialog()
            return
        # Explicit Save overwrites the opened path after baking overlays.
        # Original remains intact until this intentional action.
        diagnostics.record(EventId.PDF_SAVE_STARTED)
        try:
            path = self._document.path
            password = self._open_password()
            self._bake_to(path)
            self._edit.mark_clean()
            clear_session(path)
            self._report_font_notes()
            # Continue with the saved file. Everything that was saved (text boxes, pictures, shapes,
            # replaced text, new form fields) is now part of the pages; a fresh editing model keeps it
            # from being drawn — or replaced text removed — a second time on the next Save.
            page = self._canvas.focus_page
            zoom, mode = self._canvas.zoom, self._canvas._canvas.zoom_mode  # noqa: SLF001
            self._load_document(open_document(path, password=password))
            if mode == ZoomMode.MANUAL:
                self._canvas.set_manual_zoom(zoom)
            else:
                self._canvas.set_zoom_mode(mode)
            self._canvas.go_to_page(min(page, self._document.page_count - 1))
            self._update_title()
            self.statusBar().showMessage("Saved", 4000)
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected(
                "Save failed",
                exc,
                EventId.PDF_SAVE_FAILED,
                hint="Try Save As to a new path, or close other apps locking the file.",
            )

    def save_copy_dialog(self, dest: Path | None = None) -> Path | None:
        """Save the document as it is now (with every unsaved change) to a separate file. The open
        document, its path, its undo history and its unsaved state are unchanged; the source file is
        never touched. Returns the written path."""
        self._commit_field_editor()
        if self._document is None or self._edit is None:
            return None
        if dest is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save a Copy", self._suggest("copy", "pdf"), "PDF Files (*.pdf)")
            if not path:
                return None
            dest = Path(path)
        dest = Path(dest)
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_name(dest.name + ".pdf")
        import os

        try:
            same = dest.exists() and os.path.samefile(dest, self._document.path)
        except OSError:
            same = False
        if same:
            if not self._is_headless_ui():
                QMessageBox.information(self, "Save a Copy", "That is the open document itself. Choose another "
                                                             "name or folder, or use Save to replace it.")
            return None
        from engines.bake_edits import bake_via_backend

        try:
            bake_via_backend(self._edit, dest)  # atomic; the editing model is not changed
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected("Save a Copy failed", exc, EventId.PDF_SAVE_FAILED,
                                   hint="Pick a writable folder and ensure the file is not open elsewhere.")
            return None
        self.statusBar().showMessage(f"Saved a copy as {dest.name}; still working on {self._document.name}", 6000)
        return dest

    def save_as_dialog(self) -> None:
        self._commit_field_editor()
        if self._document is None or self._edit is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            self._suggest("" if getattr(self, "_converted_from", None) else "copy", "pdf"),
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        dest = Path(path)
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_suffix(dest.suffix + ".pdf") if dest.suffix else dest.with_suffix(".pdf")
        diagnostics.record(EventId.PDF_SAVE_STARTED)
        try:
            old_path = self._document.path
            password = self._open_password()
            self._bake_to(dest)
            self._edit.mark_clean()
            clear_session(old_path)
            self._report_font_notes()
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected(
                "Save As failed",
                exc,
                EventId.PDF_SAVE_FAILED,
                hint="Pick a writable folder and ensure the filename ends with .pdf.",
            )
            return
        # Continue working on the new file, like every desktop editor does after Save As
        try:
            document = open_document(dest, password=password)
        except Exception:  # noqa: BLE001 — e.g. password-protected copy: keep current view
            self.statusBar().showMessage(f"Saved copy to {dest.name}", 5000)
            self._on_edit_changed()
            return
        page = self._canvas.focus_page
        self._load_document(document)
        self._converted_from = None
        self._update_title()
        self._recent.add(dest)
        self._rebuild_recent_menu()
        self._refresh_welcome_recent()
        self._canvas.go_to_page(min(page, document.page_count - 1))
        self.statusBar().showMessage(f"Saved as {dest.name}", 5000)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._canvas.region_pick_active:
            self._canvas.cancel_region_pick(announce=False)
        if not getattr(self, "_closing_for_update", False) and not self._confirm_unsaved("closing"):
            event.ignore()
            return
        self._persist_preferences()
        dirty_left = bool(self._edit and self._edit.dirty)
        # Headless/CI keeps the crash-recovery session; interactive Don't Save already cleared it
        self.close_document(save_session=dirty_left)
        super().closeEvent(event)

    def _persist_preferences(self) -> None:
        """Write window geometry and panel sizes to user app-data (not project root)."""
        geo = self.geometry()
        self._prefs.window_width = max(self.minimumWidth(), geo.width())
        self._prefs.window_height = max(self.minimumHeight(), geo.height())
        self._prefs.window_x = geo.x()
        self._prefs.window_y = geo.y()
        sizes = self._splitter.sizes()
        if len(sizes) >= 3:
            if sizes[0] > 40:
                self._prefs.left_panel_width = max(72, sizes[0])
            if sizes[2] > 40:
                self._prefs.right_panel_width = max(200, sizes[2])
        self._prefs.left_panel_collapsed = not self._left.isVisible()
        self._prefs.right_panel_collapsed = not self._inspector.isVisible()
        self._prefs.last_zoom = float(self._canvas.zoom)
        try:
            self._prefs.save()
        except Exception as exc:  # noqa: BLE001
            self.statusBar().showMessage(f"Could not save preferences: {exc}", 6000)

    def set_analysis_progress(self, message: str) -> None:
        """Status-bar analysis/progress line (OCR, convert, organize)."""
        self._status.set_analysis_progress(message)

    def clear_analysis_progress(self) -> None:
        self._status.clear_analysis_progress()

    def report_error(self, title: str, detail: str, *, hint: str | None = None) -> None:
        """Show a concise actionable error — never hide failures."""
        text = detail.strip() if detail else "An unexpected error occurred."
        if hint:
            text = f"{text}\n\n{hint}"
        QMessageBox.warning(self, title, text)
        self.statusBar().showMessage(f"{title}: {detail.splitlines()[0] if detail else 'failed'}", 8000)

    def report_unexpected(self, title: str, exc: BaseException, failure: EventId, *, hint: str | None = None) -> None:
        """An operation failed. Expected, environmental problems (a locked or missing file, no
        permission, a full disk) get the usual message; anything else also offers a private problem
        report, which is sent only if the user clicks Send to Developer."""
        diagnostics.record(failure)
        if isinstance(exc, OSError) or self._is_headless_ui():
            self.report_error(title, str(exc), hint=hint)
            return
        from core.diagnostics import report as reports
        from ui.error_report_dialog import ErrorReportDialog

        text = (str(exc).strip() or "An unexpected error occurred.") + (f"\n\n{hint}" if hint else "")
        self.statusBar().showMessage(f"{title}: {text.splitlines()[0]}", 8000)
        try:
            report = reports.build(failure, exc)
        except Exception:  # noqa: BLE001 — never hide the original problem
            self.report_error(title, str(exc), hint=hint)
            return
        ErrorReportDialog(report, summary=f"<b>{title}</b><br>{text}", parent=self).exec()

    def offer_report(self, report: dict, summary: str) -> bool:
        """Show a report built elsewhere (unhandled exception, earlier crash). False when no window
        can show it right now (it is then kept for the next start)."""
        if self._is_headless_ui() or not self.isVisible():
            return False
        from ui.error_report_dialog import ErrorReportDialog

        ErrorReportDialog(report, summary=summary, parent=self).exec()
        return True

    def _autosave_session(self) -> None:
        if self._edit is None or self._document is None or not self._edit.dirty:
            return
        if not self._keeps_recovery_copy():
            return
        try:
            write_session(self._document.path, self._edit.to_dict())
        except Exception:  # noqa: BLE001
            pass

    # --- Editing actions -------------------------------------------------

    def _set_tool(self, tool: EditTool) -> None:
        if self._edit is None and tool != EditTool.SELECT:
            return
        if tool == EditTool.FORM_DETECT:
            self._detect_fields()
            return
        self._markup_sticky = None
        self._eraser_active = False
        if self._canvas.region_pick_active:
            self._canvas.cancel_region_pick(announce=False)
        if self._edit is not None:
            self._canvas.set_tool(tool)
        mapping = {
            EditTool.SELECT: self.act_select_tool,
            EditTool.TEXT_BOX: self.act_text_tool,
            EditTool.SHAPE_RECT: self.act_annot_rect,
            EditTool.SHAPE_ELLIPSE: self.act_annot_ellipse,
            EditTool.SHAPE_LINE: self.act_annot_line,
            EditTool.SHAPE_ARROW: self.act_annot_arrow,
            EditTool.SHAPE_FREEHAND: self.act_annot_ink,
        }
        act = mapping.get(tool)
        if act is not None:
            act.setChecked(True)
            if tool in (
                EditTool.SHAPE_RECT,
                EditTool.SHAPE_ELLIPSE,
                EditTool.SHAPE_LINE,
                EditTool.SHAPE_ARROW,
                EditTool.SHAPE_FREEHAND,
            ):
                self._shape_button.setDefaultAction(act)
        hints = {
            EditTool.SELECT: "Select — click objects, drag to move, double-click text to edit",
            EditTool.TEXT_BOX: "Text Box — click or drag on the page, then type (Esc when done)",
            EditTool.SHAPE_RECT: "Rectangle — drag on the page (Shift = square)",
            EditTool.SHAPE_ELLIPSE: "Ellipse — drag on the page (Shift = circle)",
            EditTool.SHAPE_LINE: "Line — drag on the page (Shift = 45° snap)",
            EditTool.SHAPE_ARROW: "Arrow — drag on the page (Shift = 45° snap)",
            EditTool.SHAPE_FREEHAND: "Freehand — draw on the page",
        }
        self.statusBar().showMessage(hints.get(tool, f"Tool: {tool.value}"), 4000)

    def _start_circle_tool(self) -> None:
        """Circle = ellipse tool with locked 1:1 aspect."""
        self._set_tool(EditTool.SHAPE_ELLIPSE)
        if self._edit is not None:
            self._edit._force_shape_lock = True  # noqa: SLF001
        self.statusBar().showMessage("Circle — drag (aspect locked)", 4000)

    def _pick_text_color(self) -> None:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog

        boxes = self._selected_text_boxes()
        fields = self._selected_style_fields()
        if not self._edit or not (boxes or fields):
            return
        inner = self._canvas._canvas  # noqa: SLF001
        if boxes:
            current = boxes[0].style.text_color or "#000000"
        else:
            current = (inner.field_editor_style() or {}).get("color") or fields[0].text_color or "#000000"
        c = QColorDialog.getColor(QColor(current), self, "Text color")
        if not c.isValid():
            return
        if fields and inner.format_field_selection(color=c.name()):
            return  # only the selected words
        self._restyle_boxes(text_color=c.name())
        if fields:
            self._restyle_field(fields, color=c.name())

    def _set_mode(self, mode: WorkspaceMode) -> None:
        if self._edit is None:
            return
        self._edit.set_mode(mode)
        self._canvas.set_tool(self._edit.tool)
        {
            WorkspaceMode.EDIT: self.act_mode_edit,
            WorkspaceMode.FORMS: self.act_mode_forms,
            WorkspaceMode.LAYOUT: self.act_mode_layout,
            WorkspaceMode.TABLES: self.act_mode_tables,
        }.get(mode, self.act_mode_edit).setChecked(True)
        self.statusBar().showMessage(f"{mode.value.title()} mode", 4000)

    def _detect_fields(self) -> None:
        if self._edit is None:
            return
        n = self._edit.detect_form_fields(self._canvas.focus_page)
        self.statusBar().showMessage(
            f"Detected {n} field candidate(s) for review — document unchanged until Accept",
            6000,
        )

    def _accept_candidates(self) -> None:
        if self._edit is None:
            return
        n = self._edit.accept_candidates()
        self.statusBar().showMessage(f"Accepted {n} candidate field(s)", 4000)

    def _reject_candidates(self) -> None:
        if self._edit is None:
            return
        self._edit.reject_candidates()
        self.statusBar().showMessage("Rejected field candidates", 3000)

    def _toggle_flatten(self, on: bool) -> None:
        if self._edit:
            self._edit.flatten_on_save = on

    def _detect_tables(self) -> None:
        if self._edit is None:
            return
        n = self._edit.detect_tables(self._canvas.focus_page)
        self.statusBar().showMessage(
            f"Found {n} table(s) above confidence threshold (no silent reflow)",
            5000,
        )

    def _table_op(self, op: str) -> None:
        if self._edit is None or not self._edit.tables:
            self.statusBar().showMessage("No tables yet — use Forms ▸ Tables ▸ Detect Tables first", 5000)
            return
        tid = None
        if self._edit.table_selection:
            tid = self._edit.table_selection[0]
        else:
            tid = next((oid for oid in self._edit.selection if oid in self._edit.tables), None)
        if tid is None and len(self._edit.tables) == 1:
            tid = next(iter(self._edit.tables))
        table = self._edit.tables.get(tid) if tid else None
        if table is None:
            self.statusBar().showMessage("Select a table first", 4000)
            return
        if op == "add_row":
            table.add_row()
        elif op == "del_row" and table.nrows > 1:
            table.delete_row(table.nrows - 1)
        elif op == "add_col":
            table.add_column()
        elif op == "del_col" and table.ncols > 1:
            table.delete_column(table.ncols - 1)
        self._edit.mark_dirty()
        self._edit._notify()  # noqa: SLF001

    def _align(self, edge: str) -> None:
        if self._edit:
            self._edit.align_selection(edge)

    def _distribute(self, axis: str) -> None:
        if self._edit:
            self._edit.distribute_selection(axis)

    def _set_layout_policy(self, policy: LayoutPolicy) -> None:
        if self._edit is None:
            return
        self._edit.layout_policy = policy.value
        self.act_policy_preserve.setChecked(policy == LayoutPolicy.PRESERVE)
        self.act_policy_smart.setChecked(policy == LayoutPolicy.SMART)
        note = (
            "Preserve Layout: explicit geometry only"
            if policy == LayoutPolicy.PRESERVE
            else "Smart Layout: related objects only — never moves unrelated content"
        )
        self.statusBar().showMessage(note, 5000)

    def _make_pdf_editable(self) -> None:
        if self._document is None:
            return
        from core.ocr.analysis import analyze_for_editable
        from core.ocr.paths import ocr_ready
        from ui.ocr_dialogs import AnalysisDialog

        analysis = analyze_for_editable(self._document)
        dlg = AnalysisDialog(analysis, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        ok, detail = ocr_ready()
        if not ok:
            self.report_error(
                "OCR unavailable",
                detail,
                hint="The text-recognition engine is missing from this installation. Run Setup again to restore it.",
            )
            return
        self._run_ocr(scope="needed", pages=analysis.pages_needing_ocr, review_overlays=True)

    # --- OCR text: area, pages, Word; languages ----------------------------------------------------

    def _ocr_languages_pref(self) -> str:
        from core.ocr.language_packs import available_languages

        have = available_languages()
        langs = [c for c in (getattr(self._prefs, "ocr_languages", "") or "eng+jpn").split("+") if c in have]
        return "+".join(langs) or "eng+jpn"

    def _ocr_ready_or_report(self) -> bool:
        from core.ocr.paths import ocr_ready

        ok, detail = ocr_ready()
        if not ok:
            self.report_error("OCR unavailable", detail,
                              hint="The text-recognition engine is missing from this installation. Run Setup again to restore it.")
        return ok

    def _ocr_collect(self, opts):
        """Run OCR without writing a file; returns the result, or None if cancelled or failed."""
        from ui.ocr_dialogs import OcrProgressDialog, OcrWorker

        worker = OcrWorker(self._document, opts, None, self)
        dlg = OcrProgressDialog(self)
        dlg.start(worker)
        ok = dlg.exec() == dlg.DialogCode.Accepted and dlg.ocr_result is not None
        worker.wait(10000)
        return dlg.ocr_result if ok else None

    def _show_ocr_text(self, result, title: str, languages: str) -> None:
        from core.convert.office_metadata import document_metadata
        from ui.ocr_dialogs import OcrTextDialog

        stem = self._document.path.stem if self._document is not None else "recognized"
        OcrTextDialog(result, title=title, languages=languages, start_dir=self._doc_dir(),
                      doc_title=f"{stem} (OCR)", metadata=document_metadata(self._document) if self._document else None,
                      parent=self).exec()

    def _ocr_area(self) -> None:
        if self._document is None or not self._ocr_ready_or_report():
            return
        from core.ocr.pipeline import OcrOptions

        languages = self._ocr_languages_pref()

        def apply(page: int, rect) -> None:
            if rect.w < 4 or rect.h < 4:
                self.statusBar().showMessage("Area OCR: drag a rectangle around the text", 5000)
                return
            opts = OcrOptions(languages=languages, pages=[page], region=rect, make_searchable=False,
                              skip_native_text=False, apply_orientation=False, dpi=300)
            result = self._ocr_collect(opts)
            if result is not None:
                skipped = [p for p in result.pages if p.skipped]
                if skipped:
                    self.statusBar().showMessage(f"Area OCR: {skipped[0].skip_reason}", 6000)
                    return
                self._show_ocr_text(result, "Recognized Text — Area", languages)

        self._pick_on_page("Area OCR: drag a rectangle around the text to read", apply, default_size=(0.0, 0.0))

    def _ocr_extract(self) -> None:
        if self._document is None or not self._ocr_ready_or_report():
            return
        from core.ocr.pipeline import OcrOptions
        from ui.ocr_dialogs import OcrScopeDialog

        dlg = OcrScopeDialog(page_count=self._document.page_count, current_page=self._canvas.focus_page,
                             selected=self._left.selected_page_indices(), languages=self._ocr_languages_pref(),
                             parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        languages = dlg.languages.value()
        opts = OcrOptions(languages=languages, pages=dlg.pages(), make_searchable=False,
                          skip_native_text=dlg.skip_text.isChecked())
        result = self._ocr_collect(opts)
        if result is None:
            return
        if not any(p.words for p in result.pages):
            skipped = sum(1 for p in result.pages if p.skipped)
            QMessageBox.information(self, "Extract Text (OCR)",
                                    "No text was recognized." + (f" {skipped} page(s) were skipped because they already contain text." if skipped else ""))
            return
        self._show_ocr_text(result, "Recognized Text", languages)

    def _scan_to_word(self) -> None:
        if self._document is None or not self._ocr_ready_or_report():
            return
        from core.ocr.pipeline import OcrOptions
        from core.ocr.text_export import write_docx
        from ui.convert_dialogs import choose_save
        from ui.ocr_dialogs import OcrScopeDialog

        dlg = OcrScopeDialog(page_count=self._document.page_count, current_page=self._canvas.focus_page,
                             selected=self._left.selected_page_indices(), languages=self._ocr_languages_pref(),
                             title="Scanned PDF to Word", parent=self)
        dlg.r_all.setChecked(True)
        dlg.skip_text.setChecked(False)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        dest = choose_save(self, "Save as Word Document", self._suggest("ocr", "docx"), "Word document (*.docx)")
        if not dest:
            return
        result = self._ocr_collect(OcrOptions(languages=dlg.languages.value(), pages=dlg.pages(), make_searchable=False,
                                              skip_native_text=dlg.skip_text.isChecked()))
        if result is None:
            return
        pages = [p for p in result.pages if p.words]
        if not pages:
            QMessageBox.information(self, "Scanned PDF to Word", "No text was recognized; no document was written.")
            return
        try:
            from core.convert.office_metadata import document_metadata

            write_docx(pages, Path(dest), title=self._document.path.stem,
                       metadata=document_metadata(self._document))
        except Exception as exc:  # noqa: BLE001
            self.report_error("Scanned PDF to Word", f"The document could not be written: {exc}")
            return
        low = sum(1 for p in pages for w in p.words if w.low_confidence)
        self.statusBar().showMessage(
            f"Wrote {Path(dest).name} — {len(pages)} page(s); check {low} low-confidence word(s)" if low
            else f"Wrote {Path(dest).name} — {len(pages)} page(s)", 8000)

    def _ocr_languages(self) -> None:
        from ui.ocr_dialogs import OcrLanguagesDialog

        dlg = OcrLanguagesDialog(self._ocr_languages_pref(), self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self._prefs.ocr_languages = dlg.value()
            self._persist_preferences()
            self.statusBar().showMessage(f"OCR languages: {dlg.value().replace('+', ', ')}", 5000)

    def _run_ocr(self, scope: str = "document", pages: list[int] | None = None, *, review_overlays: bool = False) -> None:
        if self._document is None:
            return
        from core.editing.geometry import Rect
        from core.ocr.paths import ocr_ready
        from core.ocr.pipeline import OcrOptions
        from ui.ocr_dialogs import OcrProgressDialog, OcrWorker

        ok, detail = ocr_ready()
        if not ok:
            self.report_error(
                "OCR unavailable",
                detail,
                hint="The text-recognition engine is missing from this installation. Run Setup again to restore it.",
            )
            return

        # Runtime user saves under a chosen path; default beside source for interactive use
        default_out = self._document.path.with_name(self._document.path.stem + "-searchable.pdf")
        from ui.convert_dialogs import choose_save

        dest = choose_save(self, "Save searchable OCR PDF", str(default_out), "PDF Files (*.pdf)")
        dest = str(dest) if dest else ""
        if not dest:
            return

        opts = OcrOptions(languages=self._ocr_languages_pref(), make_searchable=True, skip_native_text=True)
        if scope == "page":
            opts.pages = [self._canvas.focus_page]
            opts.skip_native_text = False
        elif scope == "region":
            # Full-page region pass (explicit page selection)
            opts.pages = [self._canvas.focus_page]
            page = self._document.page(self._canvas.focus_page)
            opts.region = Rect(0, 0, page.display_width_pt, page.display_height_pt)
            opts.skip_native_text = False
        elif scope == "needed" and pages is not None:
            opts.pages = list(pages)
        elif scope == "document":
            opts.pages = None  # auto-skip native text pages

        worker = OcrWorker(self._document, opts, Path(dest), self)
        worker.progress.connect(
            lambda c, t, m: self.set_analysis_progress(f"OCR {c}/{t}: {m}")
        )
        dlg = OcrProgressDialog(self)
        dlg.start(worker)
        accepted = dlg.exec() == dlg.DialogCode.Accepted and dlg.ocr_result is not None
        self.clear_analysis_progress()
        if accepted:
            result = dlg.ocr_result
            low = sum(1 for p in result.pages for w in p.words if w.low_confidence)
            self.statusBar().showMessage(
                f"OCR saved to {Path(dest).name} — {low} low-confidence word(s)",
                7000,
            )
            # Make PDF Editable: the recognized words become editable text boxes on the open document
            # (amber = low confidence, to review). Plain OCR commands only write the searchable copy.
            if self._edit is not None and review_overlays:
                from core.editing.text_box import TextBox
                from core.editing.text_style import TextStyle

                self._edit.last_ocr_result = result
                for page in result.pages:
                    for w in page.words:
                        style = TextStyle(
                            font_size=max(8.0, w.rect.h * 0.85),
                            text_color="#b45309" if w.low_confidence else "#1e3a5f",
                            background_color="#fbbf2422" if w.low_confidence else "#00000000",
                            border_color="#b45309" if w.low_confidence else "#00000000",
                            border_width=0.6 if w.low_confidence else 0.0,
                            opacity=0.85,
                        )
                        box = TextBox(
                            page_index=page.page_index,
                            rect=w.rect.inflate(0.5),
                            text=w.text,
                            style=style,
                        )
                        if w.low_confidence:
                            box.overflow = True  # low-confidence review indicator
                        self._edit.add_object(box)
                self._on_edit_changed()

    def _undo(self) -> None:
        # While typing / pasting in a text or field editor, undo the editor first
        if self._canvas.try_editor_undo():
            self._on_edit_changed()
            return
        if self._edit:
            page = self._annotation_page(self._edit.commands._undo)  # noqa: SLF001
            if self._edit.undo() and page is not None:
                self._refresh_page_view(page)  # the comment / highlight disappears at once

    def _redo(self) -> None:
        if self._canvas.try_editor_redo():
            self._on_edit_changed()
            return
        if self._edit:
            page = self._annotation_page(self._edit.commands._redo)  # noqa: SLF001
            if self._edit.redo() and page is not None:
                self._refresh_page_view(page)

    @staticmethod
    def _annotation_page(stack) -> int | None:
        """The page of the comment / highlight step on top of an undo or redo stack (None otherwise):
        those steps change the PDF page itself, whose picture has to be drawn again."""
        from core.editing import annot_commands as ac

        from core.editing.edit_commands import GroupCommand

        cmd = stack[-1] if stack else None
        if isinstance(cmd, GroupCommand) and cmd.commands:  # e.g. one eraser stroke
            cmd = cmd.commands[0]
        kinds = (ac.MarkupAnnotCommand, ac.HighlightStrokeCommand, ac.EraseAnnotCommand,
                 ac.AnnotCreateCommand, ac.AnnotRemoveCommand, ac.AnnotModifyCommand)
        return int(cmd.page_index) if isinstance(cmd, kinds) else None

    def _copy(self) -> None:
        if self._edit:
            self._canvas._canvas._object_clipboard = self._edit.clipboard_copy()  # noqa: SLF001

    def _cut(self) -> None:
        self._copy()
        self._delete()

    def _paste(self) -> None:
        if self._edit is None:
            return
        # In-place editors handle Ctrl+V themselves; do not paste overlay objects over them
        if self._canvas.editor_active():
            return
        payload = self._canvas._canvas._object_clipboard  # noqa: SLF001
        if payload:
            self._edit.clipboard_paste(payload, page_index=self._canvas.focus_page)

    def _duplicate(self) -> None:
        if self._edit:
            self._edit.duplicate_selection()

    def _delete(self) -> None:
        if self._left.thumbs.hasFocus() and self._document is not None:
            self._delete_selected_pages()
            return
        if self._edit:
            annot = self._canvas.selected_annotation()
            if not self._edit.selection and annot is not None:
                page, xref, _kind = annot
                self._canvas._canvas.clear_annotation_selection()  # noqa: SLF001
                self._comment_delete(self._annot_ref(page, xref))
                return
            self._edit.delete_selection()

    def _copy_style(self) -> None:
        if self._edit:
            self._edit.copy_style_selection()

    def _paste_style(self) -> None:
        if self._edit:
            self._edit.paste_style_selection()

    def _layer(self, direction: str) -> None:
        if self._edit:
            self._edit.layer_selection(direction)

    def _on_edit_changed(self) -> None:
        self._update_title()
        self._left.comments.mark_stale()
        if self._edit and self._edit.dirty:
            state, text = "modified", "Modified"
        else:
            state, text = ("saved", "Saved") if self._document else ("", "")
        if self._dirty_label.property("state") != state:
            self._dirty_label.setProperty("state", state)
            self._dirty_label.style().unpolish(self._dirty_label)
            self._dirty_label.style().polish(self._dirty_label)
        self._dirty_label.setText(text)
        can = self._edit is not None
        editor_undo = editor_redo = False
        if self._canvas.editor_active():
            ed = self._canvas._canvas._text_editor or self._canvas._canvas._field_editor  # noqa: SLF001
            if ed is not None:
                editor_undo = ed.document().isUndoAvailable()
                editor_redo = ed.document().isRedoAvailable()
        self.act_undo.setEnabled(can and (self._edit.commands.can_undo_now or editor_undo))
        self.act_redo.setEnabled(can and (self._edit.commands.can_redo_now or editor_redo))
        # Skip / debounce heavy chrome refresh during live drag/type or burst edits
        if getattr(self._canvas._canvas, "_live_interaction", False):  # noqa: SLF001
            return
        self._chrome_timer.start()

    def _flush_chrome_refresh(self) -> None:
        if getattr(self._canvas._canvas, "_live_interaction", False):  # noqa: SLF001
            return
        self._refresh_inspector()
        self._update_context_toolbar()
        self._sync_selection_actions()

    def _sync_selection_actions(self) -> None:
        """Commands that need a particular kind of selection are greyed out without one."""
        has_image = bool(self._edit and any(oid in self._edit.images for oid in self._edit.selection))
        self.act_replace_image.setEnabled(has_image)
        self.act_export_image.setEnabled(has_image)

    def _on_selection_changed(self) -> None:
        if getattr(self._canvas._canvas, "_live_interaction", False):  # noqa: SLF001
            return
        self._chrome_timer.start()

    def _refresh_inspector(self) -> None:
        if self._document is None:
            self._inspector.clear()
            return
        page = None
        try:
            page = self._document.page(self._canvas.focus_page)
        except Exception:  # noqa: BLE001
            pass
        selected = None
        selected_image = None
        selected_field = None
        selected_table = None
        selected_shape = None
        if self._edit:
            objs = self._edit.selected_objects()
            if objs:
                selected = objs[0]
            for oid in self._edit.selection:
                if oid in self._edit.shapes:
                    selected_shape = self._edit.shapes[oid]
                    break
                if oid in self._edit.images:
                    selected_image = self._edit.images[oid]
                    break
                if oid in self._edit.fields:
                    selected_field = self._edit.fields[oid]
                    break
                if oid in self._edit.tables:
                    selected_table = self._edit.tables[oid]
                    break
            if not self._edit.selection and self._edit.field_selection:
                fid = self._edit.field_selection[0]
                selected_field = self._edit.fields.get(fid)
            if not self._edit.selection and self._edit.table_selection:
                tid = self._edit.table_selection[0]
                selected_table = self._edit.tables.get(tid)
        has_sel = any(
            x is not None
            for x in (selected, selected_shape, selected_image, selected_field, selected_table)
        )
        # Auto-show inspector when an object is selected; keep preference otherwise
        if has_sel and not self._inspector.isVisible() and self.act_toggle_right.isChecked():
            self._inspector.setVisible(True)
        self._inspector.show_context(
            self._document,
            page,
            self._edit,
            text_box=selected,
            image=selected_image,
            field=selected_field,
            table=selected_table,
            shape=selected_shape,
        )

    @staticmethod
    def _popup_owned_by(container) -> bool:
        """True while a list or menu that belongs to ``container`` is open (a popup is its own window,
        so walk up from the widget that opened it)."""
        popup = QApplication.activePopupWidget()
        w = popup.parentWidget() if popup is not None else None
        while w is not None:
            if w is container:
                return True
            w = w.parentWidget()
        return False

    def _update_context_toolbar(self) -> None:
        bar = self._context_bar
        # Rebuilding hides every control on the bar, which closed a font list (or color menu) the user
        # had just opened — e.g. the first click on the font box while typing in a text box only
        # flashed the list. Wait until the list or menu is closed.
        if self._popup_owned_by(bar):
            if getattr(self, "_ctx_retry", None) is None:
                self._ctx_retry = QTimer(self)
                self._ctx_retry.setSingleShot(True)
                self._ctx_retry.setInterval(120)
                self._ctx_retry.timeout.connect(self._update_context_toolbar)
            self._ctx_retry.start()
            return
        bar.clear()  # Qt deletes the transient addWidget() actions; font controls are persistent QWidgetActions
        self._context_hint = QLabel("")
        self._context_hint.setObjectName("ContextHint")
        if self._document is None:
            bar.hide()
            return
        bar.show()

        def title(text: str) -> None:
            lab = QLabel(text)
            lab.setObjectName("ContextTitle")
            bar.addWidget(lab)

        def stretch_hint(text: str) -> None:
            self._context_hint.setText(text)
            self._context_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            bar.addWidget(self._context_hint)

        if self._edit is None:
            stretch_hint("Viewing")
            return

        kind = "none"
        if self._edit.selected_objects():
            kind = "text"
        elif any(oid in self._edit.shapes for oid in self._edit.selection):
            kind = "shape"
        elif any(oid in self._edit.images for oid in self._edit.selection):
            kind = "image"
        elif self._edit.field_selection or any(oid in self._edit.fields for oid in self._edit.selection):
            kind = "form"
        elif self._edit.table_selection or any(oid in self._edit.tables for oid in self._edit.selection):
            kind = "table"

        if kind == "text":
            title("Text")
            box = self._selected_text_box()
            if box is not None:
                self._font_family.set_family(box.style.font_family or "Segoe UI")
                self._font_size.blockSignals(True)
                self._font_size.setCurrentText(f"{box.style.font_size:.0f} pt")
                self._font_size.blockSignals(False)
                self.act_text_wrap.setChecked(bool(getattr(box.style, "wrap", True)))
                self.act_font_bold.setChecked(box.style.bold)
                self.act_font_italic.setChecked(box.style.italic)
                self.act_font_underline.setChecked(box.style.underline)
                align = getattr(getattr(box, "align", None), "value", "left")
                self.act_align_text_left.setChecked(align == "left")
                self.act_align_text_center.setChecked(align == "center")
                self.act_align_text_right.setChecked(align == "right")
                self._sync_valign_checks(getattr(getattr(box, "valign", None), "value", "top"))
            self._wire_font_controls()
            self._context_hint.setText("Text")
            bar.addAction(self._font_family_action)
            bar.addAction(self._font_size_action)
            for group in (
                (self.act_font_dec, self.act_font_inc),
                (self.act_font_bold, self.act_font_italic, self.act_font_underline),
                (self.act_align_text_left, self.act_align_text_center, self.act_align_text_right),
                (self.act_valign_top, self.act_valign_middle, self.act_valign_bottom),
                (self.act_text_wrap, self.act_text_color),
                (self.act_case_upper, self.act_case_lower),
                (self.act_copy_style, self.act_paste_style),
                (self.act_bring_forward, self.act_send_backward, self.act_delete),
            ):
                bar.addSeparator()
                for act in group:
                    bar.addAction(act)
            stretch_hint("")
        elif kind == "shape":
            title("Shape")
            self._add_shape_color_buttons(bar)
            bar.addSeparator()
            for act in (self.act_bring_front, self.act_bring_forward, self.act_send_backward, self.act_send_back):
                bar.addAction(act)
            bar.addSeparator()
            bar.addAction(self.act_duplicate)
            bar.addAction(self.act_delete)
            stretch_hint("Line width, style and opacity: Properties panel · hold Shift while drawing to constrain")
        elif kind == "image":
            title("Image")
            for act in (self.act_replace_image, self.act_export_image):
                bar.addAction(act)
            bar.addSeparator()
            for act in (self.act_bring_forward, self.act_send_backward, self.act_duplicate, self.act_delete):
                bar.addAction(act)
            stretch_hint("Drag handles to resize · arrow keys to nudge")
        elif kind == "form":
            title("Form field")
            fid = (self._edit.field_selection or [None])[0] or next(
                (oid for oid in self._edit.selection if oid in self._edit.fields), None
            )
            field = self._edit.fields.get(fid) if fid else None
            designing = self._edit.mode == WorkspaceMode.FORMS
            for act in (self.act_field_prev, self.act_field_next):
                bar.addAction(act)
            if not designing:
                bar.addAction(self.act_field_clear)
                self.act_field_clear.setEnabled(bool(field is not None and not field.readonly))
                if self._is_styleable_field(field):
                    self._wire_font_controls()
                    self._font_family.set_family(str(field.font_family or "Helvetica"))
                    self._font_size.blockSignals(True)
                    fs = float(field.font_size or 0)
                    self._font_size.setCurrentText("Auto" if fs <= 0 else f"{fs:.0f} pt")
                    self._font_size.blockSignals(False)
                    self.act_text_wrap.setChecked(bool(field.multiline))
                    self.act_font_bold.setChecked(bool(getattr(field, "bold", False)))
                    self.act_font_italic.setChecked(bool(getattr(field, "italic", False)))
                    self._sync_align_checks(str(getattr(field, "align", "left") or "left"))
                    from core.forms.fields import effective_valign

                    self._sync_valign_checks(effective_valign(field))
                    caret_style = self._canvas._canvas.field_editor_style()  # noqa: SLF001
                    if caret_style is not None:  # typing: show the look of the words at the caret
                        self._on_field_editor_format(caret_style)
                    bar.addSeparator()
                    bar.addAction(self._font_family_action)
                    bar.addAction(self._font_size_action)
                    bar.addAction(self.act_font_dec)
                    bar.addAction(self.act_font_inc)
                    bar.addSeparator()
                    bar.addAction(self.act_font_bold)
                    bar.addAction(self.act_font_italic)
                    bar.addSeparator()
                    for act in (self.act_align_text_left, self.act_align_text_center, self.act_align_text_right,
                                self.act_align_text_justify):
                        bar.addAction(act)
                    bar.addSeparator()
                    for act in (self.act_valign_top, self.act_valign_middle, self.act_valign_bottom):
                        bar.addAction(act)
                    bar.addSeparator()
                    bar.addAction(self.act_text_wrap)
                    bar.addAction(self.act_text_color)
                    bar.addSeparator()
                    bar.addAction(self.act_case_upper)
                    bar.addAction(self.act_case_lower)
            else:
                bar.addSeparator()
                bar.addAction(self.act_form_select)
                bar.addAction(self.act_delete)
            # The field's name is shown in the Properties panel; the bar holds only the tools.
            stretch_hint("")
        elif kind == "table":
            title("Table")
            for act in (self.act_table_add_row, self.act_table_del_row, self.act_table_add_col, self.act_table_del_col):
                bar.addAction(act)
            stretch_hint("")
        else:
            title("Page")
            for act in (
                self.act_rotate_ccw,
                self.act_rotate_cw,
                self.act_insert_blank,
                self.act_dup_pages,
                self.act_delete_pages,
                self.act_extract_pages,
                self.act_page_sizes,
            ):
                bar.addAction(act)
            stretch_hint("Create / navigate with the main toolbar — select an object to see its formatting tools")
        # Text-labelled buttons for actions that have no icon
        for act in bar.actions():
            btn = bar.widgetForAction(act)
            if isinstance(btn, QToolButton) and act.icon().isNull():
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_main_toolbar()

    def _fit_main_toolbar(self) -> None:
        """Narrow windows: the labelled tool buttons (Select, Text, Highlight, Eraser) show icons only, so
        zoom, page navigation, search and the panel buttons stay on the toolbar instead of moving into
        the overflow menu. Tooltips keep the names."""
        bar = getattr(self, "_main_bar", None)
        buttons = getattr(self, "_labelled_buttons", None)
        if bar is None or not buttons:
            return
        if not self._main_bar_full_width:
            for b in buttons:
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self._main_bar_full_width = bar.sizeHint().width()
        style = (Qt.ToolButtonStyle.ToolButtonTextBesideIcon if self.width() >= self._main_bar_full_width
                 else Qt.ToolButtonStyle.ToolButtonIconOnly)
        for b in buttons:
            if b.toolButtonStyle() != style:
                b.setToolButtonStyle(style)

    def _set_theme(self, key: str) -> None:
        self._prefs.theme = key
        try:
            self._prefs.save()
        except Exception:  # noqa: BLE001
            pass
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, key)
        refresh_registered_icons()
        self._left.refresh_icons()
        self._canvas.refresh_theme()
        self._left.thumbs.viewport().update()
        {"system": self.act_theme_system, "light": self.act_theme_light, "dark": self.act_theme_dark}.get(
            key, self.act_theme_system
        ).setChecked(True)
        self.statusBar().showMessage(f"Theme: {key.title()}", 3000)

    # --- Navigation / search ---------------------------------------------

    def _on_page_changed(self, index: int) -> None:
        self._left.set_current_page(index)
        if self._document is None:
            self._page_label.setText("No document")
            self._page_indicator.setText("")
            self._page_edit.setText("")
            return
        n = self._document.page_count
        self._page_label.setText(f"Page {index + 1} / {n}")
        self._page_indicator.setText(f"/ {n}")
        if not self._page_edit.hasFocus():
            self._page_edit.setText(str(index + 1))
        self.act_prev.setEnabled(index > 0)
        self.act_first.setEnabled(index > 0)
        self.act_next.setEnabled(index < n - 1)
        self.act_last.setEnabled(index < n - 1)
        self._refresh_inspector()

    def _on_zoom_changed(self, zoom: float) -> None:
        pct = f"{zoom * 100:.0f}%"
        self._zoom_label.setText(pct)
        self._status._relayout_for_width()  # noqa: SLF001 — show it (or keep it hidden during a message)
        # Keep toolbar percentage in sync without re-triggering zoom
        self._toolbar_zoom.blockSignals(True)
        self._toolbar_zoom.setCurrentText(pct)
        self._toolbar_zoom.blockSignals(False)

    def _apply_fit_mode(self, mode: ZoomMode) -> None:
        self._canvas.set_zoom_mode(mode)
        key = mode.value
        self._prefs.last_fit_mode = key
        try:
            self._prefs.save()
        except Exception:  # noqa: BLE001
            pass
        if mode == ZoomMode.FIT_WIDTH:
            self._fit_button.setDefaultAction(self.act_fit_width)
        elif mode == ZoomMode.FIT_PAGE:
            self._fit_button.setDefaultAction(self.act_fit_page)
        else:
            self._fit_button.setDefaultAction(self.act_actual)
        self._fit_button.setText("Fit")

    def _on_toolbar_zoom_chosen(self, index: int) -> None:
        data = self._toolbar_zoom.itemData(index)
        if data is None:
            return
        self._canvas.set_manual_zoom(float(data) / 100.0)

    def _on_toolbar_zoom_typed(self) -> None:
        text = (self._toolbar_zoom.currentText() or "").strip().replace("%", "")
        try:
            value = float(text)
        except ValueError:
            self._on_zoom_changed(self._canvas.zoom)
            return
        value = max(10.0, min(800.0, value))
        self._canvas.set_manual_zoom(value / 100.0)

    def _toggle_highlight_fillable(self, checked: bool) -> None:
        self._prefs.highlight_fillable_fields = bool(checked)
        try:
            self._prefs.save()
        except Exception:  # noqa: BLE001
            pass
        if self._edit is not None:
            self._edit.highlight_fillable_fields = bool(checked)
            self._edit._notify()  # noqa: SLF001

    def _selected_text_box(self):
        if not self._edit:
            return None
        objs = self._edit.selected_objects()
        return objs[0] if objs else None

    def _selected_shapes(self) -> list:
        if not self._edit:
            return []
        return [self._edit.shapes[oid] for oid in self._edit.selection if oid in self._edit.shapes]

    def _add_shape_color_buttons(self, bar) -> None:
        """Line colour and fill colour for every selected shape, right on the context toolbar."""
        from PySide6.QtWidgets import QToolButton

        from ui.color_swatches import INK_COLORS, PAPER_COLORS, SwatchMenu, swatch_icon

        shapes = self._selected_shapes()
        if not shapes:
            return
        first = shapes[0]
        closed = any(getattr(s.kind, "value", "") not in ("line", "arrow", "freehand") for s in shapes)

        def apply(**change) -> None:
            # The toolbar (with this button) is rebuilt by the deferred refresh the change triggers,
            # never from inside the button's own menu handler
            self._edit.update_shapes([s.object_id for s in self._selected_shapes()], **change)

        line_btn = QToolButton()
        line_btn.setObjectName("ShapeLineColor")
        line_btn.setText("Line")
        line_btn.setIcon(swatch_icon(first.stroke_color))
        line_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        line_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        line_btn.setToolTip("Line color of the selected shapes")
        line_btn.setMenu(SwatchMenu(INK_COLORS, lambda c: apply(stroke_color=c), title="Line color",
                                    current=lambda: first.stroke_color, parent=line_btn))
        bar.addWidget(line_btn)
        if closed:
            fill_btn = QToolButton()
            fill_btn.setObjectName("ShapeFillColor")
            fill_btn.setText("Fill")
            fill_btn.setIcon(swatch_icon(first.fill_color))
            fill_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            fill_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            fill_btn.setToolTip("Fill color of the selected shapes")
            fill_btn.setMenu(SwatchMenu(PAPER_COLORS + INK_COLORS, lambda c: apply(fill_color=c), title="Fill color",
                                        current=lambda: first.fill_color, allow_none=True, parent=fill_btn))
            bar.addWidget(fill_btn)

    def _selected_text_boxes(self) -> list:
        """Every selected text box (a rectangle drag or Ctrl+click can select several)."""
        return list(self._edit.selected_objects()) if self._edit else []

    def _restyle_boxes(self, **kwargs) -> bool:
        """The same style setting on every selected text box (one undo step). False if none."""
        diagnostics.record(EventId.STYLE_CHANGED)
        boxes = self._selected_text_boxes()
        if not boxes:
            return False
        self._edit.change_style_many([b.object_id for b in boxes], **kwargs)
        return True

    def _wire_font_controls(self) -> None:
        if self._font_controls_wired:
            return
        self._font_family.fontPicked.connect(self._apply_font_family)
        self._font_size.activated.connect(self._apply_font_size_value)
        if self._font_size.lineEdit() is not None:
            self._font_size.lineEdit().editingFinished.connect(self._apply_font_size_value)
        self._font_controls_wired = True

    @staticmethod
    def _is_styleable_field(field) -> bool:
        if field is None or getattr(field, "readonly", False):
            return False
        ftype = str(getattr(getattr(field, "field_type", None), "value", "") or "")
        return ftype in ("text", "multiline", "date", "dropdown")

    def _selected_style_field(self):
        """The (first) selected text-like form field."""
        fields = self._selected_style_fields()
        return fields[0] if fields else None

    def _selected_style_fields(self) -> list:
        """Every selected text-like form field (a rectangle drag or Ctrl+click can select several)."""
        if not self._edit:
            return []
        ids = [*self._edit.field_selection, *(oid for oid in self._edit.selection if oid in self._edit.fields)]
        fields = (self._edit.fields.get(fid) for fid in dict.fromkeys(ids))
        return [f for f in fields if self._is_styleable_field(f)]

    def _restyle_field(
        self,
        field,
        *,
        family: str | None = None,
        size: float | None = None,
        wrap: bool | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        align: str | None = None,
        valign: str | None = None,
        color: str | None = None,
        size_delta: float | None = None,
    ) -> None:
        """Change the look of one field or a list of fields (one undo step).

        ``size_delta`` without ``size`` (A+ / A−): each field grows or shrinks from its own size."""
        from core.editing.edit_commands import field_style_state
        from core.forms.autofit import effective_form_font_size
        from core.forms.rich_text import apply_to_all

        def state(f):
            return (f.font_family, f.font_size, bool(f.multiline), bool(f.bold), bool(f.italic),
                    f.align, getattr(f, "valign", ""), f.text_color, repr(f.runs))

        inner = self._canvas._canvas  # noqa: SLF001
        inner.capture_field_editor()  # words being typed keep their own formats
        # A whole-field change reaches every word: words with their own value follow the field
        # again (font, bold, italic, colour, a chosen size); A+ / A− keep size differences.
        run_change = {k: True for k, v in (("family", family), ("bold", bold), ("italic", italic),
                                            ("color", color)) if v is not None and v != ""}
        if size_delta is not None:
            run_change["size_delta"] = size_delta
        elif size is not None:
            run_change["size"] = True
        targets: dict[str, object] = {}
        # Every place the same field is shown gets the same look (a PDF keeps one style per field)
        for chosen in (field if isinstance(field, (list, tuple)) else [field]):
            for f in [chosen, *self._edit.same_field_widgets(chosen)]:
                targets.setdefault(f.object_id, f)
        if not targets:
            return
        snapshot = {oid: field_style_state(f) for oid, f in targets.items()}
        field = next(iter(targets.values()))
        changed = False
        for f in targets.values():
            before = state(f)
            if family:
                f.font_family = family
            if size is not None:
                f.font_size = size
            elif size_delta is not None:
                current = float(f.font_size or 0)
                if current <= 0:  # Auto: step from the size the text is shown at now
                    current = float(round(effective_form_font_size(f, f.value or "M")))
                f.font_size = max(4.0, min(200.0, current + size_delta))
            if wrap is not None:
                f.multiline = wrap
            if bold is not None:
                f.bold = bold
            if italic is not None:
                f.italic = italic
            if align:
                f.align = align
            if valign:
                f.valign = valign
            if color:
                f.text_color = color
            if run_change and f.runs:
                f.runs = apply_to_all(f.runs, **run_change)
            if state(f) != before:
                f.appearance_dirty = True
                f.style_dirty = True
                changed = True
        if not changed:
            return
        self._edit.push_field_style_change(snapshot, {oid: field_style_state(f) for oid, f in targets.items()})
        try:
            from core.editing.font_cache import remember_font

            remember_font(field.font_family)
        except Exception:  # noqa: BLE001
            pass
        self._edit.dirty = True
        self._edit._notify()  # noqa: SLF001
        inner.reload_field_editor_runs()  # an open editor follows at once

    def _apply_font_family(self, family: str) -> None:
        if not family or not self._edit:
            return
        # Words selected inside the open box: only those words
        if self._canvas._canvas.format_field_selection(family=family):  # noqa: SLF001
            return
        # Otherwise every selected text box and form field
        self._restyle_boxes(font_family=family)
        fields = self._selected_style_fields()
        if fields:
            self._restyle_field(fields, family=family)

    def _apply_font_size_value(self, *_args) -> None:
        if not self._edit:
            return
        text = (self._font_size.currentText() or "").replace("pt", "").strip()
        fields = self._selected_style_fields()
        inner = self._canvas._canvas  # noqa: SLF001
        if text.lower() == "auto":
            if fields and not inner.format_field_selection(size=None):  # selected words follow the field again
                self._restyle_field(fields, size=0.0)
            return  # text boxes have no automatic size
        try:
            size = max(4.0, min(200.0, float(text)))
        except ValueError:
            return
        if inner.format_field_selection(size=size):
            return
        self._restyle_boxes(font_size=size)
        if fields:
            self._restyle_field(fields, size=size)

    def _nudge_font_size(self, delta: float) -> None:
        if not self._edit:
            return
        if self._canvas._canvas.format_field_selection(size_delta=delta):  # noqa: SLF001
            return  # each selected word grows / shrinks from its own size
        # Each selected box grows / shrinks from its own size (one undo step per kind)
        boxes = self._selected_text_boxes()
        if boxes:
            self._edit.change_styles({
                b.object_id: {"font_size": max(4.0, min(200.0, b.style.font_size + delta))} for b in boxes
            })
        fields = self._selected_style_fields()
        if fields:
            self._restyle_field(fields, size_delta=delta)
        first = boxes[0].style.font_size if boxes else (fields[0].font_size if fields else 0)
        if first:
            self._font_size.setCurrentText(f"{first:.0f} pt")

    def _apply_wrap_toggle(self, *_args) -> None:
        if not self._edit:
            return
        on = self.act_text_wrap.isChecked()
        if self._restyle_boxes(wrap=on):
            self.statusBar().showMessage("Text wraps inside the box" if on else "Text stays on one line", 3000)
        fields = self._selected_style_fields()
        if fields:
            self._restyle_field(fields, wrap=on)
            self.statusBar().showMessage("Field text wraps (multi-line)" if on else "Field text on one line", 3000)

    def _change_case(self, mode: str) -> None:
        """UPPERCASE / lowercase the selected text box, or the selected field's entry."""
        if not self._edit:
            return
        convert = str.upper if mode == "upper" else str.lower
        if self._canvas._canvas.field_editor_change_case(convert):  # noqa: SLF001
            return  # only the selected words
        self._commit_field_editor()
        box = self._selected_text_box()
        if box is not None:
            new = convert(box.text or "")
            if new != box.text:
                self._edit.set_text(box.object_id, new)
            return
        field = self._selected_style_field()
        if field is not None and field.value:
            new = convert(field.value)
            if new != field.value:
                self._edit.set_field_value(field.object_id, new)
                self._canvas._canvas.update()  # noqa: SLF001

    def _apply_font_toggle(self, prop: str) -> None:
        if not self._edit:
            return
        action = {"bold": self.act_font_bold, "italic": self.act_font_italic,
                  "underline": self.act_font_underline}.get(prop)
        if action is None:
            return
        on = action.isChecked()
        fields = self._selected_style_fields() if prop in ("bold", "italic") else []
        if fields and self._canvas._canvas.format_field_selection(**{prop: on}):  # noqa: SLF001
            return  # only the selected words
        self._restyle_boxes(**{prop: on})
        if fields:
            self._restyle_field(fields, **{prop: on})

    def _apply_text_align(self, align: str) -> None:
        from core.editing.text_box import TextAlign

        if not self._edit:
            return
        if align != "justify":  # text boxes: left / centre / right
            self._restyle_boxes(align=TextAlign(align))
        fields = self._selected_style_fields()
        if fields:
            if align == "justify" and not all(f.multiline for f in fields):
                self.statusBar().showMessage("Justify shows once the text wraps — turn on Wrap Text", 4000)
            self._restyle_field(fields, align=align)
            self._sync_align_checks(align)

    def _on_field_editor_format(self, style: dict) -> None:
        """While typing in a field, the toolbar shows the look of the text at the caret."""
        if self._selected_style_field() is None:
            return
        self._font_family.blockSignals(True)
        self._font_family.set_family(str(style.get("family") or "Helvetica"))
        self._font_family.blockSignals(False)
        self._font_size.blockSignals(True)
        size = float(style.get("size") or 0)
        self._font_size.setCurrentText("Auto" if size <= 0 else f"{size:g} pt")
        self._font_size.blockSignals(False)
        self.act_font_bold.setChecked(bool(style.get("bold")))
        self.act_font_italic.setChecked(bool(style.get("italic")))

    def _apply_text_valign(self, valign: str) -> None:
        """Top / middle / bottom of the selected text box or form field."""
        from core.editing.text_box import VAlign

        if not self._edit:
            return
        changed = self._restyle_boxes(valign=VAlign(valign))
        fields = self._selected_style_fields()
        if fields:
            self._restyle_field(fields, valign=valign)
        if changed or fields:
            self._sync_valign_checks(valign)

    def _sync_valign_checks(self, valign: str) -> None:
        self.act_valign_top.setChecked(valign == "top")
        self.act_valign_middle.setChecked(valign == "middle")
        self.act_valign_bottom.setChecked(valign == "bottom")

    def _sync_align_checks(self, align: str) -> None:
        self.act_align_text_left.setChecked(align == "left")
        self.act_align_text_center.setChecked(align == "center")
        self.act_align_text_right.setChecked(align == "right")
        self.act_align_text_justify.setChecked(align == "justify")

    def _prev_page(self) -> None:
        if self._document is None:
            return
        self._canvas.go_to_page(max(0, self._canvas.focus_page - 1))

    def _next_page(self) -> None:
        if self._document is None:
            return
        self._canvas.go_to_page(min(self._document.page_count - 1, self._canvas.focus_page + 1))

    def _focus_search(self) -> None:
        if self._document is None:
            return
        self._search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search_edit.selectAll()

    def _run_search(self) -> None:
        self._run_search_query(self._search_edit.text())

    def _run_search_query(self, query: str) -> None:
        if self._document is None:
            return
        query = (query or "").strip()
        self._last_query = query
        self._canvas.clear_highlights()
        self._search_hits = []
        self._search_index = -1
        if not query:
            self._left.set_search_hits([])
            return
        if self._search_edit.text().strip() != query:
            self._search_edit.setText(query)
        hits = self._document.search(query)
        self._search_hits = hits
        labels: list[tuple[int, str]] = []
        seen: set[int] = set()
        for page_i, _rect in hits[:500]:
            if page_i in seen:
                continue
            seen.add(page_i)
            text = (self._document.page_text(page_i) or "").replace("\n", " ")
            pos = text.lower().find(query.lower())
            start = max(0, pos - 30) if pos >= 0 else 0
            snippet = text[start : start + 90].strip()
            if start > 0:
                snippet = "…" + snippet
            if start + 90 < len(text):
                snippet += "…"
            labels.append((page_i, snippet))
        self._left.set_search_hits(labels)
        if not hits:
            self.statusBar().showMessage(f"No matches for “{query}”", 4000)
            return
        self._canvas.set_highlights(hits)
        self._search_index = 0
        self._goto_hit(0)

    def _find_next(self) -> None:
        if not self._search_hits:
            self._run_search()
            return
        self._search_index = (self._search_index + 1) % len(self._search_hits)
        self._goto_hit(self._search_index)

    def _goto_hit(self, hit_index: int) -> None:
        page_index, _ = self._search_hits[hit_index]
        self._canvas.go_to_page(page_index)
        self.statusBar().showMessage(
            f"Match {hit_index + 1} of {len(self._search_hits)} — page {page_index + 1}"
            "   (Enter / F3 next · Shift+Enter / Shift+F3 previous)",
            5000,
        )

    # --- Recent / DnD / chrome -------------------------------------------

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        # Hide files that were moved or deleted; tell same-named files apart by their folder
        paths = [p for p in self._recent.list() if p.is_file()]
        if not paths:
            empty = QAction("No recent files", self)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
        names = [p.name.lower() for p in paths]
        for i, path in enumerate(paths, start=1):
            shown = path.name
            if names.count(path.name.lower()) > 1:
                shown = f"{path.name}  —  {path.parent.name or path.parent}"
            shown = shown.replace("&", "&&")  # a literal & in a file name is not a mnemonic
            label = f"&{i}  {shown}" if i < 10 else f"{i}  {shown}"
            act = QAction(label, self)
            act.setData(str(path))
            act.setToolTip(str(path))
            act.setStatusTip(str(path))
            act.triggered.connect(self._open_recent_action)
            self._recent_menu.addAction(act)
        if hasattr(self, "act_clear_recent"):
            self._recent_menu.addSeparator()
            self._recent_menu.addAction(self.act_clear_recent)
            self.act_clear_recent.setEnabled(bool(paths))

    def _open_recent_action(self) -> None:
        act = self.sender()
        if isinstance(act, QAction) and act.data():
            self.open_path(str(act.data()))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if is_openable(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if is_openable(local):
                event.acceptProposedAction()
                self.open_path(local)
                return
        event.ignore()

    def _update_title(self) -> None:
        if self._document is None:
            self.setWindowTitle(PRODUCT_NAME)
            return
        mark = " *" if (self._edit and self._edit.dirty) else ""
        src = getattr(self, "_converted_from", None)
        name = f"{src.stem}.pdf (from {src.suffix.lstrip('.').upper()} — not saved yet)" if src else self._document.name
        self.setWindowTitle(f"{name}{mark} — {PRODUCT_NAME}")

    def _refresh_welcome_recent(self) -> None:
        self._welcome.set_recent(self._recent.list())

    def _update_workspace_chrome(self) -> None:
        """Show/hide panels for empty vs document workspace."""
        has_doc = self._document is not None
        if not has_doc:
            self._inspector.clear()
            self._inspector.hide()
            self.act_toggle_right.setChecked(False)
            # Empty workspace: no navigation panel (preference is kept for the next document)
            self._left.hide()
            self.act_toggle_left.setEnabled(False)
            self.act_toggle_right.setEnabled(False)
            self._apply_splitter_sizes()
            return
        self.act_toggle_left.setEnabled(True)
        self.act_toggle_right.setEnabled(True)
        # Document open — restore panels from prefs
        self._left.setVisible(not self._prefs.left_panel_collapsed)
        self._inspector.setVisible(not self._prefs.right_panel_collapsed)
        self.act_toggle_left.setChecked(not self._prefs.left_panel_collapsed)
        self.act_toggle_right.setChecked(not self._prefs.right_panel_collapsed)
        self._apply_splitter_sizes()

    def _apply_splitter_sizes(self) -> None:
        if not hasattr(self, "_splitter"):
            return
        left = 0 if not self._left.isVisible() else max(72, self._prefs.left_panel_width)
        right = (
            0 if not self._inspector.isVisible() else max(200, self._prefs.right_panel_width)
        )
        total = max(self.width(), 900)
        mid = max(400, total - left - right)
        self._splitter.setSizes([left, mid, right])

    def _on_splitter_moved(self, *_args) -> None:
        sizes = self._splitter.sizes()
        if len(sizes) >= 3:
            if sizes[0] > 40:
                self._prefs.left_panel_width = sizes[0]
                self._prefs.left_panel_collapsed = False
                self.act_toggle_left.setChecked(True)
            else:
                self._prefs.left_panel_collapsed = True
                self.act_toggle_left.setChecked(False)
            if sizes[2] > 40:
                self._prefs.right_panel_width = sizes[2]
                self._prefs.right_panel_collapsed = False
                self.act_toggle_right.setChecked(True)
            else:
                self._prefs.right_panel_collapsed = True
                self.act_toggle_right.setChecked(False)

    def _toggle_left_panel(self) -> None:
        show = self.act_toggle_left.isChecked()
        self._prefs.left_panel_collapsed = not show
        self._left.setVisible(show)
        self._apply_splitter_sizes()

    def _toggle_right_panel(self) -> None:
        if self._document is None:
            self.act_toggle_right.setChecked(False)
            self._inspector.hide()
            return
        show = self.act_toggle_right.isChecked()
        self._prefs.right_panel_collapsed = not show
        self._inspector.setVisible(show)
        self._apply_splitter_sizes()
        try:
            self._prefs.save()  # remembered for the next start
        except Exception:  # noqa: BLE001
            pass

    def _hide_right_panel(self) -> None:
        self.act_toggle_right.setChecked(False)
        self._toggle_right_panel()
        self.statusBar().showMessage("Properties panel hidden — press F8 or View ▸ Properties Panel to show it", 5000)

    def _set_document_actions_enabled(self, enabled: bool) -> None:
        for act in (
            self.act_save,
            self.act_save_as,
            self.act_save_copy,
            self.act_close,
            self.act_fit_width,
            self.act_fit_page,
            self.act_actual,
            self.act_zoom_in,
            self.act_zoom_out,
            self.act_prev,
            self.act_next,
            self.act_find,
            self.act_find_next,
            self.act_undo,
            self.act_redo,
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_duplicate,
            self.act_delete,
            self.act_select_tool,
            self.act_text_tool,
            self.act_image_tool,
            self.act_copy_style,
            self.act_paste_style,
            self.act_bring_forward,
            self.act_send_backward,
            self.act_bring_front,
            self.act_send_back,
            self.act_mode_edit,
            self.act_mode_forms,
            self.act_mode_layout,
            self.act_mode_tables,
            self.act_form_select,
            self.act_form_text,
            self.act_form_multi,
            self.act_form_check,
            self.act_form_radio,
            self.act_form_drop,
            self.act_form_date,
            self.act_form_sig,
            self.act_form_detect,
            self.act_form_accept,
            self.act_form_reject,
            self.act_flatten,
            self.act_detect_tables,
            self.act_table_add_row,
            self.act_table_del_row,
            self.act_table_add_col,
            self.act_table_del_col,
            self.act_align_left,
            self.act_align_right,
            self.act_align_top,
            self.act_align_bottom,
            self.act_align_ch,
            self.act_align_cv,
            self.act_dist_h,
            self.act_dist_v,
            self.act_policy_preserve,
            self.act_policy_smart,
            self.act_make_editable,
            self.act_ocr_document,
            self.act_ocr_pages,
            self.act_ocr_region,
            self.act_ocr_area,
            self.act_ocr_extract,
            self.act_scan_to_word,
            self.act_insert_blank,
            self.act_insert_pdf,
            self.act_move_pages,
            self.act_delete_pages,
            self.act_dup_pages,
            self.act_replace_page,
            self.act_rotate_cw,
            self.act_rotate_ccw,
            self.act_crop_page,
            self.act_extract_pages,
            self.act_copy_to_doc,
            self.act_move_to_doc,
            self.act_page_sizes,
            self.act_split,
            self.act_pdf_to_images,
            self.act_extract_images,
            self.act_pdf_to_text,
            self.act_searchable,
            self.act_pages_export,
            self.act_flatten_export,
            self.act_meta_copy,
            self.act_pdf_to_docx,
            self.act_tables_xlsx,
            self.act_pdf_to_pptx,
            self.act_optimize,
            self.act_watermark,
            self.act_header_footer,
            self.act_background,
            self.act_remove_page_design,
            self.act_export_image,
            self.act_replace_image,
            self.act_annot_highlight,
            self.act_annot_eraser,
            self.act_annot_underline,
            self.act_annot_strike,
            self.act_annot_squiggly,
            self.act_show_comments,
            self.act_annot_comment,
            self.act_annot_callout,
            self.act_annot_ink,
            self.act_annot_line,
            self.act_annot_arrow,
            self.act_annot_rect,
            self.act_annot_ellipse,
            self.act_annot_stamp,
            self.act_sec_protect,
            self.act_sec_remove,
            self.act_sec_perms,
            self.act_sec_meta,
            self.act_sec_meta_rm,
            self.act_sec_attach,
            self.act_redact_mark,
            self.act_redact_text,
            self.act_redact_pages,
            self.act_redact_preview,
            self.act_redact_apply,
            self.act_sig_typed,
            self.act_sig_drawn,
            self.act_sig_image,
            self.act_print,
            self.act_shape_circle,
        ):
            act.setEnabled(enabled)
        for act in getattr(self, "_doc_actions_extra", ()):
            act.setEnabled(enabled)
        self._page_edit.setEnabled(enabled)
        self.act_merge.setEnabled(True)
        self.act_images_to_pdf.setEnabled(True)
        # Office → PDF works without an open document (uses the installed office suite)
        self.act_office_to_pdf.setEnabled(True)
        self.act_convert_caps.setEnabled(True)
        self.act_highlight_fields.setEnabled(
            enabled and self._edit is not None and bool(self._edit.fields)
        )
        self._toolbar_zoom.setEnabled(enabled)
        if hasattr(self, "_recent_menu"):
            self._sync_submenus()
        self._fit_button.setEnabled(enabled)
        self._search_edit.setEnabled(enabled)

    # --- Pages / organize ------------------------------------------------

    def _selected_pages(self) -> list[int]:
        pages = self._left.selected_page_indices()
        if pages:
            return pages
        if self._document is None:
            return []
        return [self._canvas.focus_page]

    def _warn_signatures_if_needed(self) -> bool:
        if self._document is None:
            return True
        from core.organize.page_ops import warning_for_signatures

        msg = warning_for_signatures(self._document)
        if not msg:
            return True
        resp = QMessageBox.warning(
            self,
            "Signature warning",
            msg + "\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return resp == QMessageBox.StandardButton.Yes

    def _page_undo_begin(self):
        """Snapshot for undo of the page operation about to run (None if the document is too large)."""
        from core.organize import page_snapshot

        try:
            return page_snapshot.capture(self._document, self._edit)
        except Exception:  # noqa: BLE001 — undo is a convenience; the operation itself must still run
            return None

    def _page_undo_end(self, before, name: str) -> None:
        """Record a finished page operation for Undo/Redo. Without a snapshot the operation cannot be
        undone; the Undo list is then cleared so earlier steps cannot act on the wrong pages."""
        diagnostics.record(EventId.PAGES_CHANGED)
        from core.organize import page_snapshot

        after = page_snapshot.capture(self._document, self._edit) if before is not None else None
        if before is None or after is None:
            self._edit.commands.clear()
            self.statusBar().showMessage(f"{name}: this document is too large to undo page changes", 6000)
            self._on_edit_changed()
            return

        def restored() -> None:
            self._refresh_after_page_ops(focus=min(self._canvas.focus_page, self._document.page_count - 1))

        page_snapshot.push(self._edit.commands, page_snapshot.PageStructureCommand(
            name, self._document, self._edit, before, after, restored))
        self._on_edit_changed()

    def _refresh_after_page_ops(self, *, focus: int | None = None, changed_pages=None) -> None:
        """Rebuild the views after a page operation. ``changed_pages`` (e.g. rotation) keeps the cached
        analysis of every other page instead of re-reading the whole document."""
        if self._document is None:
            return
        if changed_pages is None:
            self._document.invalidate_pages()
        else:
            self._document.refresh_pages(changed_pages)
        focus = 0 if focus is None else max(0, min(focus, self._document.page_count - 1))
        self._left.set_document(self._document)
        self._canvas.set_document(self._document)
        if self._edit is not None:
            self._canvas.set_edit_model(self._edit)
            self._edit.mark_dirty()
        self._canvas.go_to_page(focus)
        self._left.set_current_page(focus)
        self._on_edit_changed()
        self._update_title()
        n = self._document.page_count
        self.statusBar().showMessage(f"{n} page" if n == 1 else f"{n} pages", 4000)

    def _on_thumbs_reordered(self, new_order: list) -> None:
        if self._document is None or self._edit is None:
            return
        if not self._warn_signatures_if_needed():
            self._refresh_after_page_ops(focus=self._canvas.focus_page)
            return
        from core.organize.page_ops import reorder_pages
        from core.organize.remap import map_after_reorder

        try:
            before = self._page_undo_begin()
            mapping = map_after_reorder(list(new_order))
            reorder_pages(self._document, list(new_order))
            self._edit.remap_page_indices(mapping)
            self._refresh_after_page_ops(focus=0)
            self._page_undo_end(before, "Reorder Pages")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Reorder failed", str(exc))
            self._refresh_after_page_ops(focus=self._canvas.focus_page)

    def _page_position(self, *, title: str, intro: str, ok_text: str, count_label: str | None = None,
                       page: int | None = None) -> tuple[int, int] | None:
        """Ask where pages go (before/after page N, beginning, end). (insert index, count) or None."""
        from ui.page_position_dialog import PagePositionDialog

        n = self._document.page_count
        ref = self._canvas.focus_page if page is None else page
        dlg = PagePositionDialog(self, title=title, intro=intro, page_count=n, page=ref,
                                 ok_text=ok_text, count_label=count_label)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return None
        return dlg.insert_index(), dlg.count()

    def _reference_page(self) -> int:
        pages = self._left.selected_page_indices()
        return pages[0] if pages else self._canvas.focus_page

    def _insert_blank_page(self, at: int | None = None, count: int = 1, *, ask: bool = False) -> None:
        if self._document is None or self._edit is None:
            return
        if not self._warn_signatures_if_needed():
            return
        from core.organize.page_ops import insert_blank_page
        from core.organize.remap import map_after_insert

        if at is None and ask and not self._is_headless_ui():
            choice = self._page_position(title="Insert Blank Pages", ok_text="Insert",
                                         intro="Where should the blank pages go? They get the size of the page next to them.",
                                         count_label="Number of blank pages:", page=self._reference_page())
            if choice is None:
                return
            at, count = choice
        if at is None:
            at = self._canvas.focus_page + 1
        count = max(1, int(count))
        old_n = self._document.page_count
        at = max(0, min(int(at), old_n))
        mapping = map_after_insert(old_n, at, count)
        try:
            before = self._page_undo_begin()
            for k in range(count):
                insert_blank_page(self._document, at + k)
            self._edit.remap_page_indices(mapping)
            self._refresh_after_page_ops(focus=at)
            self._page_undo_end(before, "Insert Blank Page" if count == 1 else "Insert Blank Pages")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Insert blank", str(exc))

    def _move_selected_pages(self, target: int | None = None, *, ask: bool = False) -> None:
        """Move the selected pages (kept in their order) to insertion index ``target`` (0-based,
        counted in the current document)."""
        if self._document is None or self._edit is None:
            return
        pages = sorted(set(self._selected_pages()))
        n = self._document.page_count
        if not pages or n < 2:
            return
        if target is None:
            if not ask or self._is_headless_ui():
                return
            label = (f"page {pages[0] + 1}" if len(pages) == 1
                     else f"{len(pages)} selected pages")
            choice = self._page_position(title="Move Pages", ok_text="Move",
                                         intro=f"Move {label} to:", page=pages[-1])
            if choice is None:
                return
            target = choice[0]
        from ui.page_position_dialog import move_order

        order = move_order(n, pages, int(target))
        if order == list(range(n)):
            self.statusBar().showMessage("The pages are already there.", 4000)
            return
        self._on_thumbs_reordered(order)
        moved_to = order.index(pages[0])
        self._canvas.go_to_page(moved_to)
        self._left.set_current_page(moved_to)

    def _insert_pdf_pages(self, at: int | None = None, *, ask: bool = False) -> None:
        if self._document is None or self._edit is None:
            return
        if not self._warn_signatures_if_needed():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Insert Pages from PDF", self._doc_dir(), "PDF Files (*.pdf)")
        if not path:
            return
        from core.organize.page_ops import insert_pdf_pages
        from core.organize.remap import map_after_insert

        if at is None and ask and not self._is_headless_ui():
            choice = self._page_position(title="Insert Pages from PDF", ok_text="Insert",
                                         intro=f"Where should the pages of “{Path(path).name}” go?",
                                         page=self._reference_page())
            if choice is None:
                return
            at = choice[0]
        password = None
        if at is None:
            at = self._canvas.focus_page + 1
        at = max(0, min(int(at), self._document.page_count))
        old_n = self._document.page_count
        before = self._page_undo_begin()
        try:
            count = insert_pdf_pages(self._document, Path(path), at_index=at, password=password)
        except PasswordRequiredError:
            dlg = PasswordDialog(self, filename=Path(path).name)
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            try:
                count = insert_pdf_pages(
                    self._document, Path(path), at_index=at, password=dlg.password()
                )
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Insert PDF", str(exc))
                return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Insert PDF", str(exc))
            return
        self._edit.remap_page_indices(map_after_insert(old_n, at, count))
        self._refresh_after_page_ops(focus=at)
        self._page_undo_end(before, "Insert Pages")

    def _delete_selected_pages(self) -> None:
        if self._document is None or self._edit is None:
            return
        pages = self._selected_pages()
        if not pages:
            return
        if self._document.page_count - len(set(pages)) < 1:
            QMessageBox.warning(self, "Delete pages", "Cannot delete all pages.")
            return
        if not self._warn_signatures_if_needed():
            return
        from core.organize.page_ops import delete_pages
        from core.organize.remap import map_after_delete

        old_n = self._document.page_count
        mapping = map_after_delete(old_n, list(pages))
        try:
            before = self._page_undo_begin()
            delete_pages(self._document, pages)
            self._edit.remap_page_indices(mapping)
            self._refresh_after_page_ops(focus=min(pages))
            self._page_undo_end(before, "Delete Pages")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Delete pages", str(exc))

    def _duplicate_selected_pages(self) -> None:
        if self._document is None or self._edit is None:
            return
        pages = self._selected_pages()
        if not pages:
            return
        if not self._warn_signatures_if_needed():
            return
        from core.organize.page_ops import duplicate_pages
        from core.organize.remap import map_after_duplicate_block

        old_n = self._document.page_count
        insert_at = max(pages) + 1
        try:
            before = self._page_undo_begin()
            inserted = duplicate_pages(self._document, pages, after=True)
            self._edit.remap_page_indices(map_after_duplicate_block(old_n, insert_at, len(inserted)))
            self._refresh_after_page_ops(focus=inserted[0] if inserted else 0)
            self._page_undo_end(before, "Duplicate Pages")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Duplicate pages", str(exc))

    def _replace_page(self) -> None:
        if self._document is None or self._edit is None:
            return
        if not self._warn_signatures_if_needed():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Replacement PDF page", self._doc_dir(), "PDF Files (*.pdf)")
        if not path:
            return
        from core.organize.page_ops import replace_page

        idx = self._canvas.focus_page
        before = self._page_undo_begin()
        try:
            replace_page(self._document, idx, Path(path))
        except PasswordRequiredError:
            dlg = PasswordDialog(self, filename=Path(path).name)
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            try:
                replace_page(self._document, idx, Path(path), password=dlg.password())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Replace page", str(exc))
                return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Replace page", str(exc))
            return
        self._edit.mark_dirty()
        self._refresh_after_page_ops(focus=idx)
        self._page_undo_end(before, "Replace Page")

    # --- bookmarks ------------------------------------------------------------------------

    def _bookmark_command(self, new_toc, label: str, select: int | None) -> bool:
        if self._document is None or self._edit is None:
            return False
        from core.organize.bookmarks import SetOutlineCommand

        def changed(select=select) -> None:
            self._left.reload_bookmarks(select=select)
            self._on_edit_changed()
            self._update_title()

        try:
            cmd = SetOutlineCommand(self._edit, new_toc, label=label, on_changed=changed)
            self._edit.commands.execute(cmd)
        except Exception as exc:  # noqa: BLE001
            self.report_error("Bookmarks", str(exc))
            return False
        self._on_edit_changed()
        return True

    def _suggest_bookmark_title(self, page: int) -> str:
        try:
            for line in self._document.page_text(page).splitlines():
                line = " ".join(line.split())
                if 3 <= len(line) <= 80:
                    return line
        except Exception:  # noqa: BLE001
            pass
        return f"Page {page + 1}"

    def _bookmark_add(self, after: int = -1) -> None:
        if self._document is None or self._edit is None:
            return
        if not self._warn_signatures_if_needed():
            return
        from PySide6.QtWidgets import QInputDialog

        from core.organize.bookmarks import read_toc, with_added

        page = self._canvas.focus_page
        title, ok = QInputDialog.getText(
            self, "Add Bookmark", f"Bookmark title (opens page {page + 1}):",
            text=self._suggest_bookmark_title(page),
        )
        if not ok or not title.strip():
            return
        toc = read_toc(self._document)
        new, index = with_added(toc, title, page, after=after if after >= 0 else None)
        if self._bookmark_command(new, "Add bookmark", index):
            self._left.show_bookmarks()
            self.statusBar().showMessage(f"Bookmark added for page {page + 1}", 4000)

    def _bookmark_rename(self, index: int) -> None:
        if self._document is None or index < 0:
            return
        from PySide6.QtWidgets import QInputDialog

        from core.organize.bookmarks import read_toc, with_renamed

        toc = read_toc(self._document)
        if index >= len(toc):
            return
        title, ok = QInputDialog.getText(self, "Rename Bookmark", "Bookmark title:", text=str(toc[index][1]))
        if not ok or not title.strip() or title.strip() == str(toc[index][1]):
            return
        self._bookmark_command(with_renamed(toc, index, title), "Rename bookmark", index)

    def _bookmark_delete(self, index: int) -> None:
        if self._document is None or index < 0:
            return
        from core.organize.bookmarks import read_toc, subtree_end, with_deleted

        toc = read_toc(self._document)
        if index >= len(toc):
            return
        children = subtree_end(toc, index) - index - 1
        if children:
            answer = QMessageBox.question(
                self, "Delete Bookmark",
                f"“{toc[index][1]}” has {children} bookmark{'s' if children != 1 else ''} under it. "
                "Delete them too?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        new = with_deleted(toc, index)
        self._bookmark_command(new, "Delete bookmark", min(index, len(new) - 1) if new else None)

    def _bookmark_move(self, index: int, step: int) -> None:
        if self._document is None or index < 0:
            return
        from core.organize.bookmarks import read_toc, with_moved

        toc = read_toc(self._document)
        if index >= len(toc):
            return
        new, at = with_moved(toc, index, step)
        if at == index:
            self.statusBar().showMessage("The bookmark cannot move further at its level", 4000)
            return
        self._bookmark_command(new, "Move bookmark", at)

    def _bookmark_retarget(self, index: int) -> None:
        if self._document is None or index < 0:
            return
        from core.organize.bookmarks import read_toc, with_target

        toc = read_toc(self._document)
        if index >= len(toc):
            return
        page = self._canvas.focus_page
        if self._bookmark_command(with_target(toc, index, page), "Change bookmark page", index):
            self.statusBar().showMessage(f"“{toc[index][1]}” now opens page {page + 1}", 4000)

    def _rotate_selected(self, degrees: int) -> None:
        if self._document is None or self._edit is None:
            return
        pages = self._selected_pages()
        if not pages or not self._warn_signatures_if_needed():
            return
        self._rotate_pages(pages, degrees)

    def _rotate_pages(self, pages: list[int], degrees: int) -> bool:
        """Undoable page turn; overlays move with the page (see core.organize.rotate_command)."""
        from core.organize.rotate_command import RotatePagesCommand

        focus = pages[0] if pages else 0
        try:
            cmd = RotatePagesCommand(
                self._document,
                self._edit,
                pages,
                degrees,
                on_changed=lambda: self._refresh_after_page_ops(focus=focus, changed_pages=pages),
            )
            self._edit.commands.execute(cmd)
        except Exception as exc:  # noqa: BLE001
            self.report_error("Rotate", str(exc))
            return False
        self._on_edit_changed()  # the command is on the undo stack only now: enable Undo
        return True

    def _crop_page(self) -> None:
        if self._document is None or self._edit is None:
            return
        info = self._document.page(self._canvas.focus_page)
        from core.organize.page_ops import crop_page
        from ui.organize_dialogs import CropDialog

        dlg = CropDialog(info.width_pt, info.height_pt, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        try:
            before = self._page_undo_begin()
            crop_page(self._document, self._canvas.focus_page, dlg.crop_tuple())
            self._edit.mark_dirty()
            self._refresh_after_page_ops(focus=self._canvas.focus_page)
            self._page_undo_end(before, "Crop Page")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Crop", str(exc))

    def _extract_pages(self) -> None:
        if self._document is None:
            return
        pages = self._selected_pages()
        from ui.convert_dialogs import choose_save

        dest = choose_save(self, "Extract Pages", self._suggest("extract", "pdf"), "PDF Files (*.pdf)")
        dest = str(dest) if dest else ""
        if not dest:
            return
        from core.organize.page_ops import extract_pages

        try:
            with self._current_document() as src:
                extract_pages(src, pages, Path(dest))
            self.statusBar().showMessage(f"Extracted {len(pages)} page(s) → {Path(dest).name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Extract", str(exc))

    def _transfer_pages(self, *, move: bool) -> None:
        if self._document is None or self._edit is None:
            return
        pages = self._selected_pages()
        if not pages:
            return
        if move and not self._warn_signatures_if_needed():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Target PDF (will be saved as a new file)", self._doc_dir(), "PDF Files (*.pdf)"
        )
        if not path:
            return
        from ui.convert_dialogs import choose_save

        dest_out = choose_save(
            self,
            "Save target PDF as",
            str(Path(path).with_name(Path(path).stem + ("-moved.pdf" if move else "-copied.pdf"))),
            "PDF Files (*.pdf)",
        )
        dest_out = str(dest_out) if dest_out else ""
        if not dest_out:
            return
        from core.organize.page_ops import copy_pages_between, delete_pages
        from core.organize.remap import map_after_delete

        password = None
        try:
            other = open_document(path, password=password)
        except PasswordRequiredError:
            dlg = PasswordDialog(self, filename=Path(path).name)
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            try:
                other = open_document(path, password=dlg.password())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Open target", str(exc))
                return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Open target", str(exc))
            return
        try:
            with self._current_document() as src:
                copy_pages_between(src, other, pages, at_index=other.page_count)
            other.save_as(Path(dest_out))
            if move:
                old_n = self._document.page_count
                mapping = map_after_delete(old_n, list(pages))
                delete_pages(self._document, pages)
                self._edit.remap_page_indices(mapping)
                self._refresh_after_page_ops(focus=0)
            self.statusBar().showMessage(
                f"{'Moved' if move else 'Copied'} {len(pages)} page(s) → {Path(dest_out).name}",
                6000,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Transfer pages", str(exc))
        finally:
            other.close()

    def _change_page_size_dialog(self) -> None:
        self._commit_field_editor()
        if self._document is None:
            return
        import tempfile

        from core.organize.resize import FitMode, Orientation, resize_pdf
        from ui.convert_dialogs import choose_save
        from ui.organize_dialogs import ChangePageSizeDialog
        from ui.task_runner import run_with_progress

        sizes = []
        for i in range(self._document.page_count):
            info = self._document.page(i)
            sizes.append((info.display_width_pt, info.display_height_pt))
        dlg = ChangePageSizeDialog(
            self._document.page_count,
            self._canvas.focus_page,
            self._left.selected_page_indices(),
            sizes,
            self,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        dest = choose_save(self, "Save Resized PDF", self._suggest(dlg.paper_name(), "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        if self._document.path and Path(dest).resolve() == Path(self._document.path).resolve():
            self.report_error("Change Page Size", "Choose a new file name — the open PDF cannot be replaced here.")
            return
        paper, pages = dlg.paper_size(), dlg.pages()
        mode, orient = FitMode(dlg.fit.currentData()), Orientation(dlg.orientation.currentData())
        margin_pt = float(dlg.margin.value()) * 72.0 / 25.4
        work = Path(tempfile.mkdtemp(prefix="monographpdf-resize-")) / "current.pdf"

        from engines.bake_edits import bake_via_backend

        try:
            # Start from the document as it looks now, including unsaved edits
            bake_via_backend(self._edit, work)
            result = run_with_progress(
                self,
                "Change Page Size",
                "Resizing pages…",
                lambda: resize_pdf(work, Path(dest), paper, mode=mode, orientation=orient, margin_pt=margin_pt, pages=pages),
            )
        except Exception as exc:  # noqa: BLE001
            self.report_error("Change Page Size", str(exc))
            return
        finally:
            import shutil

            shutil.rmtree(work.parent, ignore_errors=True)  # the work folder, not only the file
        self.statusBar().showMessage(f"Resized {result.pages_changed} page(s) → {Path(dest).name}", 7000)
        resp = QMessageBox.question(
            self,
            "Change Page Size",
            f"Saved {Path(dest).name}.\n\nOpen it now?",
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close,
            QMessageBox.StandardButton.Open,
        )
        if resp == QMessageBox.StandardButton.Open and self._confirm_unsaved("opening another file"):
            self.open_path(dest)

    def _merge_combine(self) -> None:
        from ui.organize_dialogs import MergeDialog

        dlg = MergeDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.output_path:
            self.statusBar().showMessage(f"Combined PDF saved: {dlg.output_path.name}", 7000)
            resp = QMessageBox.question(
                self,
                "Open combined PDF?",
                f"Open {dlg.output_path.name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp == QMessageBox.StandardButton.Yes:
                self.open_path(dlg.output_path)

    def _split_document(self) -> None:
        if self._document is None:
            return
        from ui.organize_dialogs import SplitDialog

        with self._current_document() as src:
            dlg = SplitDialog(src, self)
            accepted = dlg.exec() == dlg.DialogCode.Accepted
        if accepted:
            n = len(dlg.output_paths)
            self.statusBar().showMessage(f"Split into {n} file(s)", 7000)

    # --- Convert / Export / Images ---------------------------------------

    def _show_convert_capabilities(self) -> None:
        from ui.convert_dialogs import CapabilitiesDialog

        CapabilitiesDialog(self).exec()

    def _batch_convert(self) -> None:
        from ui.batch_dialog import BatchConvertDialog

        # Works on files as saved on disk; the open document's unsaved changes are not part of a batch
        dlg = BatchConvertDialog(self, start_dir=self._doc_dir(), ocr_languages=self._ocr_languages_pref())
        dlg.exec()

    def _images_to_pdf(self) -> None:
        from core.convert.images_to_pdf import images_to_pdf
        from ui.convert_dialogs import choose_save

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Images to PDF", self._doc_dir(), "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)"
        )
        if not paths:
            return
        first = Path(paths[0])
        name = f"{first.stem}.pdf" if len(paths) == 1 else "images.pdf"
        dest = choose_save(self, "Save PDF", str(first.with_name(name)), "PDF (*.pdf)")
        if not dest:
            return
        try:
            images_to_pdf([Path(p) for p in paths], dest)
            self.statusBar().showMessage(f"Wrote {dest.name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Images → PDF", str(exc))

    def _pdf_to_images(self) -> None:
        if self._document is None:
            return
        if not self._confirm_unsaved_for_export("PDF to Images"):
            return
        from core.convert.pdf_to_images import pdf_pages_to_images
        from ui.app_dialogs import ExportImagesDialog

        selected = self._left.selected_page_indices()
        dlg = ExportImagesDialog(self._document.page_count, len(selected), self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        opts = dlg.options()
        out = QFileDialog.getExistingDirectory(self, "Export images to folder", self._doc_dir())
        if not out:
            return
        if opts.scope == "current":
            pages = [self._canvas.focus_page]
        elif opts.scope == "selected" and selected:
            pages = selected
        else:
            pages = None
        try:
            with self._current_document() as src:
                written = pdf_pages_to_images(
                    src,
                    Path(out),
                    pages=pages,
                    fmt=opts.fmt,
                    dpi=opts.dpi,
                    jpeg_quality=opts.jpeg_quality,
                    name_prefix=self._document.path.stem,
                )
            self.statusBar().showMessage(f"Exported {len(written)} image(s) to {Path(out).name}", 6000)
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected("Export images failed", exc, EventId.PDF_EXPORT_FAILED)

    def _extract_images(self) -> None:
        if self._document is None:
            return
        from core.convert.extract_images import extract_embedded_images
        from ui.convert_dialogs import choose_dir

        out = choose_dir(self, "Extract images to folder")
        if not out:
            return
        try:
            with self._current_document() as src:
                written = extract_embedded_images(src, out)
            self.statusBar().showMessage(f"Extracted {len(written)} embedded image(s)", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Extract images", str(exc))

    def _pdf_to_text(self) -> None:
        if self._document is None:
            return
        if not self._confirm_unsaved_for_export("PDF to Text"):
            return
        from core.convert.pdf_to_text import pdf_to_plain_text
        from ui.convert_dialogs import choose_save

        dest = choose_save(self, "Save as Plain Text", self._suggest("", "txt"), "Text (*.txt)")
        if not dest:
            return
        try:
            with self._current_document() as src:
                pdf_to_plain_text(src, dest, pages=self._selected_pages())
            self.statusBar().showMessage(f"Wrote {dest.name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PDF → Text", str(exc))

    def _scanned_to_searchable(self) -> None:
        if self._document is None:
            return
        self._run_ocr(scope="needed")

    def _export_selected_pages_pdf(self) -> None:
        if self._document is None:
            return
        from core.convert.pages_to_pdf import pages_to_pdf
        from ui.convert_dialogs import choose_save

        dest = choose_save(self, "Export Selected Pages", self._suggest("pages", "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        try:
            with self._current_document() as src:
                pages_to_pdf(src, self._selected_pages(), dest)
            self.statusBar().showMessage(f"Wrote {dest.name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Pages → PDF", str(exc))

    def _export_flattened(self) -> None:
        if self._document is None:
            return
        from core.convert.flatten_export import export_flattened_pdf
        from ui.convert_dialogs import choose_save

        dest = choose_save(self, "Export Flattened PDF", self._suggest("flattened", "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        try:
            with self._current_document() as src:
                export_flattened_pdf(src, dest)
            self.statusBar().showMessage(f"Wrote {dest.name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Flatten", str(exc))

    def _metadata_copy(self) -> None:
        if self._document is None:
            return
        from core.convert.copy_pdf import copy_pdf_preserving_metadata
        from ui.convert_dialogs import choose_save

        dest = choose_save(self, "Metadata-Preserving Copy", self._suggest("copy", "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        try:
            with self._current_document() as src:
                copy_pdf_preserving_metadata(src, dest)
            self.statusBar().showMessage(f"Wrote {dest.name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Copy", str(exc))

    def _pdf_to_docx(self) -> None:
        if self._document is None:
            return
        if not self._confirm_unsaved_for_export("PDF to Word"):
            return
        from core.convert.pdf_to_docx import pdf_to_docx
        from ui.convert_dialogs import PdfToWordDialog, choose_save
        from ui.task_runner import run_with_progress

        dlg = PdfToWordDialog(self, page_count=self._document.page_count, current_page=self._canvas.focus_page)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        try:
            opts = dlg.values()
        except Exception as exc:  # noqa: BLE001
            self.report_error("PDF to Word", f"Invalid page range: {exc}")
            return
        dest = choose_save(self, "Save as Word Document", self._suggest("", "docx"), "Word Document (*.docx)")
        if not dest:
            return
        self._commit_field_editor()
        try:
            with self._current_document() as src:
                run_with_progress(
                    self,
                    "PDF to Word",
                    f"Converting “{self._document.name}” to Word…",
                    lambda: pdf_to_docx(src, dest, pages=opts["pages"], engine=opts["engine"]),
                )
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected("PDF to Word failed", exc, EventId.CONVERT_FAILED,
                                   hint="Try the “Text only” option, or OCR scanned pages first.")
            return
        self.statusBar().showMessage(f"Saved {dest.name}", 6000)
        if opts["open_after"] and not self._is_headless_ui():
            self._open_external(dest)

    def _tables_to_xlsx(self) -> None:
        if self._document is None:
            return
        if not self._confirm_unsaved_for_export("PDF to Excel"):
            return
        from core.convert.tables_to_xlsx import FIDELITY_NOTICE, tables_to_xlsx
        from ui.convert_dialogs import choose_save, fidelity_confirm

        if not fidelity_confirm(self, "PDF Tables to Excel", FIDELITY_NOTICE):
            return
        dest = choose_save(self, "Save Tables as Excel", self._suggest("tables", "xlsx"), "Excel (*.xlsx)")
        if not dest:
            return
        try:
            with self._current_document() as src:
                tables_to_xlsx(src, dest)
            self.statusBar().showMessage(f"Saved {dest.name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PDF Tables to Excel", str(exc))

    def _pdf_to_pptx(self) -> None:
        if self._document is None:
            return
        from core.convert.pdf_to_pptx import (
            PptxReport,
            page_groups,
            pdf_to_pptx,
            pdf_to_pptx_split,
        )
        from ui.convert_dialogs import PdfToPowerPointDialog, choose_save

        if not self._confirm_unsaved_for_export("PDF to PowerPoint"):
            return
        dlg = PdfToPowerPointDialog(self, page_groups=page_groups(self._document))
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        dest = choose_save(self, "Save as PowerPoint", self._suggest("", "pptx"), "PowerPoint (*.pptx)")
        if not dest:
            return
        opts = dlg.options()
        try:
            report = PptxReport()
            with self._current_document() as src:
                if dlg.policy() == "split":
                    outs = pdf_to_pptx_split(src, dest, **opts)
                    self.statusBar().showMessage(
                        f"Saved {len(outs)} presentations: " + ", ".join(o.name for o in outs), 10000)
                    return
                pdf_to_pptx(src, dest, report=report, **opts)
            self.statusBar().showMessage(f"Saved {dest.name} — {report.summary()}", 8000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PDF to PowerPoint", str(exc))

    def _office_to_pdf(self) -> None:
        from core.convert.office_bridge import OFFICE_EXTS, office_availability, unavailable_message
        from core.convert.office_to_pdf import office_to_pdf
        from ui.convert_dialogs import choose_save
        from ui.task_runner import run_with_progress

        avail = office_availability()
        if not avail.any:
            QMessageBox.information(self, "Word, Excel or PowerPoint to PDF", unavailable_message())
            return
        patterns = " ".join(f"*{e}" for e in OFFICE_EXTS)
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a Word, Excel or PowerPoint File",
            self._doc_dir(),
            f"Office documents ({patterns});;Word (*.doc *.docx *.rtf *.odt);;Excel (*.xls *.xlsx *.ods *.csv);;"
            "PowerPoint (*.ppt *.pptx *.odp);;All files (*.*)",
        )
        if not src:
            return
        source = Path(src)
        dest = choose_save(self, "Save PDF As", str(source.with_suffix(".pdf")), "PDF (*.pdf)")
        if not dest:
            return
        try:
            run_with_progress(
                self,
                "Convert to PDF",
                f"Converting “{source.name}” to PDF with {avail.describe()}…",
                lambda: office_to_pdf(source, dest),
            )
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected("Conversion to PDF failed", exc, EventId.CONVERT_FAILED)
            return
        self.statusBar().showMessage(f"Saved {dest.name}", 6000)
        if self._is_headless_ui():
            return
        resp = QMessageBox.question(
            self, "Conversion complete", f"Open {dest.name} now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp == QMessageBox.StandardButton.Yes:
            self.open_path(dest)

    def _optimize_pdf(self) -> None:
        """Compress PDF: the document as shown (unsaved changes included, after the Save / Save As /
        Cancel decision) is compressed in memory, measured, previewed, and written atomically to the
        chosen file. The open file is replaced only when the user picks it and confirms."""
        if self._document is None:
            return
        if not self._confirm_unsaved_for_export("Compress PDF"):
            return
        from core.convert import compress as cz
        from ui.compress_dialog import CompressDialog

        try:
            with self._current_document() as src:
                data = cz._source_bytes(src)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected("Compress PDF failed", exc, EventId.CONVERT_FAILED)
            return
        password = self._open_password()
        dlg = CompressDialog(data, password=password, doc_name=self._document.name, parent=self)
        if dlg.exec() != dlg.DialogCode.Accepted or dlg.result_ is None:
            return
        result = dlg.result_
        path, _ = QFileDialog.getSaveFileName(self, "Save Compressed PDF", self._suggest("compressed", "pdf"),
                                              "PDF Files (*.pdf)")
        if not path:
            return
        self.write_compressed(result, Path(path), password=password)

    def write_compressed(self, result, dest: Path, *, password: str | None = None, confirm_replace=None) -> Path | None:
        """Write a compression result. Replacing the open document needs an explicit confirmation; the
        file is validated before it replaces anything, and the original stays intact on any failure."""
        import os

        from core.convert import compress as cz

        dest = Path(dest)
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_name(dest.name + ".pdf")
        try:
            same = dest.exists() and os.path.samefile(dest, self._document.path)
        except OSError:
            same = False
        try:
            if not same:
                cz.write_result(result, dest, password=password)
            else:
                ok = confirm_replace() if confirm_replace else (
                    self._is_headless_ui() or QMessageBox.question(
                        self, "Replace the original?",
                        f"Replace “{dest.name}” — the open document — with the compressed version? "
                        "The original cannot be recovered afterwards.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes)
                if not ok:
                    return None
                cz.validate_pdf(result.data, pages=result.profile.pages, password=password)
                page = self._canvas.focus_page
                self._document.close()  # Windows cannot replace an open file
                try:
                    cz.write_result(result, dest, password=password)
                finally:
                    self._load_document(open_document(dest, password=password))
                    self._canvas.go_to_page(min(page, self._document.page_count - 1))
                    self._update_title()
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected("Compress PDF failed", exc, EventId.CONVERT_FAILED,
                                   hint="Choose a writable folder with enough free space; the original is unchanged.")
            return None
        self.statusBar().showMessage(f"Saved {dest.name}: {cz.format_size(result.output_bytes, exact=True)} — "
                                     f"{result.status()}", 10000)
        return dest

    def _watermark(self) -> None:
        from ui.page_marks_dialogs import WatermarkDialog

        self._page_design(WatermarkDialog, "Watermark", "watermarked", "Save Watermarked PDF")

    def _header_footer(self) -> None:
        from ui.page_marks_dialogs import HeaderFooterDialog

        self._page_design(HeaderFooterDialog, "Header / Footer", "numbered", "Save PDF with Header / Footer")

    def _background(self) -> None:
        from ui.page_marks_dialogs import BackgroundDialog

        self._page_design(BackgroundDialog, "Background", "background", "Save PDF with Background")

    def _page_design(self, dialog_cls, title: str, suffix: str, save_title: str) -> None:
        """Header/footer, watermark or background: dialog with a live preview, then a new PDF.

        The preview and the output both use the document as shown, unsaved changes included."""
        if self._document is None:
            return
        from core.convert.page_marks import apply_page_marks
        from ui.convert_dialogs import choose_save

        with self._current_document() as src:
            dlg = dialog_cls(self, page_count=self._document.page_count, current_page=self._canvas.focus_page,
                             source=src)
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            try:
                pages = dlg.scope.pages()
            except Exception as exc:  # noqa: BLE001
                self.report_error(title, f"Invalid page range: {exc}")
                return
            dest = choose_save(self, save_title, self._suggest(suffix, "pdf"), "PDF (*.pdf)")
            if not dest:
                return
            try:
                result = apply_page_marks(src, dest, pages=pages, replace_existing=dlg.replace.isChecked(),
                                          **dlg.kwargs())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, title, str(exc))
                return
        note = f"Wrote {dest.name}"
        if result.removed.get("replaced"):
            note += f" — replaced the earlier one on {result.removed['replaced']} page(s)"
        if result.font_size_reduced_on:
            note += f" — text made smaller to fit on {len(result.font_size_reduced_on)} page(s)"
        self.statusBar().showMessage(note, 8000)

    def _remove_page_design(self) -> None:
        if self._document is None:
            return
        from core.convert.page_marks import remove_page_marks
        from ui.convert_dialogs import choose_save
        from ui.page_marks_dialogs import RemoveMarksDialog

        with self._current_document() as src:
            dlg = RemoveMarksDialog(self, source=src)
            if not any(dlg.counts.values()):
                QMessageBox.information(
                    self, "Remove Page Design",
                    "No header, footer, watermark or background added by Monograph PDF was found in this document.\n\n"
                    "Text or pictures added by other programs are part of the page and cannot be removed here.")
                return
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            dest = choose_save(self, "Save PDF without Page Design", self._suggest("plain", "pdf"), "PDF (*.pdf)")
            if not dest:
                return
            try:
                result = remove_page_marks(src, dest, dlg.kinds())
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Remove Page Design", str(exc))
                return
        removed = sum(result.removed.values())
        note = f"Wrote {dest.name} — removed {removed} item(s)"
        if result.retained_objects:
            note += f"; {result.retained_objects} no longer shown but still stored (shared with other pages)"
        self.statusBar().showMessage(note, 8000)

    def _add_image(self) -> None:
        if self._document is None or self._edit is None:
            return
        from core.editing.image_box import ImageBox

        path, _ = QFileDialog.getOpenFileName(
            self, "Add image", self._doc_dir(), "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)"
        )
        if not path:
            return
        page = self._canvas.focus_page
        info = self._document.page(page)
        from PySide6.QtGui import QImageReader

        from core.editing.image_box import default_image_rect

        size = QImageReader(path).size()  # header only: the picture is not decoded here
        box = ImageBox(
            page_index=page,
            rect=default_image_rect(size.width(), size.height(), info.display_width_pt, info.display_height_pt),
            source_path=path,
            z_index=self._edit.next_z(),
        )
        self._edit.add_image(box)
        self._edit.selection = [box.object_id]
        self._set_tool(EditTool.SELECT)
        self._on_edit_changed()

    def _export_selected_image(self) -> None:
        if self._edit is None:
            return
        from core.editing.image_box import export_image_box
        from ui.convert_dialogs import choose_save

        for oid in self._edit.selection:
            img = self._edit.images.get(oid)
            if img is None:
                continue
            dest = choose_save(self, "Export Image", self._suggest("image", "png"), "PNG (*.png);;JPEG (*.jpg)")
            if not dest:
                return
            try:
                export_image_box(img, dest)
                self.statusBar().showMessage(f"Exported {dest.name}", 5000)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Export image", str(exc))
            return
        QMessageBox.information(self, "Export image", "Select an image object first.")

    def _replace_selected_image(self) -> None:
        if self._edit is None:
            return
        for oid in self._edit.selection:
            if oid not in self._edit.images:
                continue
            path, _ = QFileDialog.getOpenFileName(
                self, "Replace image", self._doc_dir(), "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)"
            )
            if not path:
                return
            self._edit.replace_image_source(oid, path)
            self._on_edit_changed()
            return
        QMessageBox.information(self, "Replace image", "Select an image object first.")

    def _confirm_signed(self) -> bool:
        if self._document is None:
            return False
        from core.security.ops import warn_signed_document
        from ui.security_dialogs import confirm_signed_edit

        return confirm_signed_edit(self, warn_signed_document(self._document))

    def _page_center_rect(self, w: float = 160, h: float = 40):
        from core.editing.geometry import Rect

        page = self._document.page(self._canvas.focus_page)
        return Rect(
            max(36, (page.width_pt - w) / 2),
            max(36, (page.height_pt - h) / 2),
            w,
            h,
        )

    def _toggle_highlight_tool(self) -> None:
        """Toolbar / H: first click activates continuous Highlight; second click returns to Select."""
        if getattr(self, "_markup_sticky", None) == "highlight":
            if self._canvas.region_stroke_in_progress:
                self._canvas.abort_active_region_stroke()
            self._exit_markup_modes(message="Select mode")
            return
        self._eraser_active = False
        self._annot_markup("highlight")

    def _exit_markup_modes(self, *, message: str = "Select mode") -> None:
        self._markup_sticky = None
        self._eraser_active = False
        if self._canvas.region_pick_active:
            self._canvas.cancel_region_pick(announce=False)
        self.act_select_tool.setChecked(True)
        self.statusBar().showMessage(message, 3000)

    def _toggle_eraser_tool(self) -> None:
        """Toolbar eraser: toggle continuous removal of highlight / ink markup annotations."""
        if getattr(self, "_eraser_active", False):
            self._exit_markup_modes(message="Select mode")
            return
        if self._document is None or not self._confirm_signed():
            self.act_select_tool.setChecked(True)
            return
        self._markup_sticky = None
        if self._canvas.region_pick_active:
            self._canvas.cancel_region_pick(announce=False)
        self._eraser_active = True
        self.act_annot_eraser.setChecked(True)
        self._arm_eraser()

    def _arm_eraser(self) -> None:
        if self._document is None or not getattr(self, "_eraser_active", False):
            return
        from PySide6.QtGui import QColor

        from core.annotations import annotations_along
        from core.editing.annot_commands import EraseAnnotCommand
        from core.editing.edit_commands import GroupCommand

        def apply(page: int, rect) -> None:
            if self._edit is None or self._document is None:
                return
            # Everything the eraser was drawn over goes in one pass (a click: everything under it).
            # It used to take only the topmost mark under the press, so overlapping strokes needed
            # several passes.
            stroke = self._canvas.take_region_stroke() or []
            display = [(p.x, p.y) for p in stroke] or [(rect.x, rect.y)]
            pts = [self._to_page_point(page, x, y) for x, y in display]
            hits = annotations_along(self._document, page, pts, radius_pt=5.0)
            if not hits:
                self.statusBar().showMessage("Eraser: nothing to erase there — draw over a highlight, underline, "
                                             "strikethrough or ink mark", 4000)
                return
            done: list = []
            try:
                for hit in reversed(hits):  # topmost first
                    cmd = EraseAnnotCommand(self._document, self._edit, page, int(hit["xref"]))
                    cmd.execute()
                    done.append(cmd)
            except ValueError:
                for cmd in reversed(done):
                    cmd.undo()
                self.statusBar().showMessage("Eraser: those marks could not be removed", 4000)
                self._refresh_page_view(page)
                return
            group = done[0] if len(done) == 1 else GroupCommand("Erase", done)
            self._edit.commands.push_executed(group)
            n = len(done)
            self._after_annotation(page, f"Erased {n} mark{'s' if n != 1 else ''} — keep erasing, or Esc to finish")

        self._pick_on_page(
            "Eraser: draw over highlights, underlines, strikethroughs or ink to remove them (Esc to finish)",
            apply,
            kind="erase_stroke",
            default_size=(1.0, 1.0),
            stroke_color=QColor(100, 116, 139),
        )

    def _annot_markup(self, kind: str, *, rearm: bool = False) -> None:
        if self._document is None or not self._confirm_signed():
            self._markup_sticky = None
            self._eraser_active = False
            self.act_select_tool.setChecked(True)
            return
        from core.annotations import classify_stroke
        from core.editing.annot_commands import HighlightStrokeCommand, MarkupAnnotCommand

        label = {"highlight": "Highlight", "underline": "Underline", "strikeout": "Strikethrough",
                 "squiggly": "Squiggly underline"}[kind]
        color = self._markup_color_rgb(kind)
        pick_kind = "stroke" if kind == "highlight" else "rect"
        # Highlight stays active until toggled off, Esc (twice if mid-stroke), another tool, or close.
        self._eraser_active = False
        self._markup_sticky = "highlight" if kind == "highlight" else None
        prompt = (
            "Highlight mode: draw over text or any area; click Highlight or Esc to finish"
            if kind == "highlight"
            else f"{label}: drag across the text"
        )

        def apply(page: int, rect) -> None:
            if self._edit is None:
                return
            if kind == "highlight":
                stroke = self._canvas.take_region_stroke()
                locked = self._canvas.take_stroke_locked_color()
                stroke_color = (
                    (locked.redF(), locked.greenF(), locked.blueF())
                    if locked is not None and locked.isValid()
                    else self._markup_color_rgb("highlight")
                )
                if len(stroke) < 2:
                    self.statusBar().showMessage("Highlight: drag to mark an area (a single click marks nothing)", 4000)
                    return
                page_pts = [self._to_page_point(page, p.x, p.y) for p in stroke]
                lines, runs = classify_stroke(self._document, page, page_pts)
                if not lines and not runs:
                    self.statusBar().showMessage("Highlight: the stroke was too short to mark anything", 4000)
                    return
                self._edit.commands.execute(
                    HighlightStrokeCommand(
                        self._document, self._edit, page, lines, runs, color=stroke_color
                    )
                )
                parts = []
                if lines:
                    parts.append(f"{len(lines)} text line(s)")
                if runs:
                    parts.append(f"{len(runs)} free-area stroke(s)")
                self._after_annotation(
                    page, "Highlight added (" + ", ".join(parts) + ") — keep drawing, or Esc to finish"
                )
                return
            area = self._to_page_rect(page, rect)
            lines = self._text_line_rects(page, area)
            if not lines:
                self.statusBar().showMessage(f"{label}: no text under the selected area", 5000)
                return
            self._edit.commands.execute(
                MarkupAnnotCommand(self._document, self._edit, page, kind, lines, color=color)
            )
            self._after_annotation(page, f"{label} added ({len(lines)} line(s))")

        from PySide6.QtGui import QColor

        ink = QColor(*(int(round(c * 255)) for c in color))
        self._pick_on_page(prompt, apply, kind=pick_kind, default_size=(200.0, 18.0), stroke_color=ink)

    def _on_region_pick_cancelled(self) -> None:
        """Esc with no unfinished stroke (or after mid-stroke cancel already happened): return to Select."""
        self._markup_sticky = None
        self._eraser_active = False
        self.act_select_tool.setChecked(True)

    def _markup_color_rgb(self, kind: str) -> tuple[float, float, float]:
        """Current markup color as MuPDF RGB floats (0–1)."""
        from PySide6.QtGui import QColor

        hex_map = {
            "highlight": getattr(self._prefs, "highlight_color", None) or "#ffff00",
            "underline": getattr(self._prefs, "underline_color", None) or "#0000ff",
            "strikeout": getattr(self._prefs, "strikeout_color", None) or "#ff0000",
            "squiggly": getattr(self._prefs, "squiggly_color", None) or "#dc2626",
        }
        c = QColor(hex_map.get(kind, "#ffff00"))
        if not c.isValid():
            c = QColor("#ffff00")
        return (c.redF(), c.greenF(), c.blueF())

    def _set_highlight_color(self, hex_color: str) -> None:
        from PySide6.QtGui import QColor

        c = QColor(hex_color)
        if not c.isValid():
            return
        self._prefs.highlight_color = c.name()
        self._prefs.save()
        self._refresh_highlight_color_button()
        # Colour changes apply to future strokes only; never activate/deactivate Highlight or cancel a stroke.
        if getattr(self, "_markup_sticky", None) == "highlight":
            if self._canvas.region_stroke_in_progress:
                pass  # keep the in-progress stroke's locked colour
            elif self._canvas.region_pick_active:
                self._canvas.set_region_stroke_color(c)
            else:
                self._annot_markup("highlight")  # re-arm preview with the new colour

    def _choose_custom_highlight_color(self) -> None:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog

        current = QColor(getattr(self._prefs, "highlight_color", "#ffff00") or "#ffff00")
        chosen = QColorDialog.getColor(current, self, "Highlight color")
        if chosen.isValid():
            self._set_highlight_color(chosen.name())

    def _refresh_highlight_color_button(self) -> None:
        btn = getattr(self, "_highlight_color_button", None)
        if btn is None:
            return
        hex_color = getattr(self._prefs, "highlight_color", "#ffff00") or "#ffff00"
        from PySide6.QtGui import QColor

        faded = QColor(hex_color)
        faded.setAlpha(70)  # disabled (no document): a pale swatch like the other disabled tools
        btn.setStyleSheet(
            f"QToolButton {{ background: {hex_color}; border: 1px solid #666; border-radius: 3px; }}"
            f"QToolButton:disabled {{ background: rgba({faded.red()}, {faded.green()}, {faded.blue()}, {faded.alpha()});"
            f" border: 1px solid rgba(128, 128, 128, 90); }}"
            f"QToolButton::menu-indicator {{ image: none; width: 0; }}"
        )
        btn.setToolTip(f"Highlight color ({hex_color})")

    def _build_highlight_color_button(self) -> QToolButton:
        """Toolbar swatch: preset highlight colors + custom picker."""
        from PySide6.QtGui import QColor, QIcon, QPixmap

        btn = QToolButton()
        btn.setObjectName("HighlightColorButton")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedSize(22, 22)
        btn.setAutoRaise(True)
        menu = QMenu(btn)
        presets = (
            ("#ffff00", "Yellow"),
            ("#90ee90", "Light green"),
            ("#87cefa", "Light blue"),
            ("#ffb6c1", "Pink"),
            ("#ffa500", "Orange"),
            ("#da70d6", "Orchid"),
            ("#ffffff", "White"),
        )
        for hex_color, name in presets:
            act = QAction(name, menu)
            pix = QPixmap(16, 16)
            pix.fill(QColor(hex_color))
            act.setIcon(QIcon(pix))
            act.triggered.connect(lambda _=False, c=hex_color: self._set_highlight_color(c))
            menu.addAction(act)
        menu.addSeparator()
        custom = QAction("Custom…", menu)
        custom.triggered.connect(self._choose_custom_highlight_color)
        menu.addAction(custom)
        btn.setMenu(menu)
        self._highlight_color_button = btn
        self._refresh_highlight_color_button()
        return btn

    def _annot_comment(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from PySide6.QtWidgets import QInputDialog

        from core.annotations import add_text_comment

        def apply(page: int, rect) -> None:
            text, ok = QInputDialog.getMultiLineText(self, "Sticky Note", "Comment:")
            if not ok or not text.strip():
                return
            pt = self._to_page_point(page, rect.x, rect.y)
            color = self._note_color_rgb()
            self._run_annot_command(page, lambda: add_text_comment(self._document, page, pt, text.strip(), color=color),
                                    "Add Sticky Note")
            self._after_annotation(page, "Sticky note added (Undo removes it; edit it in the Comments panel)")

        self._pick_on_page("Sticky note: click where the note should go", apply, kind="point")

    def _annot_callout(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from PySide6.QtWidgets import QInputDialog

        from core.annotations import add_callout
        from core.editing.geometry import Point

        def apply(page: int, rect) -> None:
            text, ok = QInputDialog.getText(self, "Callout", "Callout text:")
            if not ok or not text.strip():
                return
            box = self._to_page_rect(page, rect)
            self._run_annot_command(page, lambda: add_callout(
                self._document,
                page,
                box,
                text.strip(),
                callout_point=Point(max(4.0, box.x - 40), box.y + box.h / 2),
            ), "Add Callout")
            self._after_annotation(page, "Callout added")

        self._pick_on_page("Callout: drag the text box area", apply, default_size=(180.0, 48.0))

    def _annot_ink(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.annotations import add_freehand
        from core.editing.geometry import Point

        page = self._canvas.focus_page
        info = self._document.page(page)
        # Sample stroke for tool availability (canvas freehand can refine later)
        y = info.height_pt / 2
        stroke = [Point(80 + i * 12, y + (8 if i % 2 else -8)) for i in range(12)]
        try:
            add_freehand(self._document, page, [stroke])
            self._refresh_page_view(page)
            if self._edit:
                self._edit.mark_dirty()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Freehand", str(exc))

    def _annot_line(self, arrow: bool) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.annotations import add_line_arrow
        from core.editing.geometry import Point

        page = self._canvas.focus_page
        info = self._document.page(page)
        try:
            add_line_arrow(
                self._document,
                page,
                Point(72, info.height_pt / 2),
                Point(info.width_pt - 72, info.height_pt / 2),
                arrow=arrow,
            )
            self._refresh_page_view(page)
            if self._edit:
                self._edit.mark_dirty()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Line", str(exc))

    def _annot_shape(self, kind: str) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.annotations import add_ellipse, add_rectangle

        page = self._canvas.focus_page
        rect = self._page_center_rect(160, 100)
        try:
            if kind == "rect":
                add_rectangle(self._document, page, rect)
            else:
                add_ellipse(self._document, page, rect)
            self._refresh_page_view(page)
            if self._edit:
                self._edit.mark_dirty()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Shape", str(exc))

    def _annot_stamp(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        import fitz

        from core.annotations.stamps import add_custom_stamp
        from ui.stamp_dialog import StampLibraryDialog

        dlg = StampLibraryDialog(self, start_dir=self._doc_dir())
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        spec = dlg.spec()
        w, h = dlg.default_size()

        def apply(page: int, rect) -> None:
            r = self._to_page_rect(page, rect)
            if r.w < 12 or r.h < 8:  # a click: the stamp's default size, centred on the click
                cx, cy = r.x + r.w / 2, r.y + r.h / 2
                r = type(r)(cx - w / 2, cy - h / 2, w, h)
            frect = fitz.Rect(r.x, r.y, r.x1, r.y1)
            self._run_annot_command(page, lambda: add_custom_stamp(self._document, page, frect, spec), "Add Stamp")
            label = spec.text if not spec.image_path else "picture"
            self._after_annotation(page, f"Stamp “{label}” added (Undo removes it; change it in the Comments panel)")

        self._pick_on_page("Stamp: drag a box or click to place", apply, default_size=(w, h))

    # --- comments (any annotation): undoable create / edit / delete -------------------------------

    def _run_annot_command(self, page: int, create, name: str):
        from core.editing.annot_commands import AnnotCreateCommand

        diagnostics.record(EventId.COMMENT_CHANGED)

        cmd = AnnotCreateCommand(self._document, self._edit, page, create, name)
        self._edit.commands.execute(cmd)
        return cmd

    def _note_color_rgb(self) -> tuple[float, float, float]:
        from PySide6.QtGui import QColor

        from core.annotations.note_style import DEFAULT_NOTE_COLOR

        c = QColor(getattr(self._prefs, "note_color", None) or DEFAULT_NOTE_COLOR)
        return (c.redF(), c.greenF(), c.blueF()) if c.isValid() else (1.0, 0.851, 0.4)

    def _show_comments_panel(self) -> None:
        if not self.act_toggle_left.isChecked():
            self.act_toggle_left.trigger()
        self._left.setCurrentWidget(self._left.comments)
        self._left.comments.refresh()

    def _comment_go_to(self, ref) -> None:
        if self._document is None or not (0 <= ref.page_index < self._document.page_count):
            return
        self._canvas.go_to_page(ref.page_index)
        label = {"Text": "Note", "FreeText": "Callout"}.get(ref.kind, ref.kind)
        self.statusBar().showMessage(f"{label} on page {ref.page_index + 1}", 3000)

    def _comment_change(self, ref, change, name: str) -> None:
        from core.editing.annot_commands import AnnotModifyCommand

        diagnostics.record(EventId.COMMENT_CHANGED)

        if self._document is None or self._edit is None:
            return
        if ref.kind == "Text":
            plain_change = change

            def change() -> None:  # MuPDF redraws its square icon on update: keep the note's own look
                from core.annotations.note_style import style_sticky_note

                plain_change()
                style_sticky_note(self._document, ref.page_index, ref.xref)
        try:
            self._edit.commands.execute(AnnotModifyCommand(self._document, self._edit, ref.page_index, ref.xref, change, name))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, name, f"The comment could not be changed: {exc}")
            return
        self._after_annotation(ref.page_index, f"{name} — Undo restores the previous state")
        self._left.comments.refresh()
        self._left.comments.select(ref.page_index, ref.xref)

    def _annot_ref(self, page: int, xref: int):
        from core.annotations.store import find_live
        from ui.comments_panel import CommentRef

        found = find_live(self._document, page, xref) if self._document is not None else None
        kind, rect = ("", (0.0, 0.0, 0.0, 0.0))
        if found is not None:
            kind, r = found[1].type[1], found[1].rect
            rect = (r.x0, r.y0, r.x1, r.y1)
        return CommentRef(page, int(xref), kind, rect)

    def _annot_move(self, page: int, xref: int, dx: float, dy: float) -> None:
        """Move a comment (sticky note, callout, stamp, rectangle ...) dragged with the Select tool."""
        import fitz

        from core.annotations.stamps import stamp_spec, update_stamp

        ref = self._annot_ref(page, xref)

        def change() -> None:
            if stamp_spec(self._document, xref) is not None:
                _p, live = self._live_annot(ref)
                r = live.rect
                update_stamp(self._document, page, xref, center=((r.x0 + r.x1) / 2 + dx, (r.y0 + r.y1) / 2 + dy))
                return
            _p, live = self._live_annot(ref)
            live.set_rect(live.rect + fitz.Rect(dx, dy, dx, dy))
            if live.type[1] != "Stamp":  # a stamp from another app keeps its own appearance
                live.update()

        self._comment_change(ref, change, "Move Comment")
        self._canvas.select_annotation(page, xref)

    def _live_annot(self, ref):
        from core.annotations.store import find_live

        return find_live(self._document, ref.page_index, ref.xref)

    def _comment_edit_text(self, ref) -> None:
        from PySide6.QtWidgets import QInputDialog

        from core.annotations.stamps import StampSpec, stamp_spec, update_stamp

        found = self._live_annot(ref)
        if found is None:
            return
        _page, annot = found
        custom = stamp_spec(self._document, ref.xref)
        if custom is not None and not custom[0].image_path:
            self._stamp_edit(ref, custom[0])  # text stamps: wording, theme, font, colours, frame …
            return
        current = (annot.info or {}).get("content") or ""
        text, ok = QInputDialog.getMultiLineText(self, "Edit Comment", "Text:", current)
        if not ok or text == current:
            return

        def change() -> None:
            if custom is not None:
                spec, _size = custom
                if spec.image_path:
                    import fitz

                    self._document._backend._doc.xref_set_key(ref.xref, "Contents", fitz.get_pdf_str(text))  # noqa: SLF001
                else:
                    update_stamp(self._document, ref.page_index, ref.xref, spec=StampSpec(**{**spec.__dict__, "text": text}))
                return
            page, live = self._live_annot(ref)
            live.set_info(content=text)
            live.update()

        self._comment_change(ref, change, "Edit Comment")

    def _stamp_edit(self, ref, spec) -> None:
        """Edit a Monograph PDF text stamp in place (undoable)."""
        from core.annotations.stamps import update_stamp
        from ui.stamp_dialog import StampStyleDialog

        dlg = StampStyleDialog(self, spec)
        if self._is_headless_ui() or dlg.exec() != dlg.DialogCode.Accepted:
            return
        new_spec = dlg.spec()
        if new_spec == spec:
            return
        self._comment_change(ref, lambda: update_stamp(self._document, ref.page_index, ref.xref, spec=new_spec),
                             "Edit Stamp")
        self._canvas.select_annotation(ref.page_index, ref.xref)

    def _comment_color(self, ref) -> None:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog

        from core.annotations.stamps import StampSpec, stamp_spec, update_stamp

        found = self._live_annot(ref)
        if found is None:
            return
        _page, annot = found
        stroke = (annot.colors or {}).get("stroke") or [1, 1, 0]
        initial = QColor.fromRgbF(*[float(c) for c in stroke[:3]]) if len(stroke) >= 3 else QColor("#ffff00")
        custom = stamp_spec(self._document, ref.xref)
        if custom is not None:
            initial = QColor(custom[0].color)
        color = QColorDialog.getColor(initial, self, "Comment Colour")
        if not color.isValid():
            return
        rgb = (color.redF(), color.greenF(), color.blueF())

        def change() -> None:
            if custom is not None:
                spec, _size = custom
                update_stamp(self._document, ref.page_index, ref.xref, spec=StampSpec(**{**spec.__dict__, "color": color.name()}))
                return
            page, live = self._live_annot(ref)
            if ref.kind == "FreeText":
                live.update(text_color=rgb)
            else:
                live.set_colors(stroke=rgb)
                live.update()

        self._comment_change(ref, change, "Change Comment Colour")

    def _comment_opacity(self, ref) -> None:
        from PySide6.QtWidgets import QInputDialog

        from core.annotations.stamps import StampSpec, stamp_spec, update_stamp

        found = self._live_annot(ref)
        if found is None:
            return
        _page, annot = found
        current = int(round((annot.opacity if annot.opacity >= 0 else 1.0) * 100))
        value, ok = QInputDialog.getInt(self, "Comment Opacity", "Opacity (%):", current, 5, 100, 5)
        if not ok or value == current:
            return
        custom = stamp_spec(self._document, ref.xref)

        def change() -> None:
            if custom is not None:
                spec, _size = custom
                update_stamp(self._document, ref.page_index, ref.xref, spec=StampSpec(**{**spec.__dict__, "opacity": value / 100}))
                return
            page, live = self._live_annot(ref)
            live.set_opacity(value / 100)
            live.update()

        self._comment_change(ref, change, "Change Comment Opacity")

    def _comment_delete(self, ref) -> None:
        from core.editing.annot_commands import AnnotRemoveCommand

        if self._document is None or self._edit is None:
            return
        try:
            self._edit.commands.execute(AnnotRemoveCommand(self._document, self._edit, ref.page_index, ref.xref))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Delete Comment", f"The comment could not be deleted: {exc}")
            return
        self._after_annotation(ref.page_index, "Comment deleted — Undo restores it")
        self._left.comments.refresh()

    def _password_protect(self) -> None:
        if self._document is None:
            return
        from core.security import apply_password_protection
        from ui.convert_dialogs import choose_save
        from ui.security_dialogs import PasswordProtectDialog

        dlg = PasswordProtectDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        settings = dlg.settings()
        if not settings.user_password and not settings.owner_password:
            QMessageBox.warning(self, "Protect", "Enter at least one password.")
            return
        dest = choose_save(self, "Save Protected PDF", self._suggest("protected", "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        try:
            with self._current_document() as src:
                apply_password_protection(src, dest, settings)
            self.statusBar().showMessage(f"Protected PDF saved: {dest.name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Protect", str(exc))

    def _remove_protection(self) -> None:
        if self._document is None:
            return
        from core.document import PasswordRequiredError
        from core.security import remove_password_protection
        from ui.convert_dialogs import choose_save
        from ui.security_dialogs import RemoveProtectionDialog

        dlg = RemoveProtectionDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        dest = choose_save(self, "Save Unprotected PDF", self._suggest("unlocked", "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        try:
            with self._current_document() as src:
                remove_password_protection(
                    self._document, dest, password=dlg.password.text(), content=None if src is self._document else src
                )
            self.statusBar().showMessage(f"Wrote {dest.name}", 6000)
        except PasswordRequiredError as exc:
            QMessageBox.warning(self, "Remove protection", str(exc))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Remove protection", str(exc))

    def _inspect_permissions(self) -> None:
        if self._document is None:
            return
        from core.security import inspect_permissions
        from ui.security_dialogs import InfoTextDialog

        p = inspect_permissions(self._document)
        names = {
            "print": "Printing",
            "print_hq": "High-quality printing",
            "copy": "Copying text and images",
            "modify": "Changing the document",
            "assemble": "Inserting, rotating and deleting pages",
            "annotate": "Adding comments",
            "fill_forms": "Filling in form fields",
        }
        encrypted = bool(getattr(self._document.metadata(), "encrypted", False))
        if encrypted and self._open_password() is None:
            state = "permissions password only (the file opens without a password)"
        else:
            state = "yes" if encrypted else "no"
        lines = ["Password protection: " + state, ""]
        values = p.__dict__
        for key, label in names.items():
            if key in values:
                lines.append(f"{label}: {'allowed' if values[key] else 'not allowed'}")
        if not encrypted:
            lines += ["", "Without password protection every action is allowed."]
        InfoTextDialog("Permissions", "\n".join(lines), self).exec()

    def _inspect_metadata(self) -> None:
        if self._document is None:
            return
        from core.security import inspect_metadata
        from ui.security_dialogs import InfoTextDialog

        from ui.app_dialogs import _fmt_pdf_date

        meta = inspect_metadata(self._document)
        names = {
            "title": "Title",
            "author": "Author",
            "subject": "Subject",
            "keywords": "Keywords",
            "creator": "Created with",
            "producer": "PDF producer",
            "creation_date": "Created",
            "mod_date": "Modified",
            "encrypted": "Password protection",
            "has_digital_signatures": "Digital signatures",
        }
        lines = []
        for key, label in names.items():
            value = str(meta.get(key) or "").strip()
            if key in ("creation_date", "mod_date"):
                value = _fmt_pdf_date(value)
            elif key in ("encrypted", "has_digital_signatures"):
                value = "yes" if value.lower() == "true" else "no"
            lines.append(f"{label}: {value or '—'}")
        InfoTextDialog("Metadata", "\n".join(lines), self).exec()

    def _remove_metadata(self) -> None:
        if self._document is None:
            return
        from core.security import remove_metadata
        from ui.convert_dialogs import choose_save

        dest = choose_save(self, "Save PDF without Metadata", self._suggest("clean", "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        try:
            with self._current_document() as src:
                remove_metadata(src, dest)
            self.statusBar().showMessage(f"Wrote {dest.name}", 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Remove metadata", str(exc))

    def _copy_page_as_picture(self) -> None:
        if self._document is None:
            return
        page = self._canvas.focus_page
        try:
            with self._current_document() as src:
                png = src.render_pixmap_png(page, zoom=150 / 72.0)
        except Exception as exc:  # noqa: BLE001
            self.report_error("Copy page", str(exc))
            return
        img = QImage.fromData(png, "PNG")
        if img.isNull():
            self.report_error("Copy page", "The page could not be drawn.")
            return
        QApplication.clipboard().setImage(img)
        self.statusBar().showMessage(f"Page {page + 1} copied as a picture (150 dpi)", 5000)

    def _remove_hidden_info(self) -> None:
        if self._document is None:
            return
        from core.security.sanitize import remove_hidden, scan_hidden
        from ui.convert_dialogs import choose_save
        from ui.security_dialogs import RemoveHiddenInfoDialog

        try:
            with self._current_document() as src:
                dlg = RemoveHiddenInfoDialog(scan_hidden(src), self)
                if dlg.exec() != dlg.DialogCode.Accepted:
                    return
                dest = choose_save(self, "Save Cleaned PDF", self._suggest("clean", "pdf"), "PDF (*.pdf)")
                if not dest:
                    return
                report = remove_hidden(src, dest, dlg.options())
        except Exception as exc:  # noqa: BLE001
            self.report_error("Remove hidden information", str(exc))
            return
        b, a = report.before, report.after
        rows = []
        for label, before, after in (
            ("Document properties", b.metadata_fields + int(b.xmp_metadata), a.metadata_fields + int(a.xmp_metadata)),
            ("Attached files", b.attachments, a.attachments),
            ("Scripts and actions", b.javascript, a.javascript),
            ("Page thumbnails", b.thumbnails, a.thumbnails),
            ("Private application data", b.private_data, a.private_data),
            ("Comments", b.comments, a.comments),
            ("Form fields", b.form_fields, a.form_fields),
            ("Links", b.links, a.links),
            ("Bookmarks", b.bookmarks, a.bookmarks),
            ("Pages with invisible text", b.hidden_text_pages, a.hidden_text_pages),
        ):
            if before or after:
                rows.append(f"• {label}: {before} → {after}")
        body = f"Saved {report.destination.name}.\n\n" + ("\n".join(rows) if rows else "Nothing hidden was found.")
        if report.notes:
            body += "\n\n" + "\n".join(report.notes)
        QMessageBox.information(self, "Remove Hidden Information", body)
        self.statusBar().showMessage(f"Wrote {report.destination.name}", 6000)

    def _inspect_attachments(self) -> None:
        if self._document is None:
            return
        from core.security import inspect_attachments
        from ui.security_dialogs import InfoTextDialog

        items = inspect_attachments(self._document)
        if not items:
            body = "No embedded file attachments found."
        else:
            from ui.app_dialogs import _fmt_bytes

            body = "\n".join(
                f"{a.name} ({_fmt_bytes(a.size) if a.size else 'size unknown'}) {a.description}".strip() for a in items
            )
        InfoTextDialog("Attachments", body, self).exec()

    def _redact_mark_region(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.redaction import mark_region, preview_redaction_count

        def apply(page: int, rect) -> None:
            mark_region(self._document, page, self._to_page_rect(page, rect))
            n = preview_redaction_count(self._document)
            self._after_annotation(page, f"Area marked for redaction ({n} pending — Protect ▸ Apply to remove)")

        self._pick_on_page("Redact: drag over the area to remove", apply, default_size=(180.0, 24.0))

    def _redact_mark_text(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.redaction import mark_text
        from PySide6.QtWidgets import QInputDialog

        query, ok = QInputDialog.getText(
            self, "Mark text for redaction", "Text to redact (every page is searched):"
        )
        if not ok or not query:
            return
        page = self._canvas.focus_page
        try:
            # Every occurrence in the document: redacting only the page in view would leave the
            # same text readable elsewhere.
            found = {i: len(mark_text(self._document, i, query)) for i in range(self._document.page_count)}
            total = sum(found.values())
            pages = sum(1 for n in found.values() if n)
            if total:
                msg = f"Marked {total} occurrence{'s' if total != 1 else ''} on {pages} page{'s' if pages != 1 else ''}"
            else:
                msg = f"“{query}” was not found"
            self._refresh_after_page_ops(focus=page)
            if self._edit and total:
                self._edit.mark_dirty()
            self.statusBar().showMessage(msg, 6000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Redact text", str(exc))

    def _redact_mark_pages(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from PySide6.QtWidgets import QInputDialog

        from core.organize.page_ops import parse_page_ranges
        from core.redaction import mark_pages

        current = self._canvas.focus_page + 1
        spec, ok = QInputDialog.getText(
            self, "Mark pages for redaction",
            f"Pages to redact completely (e.g. 2, 5-7). The document has {self._document.page_count} pages.\n"
            "The pages stay in the document; everything on them is removed when you apply redactions.",
            text=str(current),
        )
        if not ok or not spec.strip():
            return
        try:
            pages = parse_page_ranges(spec.strip(), self._document.page_count)
            marks = mark_pages(self._document, pages)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Mark pages for redaction", str(exc))
            return
        self._refresh_after_page_ops(focus=self._canvas.focus_page)
        if self._edit and marks:
            self._edit.mark_dirty()
        n = len(marks)
        self.statusBar().showMessage(
            f"Marked {n} page{'s' if n != 1 else ''} for redaction — nothing is removed until you apply redactions", 7000)

    def _redact_preview(self) -> None:
        if self._document is None:
            return
        from core.redaction import preview_redaction_count

        n = preview_redaction_count(self._document)
        QMessageBox.information(
            self,
            "Redaction preview",
            (f"{n} area{'s' if n != 1 else ''} marked for redaction." if n else "No areas are marked for redaction yet.")
            + "\nNothing is removed until you choose Protect ▸ Apply Redactions….",
        )

    def _redact_apply(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.redaction import apply_redactions_report, preview_redaction_count
        from ui.convert_dialogs import choose_save

        n = preview_redaction_count(self._document)
        if n <= 0:
            QMessageBox.information(self, "Redact", "No redaction marks to apply.")
            return
        resp = QMessageBox.warning(
            self,
            "Apply true redaction",
            f"Apply {n} redaction(s)? This permanently removes the content under the marks from the saved "
            "file (not an opaque cover) — including form fields, comments and links that overlap a mark.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        dest = choose_save(self, "Save Redacted PDF", self._suggest("redacted", "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        try:
            report = apply_redactions_report(self._document, dest)
            self._refresh_after_page_ops(focus=0)
            if self._edit:
                self._edit.mark_dirty()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Apply redaction", str(exc))
            return
        extra = []
        if report.removed_form_fields:
            extra.append(f"{report.removed_form_fields} form field(s)")
        if report.removed_annotations:
            extra.append(f"{report.removed_annotations} comment(s) or mark-up")
        if report.removed_links:
            extra.append(f"{report.removed_links} link(s)")
        msg = f"Redacted PDF saved: {dest.name}"
        if extra:
            msg += " — also removed under the marks: " + ", ".join(extra)
        self.statusBar().showMessage(msg, 9000)
        if report.residue:
            from core.redaction import UNCHECKED_ATTACHMENT

            removable = [r for r in report.residue if r.where != UNCHECKED_ATTACHMENT]
            unchecked = [r for r in report.residue if r.where == UNCHECKED_ATTACHMENT]
            if removable:
                self._offer_residue_scrub(dest, report.residue)
            elif unchecked:
                QMessageBox.information(
                    self, "Attachments not checked",
                    "The saved file has attachments. Monograph PDF never opens or reads attachments, so it could "
                    "not check them for the redacted text:\n" + "\n".join(f"• {r.detail}" for r in unchecked[:12])
                    + "\n\nReview them before sharing the file.")

    def _offer_residue_scrub(self, dest, residue) -> None:
        """The redacted text still occurs outside the page content: say where and offer to remove it."""
        import os
        import tempfile

        import fitz

        from core.redaction import UNCHECKED_ATTACHMENT, find_residue, marked_terms, scrub_residue

        lines = [f"• {r.detail}" for r in residue[:12]]
        if len(residue) > 12:
            lines.append(f"• … and {len(residue) - 12} more")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Redacted text found elsewhere")
        box.setText("The page content was redacted, but the same text still appears in the saved file:")
        box.setInformativeText(
            "\n".join(lines)
            + "\n\nRemove it from these places too? Comment texts, bookmark titles and document properties "
            "get “[redacted]”, form values are cleared, and attachments with the text in their name or "
            "description are deleted. Attachment contents are never read, so they cannot be checked."
        )
        yes = box.addButton("Remove These Too", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Keep Them", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(yes)
        box.exec()
        if box.clickedButton() is not yes:
            self.statusBar().showMessage(f"Redacted PDF saved: {dest.name} — text outside the pages was kept", 9000)
            return
        terms = marked_terms(self._document)
        with fitz.open(dest) as probe:
            if probe.needs_pass:  # never re-save a protected file without its protection
                QMessageBox.warning(
                    self, "Redaction",
                    "The redacted file is password-protected, so the remaining text was not removed. "
                    "Remove the protection, apply the redaction again, then protect the result.")
                return
        tmp = ""
        try:
            fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(dest.parent))
            os.close(fd)
            with fitz.open(dest) as doc:
                scrub_residue(doc, terms)
                doc.save(tmp, garbage=4, deflate=True)
            os.replace(tmp, dest)
            with fitz.open(dest) as doc:
                found = find_residue(doc, terms)
            left = [r for r in found if r.where != UNCHECKED_ATTACHMENT]
            unchecked = len(found) - len(left)
        except Exception as exc:  # noqa: BLE001
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            QMessageBox.warning(self, "Redaction", f"Could not remove the remaining text: {exc}")
            return
        if left:
            QMessageBox.warning(self, "Redaction", "Some occurrences could not be removed:\n"
                                + "\n".join(f"• {r.detail}" for r in left[:12]))
        else:
            note = f"Redacted PDF saved: {dest.name} — no other occurrences remain"
            if unchecked:
                note += f" ({unchecked} attachment(s) not checked: their content is never read)"
            self.statusBar().showMessage(note, 12000)

    def _place_signature(self, png_path, message: str, spec: dict | None = None) -> None:
        """Let the user drag where a visual signature goes; it becomes a movable picture overlay.
        ``spec`` (how it was made) is kept with it, so a double-click can change it later."""
        from core.signatures.ops import signature_box

        def apply(page: int, rect) -> None:
            if self._edit is None:
                return
            box = signature_box(page, rect, png_path)
            box.signature = dict(spec or {})
            box.z_index = self._edit.next_z()
            self._edit.add_image(box)  # undoable
            self._edit.selection = [box.object_id]
            self._set_tool(EditTool.SELECT)
            self._on_edit_changed()
            self.statusBar().showMessage(message, 6000)

        self._pick_on_page("Signature: drag where it should go (or click)", apply, default_size=(200.0, 60.0))

    def _edit_image_object(self, oid: str) -> None:
        """Double-click on a placed picture: a typed signature opens with its name, style and ink to
        change; a drawn signature opens the pad to draw it again; any other picture can be replaced.
        The new picture takes the old one's place (same centre and height) — one Undo step."""
        if self._edit is None:
            return
        img = self._edit.images.get(oid)
        if img is None:
            return
        from core.annotations.stamp_library import png_bytes_to_library

        spec = dict(getattr(img, "signature", {}) or {})
        new_path = None
        new_spec = spec
        if img.role == "signature" and spec.get("kind") == "typed":
            from ui.security_dialogs import TypedSignatureDialog

            dlg = TypedSignatureDialog(self)
            dlg.set_values(spec.get("text", ""), spec.get("family", ""), spec.get("color", ""))
            if dlg.exec() != dlg.DialogCode.Accepted or not dlg.name.text().strip():
                return
            png = dlg.signature_png()
            if not png:
                return
            new_path, new_spec = png_bytes_to_library(png), dlg.spec()
        elif img.role == "signature" and spec.get("kind") == "drawn":
            from core.signatures.ops import strokes_to_png
            from ui.app_dialogs import SignaturePadDialog

            dlg = SignaturePadDialog(self)
            if dlg.exec() != dlg.DialogCode.Accepted or not dlg.strokes():
                return
            new_path = png_bytes_to_library(strokes_to_png(dlg.strokes()))
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Replace Signature Picture" if img.role == "signature" else "Replace Image", self._doc_dir(),
                "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)")
            if not path:
                return
            from core.annotations.stamp_library import import_picture

            try:
                new_path = import_picture(Path(path), remove_white=img.role == "signature")
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Replace Image", f"The picture could not be read: {type(exc).__name__}")
                return
        self._replace_image_picture(oid, new_path, new_spec)

    def _replace_image_picture(self, oid: str, new_path, new_spec: dict) -> None:
        from PIL import Image

        from core.editing.geometry import Rect
        from core.editing.image_box import SAFE_IMAGE_FORMATS

        img = self._edit.images.get(oid)
        if img is None:
            return
        try:
            with Image.open(str(new_path), formats=SAFE_IMAGE_FORMATS) as im:
                iw, ih = im.size
        except Exception:  # noqa: BLE001
            iw, ih = 0, 0
        r = img.rect
        rect = r
        if iw > 0 and ih > 0:
            h = r.h
            w = h * iw / ih
            rect = self._edit.keep_on_page(img.page_index, Rect(r.cx - w / 2, r.cy - h / 2, w, h))
        self._edit.set_overlay_attrs(oid, source_path=str(new_path), signature=dict(new_spec), rect=rect)
        self._edit.selection = [oid]
        self._on_edit_changed()
        self.statusBar().showMessage("Signature updated — Undo restores the previous one"
                                     if img.role == "signature" else "Picture replaced — Undo restores it", 5000)

    def _sig_typed(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.annotations.stamp_library import png_bytes_to_library
        from ui.security_dialogs import TypedSignatureDialog

        dlg = TypedSignatureDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted or not dlg.name.text().strip():
            return
        png = dlg.signature_png()
        if not png:
            return
        self._place_signature(png_bytes_to_library(png), spec=dlg.spec(), message=
                              "Visual signature placed — move or resize it, Delete removes it (a picture, not a digital signature)")

    def _sig_image(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.annotations.stamp_library import import_picture

        path, _ = QFileDialog.getOpenFileName(
            self, "Signature from Image", self._doc_dir(), "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"
        )
        if not path:
            return
        answer = QMessageBox.question(
            self, "Signature from Image",
            "Make the picture's white background transparent?\n\nRecommended for a scanned or photographed signature.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
        try:
            stored = import_picture(Path(path), remove_white=answer == QMessageBox.StandardButton.Yes)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Signature from Image", f"The picture could not be read: {type(exc).__name__}")
            return
        self._place_signature(stored, spec={"kind": "image"}, message="Signature picture placed — move or resize it, Delete removes it")

    def _sig_drawn(self) -> None:
        if self._document is None or not self._confirm_signed():
            return
        from core.annotations.stamp_library import png_bytes_to_library
        from core.signatures.ops import strokes_to_png
        from ui.app_dialogs import SignaturePadDialog

        dlg = SignaturePadDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted or not dlg.strokes():
            return
        png = strokes_to_png(dlg.strokes())
        self._place_signature(png_bytes_to_library(png), spec={"kind": "drawn"}, message=
                              "Drawn signature placed — move or resize it, Delete removes it (a picture, not a digital signature)")

    def _print_document(self) -> None:
        """Print with Monograph PDF's own dialog — printer settings plus a live preview of every sheet."""
        self._commit_field_editor()
        if self._document is None:
            return
        diagnostics.record(EventId.PDF_PRINT_STARTED)
        from core.printing import ColorMode, effective_print_dpi, prepare_print_source
        from ui.print_dialog import PrintDialog, print_document_pages

        source = None
        try:
            self.set_analysis_progress("Preparing print preview…")
            QApplication.processEvents()
            source = prepare_print_source(self._document, self._edit)
            self.clear_analysis_progress()
            dlg = PrintDialog(
                source.document,
                doc_name=self._document.name,
                current_page=self._canvas.focus_page,
                selected_pages=self._left.selected_page_indices(),
                parent=self,
            )
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            settings = dlg.settings()
            if dlg.save_as_pdf:
                self._print_save_as_pdf(source, settings)
                return
            printer = dlg.printer()
            if printer is None or not settings.pages:
                return
            dpi = effective_print_dpi(printer)
            from PySide6.QtWidgets import QProgressDialog

            from ui.print_dialog import PrintCancelled, PrintJobError

            progress = QProgressDialog("Printing…", "Cancel", 0, len(settings.pages), self)
            progress.setWindowTitle("Print")
            progress.setMinimumDuration(400)

            def step(done: int, total: int) -> bool:
                progress.setValue(done)
                progress.setLabelText(f"Printing page {done + 1} of {total}…")
                QApplication.processEvents()
                return not progress.wasCanceled()

            try:
                count = print_document_pages(
                    printer,
                    source.document,
                    settings.pages,
                    dpi=dpi,
                    color_mode=settings.color_mode,
                    scaling=settings.scaling,
                    orientation=settings.orientation,
                    comments=settings.comments,
                    percent=settings.percent,
                    n_up=settings.n_up,
                    progress=step,
                )
            except PrintCancelled as cancelled:
                self.statusBar().showMessage(
                    f"Printing cancelled after {cancelled.printed} page(s); the rest was not sent", 8000)
                return
            except PrintJobError as exc:
                self.report_error("Print", str(exc),
                                  hint="Check that the printer is switched on and connected, or choose another "
                                       "printer. Your document and unsaved changes are kept.")
                return
            finally:
                progress.close()
            mode = {ColorMode.COLOR: "color", ColorMode.GRAYSCALE: "grayscale",
                    ColorMode.MONOCHROME: "black and white"}[settings.color_mode]
            self.statusBar().showMessage(
                f"Sent {count} page(s) ({mode}) to {printer.printerName() or 'printer'}", 6000
            )
        except Exception as exc:  # noqa: BLE001
            self.report_unexpected("Print failed", exc, EventId.PDF_PRINT_FAILED)
        finally:
            if source is not None:
                source.close()
            self.clear_analysis_progress()

    def _print_save_as_pdf(self, source, settings) -> None:
        """Print dialog ▸ Save as PDF: the chosen pages of the current document state as a PDF file."""
        from core.printing import save_pages_as_pdf
        from ui.convert_dialogs import choose_save

        dest = choose_save(self, "Save as PDF", self._suggest("print", "pdf"), "PDF (*.pdf)")
        if not dest:
            return
        if self._document is not None and Path(dest).resolve() == Path(self._document.path).resolve():
            self.report_error("Save as PDF", "Choose a new file name — the open PDF cannot be replaced here.")
            return
        try:
            save_pages_as_pdf(source.document, settings.pages, Path(dest), comments=settings.comments)
        except OSError as exc:
            self.report_error("Save as PDF", f"The file could not be written: {exc.strerror or exc}",
                              hint="Choose another folder (the disk may be full or the folder read-only).")
            return
        self.statusBar().showMessage(f"Saved {len(settings.pages)} page(s) as {Path(dest).name}", 7000)

    def _show_about(self) -> None:
        AboutDialog(self, updates=self._updates).exec()

    def _show_settings(self) -> None:
        from ui.settings_dialog import SettingsDialog

        SettingsDialog(self._prefs, self._updates, self).exec()

    def close_for_update(self) -> None:
        """Unsaved changes were already saved or discarded; the update helper takes over now."""
        self._closing_for_update = True
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def after_startup(self) -> None:
        """Deferred start-up work: update results and staging cleanup, earlier problem reports,
        the automatic update check (only when the user switched it on)."""
        from core.updates import manager, staging

        try:
            if staging.cleanup().kept:
                # e.g. the update helper that just restarted us is still exiting: try once more
                QTimer.singleShot(30000, lambda: self._quiet_cleanup(staging))
        except OSError:
            pass
        for res in manager.read_results():
            self._show_update_result(res)
        from core.diagnostics import crash
        from core.diagnostics import report as reports

        pending = crash.take_pending()
        if pending is not None:
            self.offer_report(pending, "<b>Monograph PDF closed unexpectedly last time.</b><br>"
                              + html.escape(reports.describe(pending)))
        else:
            terminations = crash.take_terminations()
            if terminations:
                last = max(terminations, key=lambda t: bool(t.fault_kind))  # one with details, if any
                try:
                    rep = reports.build(EventId.UNEXPECTED_TERMINATION, report_type="termination",
                                        events=last.events, fault=last)
                    title = ("Monograph PDF stopped unexpectedly last time." if last.fault_kind
                             else "Monograph PDF did not close normally last time.")
                    self.offer_report(rep, f"<b>{title}</b><br>{html.escape(reports.describe(rep))}")
                except Exception:  # noqa: BLE001
                    pass
        self._updates.maybe_auto_check()

    @staticmethod
    def _quiet_cleanup(staging) -> None:
        try:
            staging.cleanup()
        except OSError:
            pass

    def _show_update_result(self, res: dict) -> None:
        from core.updates import staging

        status, version = res.get("status"), str(res.get("expected_version", ""))[:40]
        try:
            (staging.updates_root() / res["_file"]).unlink()
        except OSError:
            pass
        if status == "installed":
            self.statusBar().showMessage(f"Monograph PDF was updated to version {version}.", 10000)
            if version and version != __import__("core.versioning", fromlist=["get_version"]).get_version():
                QMessageBox.warning(self, "Update", f"The update to {version} finished, but this program reports a "
                                                    "different version. Run Setup again from the release page.")
        elif status == "installed_restart_required":
            QMessageBox.information(self, "Update", f"Monograph PDF {version} was installed. Restart Windows to finish.")
        elif status == "failed":
            diagnostics.record(EventId.UPDATE_INSTALL_FAILED)
            QMessageBox.warning(self, "Update", f"The update to Monograph PDF {version} was not installed "
                                                f"({res.get('code', 'error')}). This version is unchanged.")

    # --- Unsaved-change guard ----------------------------------------------

    def _confirm_unsaved(self, verb: str = "continuing") -> bool:
        """Ask Save / Don't Save / Cancel when there are unsaved edits. True = proceed."""
        self._commit_field_editor()
        if self._edit is None or self._document is None or not self._edit.dirty:
            return True
        if self._is_headless_ui():
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"Save changes to “{self._document.name}” before {verb}?")
        box.setInformativeText("Your changes will be lost if you don’t save them.")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        discard = box.button(QMessageBox.StandardButton.Discard)
        if discard is not None:
            discard.setText("Don’t Save")
        resp = box.exec()
        if resp == QMessageBox.StandardButton.Cancel:
            return False
        if resp == QMessageBox.StandardButton.Save:
            self.save_document()
            return not (self._edit is not None and self._edit.dirty)
        clear_session(self._document.path)
        self._edit.mark_clean()
        return True

    def _confirm_unsaved_for_export(self, title: str) -> bool:
        """Before a conversion or compression of a document with unsaved changes: Save / Save As… /
        Cancel. True = proceed (the conversion then reads the document as just saved). Cancel keeps
        every change. The source file is never overwritten without the user choosing Save."""
        self._commit_field_editor()
        if self._edit is None or self._document is None or not self._edit.dirty:
            return True
        if self._is_headless_ui():
            return True  # automated runs convert the current state (including the unsaved changes)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(f"“{self._document.name}” has unsaved changes.")
        box.setInformativeText("Save them before converting? The result will include them. "
                               "Cancel returns to the document without losing any change.")
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        save_as = box.addButton("Save As…", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(save)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            self.save_document()
        elif clicked is save_as:
            self.save_as_dialog()
        else:
            return False
        return self._edit is not None and not self._edit.dirty

    def _close_document_interactive(self) -> None:
        if self._document is None:
            return
        if not self._confirm_unsaved("closing"):
            return
        self.close_document(save_session=False)

    # --- Suggested output names -------------------------------------------

    def _suggest(self, tag: str, ext: str) -> str:
        """Default save path beside the open document, e.g. report-optimized.pdf."""
        if self._document is None:
            return f"{tag or 'output'}.{ext}"
        base = getattr(self, "_converted_from", None) or self._document.path
        stem = base.stem
        name = f"{stem}-{tag}.{ext}" if tag else f"{stem}.{ext}"
        return str(base.with_name(name))

    def _doc_dir(self) -> str:
        base = getattr(self, "_converted_from", None) or (self._document.path if self._document else None)
        if base is not None:
            return str(base.parent)
        recent = self._recent.list()
        return str(recent[0].parent) if recent else ""

    # --- Selection / find ---------------------------------------------------

    def _select_all(self) -> None:
        if self._edit is None:
            return
        if self._left.thumbs.hasFocus():
            self._left.thumbs.selectAll()
            return
        ids = [o.object_id for o in self._edit.all_objects()]
        page = self._canvas.focus_page
        ids += [sid for sid, sh in self._edit.shapes.items() if getattr(sh, "page_index", -1) == page]
        ids += [iid for iid, im in self._edit.images.items() if getattr(im, "page_index", -1) == page]
        self._edit.selection = list(dict.fromkeys(ids))
        self._edit._notify()  # noqa: SLF001
        self.statusBar().showMessage(f"Selected {len(self._edit.selection)} object(s)", 3000)

    def _deselect_all(self) -> None:
        if self._edit is None:
            return
        self._edit.clear_selection()
        self._edit.field_selection = []
        self._edit._notify()  # noqa: SLF001

    def _find_prev(self) -> None:
        if not self._search_hits:
            self._run_search()
            return
        self._search_index = (self._search_index - 1) % len(self._search_hits)
        self._goto_hit(self._search_index)

    def _on_search_return(self) -> None:
        query = (self._search_edit.text() or "").strip()
        if query and query == getattr(self, "_last_query", None) and self._search_hits:
            self._find_next()
        else:
            self._run_search()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._search_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._find_prev()
                return True
            if key == Qt.Key.Key_Escape:
                self._search_edit.clear()
                self._canvas.clear_highlights()
                self._search_hits = []
                self._canvas.setFocus()
                return True
        return super().eventFilter(obj, event)

    # --- Navigation ---------------------------------------------------------

    def _first_page(self) -> None:
        if self._document is not None:
            self._canvas.go_to_page(0)

    def _last_page(self) -> None:
        if self._document is not None:
            self._canvas.go_to_page(self._document.page_count - 1)

    def _go_to_page_dialog(self) -> None:
        if self._document is None:
            return
        from PySide6.QtWidgets import QInputDialog

        n = self._document.page_count
        value, ok = QInputDialog.getInt(
            self, "Go to Page", f"Page number (1–{n}):", self._canvas.focus_page + 1, 1, n, 1
        )
        if ok:
            self._canvas.go_to_page(value - 1)

    def _on_page_edit(self) -> None:
        if self._document is None:
            return
        try:
            value = int((self._page_edit.text() or "").strip())
        except ValueError:
            self._page_edit.setText(str(self._canvas.focus_page + 1))
            return
        value = max(1, min(self._document.page_count, value))
        self._canvas.go_to_page(value - 1)
        self._canvas.setFocus()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            if getattr(self, "_was_maximized", False):
                self.showMaximized()
            else:
                self.showNormal()
            self.act_fullscreen.setChecked(False)
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()
            self.act_fullscreen.setChecked(True)

    # --- Help / info --------------------------------------------------------

    def _show_shortcuts(self) -> None:
        from ui.app_dialogs import ShortcutsDialog

        ShortcutsDialog(self.menuBar(), self).exec()

    def _show_user_guide(self) -> None:
        from ui.app_dialogs import UserGuideDialog

        UserGuideDialog(self).exec()

    def _show_document_properties(self) -> None:
        if self._document is None:
            return
        from ui.app_dialogs import DocumentPropertiesDialog

        DocumentPropertiesDialog(self._document, self).exec()

    def _show_in_folder(self) -> None:
        if self._document is None:
            return
        self._reveal_file(Path(getattr(self, "_converted_from", None) or self._document.path))

    def _reveal_file(self, path: Path) -> None:
        """Open the file's folder with the file selected (Explorer), or just the folder elsewhere."""
        if sys.platform.startswith("win") and path.exists():
            import subprocess

            from core.safe_paths import windows_tool

            # Full path: never a same-named program from the current folder
            subprocess.Popen([windows_tool("explorer.exe"), "/select,", str(path)])  # noqa: S603
            return
        self._open_folder(path.parent)

    def _remove_recent(self, path: str) -> None:
        self._recent.remove(path)
        self._rebuild_recent_menu()
        self._refresh_welcome_recent()

    def _open_folder(self, folder: Path) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _clear_recent(self) -> None:
        self._recent.clear()
        self._rebuild_recent_menu()
        self._refresh_welcome_recent()

    # --- Draw-to-place helpers ---------------------------------------------

    def _to_page_rect(self, page_index: int, rect):
        """Display-space rect (canvas) → unrotated page space used by PDF annotations."""
        import fitz

        from core.editing.geometry import Rect

        page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
        r = fitz.Rect(rect.x, rect.y, rect.x + rect.w, rect.y + rect.h) * page.derotation_matrix
        r.normalize()
        return Rect(r.x0, r.y0, r.width, r.height)

    def _to_page_point(self, page_index: int, x: float, y: float):
        import fitz

        from core.editing.geometry import Point

        page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
        pt = fitz.Point(x, y) * page.derotation_matrix
        return Point(pt.x, pt.y)

    def _text_line_rects(self, page_index: int, page_rect) -> list:
        """Union of words (per text line) inside ``page_rect`` — for text markup."""
        import fitz

        from core.editing.geometry import Rect

        page = self._document._backend._doc.load_page(page_index)  # noqa: SLF001
        clip = fitz.Rect(page_rect.x, page_rect.y, page_rect.x + page_rect.w, page_rect.y + page_rect.h)
        lines: dict[tuple[int, int], fitz.Rect] = {}
        for w in page.get_text("words"):
            wr = fitz.Rect(w[:4])
            inter = wr & clip
            if inter.is_empty or inter.get_area() < 0.4 * max(wr.get_area(), 1e-6):
                continue
            key = (int(w[5]), int(w[6]))
            if key in lines:
                lines[key] |= wr
            else:
                lines[key] = fitz.Rect(wr)
        return [Rect(r.x0, r.y0, r.width, r.height) for r in lines.values()]

    def _pick_on_page(
        self, prompt: str, on_done, *, kind: str = "rect", default_size=(160.0, 40.0), stroke_color=None
    ) -> None:
        """Let the user drag a box (or click) on a page, then run ``on_done(page, display_rect)``."""
        if self._document is None:
            return
        from core.editing.geometry import Rect

        if self._canvas.region_pick_active:
            self._canvas.cancel_region_pick(announce=False)

        def done(page: int, rect, was_click: bool) -> None:
            if was_click and kind == "rect":
                w, h = default_size
                info = self._document.page(page)
                x = max(0.0, min(info.display_width_pt - w, rect.x - w / 2))
                y = max(0.0, min(info.display_height_pt - h, rect.y - h / 2))
                rect = Rect(x, y, w, h)
            try:
                on_done(page, rect)
            except Exception as exc:  # noqa: BLE001
                self.report_error("Could not place item", str(exc))
            finally:
                if getattr(self, "_markup_sticky", None) and self._document is not None:
                    QTimer.singleShot(0, self._rearm_sticky_markup)
                elif getattr(self, "_eraser_active", False) and self._document is not None:
                    QTimer.singleShot(0, self._rearm_eraser)
                else:
                    self.act_select_tool.setChecked(True)

        self._canvas.begin_region_pick(prompt, done, kind=kind, stroke_color=stroke_color)

    def _rearm_sticky_markup(self) -> None:
        kind = getattr(self, "_markup_sticky", None)
        if (
            kind
            and self._document is not None
            and not self._canvas.region_pick_active
            and self.act_annot_highlight.isChecked()
        ):
            self._annot_markup(kind, rearm=True)

    def _rearm_eraser(self) -> None:
        if (
            getattr(self, "_eraser_active", False)
            and self._document is not None
            and not self._canvas.region_pick_active
            and self.act_annot_eraser.isChecked()
        ):
            self._arm_eraser()

    def _after_annotation(self, page: int, message: str) -> None:
        """A comment, highlight, stamp … was added, changed or removed on ``page``.

        Only that page is redrawn, and its new picture replaces the old one when it is ready: the
        whole document used to be reloaded into the view (every page blanked and re-rendered, the
        thumbnails rebuilt), which made the page flash after every highlight."""
        if self._document is None:
            return
        self._refresh_page_view(page)
        if self._edit:
            self._edit.mark_dirty()
        self._on_edit_changed()
        self.statusBar().showMessage(message, 4000)

    def _refresh_page_view(self, page: int) -> None:
        """Redraw one page whose annotations changed, in place (no reload of the whole view)."""
        if self._document is None:
            return
        self._document.refresh_pages([page])
        self._canvas.clear_annotation_selection()
        self._canvas.refresh_page_content([page])
        self._left.thumbs.refresh_pages([page])

    # --- Printing -----------------------------------------------------------

    def _render_to_printer(
        self,
        printer,
        pages: list[int],
        *,
        dpi: int = 300,
        color_mode=None,
        source=None,
    ) -> int:
        from core.printing import ColorMode
        from ui.print_dialog import print_document_pages

        doc = source.document if source is not None else self._document
        if doc is None:
            return 0
        return print_document_pages(printer, doc, pages, dpi=dpi, color_mode=color_mode or ColorMode.COLOR)

    def _print_preview(self) -> None:
        """The Print dialog shows the preview (Ctrl+Shift+P kept for habit)."""
        self._print_document()

    # --- Form filling helpers --------------------------------------------------

    @contextmanager
    def _current_document(self, *, flatten: bool = False):
        """The open document as shown — including every unsaved change — for printing, exports and
        conversions: a temporary baked copy when something is unsaved (the file is never touched)."""
        self._commit_field_editor()
        from core.printing import prepare_current_source

        source = prepare_current_source(self._document, self._edit, flatten=flatten)
        try:
            yield source.document
        finally:
            source.close()

    def _commit_field_editor(self) -> None:
        try:
            self._canvas.close_field_editor(commit=True)
        except Exception:  # noqa: BLE001
            pass

    def _on_field_typed(self, field_id: str, text: str) -> None:
        """Live typing in a field: mark modified, mirror into the inspector (no rebuild)."""
        if self._edit is None:
            return
        field = self._edit.fields.get(field_id)
        if field is not None and not self._edit.dirty:
            self._edit.dirty = True
            self._update_title()
            self._dirty_label.setProperty("state", "modified")
            self._dirty_label.style().unpolish(self._dirty_label)
            self._dirty_label.style().polish(self._dirty_label)
            self._dirty_label.setText("Modified")
        self._inspector.sync_field_value(field_id, text)

    def _clear_selected_field(self) -> None:
        if self._edit is None:
            return
        self._commit_field_editor()
        fid = (self._edit.field_selection or [None])[0]
        field = self._edit.fields.get(fid) if fid else None
        if field is None or field.readonly:
            return
        if field.field_type.value in ("checkbox", "radio"):
            self._edit.set_field_value(fid, checked=False)
        else:
            self._edit.set_field_value(fid, "")
        self.statusBar().showMessage("Field cleared", 3000)

    # --- Opening images / Office files, rotation, default app -----------------

    def _convert_for_viewing(self, path: Path) -> Path | None:
        """Make a temporary PDF from an image or Office file so it can be viewed and edited."""
        import uuid

        from app.paths import TEMP_DIR
        from core.convert.office_bridge import OFFICE_EXTS, office_availability, unavailable_message
        from ui.task_runner import run_with_progress

        ext = path.suffix.lower()
        out = TEMP_DIR / "converted" / uuid.uuid4().hex[:12] / f"{path.stem}.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            if ext in IMAGE_EXTS:
                from core.convert.images_to_pdf import images_to_pdf

                images_to_pdf([path], out)
            elif ext in OFFICE_EXTS:
                if not office_availability().can_convert(ext):
                    QMessageBox.information(self, "Cannot open this file", unavailable_message(ext))
                    return None
                from core.convert.office_to_pdf import office_to_pdf

                run_with_progress(
                    self, "Opening", f"Converting “{path.name}” to PDF…", lambda: office_to_pdf(path, out)
                )
            else:
                self.report_error(
                    "Cannot open this file",
                    f"“{path.name}” is not a PDF, image or Office document.",
                )
                return None
        except Exception as exc:  # noqa: BLE001
            self.report_error("Cannot open this file", str(exc))
            return None
        return out

    def _open_external(self, path: Path) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _rotate_pages_dialog(self) -> None:
        if self._document is None or self._edit is None:
            return
        from ui.organize_dialogs import RotatePagesDialog

        dlg = RotatePagesDialog(
            self._document.page_count, self._canvas.focus_page, self._left.selected_page_indices(), self
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        try:
            pages = dlg.pages()
        except Exception as exc:  # noqa: BLE001
            self.report_error("Rotate Pages", f"Invalid page range: {exc}")
            return
        if not pages:
            return
        if not self._warn_signatures_if_needed():
            return
        if not self._rotate_pages(pages, dlg.degrees()):
            return
        self.statusBar().showMessage(f"Rotated {len(pages)} page(s) — Save to keep the change", 5000)

    def _make_default_app(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QMessageBox.information(
            self,
            "Default PDF App",
            "Windows lets you choose the default app yourself.\n\n"
            "In the Settings page that opens, find “.pdf” (or Monograph PDF), and select Monograph PDF.",
        )
        if not QDesktopServices.openUrl(QUrl(f"ms-settings:defaultapps?registeredAppUser={PRODUCT_NAME}")):
            QDesktopServices.openUrl(QUrl("ms-settings:defaultapps"))

    def _run_welcome_tool(self, key: str) -> None:
        """Welcome-screen tool tiles; tools that work on a PDF ask for one first."""
        no_doc = {
            "merge": self._merge_combine,
            "office_to_pdf": self._office_to_pdf,
            "images_to_pdf": self._images_to_pdf,
            "batch": self._batch_convert,
        }
        if key in no_doc:
            no_doc[key]()
            return
        if self._document is None:
            self.open_file_dialog()
            if self._document is None:
                return
        {
            "pdf_to_word": self._pdf_to_docx,
            "rotate": self._rotate_pages_dialog,
            "protect": self._password_protect,
            "unlock": self._remove_protection,
            "watermark": self._watermark,
            "sign": self._sig_typed,
            "ocr": lambda: self._run_ocr(scope="needed"),
            "compress": self._optimize_pdf,
            "pdf_to_pptx": self._pdf_to_pptx,
        }.get(key, lambda: None)()
