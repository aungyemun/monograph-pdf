"""Redaction removes what lies under a mark — form fields, comments and links included — and
reports (and on request removes) the same text elsewhere in the file.

Verified from the written bytes: raw file, every object and every decompressed stream.
"""

from __future__ import annotations

import fitz

from core.document import open_document
from core.redaction import (
    apply_redactions,
    apply_redactions_report,
    find_residue,
    mark_region,
    mark_text,
    marked_terms,
    scrub_residue,
)
from core.editing.geometry import Rect

SECRET = "ZEBRA-4711"


def _everything(path) -> list[bytes]:
    blobs = [path.read_bytes()]
    with fitz.open(path) as d:
        for x in range(1, d.xref_length()):
            try:
                blobs.append(d.xref_object(x).encode("latin-1", "replace"))
                if d.xref_is_stream(x):
                    blobs.append(d.xref_stream(x) or b"")
            except Exception:  # noqa: BLE001
                pass
    return blobs


def _fixture(path, *, with_extras: bool = True):
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), f"Account {SECRET} is private", fontsize=12)
    p.insert_text((72, 140), "Unrelated line stays", fontsize=12)
    w = fitz.Widget()
    w.field_name, w.field_type = "acct", fitz.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = fitz.Rect(72, 400, 300, 424), SECRET
    p.add_widget(w)
    w2 = fitz.Widget()
    w2.field_name, w2.field_type = "other", fitz.PDF_WIDGET_TYPE_TEXT
    w2.rect, w2.field_value = fitz.Rect(72, 500, 300, 524), "keep me"
    p.add_widget(w2)
    hl = p.add_highlight_annot(fitz.Rect(150, 88, 230, 104))  # over the secret on the page
    hl.set_info(content="highlight over the account")
    hl.update()
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 88, 140, 104), "uri": "https://example.invalid/"})
    if with_extras:
        p.add_text_annot((400, 300), f"note mentions {SECRET}")
        d.set_toc([[1, f"Section {SECRET}", 1], [1, "Other section", 1]])
        d.set_metadata({"title": f"Doc {SECRET}", "subject": SECRET, "author": "Someone"})
        d.embfile_add(f"notes-{SECRET}.txt", b"named after the secret")
        d.embfile_add("keep.txt", f"content mentions {SECRET}".encode(), desc="plain")
    d.save(path)
    d.close()
    return path


def _mark_all(doc, term=SECRET):
    return sum(len(mark_text(doc, i, term)) for i in range(doc.page_count))


def test_form_field_under_a_text_mark_is_removed_with_its_value(tmp_path):
    src = _fixture(tmp_path / "src.pdf", with_extras=False)
    doc = open_document(src)
    try:
        assert _mark_all(doc) == 2  # page text and the field showing the same text
        report = apply_redactions_report(doc, tmp_path / "out.pdf")
    finally:
        doc.close()
    assert report.removed_form_fields == 1
    with fitz.open(tmp_path / "out.pdf") as d:
        assert SECRET not in d[0].get_text()
        assert [(w.field_name, w.field_value) for w in d[0].widgets()] == [("other", "keep me")]
        assert "Unrelated line stays" in d[0].get_text()
    assert not any(SECRET.encode() in b for b in _everything(tmp_path / "out.pdf"))


def test_comments_and_links_under_an_area_mark_are_removed_others_kept(tmp_path):
    src = _fixture(tmp_path / "src.pdf", with_extras=False)
    doc = open_document(src)
    try:
        mark_region(doc, 0, Rect(60, 80, 300, 30))  # covers the first line, its highlight and its link
        report = apply_redactions_report(doc, tmp_path / "out.pdf")
    finally:
        doc.close()
    assert report.removed_annotations == 1 and report.removed_links == 1
    assert report.residue == []  # area marks have no search term to look for
    with fitz.open(tmp_path / "out.pdf") as d:
        assert not list(d[0].annots(types=[fitz.PDF_ANNOT_HIGHLIGHT]))
        assert d[0].get_links() == []
        assert len(list(d[0].widgets())) == 2


def test_residue_outside_the_pages_is_reported_not_silently_changed(tmp_path):
    src = _fixture(tmp_path / "src.pdf")
    doc = open_document(src)
    try:
        _mark_all(doc)
        assert marked_terms(doc) == {SECRET}
        report = apply_redactions_report(doc, tmp_path / "out.pdf")
    finally:
        doc.close()
    kinds = sorted({r.where for r in report.residue})
    assert kinds == ["attachment", "attachment (not checked)", "bookmark", "comment", "document properties"]
    assert any("keep.txt" in r.detail for r in report.residue if r.where == "attachment (not checked)")
    with fitz.open(tmp_path / "out.pdf") as d:  # still there: the user decides
        assert d.get_toc()[0][1] == f"Section {SECRET}"
        assert f"notes-{SECRET}.txt" in d.embfile_names()


