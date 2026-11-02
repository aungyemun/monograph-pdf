"""Release-notes text signed into the update manifest (0.5.1).

The 0.5.0 manifest's release_notes began with an invisible U+FEFF: the notes file had a UTF-8
byte-order mark, ``read_text("utf-8")`` keeps it as a character and ``strip()`` does not remove it.
The published 0.5.0 manifest is not changed; these tests pin the normalization for later manifests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "packaging"))

import update_manifest as um  # noqa: E402
import validate_release_notes as vrn  # noqa: E402

BOM = chr(0xFEFF)


def test_bom_crlf_and_blank_edges_are_removed(tmp_path):
    p = tmp_path / "v0.5.1.md"
    p.write_bytes(b"\xef\xbb\xbf\r\nMonograph PDF 0.5.1, released 2026-11-01.\r\n\r\n## Fixed\r\n- one\r\n\r\n")
    text = um.notes_text(p)
    assert text == "Monograph PDF 0.5.1, released 2026-11-01.\n\n## Fixed\n- one"
    assert um.notes_problems(text) == []


def test_stray_bom_inside_the_text_is_removed_and_japanese_is_kept(tmp_path):
    p = tmp_path / "notes.md"
    decomposed = "か" + chr(0x3099)  # ka + combining voiced mark, as some editors save it
    composed = chr(0x304C)  # ga
    p.write_text(f"保存{BOM}の修正 {decomposed}", encoding="utf-8")
    text = um.notes_text(p)
    assert BOM not in text and text == "保存の修正 " + composed  # NFC: one composed character
    assert len(text) == len("保存の修正 ") + 1


def test_problems_name_what_the_0_5_0_manifest_had():
    assert "byte-order mark" in um.notes_problems(BOM + "Monograph PDF 0.5.0")[0]
    assert um.notes_problems("a\r\nb")
    assert um.notes_problems(" padded ")


def test_published_0_5_0_notes_text_is_flagged_but_normalizes_cleanly():
    signed = BOM + "Monograph PDF 0.5.0, released 2026-10-28. A feature release"
    assert um.notes_problems(signed)
    assert um.notes_problems(um.normalize_notes(signed)) == []


def test_release_notes_validator_rejects_a_bom_file():
    r = vrn.validate(BOM + "Monograph PDF 9.9.9, released 2026-11-01.\n", "9.9.9")
    assert any("byte-order mark" in p for p in r.problems)
