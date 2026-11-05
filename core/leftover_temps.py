"""Temporary files that an interrupted save left beside a document (0.6.0, audit finding F-13).

Every save writes a temporary file in the document's folder and swaps it in. If Monograph PDF is
ended, crashes or the power fails in between, that temporary file stays. This module only *finds*
them, narrowly:

* only in the folder of the document being opened, and only names that Monograph PDF itself uses
  for *that* document (``.{stem}.{8 hex}.part``, ``.{stem}.saving-{8 hex}.pdf``,
  ``.{name}.{8 hex}.part``, ``.{stem}.{8 hex}.part.pdf``) — exact patterns, no wildcards;
* only regular files (no folders, no links) not changed for at least ``min_age`` seconds, so a save
  in progress in another Monograph PDF window is never listed;
* nothing is deleted here. The window lists them and moves them to the Recycle Bin only when the
  user chooses so; otherwise they stay for manual review. A file that is a complete PDF is marked as
  such: it may hold changes that never reached the document.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

MIN_AGE_SECONDS = 600


@dataclass(frozen=True)
class Leftover:
    path: Path
    size: int
    mtime: float
    complete_pdf: bool  # starts with %PDF and ends with %%EOF: a whole copy, maybe with unsaved changes


def _patterns(document: Path) -> list[re.Pattern]:
    stem, name = re.escape(document.stem), re.escape(document.name)
    hex8 = r"[0-9a-f]{8}"
    return [
        re.compile(rf"\.{stem}\.{hex8}\.part"),  # safe_write / bake_edits / compress
        re.compile(rf"\.{stem}\.saving-{hex8}\.pdf"),  # Save over the open file
        re.compile(rf"\.{name}\.{hex8}\.part"),  # moving a finished file into place
        re.compile(rf"\.{stem}\.{hex8}\.part\.pdf"),  # Office → PDF conversion
    ]


def _complete_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(5)
            fh.seek(max(0, path.stat().st_size - 1024))
            tail = fh.read()
        return head == b"%PDF-" and b"%%EOF" in tail
    except OSError:
        return False


def find_leftovers(document: Path | str, *, min_age: float = MIN_AGE_SECONDS, now: float | None = None) -> list[Leftover]:
    """Temporary files of interrupted saves of ``document`` (see the module description)."""
    document = Path(document)
    folder = document.parent
    patterns = _patterns(document)
    now = time.time() if now is None else now
    found: list[Leftover] = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return []
    for entry in entries:
        if not entry.name.startswith(".") or not any(p.fullmatch(entry.name) for p in patterns):
            continue
        try:
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                continue
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if now - st.st_mtime < min_age:
            continue  # may belong to a save that is still running
        path = Path(entry.path)
        found.append(Leftover(path, int(st.st_size), float(st.st_mtime), _complete_pdf(path)))
    return sorted(found, key=lambda x: x.mtime)
