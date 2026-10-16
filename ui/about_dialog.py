"""About dialog — product identity, components, licence and third-party notices."""

from __future__ import annotations

import platform
import re
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.product_meta import (
    PRODUCT_DESCRIPTION,
    PRODUCT_HISTORY_NOTE,
    get_product_identity,
    resolve_about_logo_path,
)

FEATURES = (
    "View, search, and print PDF documents",
    "Edit text; insert text boxes, images, shapes, and comments",
    "Fill existing forms and create new form fields",
    "Merge, split, rotate, insert, extract, and reorder pages",
    "Convert PDF to Word, Excel, PowerPoint, images, and plain text",
    "Convert Word, Excel, PowerPoint, and images to PDF",
    "Perform OCR on scanned pages (English and Japanese)",
    "Apply password protection and permissions, or remove encryption",
    "Add watermarks, headers, footers, and page numbers",
    "Place visual signatures and apply true redaction",
)

_LEGAL_VIEWER_CSS = """
body {
    font-family: "Segoe UI", "Yu Gothic UI", sans-serif;
    font-size: 13px;
    line-height: 1.5;
    margin: 8px 12px;
}
h1, h2, h3, h4 {
    text-align: left;
    line-height: 1.3;
    margin-top: 1.1em;
    margin-bottom: 0.45em;
}
p { margin: 0 0 0.85em 0; }
li { margin-bottom: 0.25em; }
table { text-align: left; border-collapse: collapse; margin: 0.6em 0 1em 0; }
th, td { text-align: left; padding: 4px 10px 4px 0; vertical-align: top; }
pre, code { text-align: left; font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; }
"""


def _version_of(module: str) -> str:
    try:
        if module == "PyMuPDF":
            import fitz

            return str(fitz.VersionBind)
        if module == "PySide6":
            from PySide6 import __version__

            return __version__
        if module == "pdf2docx":
            from importlib.metadata import version

            return version("pdf2docx")
        if module == "Python":
            return platform.python_version()
    except Exception:  # noqa: BLE001
        pass
    return "—"


