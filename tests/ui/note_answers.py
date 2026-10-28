"""Answer the sticky-note text question the way a person would, on every Qt platform.

Offscreen the app asks with QInputDialog.getMultiLineText; on a real display (live runs, macOS,
Windows) it opens the full NoteDialog (text, icon, colour). Tests patch both with the same answer.
"""

from __future__ import annotations


def answer_note_text(monkeypatch, text: str, asked: list | None = None) -> None:
    from PySide6.QtWidgets import QDialog, QInputDialog

    from ui.note_dialog import NoteDialog

    def input_dialog(parent, title, label, current="", *a, **k):
        if asked is not None:
            asked.append(current)
        return (text, True)

    def note_dialog_exec(dlg):
        if asked is not None:
            asked.append(dlg.note_text())
        dlg.text.setPlainText(text)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QInputDialog, "getMultiLineText", staticmethod(input_dialog))
    monkeypatch.setattr(NoteDialog, "exec", note_dialog_exec)
