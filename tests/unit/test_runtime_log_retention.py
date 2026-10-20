"""Diagnostic files written on every launch / drag stay bounded and out of installed profiles."""

from __future__ import annotations

import os

from core import startup_timing as st


def test_startup_logs_are_pruned_to_the_newest(tmp_path, monkeypatch):
    for stamp in range(1000, 1000 + st.KEEP_LOGS + 15):
        (tmp_path / f"startup-{stamp}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "startup-latest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "other-1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(st, "_enabled", True)
    st.reset()
    st.mark("first_visible")
    monkeypatch.setattr(st, "_log_dir", lambda: tmp_path)
    written = st.write_log(tag="startup")
    stamped = sorted(p.name for p in tmp_path.glob("startup-*.json") if p.name != "startup-latest.json")
    assert len(stamped) == st.KEEP_LOGS
    assert written.name in stamped  # the new log is kept
    assert "startup-1000.json" not in stamped  # the oldest are gone
    assert (tmp_path / "startup-latest.json").exists() and (tmp_path / "other-1.json").exists()


def test_installed_layout_has_no_second_logs_folder():
    from app import paths

    if paths.INSTALLED_READ_ONLY:
        assert paths.TEST_LOGS == paths.RUNTIME_DIR / "logs"
    else:
        assert paths.TEST_LOGS == paths.TEST_OUTPUTS / "logs"
    assert paths.TEST_LOGS.name == "logs" and paths.TEST_LOGS.parent.name != "logs"


def test_drag_perf_log_is_not_written_by_an_installed_copy(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from app import paths
    from ui.pdf_canvas import _CanvasWidget as PdfCanvas

    monkeypatch.setattr(paths, "INSTALLED_READ_ONLY", True)
    monkeypatch.setattr(paths, "TEST_LOGS", tmp_path)
    monkeypatch.delenv("MONOGRAPH_PDF_PERF_LOG", raising=False)
    fake = type("C", (), {"_drag_perf": [1.0, 2.0]})()
    PdfCanvas._write_drag_perf(fake, "move")
    assert not (tmp_path / "textbox_interaction_perf.log").exists()
    assert fake._drag_perf == []
    monkeypatch.setenv("MONOGRAPH_PDF_PERF_LOG", "1")
    fake._drag_perf = [3.0]
    PdfCanvas._write_drag_perf(fake, "move")
    assert (tmp_path / "textbox_interaction_perf.log").read_text(encoding="utf-8").startswith("move n=1")
