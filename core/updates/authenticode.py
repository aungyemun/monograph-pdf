"""Windows Authenticode check of a downloaded installer (an extra layer on top of the signed
manifest). Monograph PDF releases are not code-signed today (docs/CODE_SIGNING.md), so the result
is recorded and only enforced when the bundled configuration sets ``require_authenticode``.

Revocation is checked from the local cache only, so the check itself never goes online.
"""

from __future__ import annotations

import sys
from pathlib import Path

VALID, UNSIGNED, INVALID, UNAVAILABLE = "valid", "unsigned", "invalid", "unavailable"


def check(path: Path) -> str:
    if not sys.platform.startswith("win"):
        return UNAVAILABLE
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class WINTRUST_FILE_INFO(ctypes.Structure):
        _fields_ = [("cbStruct", wintypes.DWORD), ("pcwszFilePath", wintypes.LPCWSTR),
                    ("hFile", wintypes.HANDLE), ("pgKnownSubject", ctypes.c_void_p)]

    class WINTRUST_DATA(ctypes.Structure):
        _fields_ = [("cbStruct", wintypes.DWORD), ("pPolicyCallbackData", ctypes.c_void_p),
                    ("pSIPClientData", ctypes.c_void_p), ("dwUIChoice", wintypes.DWORD),
                    ("fdwRevocationChecks", wintypes.DWORD), ("dwUnionChoice", wintypes.DWORD),
                    ("pFile", ctypes.POINTER(WINTRUST_FILE_INFO)), ("dwStateAction", wintypes.DWORD),
                    ("hWVTStateData", wintypes.HANDLE), ("pwszURLReference", wintypes.LPCWSTR),
                    ("dwProvFlags", wintypes.DWORD), ("dwUIContext", wintypes.DWORD),
                    ("pSignatureSettings", ctypes.c_void_p)]

    action = GUID(0xAAC56B, 0xCD44, 0x11D0, (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE))
    info = WINTRUST_FILE_INFO(ctypes.sizeof(WINTRUST_FILE_INFO), str(path), None, None)
    data = WINTRUST_DATA()
    data.cbStruct = ctypes.sizeof(WINTRUST_DATA)
    data.dwUIChoice = 2            # WTD_UI_NONE
    data.fdwRevocationChecks = 0   # WTD_REVOKE_NONE (see dwProvFlags)
    data.dwUnionChoice = 1         # WTD_CHOICE_FILE
    data.pFile = ctypes.pointer(info)
    data.dwStateAction = 0
    data.dwProvFlags = 0x1000      # WTD_CACHE_ONLY_URL_RETRIEVAL: no network
    try:
        wintrust = ctypes.WinDLL("wintrust")
        wintrust.WinVerifyTrust.restype = ctypes.c_long
        rc = wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(data)) & 0xFFFFFFFF
    except OSError:
        return UNAVAILABLE
    if rc == 0:
        return VALID
    if rc in (0x800B0100, 0x800B0003):  # TRUST_E_NOSIGNATURE, TRUST_E_SUBJECT_FORM_UNKNOWN
        return UNSIGNED
    return INVALID
