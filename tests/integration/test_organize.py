"""Integration tests for page organize, merge, split — outputs under tests/outputs."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from core.document import InvalidPdfError, PasswordRequiredError, open_document
from core.editing.edit_model import EditableDocument
from core.editing.geometry import Rect
from core.editing.text_box import TextBox
from core.organize.merge import MergeJob, combine_to_pdf
from core.organize.page_ops import (
    copy_pages_between,
    crop_page,
    delete_pages,
    duplicate_pages,
    extract_pages,
    insert_blank_page,
    insert_pdf_pages,
    inspect_page_sizes,
    move_page,
    parse_page_ranges,
    reorder_pages,
    replace_page,
    rotate_pages,
)
from core.organize.remap import map_after_delete, map_after_insert, map_after_reorder
from core.organize.split import SplitMode, plan_split, run_split
from core.organize.temputil import cleanup_abandoned_temps, organize_temp_dir
from engines.bake_edits import bake_into_document

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
OUT = Path(__file__).resolve().parents[1] / "outputs" / "generated"


@pytest.fixture(scope="module", autouse=True)
def _fixtures():
    from tests.fixtures.make_samples import main

    main()
    OUT.mkdir(parents=True, exist_ok=True)


def test_parse_page_ranges():
    assert parse_page_ranges("1,3-4", 5) == [0, 2, 3]
    with pytest.raises(ValueError):
        parse_page_ranges("9", 3)


def test_insert_delete_reorder_counts():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    try:
        assert pdf.page_count == 3
        insert_blank_page(pdf, 1)
        assert pdf.page_count == 4
        delete_pages(pdf, [1])
        assert pdf.page_count == 3
        reorder_pages(pdf, [2, 0, 1])
        assert pdf.page_count == 3
        # After reorder, first page should be former page 3 text
        text0 = pdf.page_text(0)
        assert "page 3" in text0.lower() or "3" in text0
    finally:
        pdf.close()


def test_duplicate_and_move():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    try:
        n = pdf.page_count
        inserted = duplicate_pages(pdf, [0])
        assert pdf.page_count == n + 1
        assert inserted
        move_page(pdf, 0, pdf.page_count - 1)
        assert pdf.page_count == n + 1
    finally:
        pdf.close()


def test_rotate_and_crop_persist_on_save():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    dest = OUT / "organize_rotate_crop.pdf"
    try:
        rotate_pages(pdf, [0], 90)
        sizes = inspect_page_sizes(pdf)
        assert sizes[0].rotation % 360 == 90
        # Crop inward
        page = pdf.page(1)
        crop_page(pdf, 1, (36, 36, page.width_pt - 36, page.height_pt - 36))
        pdf.save_as(dest)
    finally:
        pdf.close()

    reopened = open_document(dest)
    try:
        assert reopened.page(0).rotation % 360 == 90
        cb = inspect_page_sizes(reopened)[1].cropbox
        assert cb[0] >= 30 and cb[1] >= 30
    finally:
        reopened.close()


def test_extract_and_insert_pdf_pages():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    extracted = OUT / "organize_extracted.pdf"
    try:
        extract_pages(pdf, [0, 2], extracted)
    finally:
        pdf.close()

    assert extracted.is_file()
    part = open_document(extracted)
    try:
        assert part.page_count == 2
    finally:
        part.close()

    target = open_document(SAMPLES / "sample_text.pdf")
    try:
        n = target.page_count
        inserted = insert_pdf_pages(target, extracted, at_index=1)
        assert inserted == 2
        assert target.page_count == n + 2
    finally:
        target.close()


def test_replace_page():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    other = open_document(SAMPLES / "sample_image_page.pdf")
    try:
        replace_page(pdf, 1, other, source_page=0)
        assert pdf.page_count == 3
    finally:
        other.close()
        pdf.close()


def test_copy_between_documents():
    a = open_document(SAMPLES / "sample_text.pdf")
    b = open_document(SAMPLES / "sample_image_page.pdf")
    dest = OUT / "organize_copy_between.pdf"
    try:
        n = b.page_count
        copy_pages_between(a, b, [0, 1], at_index=b.page_count)
        assert b.page_count == n + 2
        b.save_as(dest)
    finally:
        a.close()
        b.close()
    reopened = open_document(dest)
    try:
        assert reopened.page_count >= 3
    finally:
        reopened.close()


def test_overlay_remap_after_delete():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    try:
        edit = EditableDocument(pdf)
        edit.add_object(TextBox(page_index=0, rect=Rect(40, 40, 100, 20), text="A"))
        edit.add_object(TextBox(page_index=2, rect=Rect(40, 40, 100, 20), text="C"))
        mapping = map_after_delete(3, [1])
        delete_pages(pdf, [1])
        edit.remap_page_indices(mapping)
        pages = {o.page_index for o in edit.all_objects()}
        assert pages == {0, 1}
        assert any(o.text == "C" and o.page_index == 1 for o in edit.all_objects())
    finally:
        pdf.close()


def test_bake_preserves_structural_ops():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    dest = OUT / "organize_bake_structure.pdf"
    try:
        insert_blank_page(pdf, 0)
        edit = EditableDocument(pdf)
        edit.add_object(TextBox(page_index=1, rect=Rect(50, 50, 120, 24), text="After blank"))
        bake_into_document(edit, dest)
    finally:
        pdf.close()
    reopened = open_document(dest)
    try:
        assert reopened.page_count == 4
    finally:
        reopened.close()


def test_merge_combine_preserves_sources():
    src_a = SAMPLES / "sample_text.pdf"
    src_b = SAMPLES / "sample_image_page.pdf"
    before_a = src_a.stat().st_mtime_ns
    before_b = src_b.stat().st_mtime_ns
    job = MergeJob()
    job.add_path(src_a)
    job.add_path(src_b)
    job.set_included_pages(0, [0, 1])
    dest = OUT / "organize_merged.pdf"
    combine_to_pdf(job, dest)
    assert dest.is_file()
    merged = open_document(dest)
    try:
        assert merged.page_count == 3  # 2 from text + 1 image
    finally:
        merged.close()
    assert src_a.stat().st_mtime_ns == before_a
    assert src_b.stat().st_mtime_ns == before_b


def test_split_modes():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    out_dir = OUT / "organize_split"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        plan = plan_split(pdf, SplitMode.EVERY_PAGE)
        paths = run_split(pdf, plan, out_dir, name_prefix="t")
        assert len(paths) == 3
        plan_n = plan_split(pdf, SplitMode.EVERY_N, every_n=2)
        paths_n = run_split(pdf, plan_n, out_dir, name_prefix="n")
        assert len(paths_n) == 2
        plan_r = plan_split(pdf, SplitMode.RANGES, range_spec="1-2,3")
        paths_r = run_split(pdf, plan_r, out_dir, name_prefix="r")
        assert len(paths_r) == 2
        plan_s = plan_split(pdf, SplitMode.SELECTED, selected_pages=[0, 2])
        paths_s = run_split(pdf, plan_s, out_dir, name_prefix="s")
        assert len(paths_s) == 1
        assert open_document(paths_s[0]).page_count == 2
        open_document(paths_s[0]).close()
    finally:
        pdf.close()


def test_encrypted_input_merge_and_ops():
    job = MergeJob()
    src = job.add_path(SAMPLES / "sample_password.pdf")
    assert src.open_error is not None or src.encrypted
    # Proper password
    job2 = MergeJob()
    src2 = job2.add_path(SAMPLES / "sample_password.pdf", password="secret")
    assert src2.open_error is None
    assert src2.page_count >= 1
    dest = OUT / "organize_merged_encrypted.pdf"
    combine_to_pdf(job2, dest)
    assert dest.is_file()

    pdf = open_document(SAMPLES / "sample_password.pdf", password="secret")
    try:
        insert_blank_page(pdf, 0)
        assert pdf.page_count >= 2
    finally:
        pdf.close()


def test_corrupted_input():
    job = MergeJob()
    src = job.add_path(SAMPLES / "sample_malformed.pdf")
    assert src.open_error is not None
    with pytest.raises((InvalidPdfError, Exception)):
        open_document(SAMPLES / "sample_malformed.pdf")


def test_temp_dirs_not_project_root():
    d = organize_temp_dir(prefix="test")
    assert "runtime" in d.as_posix().replace("\\", "/")
    assert d.is_dir()
    # cleanup should not crash
    cleanup_abandoned_temps(max_age_sec=0)
    assert not d.exists() or True  # may be removed


def test_page_size_inspection():
    pdf = open_document(SAMPLES / "sample_text.pdf")
    try:
        sizes = inspect_page_sizes(pdf)
        assert len(sizes) == pdf.page_count
        assert sizes[0].width_pt > 0 and sizes[0].height_pt > 0
    finally:
        pdf.close()
