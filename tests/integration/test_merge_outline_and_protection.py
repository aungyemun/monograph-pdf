"""Combine keeps each source's bookmarks (re-pointed) and says when protection is not carried over."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.organize.merge import MergeJob, combine_to_pdf


def _src(path: Path, pages: int, toc, *, password: str | None = None) -> Path:
    d = fitz.open()
    for i in range(pages):
        d.new_page().insert_text((72, 72), f"{path.stem} p{i + 1}")
    if toc:
        d.set_toc(toc)
    kw = {}
    if password:
        kw = {"encryption": fitz.PDF_ENCRYPT_AES_256, "user_pw": password, "owner_pw": password}
    d.save(path, **kw)
    d.close()
    return path


def test_bookmarks_are_kept_and_repointed(tmp_path):
    a = _src(tmp_path / "A.pdf", 3, [[1, "A intro", 1], [2, "A detail", 2], [1, "A end", 3]])
    b = _src(tmp_path / "B.pdf", 2, [[1, "B start", 1], [1, "B two", 2]])
    job = MergeJob()
    job.add_path(a)
    job.add_path(b)
    out = combine_to_pdf(job, tmp_path / "out.pdf")
    with fitz.open(out) as d:
        assert d.page_count == 5
        assert d.get_toc() == [[1, "A intro", 1], [2, "A detail", 2], [1, "A end", 3], [1, "B start", 4], [1, "B two", 5]]
        for _lvl, title, page in d.get_toc():  # each bookmark lands on the page it named
            assert title.split()[0] in d[page - 1].get_text()


def test_bookmarks_to_excluded_pages_are_dropped_and_levels_stay_valid(tmp_path):
    a = _src(tmp_path / "A.pdf", 3, [[1, "Parent", 1], [2, "Child", 3], [1, "Gone", 2]])
    job = MergeJob()
    job.add_path(a)
    job.set_included_pages(0, [2])  # only page 3: the parent and "Gone" are left out
    out = combine_to_pdf(job, tmp_path / "out.pdf")
    with fitz.open(out) as d:
        assert d.get_toc() == [[1, "Child", 1]]


def test_protected_sources_are_reported(tmp_path):
    a = _src(tmp_path / "A.pdf", 1, None)
    b = _src(tmp_path / "B.pdf", 1, None, password="pw")
    job = MergeJob()
    job.add_path(a)
    job.add_path(b, password="pw")
    assert "B.pdf" in job.protection_warning() and "A.pdf" not in job.protection_warning()
    out = combine_to_pdf(job, tmp_path / "out.pdf")
    with fitz.open(out) as d:
        assert not d.needs_pass and d.page_count == 2  # as the warning says
    plain = MergeJob()
    plain.add_path(a)
    assert plain.protection_warning() is None