def test_scrub_removes_every_remaining_occurrence_and_keeps_the_rest(tmp_path):
    src = _fixture(tmp_path / "src.pdf")
    doc = open_document(src)
    try:
        _mark_all(doc)
        apply_redactions_report(doc, tmp_path / "out.pdf")
    finally:
        doc.close()
    with fitz.open(tmp_path / "out.pdf") as d:
        assert scrub_residue(d, {SECRET}) == 4
        d.save(tmp_path / "clean.pdf", garbage=4, deflate=True)
    clean = tmp_path / "clean.pdf"
    with fitz.open(clean) as d:
        left = find_residue(d, {SECRET})
        # only the attachment whose content is never read remains listed, as "not checked"
        assert [(r.where, "keep.txt" in r.detail) for r in left] == [("attachment (not checked)", True)]
        d.embfile_del("keep.txt")  # the user's own decision after review
        d.save(tmp_path / "reviewed.pdf", garbage=4, deflate=True)
    reviewed = tmp_path / "reviewed.pdf"
    assert not any(SECRET.encode() in b for b in _everything(reviewed))
    assert not any(SECRET.encode("utf-16-be") in b for b in _everything(reviewed))
    with fitz.open(clean) as d:
        assert [row[1] for row in d.get_toc()] == ["Section [redacted]", "Other section"]
        assert d.embfile_names() == ["keep.txt"]  # named attachment removed, the other kept
        assert d.metadata["author"] == "Someone" and d.metadata["title"] == "Doc [redacted]"
        assert "Unrelated line stays" in d[0].get_text()
        assert ("other", "keep me") in [(w.field_name, w.field_value) for w in d[0].widgets()]


def test_case_insensitive_matching_and_legacy_signature(tmp_path):
    src = _fixture(tmp_path / "src.pdf")
    doc = open_document(src)
    try:
        _mark_all(doc, SECRET.lower())
        out = apply_redactions(doc, tmp_path / "out.pdf")
    finally:
        doc.close()
    assert out == tmp_path / "out.pdf"
    with fitz.open(out) as d:
        assert SECRET not in d[0].get_text()
        found = find_residue(d, {SECRET.lower()})
        assert {r.where for r in found} >= {"bookmark", "attachment"}


def test_terms_are_kept_per_document_in_memory_only(tmp_path):
    a = open_document(_fixture(tmp_path / "a.pdf", with_extras=False))
    b = open_document(_fixture(tmp_path / "b.pdf", with_extras=False))
    try:
        mark_text(a, 0, SECRET)
        assert marked_terms(a) == {SECRET} and marked_terms(b) == set()
    finally:
        a.close()
        b.close()


def test_whole_page_redaction_also_removes_content_outside_the_visible_area(tmp_path):
    from core.redaction import mark_pages

    d = fitz.open()
    for rot in (0, 90):
        p = d.new_page(width=700, height=900)
        p.insert_text((20, 30), f"HIDDEN{rot}", fontsize=10)  # outside the crop box below
        p.insert_text((300, 450), f"VISIBLE{rot}", fontsize=10)
        p.insert_image(fitz.Rect(300, 500, 400, 600), stream=_png_bytes())
        p.set_cropbox(fitz.Rect(100, 100, 600, 800))
        p.set_rotation(rot)
    keep = d.new_page()
    keep.insert_text((72, 72), "KEEPPAGE", fontsize=10)
    d.set_toc([[1, "Kept", 3]])
    d.save(tmp_path / "src.pdf")
    d.close()
    doc = open_document(tmp_path / "src.pdf")
    try:
        assert len(mark_pages(doc, [0, 1])) == 2
        apply_redactions(doc, tmp_path / "out.pdf")
    finally:
        doc.close()
    blobs = b"".join(_everything(tmp_path / "out.pdf"))
    for word in (b"HIDDEN0", b"HIDDEN90", b"VISIBLE0", b"VISIBLE90"):
        assert word not in blobs, word
    with fitz.open(tmp_path / "out.pdf") as out:
        assert out.page_count == 3 and out.get_toc() == [[1, "Kept", 3]]
        assert [p.rotation for p in out][:2] == [0, 90]
        assert "KEEPPAGE" in out[2].get_text()
        assert not out[0].get_images() and not out[1].get_images()


def test_whole_page_redaction_rejects_missing_pages(tmp_path):
    import pytest

    from core.redaction import mark_pages

    doc = open_document(_fixture(tmp_path / "src.pdf", with_extras=False))
    try:
        with pytest.raises(ValueError):
            mark_pages(doc, [5])
    finally:
        doc.close()


def _png_bytes() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()
