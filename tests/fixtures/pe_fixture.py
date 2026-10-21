"""A minimal, valid PE32+ (x64) image for tests of the PE tools (no code; never executed).

Layout: DOS header (e_lfanew 0x80), COFF header, PE32+ optional header with 16 data directories,
one section ``.rdata`` at file offset 0x200 / RVA 0x1000 holding one IMAGE_DEBUG_DIRECTORY entry and,
optionally, an import directory naming the given DLLs. Optional trailing ``overlay`` bytes stand in
for PyInstaller's appended archive.
"""

from __future__ import annotations

import struct

FILE_ALIGN = 0x200
SECT_ALIGN = 0x1000
RVA = 0x1000


def build_pe(timestamp: int = 1_700_000_000, imports: tuple[str, ...] = (), machine: int = 0x8664,
             overlay: bytes = b"") -> bytes:
    sect = bytearray(FILE_ALIGN * 2)
    # IMAGE_DEBUG_DIRECTORY at section offset 0 (28 bytes): Characteristics, TimeDateStamp, ...
    struct.pack_into("<IIHHIIII", sect, 0, 0, timestamp, 0, 0, 2, 0, 0, 0)
    import_rva = import_size = 0
    if imports:
        # descriptors at 0x40, names at 0x200, a shared thunk table at 0x300, hint/name at 0x380
        desc_off, name_off, thunk_off, hint_off = 0x40, 0x200, 0x300, 0x380
        # one imported function per DLL (pefile ignores descriptors without any): thunk -> hint/name
        struct.pack_into("<QQ", sect, thunk_off, RVA + hint_off, 0)
        sect[hint_off:hint_off + 7] = b"\0\0Stub\0"
        for i, name in enumerate(imports):
            nb = name.encode("ascii") + b"\0"
            sect[name_off:name_off + len(nb)] = nb
            # OriginalFirstThunk, TimeDateStamp, ForwarderChain, Name, FirstThunk
            struct.pack_into("<IIIII", sect, desc_off + 20 * i, RVA + thunk_off, 0, 0, RVA + name_off, RVA + thunk_off)
            name_off += len(nb)
        import_rva, import_size = RVA + desc_off, 20 * (len(imports) + 1)
    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)
    coff = struct.pack("<4sHHIIIHH", b"PE\0\0", machine, 1, timestamp, 0, 0, 240, 0x0022)
    dirs = [(0, 0)] * 16
    dirs[1] = (import_rva, import_size)
    dirs[6] = (RVA, 28)  # debug
    opt = struct.pack(
        "<HBBIIIIIQIIHHHHHHIIIIHHQQQQII",
        0x20B, 14, 0, FILE_ALIGN, 0, 0, RVA, RVA, 0x140000000, SECT_ALIGN, FILE_ALIGN,
        6, 0, 0, 0, 6, 0, 0, RVA + SECT_ALIGN, FILE_ALIGN, 0, 3, 0x8160,
        0x100000, 0x1000, 0x100000, 0x1000, 0, 16,
    ) + b"".join(struct.pack("<II", *d) for d in dirs)
    section = struct.pack("<8sIIIIIIHHI", b".rdata", len(sect), RVA, len(sect), FILE_ALIGN, 0, 0, 0, 0, 0x40000040)
    header = bytes(dos) + coff + opt + section
    header += b"\0" * (FILE_ALIGN - len(header))
    return header + bytes(sect) + overlay
