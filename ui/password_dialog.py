"""Password prompt shown only when a PDF requires authentication."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class PasswordDialog(QDialog):
    """
    Protected PDF password entry.

    Credentials are never logged and are only returned via password() to the
    caller for a single authenticate() attempt — not persisted to Recent/session.
    """

    def __init__(self, parent=None, filename: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Protected PDF")
        self.setModal(True)
        self.setAccessibleName("Protected PDF password dialog")
        layout = QVBoxLayout(self)

        title = QLabel("Protected PDF")
        title.setObjectName("DialogTitle")
        font = title.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        body = QLabel("This document requires a password.")
        body.setWordWrap(True)
        layout.addWidget(body)
        if filename:
            name = QLabel(filename)
            name.setWordWrap(True)
            name.setObjectName("ContextHint")
            layout.addWidget(name)

        form = QFormLayout()
        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("Password")
        self._edit.setClearButtonEnabled(True)
        form.addRow("Password:", self._edit)
        layout.addLayout(form)

        self._show = QCheckBox("Show password")
        self._show.toggled.connect(self._toggle_echo)
        layout.addWidget(self._show)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setObjectName("DialogError")
        self._error.hide()
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
        # Map Open -> Accept
        open_btn = buttons.button(QDialogButtonBox.StandardButton.Open)
        if open_btn is not None:
            open_btn.setDefault(True)
            open_btn.setAutoDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._edit.setFocus()
        self._edit.returnPressed.connect(self.accept)

    def _toggle_echo(self, checked: bool) -> None:
        self._edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def password(self) -> str:
        return self._edit.text()

    def set_incorrect(self) -> None:
        """Keep dialog open after a failed authenticate attempt."""
        self._error.setText("Incorrect password. Please try again.")
        self._error.show()
        self._edit.selectAll()
        self._edit.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
