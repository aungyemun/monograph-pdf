"""macOS LaunchServices integration (no pyobjc: CoreServices through ctypes)."""

from __future__ import annotations

import ctypes
import ctypes.util

BUNDLE_ID = "com.aungyemun.monographpdf"
PDF_UTI = "com.adobe.pdf"
_K_LS_ROLES_ALL = 0xFFFFFFFF
_K_CF_STRING_ENCODING_UTF8 = 0x08000100


def _frameworks():
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    cs = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreServices"))
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cs.LSSetDefaultRoleHandlerForContentType.restype = ctypes.c_int32
    cs.LSSetDefaultRoleHandlerForContentType.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    cs.LSCopyDefaultRoleHandlerForContentType.restype = ctypes.c_void_p
    cs.LSCopyDefaultRoleHandlerForContentType.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    return cf, cs


def _cfstr(cf, text: str):
    return cf.CFStringCreateWithCString(None, text.encode("utf-8"), _K_CF_STRING_ENCODING_UTF8)


def default_pdf_handler() -> str | None:
    """Bundle identifier of the current default PDF app (``None`` when unknown)."""
    cf, cs = _frameworks()
    uti = _cfstr(cf, PDF_UTI)
    try:
        ref = cs.LSCopyDefaultRoleHandlerForContentType(uti, _K_LS_ROLES_ALL)
        if not ref:
            return None
        buf = ctypes.create_string_buffer(512)
        ok = cf.CFStringGetCString(ref, buf, len(buf), _K_CF_STRING_ENCODING_UTF8)
        cf.CFRelease(ref)
        return buf.value.decode("utf-8") if ok else None
    finally:
        cf.CFRelease(uti)


def set_default_pdf_handler(bundle_id: str = BUNDLE_ID) -> tuple[bool, str]:
    """Ask LaunchServices to open PDFs with ``bundle_id``. macOS may ask the user to confirm."""
    try:
        cf, cs = _frameworks()
    except OSError as exc:
        return False, f"CoreServices is not available ({exc})."
    uti, handler = _cfstr(cf, PDF_UTI), _cfstr(cf, bundle_id)
    try:
        status = cs.LSSetDefaultRoleHandlerForContentType(uti, _K_LS_ROLES_ALL, handler)
    finally:
        cf.CFRelease(uti)
        cf.CFRelease(handler)
    if status != 0:
        return False, (f"macOS did not change the default PDF app (error {status}). In Finder choose "
                       "Get Info on a PDF, set “Open with” to Monograph PDF, then click Change All…")
    return True, ("PDF documents now open with Monograph PDF. If macOS asked you to confirm, "
                  "choose “Use Monograph PDF”.")
