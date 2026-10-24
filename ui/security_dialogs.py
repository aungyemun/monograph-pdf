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


def _strength_label() -> QLabel:
    lab = QLabel("")
    lab.setObjectName("PasswordStrength")
    lab.setWordWrap(True)
    lab.hide()
    return lab


def _show_strength(label: QLabel, password: str) -> None:
    from core.security.password_strength import rate_password

    s = rate_password(password)
    if not s.label:
        label.hide()
        return
    try:
        from ui.theme import current_palette

        pal = current_palette()
        color = (pal.danger, pal.danger, pal.warning, pal.success, pal.success)[s.score]
    except Exception:  # noqa: BLE001
        color = "#5f6b7a"
    bars = "\u25a0" * (s.score + 1) + "\u25a1" * (4 - s.score)
    label.setText(f"<span style='color:{color}'>{bars}&nbsp; {s.label}</span>"
                  + (f"<br><span>{s.hint}</span>" if s.hint else ""))
    label.setAccessibleDescription(f"Password strength: {s.label}. {s.hint}".strip())
    label.show()


class PasswordProtectDialog(QDialog):
    def __init__(self, parent=None, *, watermark_pages: int = 0) -> None:
        super().__init__(parent)
        self._watermark_pages = int(watermark_pages)
        self.setWindowTitle("Protect with Password")
        self.setMinimumWidth(640)
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
        self.user_strength = _strength_label()
        f1.addRow("", self.user_strength)
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
        self.owner_strength = _strength_label()
        f2.addRow("", self.owner_strength)
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
        # two columns: the dialog stays short enough for a 768-pixel-high screen
        from PySide6.QtWidgets import QGridLayout

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)
        left = (self.perm_print, self.perm_print_hq, self.perm_copy, self.perm_forms)
        right = (self.perm_annotate, self.perm_modify, self.perm_assemble)
        for r, w in enumerate(left):
            grid.addWidget(w, r, 0)
        for r, w in enumerate(right):
            grid.addWidget(w, r, 1)
        self.perm_assemble.setText("Allow inserting, rotating, deleting pages")
        perm_layout.addLayout(grid)
        self.perm_print_hq.setContentsMargins(22, 0, 0, 0)
        root.addWidget(perm_box)

        info_box = QGroupBox("Document information and watermark")
        info_layout = QVBoxLayout(info_box)
        info_layout.setSpacing(6)
        self.meta_status = _hint("")
        info_layout.addWidget(self.meta_status)
        self.strip_meta = QCheckBox("Remove the document information (title, author, keywords …)")
        self.strip_meta.setToolTip("The protected copy carries no document information or XMP metadata at all")
        info_layout.addWidget(self.strip_meta)
        self.lock_wm = QCheckBox("Lock the watermark")
        if self._watermark_pages:
            self.lock_wm.setText(f"Lock the watermark ({self._watermark_pages} page"
                                 f"{'s' if self._watermark_pages != 1 else ''})")
            self.lock_wm.setChecked(True)
            self.lock_wm.setToolTip("The watermark becomes part of the pages: it can no longer be hidden as a "
                                    "layer or removed with Remove Watermark. Changes stay disallowed.")
        else:
            self.lock_wm.setEnabled(False)
            self.lock_wm.setToolTip("This document has no watermark added by Monograph PDF")
        self.lock_wm.toggled.connect(self._watermark_toggled)
        info_layout.addWidget(self.lock_wm)
        root.addWidget(info_box)

        row = QFormLayout()
        self.algo = QComboBox()
        self.algo.addItem("AES-256 — strongest, recommended (PDF 2.0; Acrobat X and later)", "AES-256")
        self.algo.addItem("AES-128 — only for very old PDF readers", "AES-128")
        self.algo.setToolTip("AES-256 with SHA-256 based password checks is the strongest encryption PDF "
                             "defines; every current PDF reader opens it.")
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
        self.user_pw.textChanged.connect(lambda _t: self._update_meta_status())
        self.strip_meta.toggled.connect(lambda _on: self._update_meta_status())
        self._update_meta_status()
        self._watermark_toggled(self.lock_wm.isChecked())
        self.user_pw.textChanged.connect(lambda t: _show_strength(self.user_strength, t))
        self.owner_pw.textChanged.connect(lambda t: _show_strength(self.owner_strength, t))
        self._validate()

    def _update_meta_status(self) -> None:
        if self.strip_meta.isChecked():
            text = "The protected copy will contain no document information."
        elif self.user_pw.text():
            text = ("Title, author and other document information are encrypted together with the pages "
                    "(only the open password reveals them).")
        else:
            text = ("Without an open password anyone can open the file and read its title, author and other "
                    "document information. Set an open password or remove the information.")
        self.meta_status.setText(text)

    def _watermark_toggled(self, on: bool) -> None:
        if on:
            self.perm_modify.setChecked(False)  # a locked watermark is meant to stay
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
        same = bool(self.user_pw.text()) and self.user_pw.text() == self.owner_pw.text()
        if mismatch:
            text = "The open passwords do not match."
        elif same:
            text = ("The permissions password is the same as the open password, so anyone who can open "
                    "the file can also lift the restrictions. Use a different one.")
        elif self.lock_wm.isChecked() and not self.owner_pw.text():
            text = ("To keep the watermark, also set a permissions password: without one, anyone who can "
                    "open the file may change it.")
        else:
            text = ""
        self._error.setText(text)
        self._error.setVisible(bool(text))

    def _validate_accept(self) -> None:
        if not self._problem():
            self.accept()

    def settings(self) -> EncryptionSettings:
        return EncryptionSettings(
            user_password=self.user_pw.text(),
            owner_password=self.owner_pw.text(),
            algorithm=self.algo.currentData(),
            strip_metadata=self.strip_meta.isChecked(),
            lock_watermarks=self.lock_wm.isEnabled() and self.lock_wm.isChecked(),
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


class RemoveHiddenInfoDialog(QDialog):
    """Lists what the document carries besides its visible pages; the user picks what to remove."""

    ROWS = (
        ("metadata", "Document properties and XMP metadata", "Title, author, creator tool, dates and XML metadata"),
        ("attachments", "Attached files", "Embedded files and file-attachment comments"),
        ("javascript", "Scripts and automatic actions", "JavaScript and actions that run when the file is opened"),
        ("thumbnails", "Embedded page thumbnails", "Small preview images stored inside the file"),
        ("private_data", "Private application data", "Data other programs saved for their own use"),
        ("comments", "Comments and markup", "Notes, highlights, shapes and stamps"),
        ("form_fields", "Form fields", "Fields and the values typed into them"),
        ("links", "Links", "Web links and jumps to other pages"),
        ("bookmarks", "Bookmarks", "The document outline"),
        ("hidden_text", "Invisible text", "Text that is present but not shown — usually recognised (OCR) text, "
                                          "which makes scanned pages searchable"),
    )

    def __init__(self, info, parent=None) -> None:
        super().__init__(parent)
        from core.security.sanitize import SanitizeOptions

        self.setWindowTitle("Remove Hidden Information")
        self.setMinimumWidth(520)
        defaults = SanitizeOptions()
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.addWidget(_title("Remove hidden information"))
        root.addWidget(_hint(
            "Choose what to remove. The result is saved as a new PDF; this document is not changed."
        ))
        box = QGroupBox("Found in this document")
        lay = QVBoxLayout(box)
        lay.setSpacing(4)
        self._checks: dict[str, QCheckBox] = {}
        found_any = False
        for key, label, tip in self.ROWS:
            if key == "metadata":
                n = int(info.metadata_fields) + (1 if info.xmp_metadata else 0)
            elif key == "hidden_text":
                n = int(info.hidden_text_pages)
            else:
                n = int(getattr(info, key))
            suffix = {"hidden_text": "page", "metadata": "item"}.get(key, "")
            count = "none" if not n else (f"{n} {suffix}{'s' if n != 1 else ''}" if suffix else str(n))
            cb = QCheckBox(f"{label}  ({count})")
            cb.setObjectName(f"Hidden_{key}")
            cb.setToolTip(tip)
            cb.setEnabled(n > 0)
            cb.setChecked(n > 0 and bool(getattr(defaults, key)))
            found_any |= n > 0
            lay.addWidget(cb)
            self._checks[key] = cb
        root.addWidget(box)
        if info.redaction_marks:
            root.addWidget(_hint(
                f"{info.redaction_marks} redaction mark(s) are waiting to be applied. They are not applied here — "
                "use Protect ▸ Apply Redactions to remove the marked content.", "DialogError"))
        if not found_any:
            root.addWidget(_hint("Nothing hidden was found. You can still save a cleaned copy."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setText("Remove && Save As…")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def options(self):
        from core.security.sanitize import SanitizeOptions

        return SanitizeOptions(**{k: cb.isEnabled() and cb.isChecked() for k, cb in self._checks.items()})


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
SIGNATURE_INKS = (("Blue ink", "#0d1f73"), ("Black ink", "#111111"), ("Dark blue ink", "#0a2a55"),
                  ("Navy ink", "#1f3a5f"), ("Charcoal ink", "#333333"), ("Dark green ink", "#14532d"),
                  ("Burgundy ink", "#7f1d1d"))


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

    def set_values(self, text: str, family: str = "", color: str = "") -> None:
        """Open on a signature placed earlier (to change its text, style or ink)."""
        self.setWindowTitle("Edit Signature")
        self._ok.setText("Update Signature")
        self.name.setText(text)
        if family:
            i = self.style.findText(family)
            if i < 0:  # a style no longer installed: keep it selectable
                self.style.addItem(family)
                i = self.style.count() - 1
            self.style.setCurrentIndex(i)
        if color:
            i = self.ink.findData(color.lower())
            if i < 0:
                self.ink.addItem(f"Ink {color.upper()}", color.lower())
                i = self.ink.count() - 1
            self.ink.setCurrentIndex(i)
        self._update_preview()

    def spec(self) -> dict:
        """What the signature is made of — stored with it, so it can be edited after placing."""
        return {"kind": "typed", "text": self.name.text().strip(), "family": self.style.currentText(),
                "color": self.ink_color()}

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


class PermissionsPasswordDialog(QDialog):
    """Asks for the permissions (owner) password when the open PDF does not allow an action."""

    def __init__(self, parent, *, action: str, restriction: str, filename: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Permissions Password Required")
        self.setModal(True)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        title = QLabel(f"{action} needs the permissions password")
        title.setObjectName("DialogTitle")
        f = title.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 1.5)
        title.setFont(f)
        title.setWordWrap(True)
        lay.addWidget(title)
        body = QLabel(
            f"The author of {filename or 'this PDF'} protected it against {restriction}. "
            "Enter the permissions password (also called the owner password) to continue. "
            "The open password is not enough. The password is checked on this computer only and is "
            "not stored."
        )
        body.setWordWrap(True)
        lay.addWidget(body)
        form = QFormLayout()
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText("Permissions password")
        self.edit.setClearButtonEnabled(True)
        self.edit.setAccessibleName("Permissions password")
        form.addRow("Password:", self.edit)
        lay.addLayout(form)
        show = QCheckBox("Show password")
        show.toggled.connect(lambda on: self.edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        lay.addWidget(show)
        self.error = QLabel("")
        self.error.setObjectName("DialogError")
        self.error.setWordWrap(True)
        self.error.hide()
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Unlock")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.edit.setFocus()

    def password(self) -> str:
        return self.edit.text()

    def show_error(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()
        self.edit.selectAll()
        self.edit.setFocus()


def ask_permissions_password(parent, document, permission: str, action: str) -> bool:
    """True when ``document`` allows ``permission`` or the permissions password was entered now."""
    from core.security.protection import PERMISSION_LABELS, allowed, unlock_with_owner_password

    if document is None or allowed(document, permission):
        return True
    dlg = PermissionsPasswordDialog(parent, action=action, restriction=PERMISSION_LABELS.get(permission, permission),
                                    filename=getattr(document, "name", ""))
    while dlg.exec() == QDialog.DialogCode.Accepted:
        if unlock_with_owner_password(document, dlg.password()):
            return True
        dlg.show_error("That is not the permissions password of this PDF.")
    return False


def confirm_save_signed(parent, count: int) -> bool:
    """Saving changes to a digitally signed PDF makes its signatures invalid: confirm first."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Signed PDF")
    box.setText(f"This PDF is digitally signed ({count} signature{'s' if count != 1 else ''}).")
    box.setInformativeText(
        "Saving your changes rewrites the file, and the existing digital signatures will no longer be "
        "valid. To keep the signed original, save your changes under a new name (File ▸ Save As) and "
        "keep the original file.\n\nSave the changes?"
    )
    box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    return box.exec() == QMessageBox.StandardButton.Save
