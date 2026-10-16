"""Integration/UI smoke for editing model wired into the main window."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


@pytest.fixture(scope="module", autouse=True)
def _ensure_samples():
    from tests.fixtures.make_samples import main

    main()


def test_main_window_edit_create_undo(qtbot, tmp_path: Path):
    pytest.importorskip("PySide6")
    from core.editing.geometry import Rect
    from ui.main_window import MainWindow, create_application

    create_application(["monograph-pdf-edit-test"])
    src = tmp_path / "ui_edit.pdf"
    src.write_bytes((SAMPLES / "sample_text.pdf").read_bytes())
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.open_path(src)
    assert window._edit is not None  # noqa: SLF001
    window._edit.create_text_box(0, Rect(60, 60, 140, 36), text="UI-Box")  # noqa: SLF001
    assert window._edit.dirty  # noqa: SLF001
    assert "*" in window.windowTitle()
    window._edit.undo()  # noqa: SLF001
    assert not any(o.text == "UI-Box" for o in window._edit.all_objects())  # noqa: SLF001
    window.close_document(save_session=False)
    window.close()
