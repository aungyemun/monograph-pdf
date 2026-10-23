"""Settings dialog (File ▸ Settings…). Currently one page: Updates."""

from __future__ import annotations

import time

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.updates.state import UpdateState

INTERVALS = [(24, "Every day (24 hours)"), (72, "Every 3 days"), (168, "Every week")]


def _when(stamp: int) -> str:
    if not stamp:
        return "Never"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))


class UpdatesPage(QWidget):
    def __init__(self, prefs, controller, parent=None) -> None:
        super().__init__(parent)
        self._prefs, self._controller = prefs, controller
        lay = QVBoxLayout(self)
        if not controller.configured:
            note = QLabel(controller.config.disabled_reason or "Updates are not configured for this build.")
            note.setWordWrap(True)
            note.setObjectName("DialogHint")
            lay.addWidget(note)
        self.auto = QCheckBox("Automatically check for updates")
        self.auto.setToolTip("Only checks. Nothing is downloaded or installed until you click Update Now; "
                             "a check that cannot reach GitHub (for example offline) fails quietly and is tried again after the check interval.")
        self.auto.setChecked(bool(prefs.update_auto_check))
        lay.addWidget(self.auto)
        form = QFormLayout()
        self.interval = QComboBox()
        for hours, label in INTERVALS:
            self.interval.addItem(label, hours)
        idx = self.interval.findData(int(prefs.update_interval_hours))
        self.interval.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("Check interval:", self.interval)
        lay.addLayout(form)
        chan = QGroupBox("Release channel")
        cl = QVBoxLayout(chan)
        self.stable = QRadioButton("Stable releases (recommended)")
        self.pre = QRadioButton("Prereleases as well (test versions; may contain unfinished features)")
        group = QButtonGroup(self)
        group.addButton(self.stable)
        group.addButton(self.pre)
        (self.pre if prefs.update_channel == "prerelease" else self.stable).setChecked(True)
        cl.addWidget(self.stable)
        cl.addWidget(self.pre)
        lay.addWidget(chan)
        st = UpdateState.load()
        info = QFormLayout()
        self.last = QLabel(_when(st.last_success))
        self.status = QLabel(controller.status_text())
        info.addRow("Last successful check:", self.last)
        info.addRow("Update status:", self.status)
        lay.addLayout(info)
        row = QHBoxLayout()
        self.check_now = QPushButton("Check Now")
        self.check_now.setEnabled(controller.configured)
        self.check_now.clicked.connect(self._check_now)
        row.addWidget(self.check_now)
        row.addStretch(1)
        lay.addLayout(row)
        privacy = QLabel("Update checks contact GitHub Releases only (no account, no document data). "
                         "Downloads are verified with Monograph PDF's signing key before anything is installed.")
        privacy.setWordWrap(True)
        privacy.setObjectName("DialogHint")
        lay.addWidget(privacy)
        lay.addStretch(1)
        controller.status_changed.connect(self._status_changed)
        for w in (self.auto, self.interval, self.stable, self.pre):
            w.setEnabled(controller.configured)

    def _status_changed(self, res) -> None:
        from ui.update_dialogs import status_line

        self.status.setText(status_line(res.status))
        self.last.setText(_when(UpdateState.load().last_success))

    def _check_now(self) -> None:
        self._controller.check(manual=True, channel="prerelease" if self.pre.isChecked() else "stable")

    def apply(self) -> None:
        self._prefs.update_auto_check = self.auto.isChecked()
        self._prefs.update_interval_hours = int(self.interval.currentData())
        self._prefs.update_channel = "prerelease" if self.pre.isChecked() else "stable"


class SettingsDialog(QDialog):
    def __init__(self, prefs, controller, parent=None) -> None:
        super().__init__(parent)
        self._prefs = prefs
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.updates = UpdatesPage(prefs, controller, self)
        self.tabs.addTab(self.updates, "Updates")
        lay.addWidget(self.tabs)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def accept(self) -> None:
        self.updates.apply()
        try:
            self._prefs.save()
        except OSError:
            pass
        super().accept()