def _tesseract_version() -> str:
    try:
        from core.ocr.paths import tesseract_exe

        exe = tesseract_exe()
        if exe is None:
            return "—"
        import subprocess

        proc = subprocess.run(
            [str(exe), "--version"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = (proc.stdout or proc.stderr or "").splitlines()
        if text:
            m = re.search(r"tesseract\s+v?(\d+(?:\.\d+){0,2})", text[0], re.I)
            if m:
                return m.group(1)
    except Exception:  # noqa: BLE001
        pass
    return "—"


def _pyinstaller_version() -> str:
    try:
        from importlib.metadata import version

        return version("pyinstaller")
    except Exception:  # noqa: BLE001
        return "—"


def windows_label() -> str:
    """'Windows 11 (build 22631)' — platform.release() reports Windows 11 as '10' on Python 3.11."""
    if sys.platform != "win32":
        return f"{platform.system()} {platform.release()}".strip()
    try:
        ver = sys.getwindowsversion()
        name = "Windows 11" if (ver.major, ver.build) >= (10, 22000) else f"Windows {platform.release()}"
        return f"{name} (build {ver.build})"
    except Exception:  # noqa: BLE001
        return f"Windows {platform.release()}"


def _body_label(text: str, *, object_name: str = "AboutBody") -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    lab.setObjectName(object_name)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def _configure_legal_browser(view: QTextBrowser) -> None:
    view.setObjectName("LegalDocumentBrowser")
    view.setOpenExternalLinks(True)
    view.document().setDefaultStyleSheet(_LEGAL_VIEWER_CSS)
    font = QFont(view.font())
    if font.pointSize() < 10:
        font.setPointSize(10)
    view.setFont(font)


def _component_rows() -> list[tuple[str, str, str, str]]:
    """Component, Version, Status, License — what ships inside Monograph PDF (no filesystem paths).

    Microsoft Office / LibreOffice have their own tab; build-only tools are not listed.
    """
    from core.ocr.paths import ocr_ready

    rows: list[tuple[str, str, str, str]] = [
        ("PDF engine (PyMuPDF / MuPDF)", _version_of("PyMuPDF"), "Bundled", "AGPL-3.0"),
        ("User interface (Qt / PySide6)", _version_of("PySide6"), "Bundled", "LGPL-3.0"),
        ("PDF to Word (pdf2docx)", _version_of("pdf2docx"), "Bundled", "GPL-3.0"),
        ("Python runtime", _version_of("Python"), "Bundled", "PSF"),
    ]

    ocr_ok, _ = ocr_ready()
    rows.append(
        (
            "Tesseract OCR",
            _tesseract_version() if ocr_ok else "—",
            "Bundled" if ocr_ok else "Not installed",
            "Apache-2.0",
        )
    )

    rows.append(("Application launcher (PyInstaller)", _pyinstaller_version(), "Bundled", "GPL-2.0+ with exception"))
    return rows


def _office_integration_html() -> str:
    try:
        from core.convert.office_bridge import office_availability

        avail = office_availability(refresh=True)
    except Exception:  # noqa: BLE001
        return (
            "<p>Office integration status could not be determined on this computer. "
            "Only Office-to-PDF conversion depends on it.</p>"
        )

    parts: list[str] = []
    ms = avail.word or avail.excel or avail.powerpoint
    if ms:
        apps = [n for n, ok in (("Word", avail.word), ("Excel", avail.excel), ("PowerPoint", avail.powerpoint)) if ok]
        parts.append(
            "<p><b>Microsoft Office — Available</b></p>"
            f"<p>Detected: {', '.join(apps)}. Used to convert Office documents to PDF with "
            "Office's own export, so the layout matches what Office shows.</p>"
        )
    else:
        parts.append(
            "<p><b>Microsoft Office — Not available</b></p>"
            "<p>Not detected. Office-to-PDF conversion needs Word, Excel or PowerPoint (or "
            "LibreOffice) on this computer; everything else works without it.</p>"
        )

    if avail.libreoffice:
        parts.append(
            "<p><b>LibreOffice — Available</b></p>"
            "<p>Detected. Used for Office-to-PDF conversion when Microsoft Office is not available.</p>"
        )
    else:
        parts.append(
            "<p><b>LibreOffice — Not available</b></p>"
            "<p>Not detected. Optional — only needed when Microsoft Office is not installed.</p>"
        )

    if not avail.any:
        parts.append(
            "<p>No office suite was found, so Office-to-PDF conversion is unavailable. Viewing, "
            "editing, forms, OCR and all other features work normally.</p>"
        )
    else:
        parts.append(
            "<p>Office suites are not bundled with Monograph PDF; the installed suite follows its own "
            "settings and license terms.</p>"
        )

    parts.append(
        f"<p class='sysmeta'>This computer: {windows_label()} · "
        f"{'64-bit' if sys.maxsize > 2**32 else '32-bit'}</p>"
    )
    return "".join(parts)


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        identity = get_product_identity()
        self.setWindowTitle(identity.about_title)
        self.setModal(True)
        self.setMinimumSize(600, 560)
        self._office_loaded = False

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(18, 16, 18, 14)

        header = QHBoxLayout()
        header.setSpacing(18)
        logo = QLabel()
        logo.setObjectName("AboutLogo")
        logo.setFixedSize(72, 72)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = resolve_about_logo_path()
        pix = QPixmap(str(path)) if path is not None else QPixmap()
        if not pix.isNull():
            dpr = self.devicePixelRatioF()
            scaled = pix.scaled(
                int(72 * dpr),
                int(72 * dpr),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
            logo.setPixmap(scaled)
        else:
            logo.setText(identity.product_name[:1])
            logo.setToolTip("Application logo is unavailable.")
        header.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        name = QLabel(identity.product_name)
        name.setObjectName("AboutTitle")
        font = name.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        name.setFont(font)
        ver = QLabel(f"Version {identity.version}")
        ver.setObjectName("AboutVersion")
        ver.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tagline = QLabel(PRODUCT_DESCRIPTION)
        tagline.setObjectName("AboutTagline")
        tagline.setWordWrap(True)
        titles.addWidget(name)
        titles.addWidget(ver)
        titles.addWidget(tagline)
        titles.addStretch(1)
        header.addLayout(titles, 1)
        root.addLayout(header)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        about = QWidget()
        al = QVBoxLayout(about)
        al.setContentsMargins(14, 14, 14, 14)
        al.setSpacing(12)
        feat_title = QLabel("Capabilities")
        feat_title.setObjectName("AboutSectionTitle")
        al.addWidget(feat_title)
        feats = QLabel(
            "<table cellspacing='0' cellpadding='0'>"
            + "".join(
                f"<tr><td style='padding:0 8px 4px 2px;'>•</td><td style='padding:0 0 4px 0;'>{f}</td></tr>"
                for f in FEATURES
            )
            + "</table>"
        )
        feats.setTextFormat(Qt.TextFormat.RichText)
        feats.setWordWrap(True)
        feats.setObjectName("AboutFeatures")
        al.addWidget(feats)

        al.addWidget(
            _body_label(
                "Everything runs on this computer: documents are never uploaded, no internet "
                "connection is needed and no usage data is collected.",
                object_name="AboutPrivacy",
            )
        )
        al.addWidget(_body_label(PRODUCT_HISTORY_NOTE, object_name="AboutHistory"))
        al.addStretch(1)
        al.addWidget(
            _body_label(
                "Licensed under the GNU Affero General Public License v3 or later (AGPL-3.0-or-later). "
                "Its PDF engine (MuPDF / PyMuPDF) is under upstream AGPL-3.0. Bundled components keep "
                "their own licenses — see Third-Party Notices.",
                object_name="AboutLicenseNote",
            )
        )
        self._tabs.addTab(about, "About")

        comps = QTreeWidget()
        comps.setColumnCount(4)
        comps.setHeaderLabels(["Component", "Version", "Status", "License"])
        comps.setRootIsDecorated(False)
        comps.setAlternatingRowColors(True)
        comps.setUniformRowHeights(True)
        comps.setObjectName("AboutComponents")
        h = comps.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for row in _component_rows():
            comps.addTopLevelItem(QTreeWidgetItem(list(row)))
        self._tabs.addTab(comps, "Components")

        self._office = QTextBrowser()
        _configure_legal_browser(self._office)
        self._office.setHtml(
            "<p>Open this tab to detect optional Microsoft Office or LibreOffice integration.</p>"
        )
        self._tabs.addTab(self._office, "Office Integration")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        copy = QLabel(identity.copyright_display)
        copy.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy.setObjectName("AboutCopyright")
        root.addWidget(copy)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        lic_btn = QPushButton("View License…")
        notices_btn = QPushButton("Third-Party Notices…")
        buttons.addButton(lic_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(notices_btn, QDialogButtonBox.ButtonRole.ActionRole)
        # Enter closes the dialog; the document buttons open only when clicked
        for extra in (lic_btn, notices_btn):
            extra.setAutoDefault(False)
            extra.setDefault(False)
        buttons.button(QDialogButtonBox.StandardButton.Close).setDefault(True)
        lic_btn.clicked.connect(lambda: self._show_doc("LICENSE.md", "License"))
        notices_btn.clicked.connect(lambda: self._show_doc("THIRD_PARTY_NOTICES.md", "Third-Party Notices"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    def _on_tab_changed(self, index: int) -> None:
        if self._tabs.tabText(index) != "Office Integration":
            return
        if self._office_loaded:
            return
        self._office_loaded = True
        self._office.document().setDefaultStyleSheet(
            _LEGAL_VIEWER_CSS + "p.sysmeta { text-align: left; color: palette(mid); margin-top: 1.2em; }"
        )
        self._office.setHtml(_office_integration_html())

    def _show_doc(self, filename: str, title: str) -> None:
        from app.paths import BUNDLE_ROOT, ROOT

        text = None
        for base in (ROOT, BUNDLE_ROOT):
            path = base / filename
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                break
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(640, 520)
        dlg.resize(760, 680)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(10)
        view = QTextBrowser()
        _configure_legal_browser(view)
        if text is None:
            view.setPlainText(
                f"The document “{filename}” could not be found next to the application. "
                "Reinstall Monograph PDF or restore the file from the distribution package."
            )
        elif filename.endswith(".md"):
            view.setMarkdown(text)
        else:
            view.setPlainText(text)
        lay.addWidget(view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        lay.addWidget(bb)
        dlg.exec()
