"""Regenerate the README screenshots in docs/images from the real application window.

Usage (Windows, from the project folder):
    env\\Scripts\\python.exe scripts\\make_readme_screenshots.py [out_dir]

Builds a sample document, opens it in ``MainWindow`` with throw-away settings (your own settings,
recent files and documents are never touched) and saves window captures made by Qt itself — no
screen recording, so other windows never appear in the images.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(tempfile.mkdtemp(prefix="monograph_readme_shots_"))
os.environ["MONOGRAPH_PDF_USER_DATA_DIR"] = str(WORK / "userdata")
os.environ["MONOGRAPH_PDF_RUNTIME_DIR"] = str(WORK / "runtime")
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

SIZE = (1360, 860)
BLUE = (0.11, 0.23, 0.45)
GREY = (0.35, 0.35, 0.35)

PAGES = [
    ("Monograph PDF", "Offline, privacy-first PDF editor for Windows",
     "Monograph PDF lets you read, annotate and edit PDF documents entirely on your own computer. "
     "Documents are never uploaded, and no internet connection is needed.",
     ["View, search, print and edit bookmarks", "Edit text; add text boxes, images, shapes and comments",
      "Fill in and design forms", "Merge, split, rotate and reorder pages",
      "Headers, footers, page and Bates numbers, watermarks",
      "Convert between PDF, Word, Excel, PowerPoint and images",
      "Offline OCR for scanned pages (English and Japanese)",
      "Protect, redact, remove hidden information and sign"]),
    ("Editing", "Text, comments and forms", "Edit existing text, add text boxes, images and shapes, "
     "highlight and comment. Every change can be undone and is written only when you save.", []),
    ("Organizing", "Pages and bookmarks", "Insert, delete, rotate, crop and reorder pages; merge and "
     "split files; add, rename and reorder bookmarks in the Navigation panel.", []),
    ("Protecting", "Passwords, redaction and clean copies", "Encrypt with AES-256, redact content "
     "permanently and save copies without metadata, attachments or scripts.", []),
]


def make_sample(path: Path) -> Path:
    doc = fitz.open()
    for i, (title, subtitle, body, bullets) in enumerate(PAGES):
        page = doc.new_page()  # A4
        page.insert_text((60, 110), title, fontsize=30, color=BLUE)
        page.insert_text((60, 140), subtitle, fontsize=13, color=GREY)
        page.draw_line((60, 155), (535, 155), color=BLUE, width=1.2)
        rect = fitz.Rect(60, 172, 535, 260)
        page.insert_textbox(rect, body, fontsize=11.5, lineheight=1.45)
        y = 232
        if bullets:
            page.insert_text((60, y), "Highlights", fontsize=12)
            for b in bullets:
                y += 20
                page.insert_text((66, y), f"- {b}", fontsize=11.5)
        page.insert_text((60, 800), f"Monograph PDF overview  ·  page {i + 1} of {len(PAGES)}", fontsize=8, color=GREY)
    hits = doc[0].search_for("never uploaded")
    if hits:
        doc[0].add_highlight_annot(hits[0])
    doc.set_toc([[1, t, i + 1] for i, (t, *_rest) in enumerate(PAGES)])
    doc.set_metadata({"title": "Monograph PDF Overview", "author": "Sample author"})
    doc.embfile_add("notes.txt", b"Sample attachment")
    doc.save(path)
    doc.close()
    return path


def make_review(path: Path) -> Path:
    """A one-page project update with typical review markup: highlight, underline, rectangle,
    sticky note, text box and arrow (real PDF annotations, drawn by the app)."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 100), "Quarterly Project Update", fontsize=26, color=BLUE)
    page.insert_text((60, 128), "Draft for review  -  sample document", fontsize=12, color=GREY)
    page.draw_line((60, 142), (535, 142), color=BLUE, width=1.2)
    body = ("The pilot phase finished on schedule. All twelve test sites reported stable results, and "
            "the average processing time fell by 18 percent compared with the previous quarter. "
            "Two sites still need updated equipment before the full rollout.\n\n"
            "Next steps: confirm the rollout budget, schedule training for the remaining sites and "
            "publish the final report to all partners by the end of the month.")
    page.insert_textbox(fitz.Rect(60, 160, 535, 330), body, fontsize=12, lineheight=1.5)
    for needle, kind in (("fell by 18 percent", "highlight"), ("updated equipment", "underline")):
        hits = page.search_for(needle)
        if hits:
            (page.add_highlight_annot if kind == "highlight" else page.add_underline_annot)(hits[0])
    budget = page.search_for("by the end of the month")[0]
    rect = page.add_rect_annot(budget + (-3, -2, 3, 2))  # around the words, from their position
    rect.set_colors(stroke=(0.85, 0.2, 0.2))
    rect.set_border(width=1.5)
    rect.update()
    note = page.add_text_annot((542, budget.y0 - 2), "Is this date agreed with all partners?")
    note.set_info(title="Reviewer")
    note.update()
    box_rect = fitz.Rect(330, budget.y1 + 60, 535, budget.y1 + 84)
    box = page.add_freetext_annot(box_rect, "Move to the 15th?", fontsize=11,
                                  text_color=(0.11, 0.23, 0.45), fill_color=(1, 0.98, 0.85))
    box.update()
    arrow = page.add_line_annot((box_rect.x0 + 30, box_rect.y0), ((budget.x0 + budget.x1) / 2, budget.y1 + 3))
    arrow.set_colors(stroke=(0.85, 0.2, 0.2))
    arrow.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_OPEN_ARROW)
    arrow.set_border(width=1.5)
    arrow.update()
    doc.set_metadata({"title": "Quarterly Project Update", "author": "Sample author"})
    doc.save(path)
    doc.close()
    return path


