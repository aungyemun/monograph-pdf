"""macOS Finder / Dock / "Open With" file delivery.

macOS never passes these files on the command line: LaunchServices sends an Apple Event that Qt
turns into ``QEvent.FileOpen`` on the application object. A cold start delivers it before the main
window exists, so paths are queued until :meth:`FileOpenRouter.attach` is called.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer


class FileOpenRouter(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = None
        self._queued: list[str] = []
        self._flush = QTimer(self)
        self._flush.setSingleShot(True)
        self._flush.setInterval(0)  # one hand-over for a multi-file drop on the Dock icon
        self._flush.timeout.connect(self._deliver)

    def attach(self, window) -> None:
        self._window = window
        if self._queued:
            self._flush.start()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt override
        if event.type() == QEvent.Type.FileOpen:
            path = event.file()
            if path:
                self._queued.append(path)
                if self._window is not None:
                    self._flush.start()
            return True
        return False

    def _deliver(self) -> None:
        files, self._queued = self._queued, []
        if files and self._window is not None:
            self._window.handle_instance_request(files)


def install(app) -> FileOpenRouter:
    router = FileOpenRouter(app)
    app.installEventFilter(router)
    return router
