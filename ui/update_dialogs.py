"""Update user interface: checks in the background, the "update available" dialog and the
download / verify / prepare progress before handing over to the update helper."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from core.diagnostics import EventId, diagnostics
from core.updates import config as update_config
from core.updates import install_target, manager, staging
from core.updates.manager import CheckResult, UpdateError, UpdateStatus
from core.updates.state import UpdateState
from core.versioning import get_version

RELEASES_PAGE = "https://github.com/aungyemun/monograph-pdf/releases"


def fmt_size(n: int) -> str:
    return f"{n / 1024**2:.1f} MB" if n >= 1024**2 else f"{max(1, n // 1024)} KB"


class _CheckWorker(QThread):
    result = Signal(object)

    def __init__(self, cfg, channel: str, installed: str) -> None:
        super().__init__()
        self._cfg, self._channel, self._installed = cfg, channel, installed

    def run(self) -> None:
        state = UpdateState.load()
        try:
            res = manager.check(self._cfg, self._channel, self._installed, state)
        except Exception:  # noqa: BLE001 — never "up to date" on an unexpected error
            res = CheckResult(UpdateStatus.UNAVAILABLE, "Unable to check for updates (unexpected error).",
                              self._installed, checked_at=int(time.time()))
        try:
            state.save()
        except OSError:
            pass
        self.result.emit(res)


class _DownloadWorker(QThread):
    progress = Signal(str, int, int)
    done = Signal(object)
    failed = Signal(object)

    def __init__(self, cfg, release, target) -> None:
        super().__init__()
        self._cfg, self._release, self._target = cfg, release, target
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            sd = manager.download_and_verify(self._cfg, self._release, self._target, self.cancel,
                                             lambda stage, got, total: self.progress.emit(stage, got, total))
            self.done.emit(sd)
        except UpdateError as exc:
            self.failed.emit(exc)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(UpdateError(f"The update failed unexpectedly ({type(exc).__name__}).", "unexpected"))


class UpdateAvailableDialog(QDialog):
    """Installed / available version, release date, notes, download size; Update Now · Remind Me Later."""

    def __init__(self, result: CheckResult, *, install_block: str = "", parent=None) -> None:
        super().__init__(parent)
        rel = result.release
        self.setWindowTitle("Monograph PDF Update Available")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        head = QLabel("MONOGRAPH PDF UPDATE AVAILABLE")
        head.setObjectName("UpdateHeader")
        f = head.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.15)
        head.setFont(f)
        lay.addWidget(head)
        form = QFormLayout()
        form.addRow("Installed version:", QLabel(result.installed))
        form.addRow("Available version:", QLabel(str(rel.version) + (" (prerelease)" if rel.version.is_prerelease else "")))
        form.addRow("Release date:", QLabel(rel.release_date))
        form.addRow("Download size:", QLabel(fmt_size(rel.artifact.size)))
        lay.addLayout(form)
        lay.addWidget(QLabel("Release notes:"))
        notes = QTextBrowser()
        notes.setPlainText(rel.release_notes or "No release notes were published with this update.")
        notes.setOpenLinks(False)
        notes.setMinimumHeight(160)
        lay.addWidget(notes)
        if rel.release_page:
            link = QLabel(f'<a href="{rel.release_page}">Open the release page</a>')
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            link.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
            lay.addWidget(link)
        hint = QLabel(install_block or "Update Now downloads this version, verifies it, closes Monograph PDF "
                                       "(you can save open changes first), installs it in the same place and "
                                       "restarts Monograph PDF. Your settings and documents are kept.")
        hint.setWordWrap(True)
        hint.setObjectName("DialogHint")
        lay.addWidget(hint)
        box = QDialogButtonBox()
        self.update_now = box.addButton("Update Now", QDialogButtonBox.ButtonRole.AcceptRole)
        self.later = box.addButton("Remind Me Later", QDialogButtonBox.ButtonRole.RejectRole)
        self.update_now.setEnabled(not install_block)
        self.update_now.clicked.connect(self.accept)
        self.later.clicked.connect(self.reject)
        lay.addWidget(box)


class UpdateProgressDialog(QDialog):
    """Downloading (bytes) · Verifying · Preparing — real progress, cancellable until hand-off."""

    def __init__(self, version: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Updating to Monograph PDF {version}")
        self.setModal(True)
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        self.stage = QLabel("Downloading…")
        lay.addWidget(self.stage)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.detail = QLabel("")
        self.detail.setObjectName("DialogHint")
        lay.addWidget(self.detail)
        self.cancel = QPushButton("Cancel")
        lay.addWidget(self.cancel, alignment=Qt.AlignmentFlag.AlignRight)

    def show_stage(self, stage: str, got: int, total: int) -> None:
        if stage == "downloading":
            self.stage.setText("Downloading…")
            self.bar.setRange(0, max(1, total))
            self.bar.setValue(min(got, total))
            self.detail.setText(f"{fmt_size(got)} of {fmt_size(total)}")
        else:
            self.stage.setText({"verifying": "Verifying…", "preparing": "Preparing…",
                                "installing": "Installing…"}.get(stage, stage))
            self.bar.setRange(0, 0)
            self.detail.setText("")

    def reject(self) -> None:  # Esc / close button = Cancel while it is allowed
        if self.cancel.isEnabled():
            self.cancel.click()

    def close_now(self, ok: bool) -> None:
        self.done(1 if ok else 0)


class UpdateController(QObject):
    """Owns update checks and the Update Now workflow for the main window."""

    status_changed = Signal(object)  # CheckResult

    def __init__(self, window) -> None:
        super().__init__(window)
        self._window = window
        self._config = update_config.load_or_disabled()
        self._worker: _CheckWorker | None = None
        self._download: _DownloadWorker | None = None
        self.last: CheckResult | None = None
        self._dialog: UpdateAvailableDialog | None = None

    # ------------------------------------------------------------------ status

    @property
    def configured(self) -> bool:
        return self._config.usable

    @property
    def config(self):
        return self._config

    def status_text(self) -> str:
        if not self._config.usable:
            return "Not configured for this build"
        if self.last is not None:
            return self.last.status.label
        st = UpdateState.load()
        return UpdateStatus(st.last_status).label if st.last_status in {s.value for s in UpdateStatus} else "Not checked yet"

    # ------------------------------------------------------------------ checks

    def check(self, *, manual: bool, channel: str | None = None) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        prefs = self._window._prefs
        diagnostics.record(EventId.UPDATE_CHECK_STARTED)
        self.status_changed.emit(CheckResult(UpdateStatus.CHECKING, "Checking for updates…", get_version()))
        self._worker = _CheckWorker(self._config, channel or prefs.update_channel, get_version())
        self._worker.result.connect(lambda res, manual=manual: self._checked(res, manual))
        self._worker.start()

    def maybe_auto_check(self) -> None:
        prefs = self._window._prefs
        if prefs.update_auto_check and self._config.usable and UpdateState.load().due(prefs.update_interval_hours):
            self.check(manual=False)

    def _checked(self, res: CheckResult, manual: bool) -> None:
        self.last = res
        self.status_changed.emit(res)
        if res.status in (UpdateStatus.UNAVAILABLE, UpdateStatus.VERIFICATION_FAILED):
            diagnostics.record(EventId.UPDATE_CHECK_FAILED)
        if res.status == UpdateStatus.AVAILABLE:
            st = UpdateState.load()
            if not manual and st.remind_version == str(res.release.version) and time.time() < st.remind_after:
                return
            self.show_available(res)
            return
        if not manual:
            return  # automatic checks stay quiet unless there is an update
        box = QMessageBox.information if res.status in (UpdateStatus.UP_TO_DATE, UpdateStatus.NOT_CONFIGURED) \
            else QMessageBox.warning
        box(self._window, "Check for Updates", f"{res.status.label}\n\n{res.message}")

    def show_available(self, res: CheckResult) -> None:
        block = self._install_block(res)
        dlg = UpdateAvailableDialog(res, install_block=block, parent=self._window)
        self._dialog = dlg
        dlg.accepted.connect(lambda: self.start_update(res))
        dlg.rejected.connect(lambda: self._remind_later(res))
        dlg.setModal(False)
        dlg.show()

    def _remind_later(self, res: CheckResult) -> None:
        st = UpdateState.load()
        st.remind_version = str(res.release.version)
        st.remind_after = int(time.time()) + max(1, self._window._prefs.update_interval_hours) * 3600
        try:
            st.save()
        except OSError:
            pass

    @staticmethod
    def _install_block(res: CheckResult) -> str:
        target = install_target.detect()
        if not target.ok:
            return target.reason
        return manager.install_permitted(res.release, target.version or res.installed)

    # ------------------------------------------------------------------ Update Now

    def start_update(self, res: CheckResult) -> None:
        """The user's Update Now: download, verify, resolve unsaved changes, hand off, exit."""
        w = self._window
        target = install_target.detect()
        block = target.reason if not target.ok else manager.install_permitted(res.release, target.version or res.installed)
        if block:
            QMessageBox.warning(w, "Update", block)
            return
        lock = staging.UpdateLock()
        if not lock.acquire():
            QMessageBox.information(w, "Update", "Another Monograph PDF update is already in progress.")
            return
        diagnostics.record(EventId.UPDATE_DOWNLOAD_STARTED)
        dlg = UpdateProgressDialog(str(res.release.version), w)
        worker = _DownloadWorker(self._config, res.release, target)
        self._download = worker
        outcome: dict = {}
        worker.progress.connect(dlg.show_stage)
        worker.done.connect(lambda sd: (outcome.__setitem__("sd", sd), dlg.close_now(True)))
        worker.failed.connect(lambda exc: (outcome.__setitem__("error", exc), dlg.close_now(False)))
        dlg.cancel.clicked.connect(lambda: (worker.cancel.set(), dlg.cancel.setEnabled(False),
                                            dlg.stage.setText("Cancelling…")))
        worker.start()
        dlg.exec()
        worker.wait()
        if "error" in outcome:
            lock.release()
            err = outcome["error"]
            if err.code != "cancelled":
                diagnostics.record(EventId.UPDATE_DOWNLOAD_FAILED)
                QMessageBox.warning(w, "Update not installed", f"{err}\n\nMonograph PDF {get_version()} is unchanged.")
            return
        sd = outcome.get("sd")
        if sd is None:
            lock.release()
            return
        # Save or discard open changes before the application closes (Cancel stops the update)
        if not w._confirm_unsaved("updating"):
            staging.remove_staging(sd.path)
            lock.release()
            w.statusBar().showMessage("Update cancelled; the downloaded installer was removed.", 6000)
            return
        w.statusBar().showMessage("Preparing… Monograph PDF will close, install the update and restart.")
        try:
            diagnostics.record(EventId.UPDATE_INSTALL_STARTED)
            manager.hand_off(sd, res.release, target, lock)
        except UpdateError as exc:
            diagnostics.record(EventId.UPDATE_INSTALL_FAILED)
            staging.remove_staging(sd.path)
            lock.release()
            QMessageBox.warning(w, "Update not installed", str(exc))
            return
        w.close_for_update()
