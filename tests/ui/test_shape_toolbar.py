"""The shape toolbar: line thickness, line style, opacity and (lines / arrows) the end styles."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from tests.ui.test_text_box_word_formats import win  # noqa: E402,F401


def _bar_widget(win, name):
    return win._context_bar.findChild(object, name)  # noqa: SLF001


def test_thickness_style_opacity_and_heads_from_the_toolbar(win, qtbot):  # noqa: F811
    from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox

    from core.editing.geometry import Rect

    s = win._edit.create_shape(0, Rect(80, 80, 120, 40), "arrow", x0=80, y0=120, x1=200, y1=80)  # noqa: SLF001
    win._edit.select([s.object_id])  # noqa: SLF001
    win._on_edit_changed()  # noqa: SLF001
    bar = win._context_bar  # noqa: SLF001
    qtbot.waitUntil(lambda: bar.findChild(QDoubleSpinBox, "ShapeLineWidth") is not None, timeout=3000)
    bar.findChild(QDoubleSpinBox, "ShapeLineWidth").setValue(4.0)
    assert win._edit.shapes[s.object_id].stroke_width == 4.0  # noqa: SLF001
    qtbot.waitUntil(lambda: bar.findChild(QComboBox, "ShapeLineStyle") is not None, timeout=3000)
    style = bar.findChild(QComboBox, "ShapeLineStyle")
    style.activated.emit(style.findData("dotted"))
    assert getattr(win._edit.shapes[s.object_id].stroke_style, "value", "") == "dotted"  # noqa: SLF001
    qtbot.waitUntil(lambda: bar.findChild(QSpinBox, "ShapeOpacity") is not None, timeout=3000)
    bar.findChild(QSpinBox, "ShapeOpacity").setValue(50)
    assert win._edit.shapes[s.object_id].opacity == pytest.approx(0.5)  # noqa: SLF001
    qtbot.waitUntil(lambda: bar.findChild(QComboBox, "ShapeHeadStart") is not None, timeout=3000)
    start = bar.findChild(QComboBox, "ShapeHeadStart")
    start.activated.emit(start.findData("circle"))
    assert win._edit.shapes[s.object_id].heads()[0] == "circle"  # noqa: SLF001
    win._edit.commands.undo()  # noqa: SLF001
    assert win._edit.shapes[s.object_id].heads()[0] == "none"  # noqa: SLF001
