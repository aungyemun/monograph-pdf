"""Security, redaction, signature, and annotation helper dialogs."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
)

from core.security.ops import EncryptionSettings, PermissionFlags


def _title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogTitle")
    return lab


def _hint(text: str, name: str = "DialogHint") -> QLabel:
    lab = QLabel(text)
    lab.setObjectName(name)
    lab.setWordWrap(True)
    return lab


class PasswordProtectDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Protect with Password")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Encrypt with a password"))
        root.addWidget(
            _hint("The protected copy is saved as a new file. Keep your password safe — it cannot be recovered.")
        )

        open_box = QGroupBox("Require a password to open the document")
        f1 = QFormLayout(open_box)
        self.user_pw = QLineEdit()
        self.user_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.user_pw.setPlaceholderText("Document open password")
        self.user_pw_confirm = QLineEdit()
        self.user_pw_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.user_pw_confirm.setPlaceholderText("Repeat password")
        f1.addRow("Password:", self.user_pw)
        f1.addRow("Confirm:", self.user_pw_confirm)
        root.addWidget(open_box)

        perm_box = QGroupBox("Restrict printing, copying and editing")
        perm_layout = QVBoxLayout(perm_box)
        perm_layout.setSpacing(6)
        f2 = QFormLayout()
        self.owner_pw = QLineEdit()
        self.owner_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.owner_pw.setPlaceholderText("Needed later to change these permissions")
        f2.addRow("Permissions password:", self.owner_pw)
        perm_layout.addLayout(f2)
        self.perm_print = QCheckBox("Allow printing")
        self.perm_print.setChecked(True)
        self.perm_print_hq = QCheckBox("Allow high-quality printing")
        self.perm_print_hq.setChecked(True)
        self.perm_print.toggled.connect(self.perm_print_hq.setEnabled)
        self.perm_copy = QCheckBox("Allow copying text and images")
        self.perm_copy.setChecked(True)
        self.perm_modify = QCheckBox("Allow changes to the document")
        self.perm_modify.setChecked(False)
        self.perm_assemble = QCheckBox("Allow inserting, rotating and deleting pages")
        self.perm_assemble.setChecked(False)
        self.perm_annotate = QCheckBox("Allow comments")
        self.perm_annotate.setChecked(True)
        self.perm_forms = QCheckBox("Allow filling in form fields")
        self.perm_forms.setChecked(True)
        for w in (
            self.perm_print,
            self.perm_print_hq,
            self.perm_copy,
            self.perm_modify,
            self.perm_assemble,
            self.perm_annotate,
            self.perm_forms,
        ):
            perm_layout.addWidget(w)
        self.perm_print_hq.setContentsMargins(22, 0, 0, 0)
        root.addWidget(perm_box)

        row = QFormLayout()
        self.algo = QComboBox()
        self.algo.addItem("AES-256 (recommended)", "AES-256")
        self.algo.addItem("AES-128 (compatible with older PDF readers)", "AES-128")
        row.addRow("Encryption:", self.algo)
        self.show_pw = QCheckBox("Show passwords")
        self.show_pw.toggled.connect(self._toggle_echo)
        row.addRow("", self.show_pw)
        root.addLayout(row)

        self._error = _hint("", "DialogError")
        self._error.hide()
        root.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText("Protect && Save As…")
        buttons.accepted.connect(self._validate_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        for w in (self.user_pw, self.user_pw_confirm, self.owner_pw):
            w.textChanged.connect(self._validate)
        self._validate()

    def _toggle_echo(self, on: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        for w in (self.user_pw, self.user_pw_confirm, self.owner_pw):
            w.setEchoMode(mode)

    def _problem(self) -> str:
        if not self.user_pw.text() and not self.owner_pw.text():
            return "Enter an open password, a permissions password, or both."
        if self.user_pw.text() != self.user_pw_confirm.text():
            return "The open passwords do not match."
        return ""

    def _validate(self) -> None:
        problem = self._problem()
        self._ok.setEnabled(not problem)
        mismatch = bool(self.user_pw_confirm.text()) and self.user_pw.text() != self.user_pw_confirm.text()
        self._error.setText("The open passwords do not match." if mismatch else "")
        self._error.setVisible(mismatch)

    def _validate_accept(self) -> None:
        if not self._problem():
            self.accept()

    def settings(self) -> EncryptionSettings:
        return EncryptionSettings(
            user_password=self.user_pw.text(),
            owner_password=self.owner_pw.text(),
            algorithm=self.algo.currentData(),
            permissions=PermissionFlags(
                print=self.perm_print.isChecked(),
                copy=self.perm_copy.isChecked(),
                modify=self.perm_modify.isChecked(),
                annotate=self.perm_annotate.isChecked(),
                fill_forms=self.perm_forms.isChecked(),
                assemble=self.perm_assemble.isChecked(),
                print_hq=self.perm_print.isChecked() and self.perm_print_hq.isChecked(),
            ),
        )


class RemoveProtectionDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Unlock PDF")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(_title("Unlock PDF"))
        layout.addWidget(
            _hint(
                "Saves an unlocked copy with no open password and no restrictions. "
                "Enter the document’s open or permissions password to confirm you may do this."
            )
        )
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Open or permissions password")
        layout.addWidget(self.password)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Unlock && Save As…")
        ok.setEnabled(False)
        self.password.textChanged.connect(lambda t: ok.setEnabled(bool(t)))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class InfoTextDialog(QDialog):
    def __init__(self, title: str, body: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 380)
        layout = QVBoxLayout(self)
        layout.addWidget(_title(title))
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(body)
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


# Handwriting faces shipped with Windows (first available ones are offered), plus a generic fallback.
SIGNATURE_FONTS = (
    "Segoe Script",
    "Ink Free",
    "Lucida Handwriting",
    "Segoe Print",
    "Brush Script MT",
    "Mistral",
    "Freestyle Script",
    "Bradley Hand ITC",
    "Kristen ITC",
)
SIGNATURE_INKS = (("Blue ink", "#0d1f73"), ("Black ink", "#111111"), ("Dark blue ink", "#0a2a55"))


def available_signature_fonts() -> list[str]:
    from PySide6.QtGui import QFontDatabase

    installed = {f.lower(): f for f in QFontDatabase.families()}
    found = [installed[f.lower()] for f in SIGNATURE_FONTS if f.lower() in installed]
    return found or ["Serif Italic"]


def render_signature_png(text: str, family: str, color: str, *, height_px: int = 240) -> bytes:
    """Render ``text`` in ``family`` onto a transparent PNG cropped tightly to the ink."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect
    from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter

    font = QFont(family)
    if family == "Serif Italic":
        font = QFont("Times New Roman")
        font.setStyleHint(QFont.StyleHint.Serif)
        font.setItalic(True)
    font.setStyleHint(QFont.StyleHint.Cursive, QFont.StyleStrategy.PreferAntialias)
    font.setPixelSize(int(height_px * 0.62))
    fm = QFontMetrics(font)
    pad = int(height_px * 0.15)
    w = max(1, fm.horizontalAdvance(text)) + 2 * pad + int(height_px * 0.3)
    img = QImage(w, height_px, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(QRect(pad, 0, w - 2 * pad, height_px), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text)
    painter.end()
    # Crop to the ink so the signature fills the box it is placed in
    left, top, right, bottom = w, height_px, -1, -1
    for y in range(0, height_px, 2):
        for x in range(0, w, 2):
            if img.pixelColor(x, y).alpha() > 8:
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
    if right > left and bottom > top:
        m = 6
        img = img.copy(QRect(max(0, left - m), max(0, top - m), min(w, right + m) - max(0, left - m), min(height_px, bottom + m) - max(0, top - m)))
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(data.data())


class TypedSignatureDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Type a Signature")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(_title("Type your signature"))
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Your full name")
        self.name.setClearButtonEnabled(True)
        form.addRow("Name:", self.name)
        self.style = QComboBox()
        self.style.addItems(available_signature_fonts())
        form.addRow("Style:", self.style)
        self.ink = QComboBox()
        for label, hexcol in SIGNATURE_INKS:
            self.ink.addItem(label, hexcol)
        form.addRow("Ink:", self.ink)
        layout.addLayout(form)
        self.preview = QLabel("")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(96)
        self.preview.setObjectName("SignaturePad")
        layout.addWidget(self.preview)
        layout.addWidget(
            _hint(
                "After you choose Place on Page, drag a box where the signature should go. "
                "This is a visual signature, like signing a printed page — not a certificate-based digital signature."
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText("Place on Page")
        self._ok.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name.textChanged.connect(self._update_preview)
        self.style.currentIndexChanged.connect(self._update_preview)
        self.ink.currentIndexChanged.connect(self._update_preview)
        self._update_preview()

    def ink_color(self) -> str:
        return str(self.ink.currentData())

    def _update_preview(self) -> None:
        text = self.name.text().strip()
        self._ok.setEnabled(bool(text))
        family = self.style.currentText()
        font = QFont(family)
        if family == "Serif Italic":
            font = QFont("Times New Roman")
            font.setItalic(True)
        font.setPointSize(26)
        self.preview.setFont(font)
        self.preview.setStyleSheet(f"color: {self.ink_color()};")
        self.preview.setText(text)

    def signature_png(self) -> bytes:
        return render_signature_png(self.name.text().strip(), self.style.currentText(), self.ink_color())


def confirm_signed_edit(parent, message: str | None) -> bool:
    if not message:
        return True
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Signed PDF")
    box.setText("This document is digitally signed.")
    box.setInformativeText(message + "\n\nContinue anyway?")
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    return box.exec() == QMessageBox.StandardButton.Yes
