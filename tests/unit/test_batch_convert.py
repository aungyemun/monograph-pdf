"""Batch conversion: formats, page ranges, unique names, failures and cancellation leave no partial
files, bounded (one at a time) processing."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.convert.batch import (
    FORMAT_BY_KEY,
    BatchItem,
    BatchOptions,
    BatchRunner,
    accepted,
    parse_page_range,
    unique_path,
)


def _pdf(path: Path, pages: int = 3, text: str = "Batch page") -> Path:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"{text} {i + 1}", fontsize=14)
    doc.save(path)
    doc.close()
    return path


def _run(items, **kw):
    runner = BatchRunner(items, BatchOptions(**kw))
    runner.run()
    return runner


@pytest.mark.parametrize("text,expected", [
    ("", None), ("1", [0]), ("1-3", [0, 1, 2]), ("2, 4-", [1, 3, 4]), ("-2", [0, 1]), ("3-3,1", [2, 0]),
    ("1-99", [0, 1, 2, 3, 4]),
])
def test_page_ranges(text, expected):
    assert parse_page_range(text, 5) == expected


@pytest.mark.parametrize("bad", ["x", "3-1", "0", "9", "1-2-3"])
def test_invalid_page_ranges(bad):
    with pytest.raises(ValueError):
        parse_page_range(bad, 5)


def test_unique_names_never_overwrite(tmp_path):
    (tmp_path / "a.docx").write_text("x")
    (tmp_path / "a (1).docx").write_text("x")
    assert unique_path(tmp_path / "a.docx").name == "a (2).docx"
    assert unique_path(tmp_path / "b.docx", {tmp_path / "b.docx"}).name == "b (1).docx"


def test_text_and_pictures_with_page_range_and_collisions(tmp_path):
    src = _pdf(tmp_path / "in.pdf")
    out = tmp_path / "out"
    out.mkdir()
    (out / "in.txt").write_text("keep me")
    items = [BatchItem(src)]
    _run(items, format_key="txt", output_dir=out, page_range="2-3")
    assert items[0].status == "done"
    assert (out / "in.txt").read_text() == "keep me"  # not overwritten
    produced = (out / "in (1).txt").read_text(encoding="utf-8-sig")
    assert "Batch page 2" in produced and "Batch page 3" in produced and "Batch page 1" not in produced
    items = [BatchItem(src)]
    _run(items, format_key="png", output_dir=out, page_range="1,3", dpi=72)
    assert items[0].status == "done" and len(items[0].outputs) == 2
    assert all(p.suffix == ".png" and p.is_file() for p in items[0].outputs)
    assert not list(out.glob("*.part"))


@pytest.mark.parametrize("key", ["docx", "pptx", "xlsx"])
def test_office_formats_from_pdf(tmp_path, key):
    src = _pdf(tmp_path / "doc.pdf", pages=2)
    items = [BatchItem(src)]
    _run(items, format_key=key, output_dir=tmp_path / "out")
    assert items[0].status == "done", items[0].message
    assert items[0].outputs[0].suffix == FORMAT_BY_KEY[key].suffix and items[0].outputs[0].stat().st_size > 0


def test_pictures_to_pdf(tmp_path):
    from PIL import Image

    pic = tmp_path / "photo.png"
    Image.new("RGB", (120, 80), (10, 120, 200)).save(pic)
    items = [BatchItem(pic)]
    _run(items, format_key="image_pdf", output_dir=tmp_path / "out")
    assert items[0].status == "done"
    with fitz.open(items[0].outputs[0]) as d:
        assert d.page_count == 1 and d[0].get_images()


def test_a_bad_file_fails_alone_and_unsupported_files_are_skipped(tmp_path):
    good = _pdf(tmp_path / "good.pdf")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7 not really")
    picture = tmp_path / "p.png"
    picture.write_bytes(b"\x89PNG")
    items = [BatchItem(broken), BatchItem(picture), BatchItem(good)]
    _run(items, format_key="txt", output_dir=tmp_path / "out")
    assert [i.status for i in items] == ["failed", "skipped", "done"]
    assert not list((tmp_path / "out").glob("*.part")) and len(list((tmp_path / "out").iterdir())) == 1


def test_password_protected_pdf_is_skipped_without_a_password(tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "secret")
    locked = tmp_path / "locked.pdf"
    doc.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    items = [BatchItem(locked)]
    _run(items, format_key="txt", output_dir=tmp_path / "out")
    assert items[0].status == "failed" and "password" in items[0].message
    items = [BatchItem(locked)]
    _run(items, format_key="txt", output_dir=tmp_path / "out2", password=lambda p: "u")
    assert items[0].status == "done"


def test_cancel_stops_before_the_next_file_and_keeps_no_partial_output(tmp_path):
    files = [_pdf(tmp_path / f"f{i}.pdf") for i in range(3)]
    items = [BatchItem(f) for f in files]
    seen = []

    runner = BatchRunner(items, BatchOptions(format_key="txt", output_dir=tmp_path / "out"))

    def on_update(i, item):
        seen.append((i, item.status))
        if i == 0 and item.status == "done":
            runner.cancel()

    runner.on_update = on_update
    runner.run()
    assert [i.status for i in items] == ["done", "cancelled", "cancelled"]
    assert len(list((tmp_path / "out").iterdir())) == 1


def test_accepted_inputs_follow_the_format():
    paths = [Path("a.pdf"), Path("b.PNG"), Path("c.docx"), Path("d.txt")]
    assert accepted(paths, "docx") == [Path("a.pdf")]
    assert accepted(paths, "image_pdf") == [Path("b.PNG")]
    assert accepted(paths, "office_pdf") == [Path("c.docx")]
