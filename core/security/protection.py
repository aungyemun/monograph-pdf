"""How password-protected, digitally signed and watermarked PDFs are handled by every output.

One place decides, so Save, Save As, Save a Copy, the page-design commands, redaction, conversion to
Word / PowerPoint / Excel / images / text, printing and combining behave the same way.

Password protection
    * A PDF written from a protected PDF keeps its protection: the same open password, permissions
      password, permissions and AES-256 / RC4 settings (MuPDF ``PDF_ENCRYPT_KEEP`` on a full copy).
      Only **Remove Protection** (with a password) or **Protect with Password** change it.
    * The permissions a PDF grants are honoured. With the open password only, an action the PDF
      does not allow needs the **permissions password** (owner password); once entered it counts for
      the rest of the session of that document. Without it the action is not carried out:

      ========================================  ====================
      Action                                     Needs permission
      ========================================  ====================
      Word, PowerPoint, Excel, text, images,     ``copy`` (content copying)
      Extract Images, OCR text export
      Print                                      ``print``
      Save changes; page design; redaction;      ``edit`` (changing the document)
      page organisation; Flatten
      Combine / extract / split pages             ``assemble``
      Change the protection                       the permissions password, always
      ========================================  ====================

Digital signatures (certificate-based)
    * An unchanged signed PDF saved under another name is copied byte for byte, so its signatures
      stay valid.
    * Saving changes rewrites the file and makes the existing signatures invalid; Monograph PDF says
      so before saving and suggests saving under a new name.
    * Word, PowerPoint and image exports show how a signature looks, but no exported file is
      digitally signed.

Watermarks
    * Watermarks, headers, footers and backgrounds are part of the pages and are kept in every
      output. Marks added by Monograph PDF that are still removable can be left out of a Word /
      PowerPoint / image export when the user asks; a *locked* watermark (Protect with Password ▸
      lock the watermark) and every watermark made by other programs always stay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fitz

PERMISSION_LABELS = {
    "copy": "copying or extracting its content",
    "print": "printing",
    "edit": "changes to the document",
    "assemble": "combining, extracting or reordering pages",
    "annotate": "adding comments",
    "fill_forms": "filling in form fields",
    "owner": "changes to its security settings",
}

# what each kind of action needs
ACTION_PERMISSION = {
    "export": "copy",
    "print": "print",
    "save_changes": "edit",
    "assemble": "assemble",
}


def is_protected(doc: fitz.Document) -> bool:
    """True for a PDF with a security handler (open password and/or permissions password), also once
    unlocked. (``is_encrypted`` turns False after unlocking and is always False for a PDF with only a
    permissions password; ``needs_pass`` must not be read on an unlocked document — with PyMuPDF
    1.25 that resets the unlocked state.)"""
    try:
        return bool((doc.metadata or {}).get("encryption"))
    except Exception:  # noqa: BLE001
        return False


def _backend(document):
    return getattr(document, "_backend", None)


def _live(document) -> fitz.Document | None:
    backend = _backend(document)
    doc = getattr(backend, "_doc", None) if backend is not None else None
    if doc is None or getattr(doc, "is_closed", True):
        return None
    return doc


def owner_unlocked(document) -> bool:
    return bool(getattr(_backend(document), "_owner_unlocked", False))


def raw_permissions(doc: fitz.Document) -> dict[str, bool]:
    """Permissions recorded in the PDF (all allowed without a security handler)."""
    if not is_protected(doc):
        return {k: True for k in PERMISSION_LABELS if k != "owner"}
    try:
        p = int(doc.permissions)
    except Exception:  # noqa: BLE001
        return {k: True for k in PERMISSION_LABELS if k != "owner"}
    return {
        "print": bool(p & fitz.PDF_PERM_PRINT),
        "copy": bool(p & fitz.PDF_PERM_COPY),
        "edit": bool(p & fitz.PDF_PERM_MODIFY),
        "annotate": bool(p & fitz.PDF_PERM_ANNOTATE),
        "fill_forms": bool(p & getattr(fitz, "PDF_PERM_FORM", 0)),
        "assemble": bool(p & getattr(fitz, "PDF_PERM_ASSEMBLE", 0)),
    }


def effective_permissions(document) -> dict[str, bool]:
    """What the person working on ``document`` may do now: everything with the permissions password
    (MuPDF keeps reporting the recorded restrictions even then), otherwise what the PDF allows."""
    doc = _live(document)
    if doc is None or not is_protected(doc) or owner_unlocked(document):
        return {k: True for k in PERMISSION_LABELS if k != "owner"}
    return raw_permissions(doc)


def allowed(document, permission: str) -> bool:
    """``permission``: a key of :data:`PERMISSION_LABELS`; "owner" = only with the permissions password
    (changing the protection of a protected PDF)."""
    if permission == "owner":
        doc = _live(document)
        return doc is None or not is_protected(doc) or owner_unlocked(document)
    return bool(effective_permissions(document).get(permission, True))


def unlock_with_owner_password(document, password: str) -> bool:
    """Check ``password`` as the permissions (owner) password of ``document``'s file; on success all
    actions are allowed for this document until it is closed. Nothing is written."""
    backend = _backend(document)
    doc = _live(document)
    if backend is None or doc is None or not password:
        return False
    try:
        with fitz.open(Path(document.path)) as probe:
            level = int(probe.authenticate(password))
    except Exception:  # noqa: BLE001
        return False
    if level & 4:  # 4 = owner (permissions) password; 2 = open password only
        backend._owner_unlocked = True  # noqa: SLF001
        return True
    return False


def signed_signature_count(doc: fitz.Document) -> int:
    """Number of signature fields that carry a signature (a /V value with a /ByteRange). Empty
    signature fields waiting to be signed are not counted."""
    count = 0
    try:
        for page in doc:
            for widget in page.widgets() or []:
                if widget.field_type != getattr(fitz, "PDF_WIDGET_TYPE_SIGNATURE", 7):
                    continue
                kind, val = doc.xref_get_key(widget.xref, "V")
                if kind == "xref":
                    vx = int(val.split()[0])
                    if doc.xref_get_key(vx, "ByteRange")[0] != "null" or doc.xref_get_key(vx, "Contents")[0] != "null":
                        count += 1
                elif kind == "dict" and "ByteRange" in val:
                    count += 1
    except Exception:  # noqa: BLE001
        return count
    return count


def other_watermarks(doc: fitz.Document, *, max_pages: int = 30) -> bool:
    """True when a watermark made by another program is recognisable: a Watermark annotation or
    content marked as a watermark artifact (``/Artifact <</Subtype /Watermark``)."""
    try:
        for i in range(min(doc.page_count, max_pages)):
            page = doc.load_page(i)
            for annot in page.annots() or []:
                if (annot.type[1] or "").lower() == "watermark":
                    return True
            for xref in page.get_contents():
                data = doc.xref_stream(xref) or b""
                if b"/Watermark" in data and b"/Artifact" in data:
                    return True
    except Exception:  # noqa: BLE001
        return False
    return False


@dataclass
class ProtectionInfo:
    protected: bool = False
    open_password: bool = False
    owner_unlocked: bool = False
    permissions: dict[str, bool] = field(default_factory=dict)
    signatures: int = 0
    marks: dict[str, int] = field(default_factory=dict)  # removable Monograph PDF marks by kind
    other_watermarks: bool = False

    @property
    def restricted(self) -> list[str]:
        return [k for k, v in self.permissions.items() if not v]

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.protected:
            if self.open_password:
                lines.append("Password-protected: copies and saved versions keep the same passwords and permissions.")
            else:
                lines.append("Has a permissions password: copies and saved versions keep it and its restrictions.")
            if self.restricted and not self.owner_unlocked:
                lines.append("Not allowed without the permissions password: "
                             + "; ".join(PERMISSION_LABELS[k] for k in self.restricted) + ".")
        if self.signatures:
            lines.append(f"Digitally signed ({self.signatures} signature{'s' if self.signatures != 1 else ''}): "
                         "saving changes makes the signatures invalid; an unchanged copy keeps them valid. "
                         "Exported files show the signature's appearance but are not digitally signed.")
        if self.marks:
            lines.append("Has a watermark, header/footer or background added with Monograph PDF: kept in every "
                         "output unless you choose to leave it out of an export.")
        if self.other_watermarks:
            lines.append("Has a watermark made by another program: it stays in every output.")
        return lines


def protection_info(document) -> ProtectionInfo:
    doc = _live(document)
    if doc is None:
        return ProtectionInfo()
    info = ProtectionInfo(
        protected=is_protected(doc),
        open_password=bool(getattr(_backend(document), "_needs_password", False)),
        owner_unlocked=owner_unlocked(document),
        permissions=effective_permissions(document),
        signatures=signed_signature_count(doc),
        other_watermarks=other_watermarks(doc),
    )
    try:
        from core.convert.page_marks import count_marks

        info.marks = {k: v for k, v in count_marks(doc).items() if v}
    except Exception:  # noqa: BLE001
        info.marks = {}
    return info


# --------------------------------------------------------------------------- writing copies
def working_copy(document, *, keep_encryption: bool = True) -> fitz.Document:
    """A full, independent copy of the live document (unsaved page changes, forms, bookmarks,
    attachments included). A protected document's copy keeps its security handler and is unlocked
    with the password used to open it, so :func:`save_copy` writes it protected again."""
    live = _live(document)
    if live is None:
        raise RuntimeError("The document is closed.")
    password = getattr(_backend(document), "_password", None)
    if keep_encryption and is_protected(live):
        data = live.tobytes(garbage=0, deflate=False, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc = fitz.open("pdf", data)
        if not doc.needs_pass or (password and doc.authenticate(password)):
            return doc
        doc.close()
        raise RuntimeError("The protected copy could not be unlocked.")
    return fitz.open("pdf", live.tobytes(garbage=0, deflate=False, encryption=fitz.PDF_ENCRYPT_NONE))


def save_copy(doc: fitz.Document, destination: Path, **kwargs) -> Path:
    """Save ``doc`` (made with :func:`working_copy`) keeping any protection it has."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    kwargs.setdefault("garbage", 3)
    kwargs.setdefault("deflate", True)
    kwargs["encryption"] = fitz.PDF_ENCRYPT_KEEP if is_protected(doc) else fitz.PDF_ENCRYPT_NONE
    doc.save(destination.as_posix(), **kwargs)
    return destination


def copy_file_exactly(document, destination: Path) -> Path:
    """Byte-for-byte copy of the file on disk (keeps digital signatures valid and the protection as is)."""
    import shutil

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if Path(document.path).resolve() != destination.resolve():
        shutil.copyfile(document.path, destination)
    return destination


def export_source_without_marks(document, kinds: set[str]) -> fitz.Document:
    """Unprotected in-memory copy for an export, without the removable Monograph PDF marks of
    ``kinds``. Locked marks and other programs' watermarks are part of the page and stay."""
    from core.convert.page_marks import _remove_on_page  # noqa: PLC2701

    doc = working_copy(document, keep_encryption=False)
    for page in doc:
        _remove_on_page(page, set(kinds))
    return doc