def make_form(path: Path) -> Path:
    """A simple application form with text fields, a choice list and check boxes, partly filled in."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 100), "Membership Application", fontsize=26, color=BLUE)
    page.insert_text((60, 128), "Sample form  -  fields can be filled in Monograph PDF", fontsize=12, color=GREY)
    page.draw_line((60, 142), (535, 142), color=BLUE, width=1.2)
    rows = [("Full name", "name", "Alex Sample"), ("Email", "email", "alex@example.com"),
            ("Organization", "org", ""), ("Phone", "phone", "")]
    y = 180
    for label, name, value in rows:
        page.insert_text((60, y + 14), label, fontsize=12)
        w = fitz.Widget()
        w.field_name, w.field_type = name, fitz.PDF_WIDGET_TYPE_TEXT
        w.rect, w.field_value, w.text_fontsize = fitz.Rect(190, y, 535, y + 22), value, 11
        page.add_widget(w)
        y += 40
    page.insert_text((60, y + 14), "Membership", fontsize=12)
    w = fitz.Widget()
    w.field_name, w.field_type = "plan", fitz.PDF_WIDGET_TYPE_COMBOBOX
    w.choice_values = ["Individual", "Team", "Organization"]
    w.rect, w.field_value, w.text_fontsize = fitz.Rect(190, y, 380, y + 22), "Team", 11
    page.add_widget(w)
    y += 50
    for i, (label, on) in enumerate((("Send me the newsletter", True), ("I agree to the terms", False))):
        w = fitz.Widget()
        w.field_name, w.field_type = f"check{i}", fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.rect, w.field_value = fitz.Rect(60, y + i * 32, 76, y + 16 + i * 32), on
        page.add_widget(w)
        page.insert_text((86, y + 13 + i * 32), label, fontsize=12)
    doc.save(path)
    doc.close()
    return path


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from core.security.sanitize import scan_hidden
    from ui.main_window import MainWindow, create_application
    from ui.security_dialogs import RemoveHiddenInfoDialog

    create_application(["monograph-pdf-readme-shots"])
    app = QApplication.instance()
    win = MainWindow()
    win.resize(*SIZE)
    win.move(QPoint(40, 40))
    win.show()

    def settle(ms: int = 1200) -> None:
        for _ in range(5):
            app.processEvents()
        QTest.qWait(ms)

    def shot(name: str, widget=None) -> None:
        (widget or win).grab().save(str(out / name))
        print("wrote", out / name)

    win._set_theme("dark")  # noqa: SLF001
    win.statusBar().clearMessage()
    settle()
    shot("monograph-pdf-start-dark.png")

    sample = make_sample(WORK / "Monograph PDF Overview.pdf")
    assert win.open_path(sample)
    total = sum(win._splitter.sizes())  # noqa: SLF001
    win._splitter.setSizes([340, total - 340 - 300, 300])  # noqa: SLF001 - all navigation tabs visible
    win._left.show_bookmarks()  # noqa: SLF001
    win._left._bookmarks.setCurrentRow(0)  # noqa: SLF001
    for theme, name in (("light", "monograph-pdf-ui.png"), ("dark", "monograph-pdf-viewer-dark.png")):
        win._set_theme(theme)  # noqa: SLF001
        win.statusBar().clearMessage()
        settle(1800)
        shot(name)

    win._set_theme("light")  # noqa: SLF001
    settle()
    dlg = RemoveHiddenInfoDialog(scan_hidden(win._document), win)  # noqa: SLF001
    dlg.show()
    settle(600)
    shot("monograph-pdf-remove-hidden.png", dlg)
    dlg.close()

    # Page thumbnails (Navigation panel, Pages tab)
    win._left.setCurrentIndex(0)  # noqa: SLF001
    win.statusBar().clearMessage()
    settle(1800)
    shot("monograph-pdf-page-thumbnails.png")

    # Dialogs opened through their real menu commands; grabbed, then cancelled (nothing is saved).
    from PySide6.QtCore import QTimer

    def capture_modal(action, name: str) -> None:
        state = {"tries": 0, "done": False}

        def grab() -> None:
            w = QApplication.activeModalWidget()
            if w is None:
                state["tries"] += 1
                if state["tries"] < 50:
                    QTimer.singleShot(100, grab)
                return
            QTest.qWait(900)  # live previews render
            shot(name, w)
            state["done"] = True
            w.reject()

        QTimer.singleShot(300, grab)
        action.trigger()
        if not state["done"]:
            raise RuntimeError(f"{name}: the dialog did not open")

    capture_modal(win.act_header_footer, "monograph-pdf-header-footer.png")
    capture_modal(win.act_sec_protect, "monograph-pdf-password-protect.png")

    # Editing and review markup
    win.close_document(save_session=False)
    assert win.open_path(make_review(WORK / "Quarterly Project Update.pdf"))
    win._left.setCurrentIndex(0)  # noqa: SLF001
    win.act_fit_width.trigger()
    win.statusBar().clearMessage()
    settle(1800)
    shot("monograph-pdf-editing-comments.png")

    # Forms: fields highlighted (View > Highlight Fillable Fields; display only, never saved)
    win.close_document(save_session=False)
    assert win.open_path(make_form(WORK / "Membership Application.pdf"))
    if not win.act_highlight_fields.isChecked():
        win.act_highlight_fields.trigger()
    win.act_fit_width.trigger()
    win.statusBar().clearMessage()
    settle(1800)
    shot("monograph-pdf-forms.png")
    win.act_highlight_fields.trigger()  # leave the (remembered) view option off again

    win.close_document(save_session=False)
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
