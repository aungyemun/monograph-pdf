"""Set the build-time stamps of a Windows program file to a fixed time (reproducible builds).

    python scripts/packaging/normalize_pe.py --epoch SECONDS FILE...

PyInstaller writes the current time into ``MonographPDF.exe``: the COFF header ``TimeDateStamp`` and
the ``TimeDateStamp`` of every debug-directory entry; the PE checksum then differs as well. Two builds
of the same commit were otherwise byte-identical (0.3.0 development measurement: 482 of 483 files
identical, the launcher differing only in these 6 bytes). This tool overwrites exactly those fields
with ``--epoch`` (the commit time, or ``SOURCE_DATE_EPOCH``) and recomputes the checksum. Nothing else
in the file — code, resources, the appended application archive — is changed. Only the header bytes
are patched in place, so the overlay (PyInstaller's archive) keeps its position.
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def normalize(path: Path, epoch: int) -> bool:
    """Return True if the file changed."""
    import pefile  # build-time only (installed with PyInstaller)

    data = bytearray(path.read_bytes())
    pe = pefile.PE(data=bytes(data), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DEBUG"]])
    offsets = [pe.FILE_HEADER.get_field_absolute_offset("TimeDateStamp")]
    for entry in getattr(pe, "DIRECTORY_ENTRY_DEBUG", []):
        offsets.append(entry.struct.get_field_absolute_offset("TimeDateStamp"))
    checksum_offset = pe.OPTIONAL_HEADER.get_field_absolute_offset("CheckSum")
    pe.close()
    for off in offsets:
        struct.pack_into("<I", data, off, epoch & 0xFFFFFFFF)
    patched = pefile.PE(data=bytes(data), fast_load=True)
    struct.pack_into("<I", data, checksum_offset, patched.generate_checksum())
    patched.close()
    if bytes(data) == path.read_bytes():
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(bytes(data))
    tmp.replace(path)
    return True


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--epoch", type=int, required=True)
    ap.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args(argv)
    if not 0 < a.epoch < 2**32:
        print("epoch out of range", file=sys.stderr)
        return 2
    for f in a.files:
        changed = normalize(f, a.epoch)
        print(f"{f.name}: time stamps {'set to' if changed else 'already'} {a.epoch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
