"""Colour picker: values stay in step, hex input, swatches, recent colours, contrast, opacity."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MONOGRAPH_PDF_HEADLESS", "1")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402


@pytest.fixture
def prefs_dir(tmp_path, monkeypatch):
    from core import user_prefs

    monkeypatch.setattr(user_prefs, "user_data_dir", lambda: tmp_path / "appdata")
    return tmp_path


def test_parse_color_forms():
    from ui.color_picker import parse_color

    assert parse_color("#1D4ED8").name() == "#1d4ed8"
    assert parse_color("1d4ed8").name() == "#1d4ed8"
    assert parse_color("#abc").name() == "#aabbcc"
    assert parse_color("navy").name() == "#000080"
    assert not parse_color("nonsense").isValid()
    assert not parse_color("").isValid()


def test_contrast_ratio_matches_wcag():
    from ui.color_picker import contrast_ratio

    assert contrast_ratio(QColor("#000000"), QColor("#ffffff")) == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio(QColor("#767676"), QColor("#ffffff")) == pytest.approx(4.54, abs=0.02)


def test_dialog_fields_stay_in_step(qtbot, prefs_dir):
    from ui.color_picker import ColorPickerDialog

    dlg = ColorPickerDialog(None, initial="#1d4ed8", title="Text color")
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.hex_edit.text() == "#1d4ed8"
    assert (dlg.spins["r"].value(), dlg.spins["g"].value(), dlg.spins["b"].value()) == (0x1D, 0x4E, 0xD8)
    # typing a hex value updates RGB and the preview
    dlg.hex_edit.setText("ff8800")
    dlg.hex_edit.editingFinished.emit()
    assert dlg.color().name() == "#ff8800"
    assert dlg.spins["g"].value() == 0x88
    assert dlg.preview.new.name() == "#ff8800"
    assert dlg.preview.old.name() == "#1d4ed8"  # the colour before stays visible
    # changing a channel updates hex
    dlg.spins["b"].setValue(0x44)
    assert dlg.hex_edit.text() == "#ff8844"
    # an unreadable entry falls back to the current colour
    dlg.hex_edit.setText("zzz")
    dlg.hex_edit.editingFinished.emit()
    assert dlg.hex_edit.text() == "#ff8844"
    # contrast hint for text colours
    assert dlg.contrast.isVisibleTo(dlg)
    assert "Contrast on white paper" in dlg.contrast.text()


def test_dragging_the_field_and_hue_strip(qtbot, prefs_dir):
    from ui.color_picker import ColorPickerDialog

    dlg = ColorPickerDialog(None, initial="#ff0000", title="Shape color")
    qtbot.addWidget(dlg)
    dlg.resize(700, 520)
    dlg.show()
    qtbot.waitExposed(dlg)
    assert not dlg.contrast.isVisibleTo(dlg)
    f = dlg.field
    qtbot.mouseClick(f, Qt.MouseButton.LeftButton, pos=QPoint(f.width() - 1, 0))
    assert dlg.color().name() == "#ff0000"  # top right = full saturation and brightness
    qtbot.mouseClick(f, Qt.MouseButton.LeftButton, pos=QPoint(0, 1))  # (0, 0) means "centre" to QTest
    assert dlg.color().saturation() == 0 and dlg.color().value() >= 253
    qtbot.mouseClick(f, Qt.MouseButton.LeftButton, pos=QPoint(f.width() // 2, f.height() - 1))
    assert dlg.color().name() == "#000000"
    qtbot.mouseClick(f, Qt.MouseButton.LeftButton, pos=QPoint(f.width() - 1, 0))
    h = dlg.hue
    pad = dlg.field.PAD
    qtbot.mouseClick(h, Qt.MouseButton.LeftButton, pos=QPoint(h.width() // 2, int(pad + (h.height() - 2 * pad) / 3)))
    c = dlg.color()
    assert c.hsvHue() in range(115, 125)  # one third down the strip = green
    # keyboard: arrow keys move the marker
    f.setFocus()
    qtbot.keyClick(f, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert dlg.color().value() < 255


def test_swatch_double_click_accepts_and_is_remembered(qtbot, prefs_dir):
    from core.user_prefs import UserPreferences
    from ui.color_picker import STANDARD_COLORS, ColorPickerDialog

    dlg = ColorPickerDialog(None, initial="#000000", title="Color")
    qtbot.addWidget(dlg)
    dlg.show()
    blue = next(s for s in dlg._swatches if s.value == "#1D4ED8")  # noqa: SLF001
    blue.click()
    assert dlg.color().name() == "#1d4ed8" and blue.selected
    qtbot.mouseDClick(blue, Qt.MouseButton.LeftButton)
    assert dlg.result() == dlg.DialogCode.Accepted
    assert UserPreferences.load().recent_colors[0] == "#1d4ed8"
    # the next dialog shows it under Recent colors
    dlg2 = ColorPickerDialog(None, initial="#000000", title="Color")
    qtbot.addWidget(dlg2)
    recent = [s.value for s in dlg2._swatches[len(STANDARD_COLORS):]]  # noqa: SLF001
    assert recent[:1] == ["#1d4ed8"]


def test_opacity_only_when_allowed(qtbot, prefs_dir):
    from ui.color_picker import ColorPickerDialog

    plain = ColorPickerDialog(None, initial="#801d4ed8", title="Color")
    qtbot.addWidget(plain)
    assert plain.opacity is None and plain.color().alpha() == 255
    dlg = ColorPickerDialog(None, initial="#801d4ed8", title="Color", allow_alpha=True)
    qtbot.addWidget(dlg)
    assert dlg.opacity.value() == 50
    dlg.opacity.setValue(25)
    assert dlg.color().alpha() == 64
    assert dlg.selected_name() == "#401d4ed8"


def test_get_color_returns_invalid_on_cancel(qtbot, prefs_dir, monkeypatch):
    import ui.color_picker as cp

    monkeypatch.setattr(cp.ColorPickerDialog, "exec", lambda self: cp.QDialog.DialogCode.Rejected)
    assert not cp.get_color("#123456", None, "Color").isValid()
    monkeypatch.setattr(cp.ColorPickerDialog, "exec", lambda self: cp.QDialog.DialogCode.Accepted)
    assert cp.get_color("#123456", None, "Color").name() == "#123456"


def test_screen_picker_reads_the_pixel_under_the_pointer(qtbot):
    from PySide6.QtGui import QPixmap

    from ui.color_picker import ScreenColorPicker

    pk = ScreenColorPicker()
    qtbot.addWidget(pk)
    shot = QPixmap(40, 40)
    shot.fill(QColor("#336699"))
    pk._shot = shot  # noqa: SLF001
    pk._image = shot.toImage()  # noqa: SLF001
    got = []
    pk.picked.connect(got.append)
    pk.resize(40, 40)
    pk.show()
    qtbot.mouseClick(pk, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    assert got and got[0].name() == "#336699"


def test_text_box_stays_open_while_the_picker_is_used(qtbot, prefs_dir):
    from ui.color_picker import ColorPickerDialog
    from ui.pdf_canvas import _CanvasWidget

    dlg = ColorPickerDialog(None, initial="#000000", title="Text color")
    qtbot.addWidget(dlg)
    assert _CanvasWidget._is_formatting_control(dlg.hex_edit)  # noqa: SLF001
    _ = QPointF
