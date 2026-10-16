"""Password protection, permissions, metadata, attachments — never silently weaken."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fitz

from core.document import DocumentError, PasswordRequiredError, PdfDocument, PermissionError_


@dataclass
class PermissionFlags:
    print: bool = True
    modify: bool = True
    copy: bool = True
    annotate: bool = True
    fill_forms: bool = True
    assemble: bool = True
    print_hq: bool = True

    def to_bitmask(self) -> int:
        bits = 0
        if self.print:
            bits |= int(fitz.PDF_PERM_PRINT)
        if self.modify:
            bits |= int(fitz.PDF_PERM_MODIFY)
        if self.copy:
            bits |= int(fitz.PDF_PERM_COPY)
        if self.annotate:
            bits |= int(fitz.PDF_PERM_ANNOTATE)
        if self.fill_forms and hasattr(fitz, "PDF_PERM_FORM"):
            bits |= int(fitz.PDF_PERM_FORM)
        if self.assemble and hasattr(fitz, "PDF_PERM_ASSEMBLE"):
            bits |= int(fitz.PDF_PERM_ASSEMBLE)
        if self.print_hq and hasattr(fitz, "PDF_PERM_PRINT_HQ"):
            bits |= int(fitz.PDF_PERM_PRINT_HQ)
        return bits

    @staticmethod
    def from_document(document: PdfDocument) -> "PermissionFlags":
        perms = document.metadata().permissions or {}
        return PermissionFlags(
            print=bool(perms.get("print", True)),
            modify=bool(perms.get("edit", True)),
            copy=bool(perms.get("copy", True)),
            annotate=bool(perms.get("annotate", True)),
            fill_forms=bool(perms.get("fill_forms", True)),
            assemble=bool(perms.get("assemble", True)),
            print_hq=bool(perms.get("print", True)),
        )


@dataclass
class EncryptionSettings:
    """Supported offline encryption settings (AES-256 via MuPDF)."""

    user_password: str = ""
    owner_password: str = ""
    algorithm: str = "AES-256"  # only redistributable MuPDF path we ship
    permissions: PermissionFlags = field(default_factory=PermissionFlags)

    def encryption_constant(self) -> int:
        if self.algorithm.upper() in ("AES-256", "AES256", "AES"):
            return int(fitz.PDF_ENCRYPT_AES_256)
        if self.algorithm.upper() in ("AES-128", "AES128"):
            return int(getattr(fitz, "PDF_ENCRYPT_AES_128", fitz.PDF_ENCRYPT_AES_256))
        raise ValueError(f"Unsupported encryption algorithm: {self.algorithm}")


@dataclass
class AttachmentInfo:
    name: str
    size: int | None = None
    description: str = ""


def inspect_permissions(document: PdfDocument) -> PermissionFlags:
    return PermissionFlags.from_document(document)


def inspect_metadata(document: PdfDocument) -> dict[str, str]:
    meta = document.metadata()
    return {
        "title": meta.title,
        "author": meta.author,
        "subject": meta.subject,
        "keywords": meta.keywords,
        "creator": meta.creator,
        "producer": meta.producer,
        "creation_date": meta.creation_date,
        "mod_date": meta.mod_date,
        "encrypted": str(meta.encrypted),
        "has_digital_signatures": str(meta.has_digital_signatures),
    }


def inspect_attachments(document: PdfDocument) -> list[AttachmentInfo]:
    doc: fitz.Document = document._backend._doc  # noqa: SLF001
    out: list[AttachmentInfo] = []
    try:
        names = doc.embfile_names() or []
    except Exception:  # noqa: BLE001
        names = []
    for name in names:
        size = None
        desc = ""
        try:
            info = doc.embfile_info(name) or {}
            size = int(info.get("size") or 0) or None
            desc = str(info.get("desc") or "")
        except Exception:  # noqa: BLE001
            pass
        out.append(AttachmentInfo(name=str(name), size=size, description=desc))
    return out


def apply_password_protection(
    document: PdfDocument,
    destination: Path,
    settings: EncryptionSettings,
) -> Path:
    """
    Write a password-protected copy. Does not modify the source path.
    Requires at least an owner or user password.
    """
    if not settings.user_password and not settings.owner_password:
        raise ValueError("At least one of user or owner password is required")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    # Work on a byte-level copy so the live document is untouched and everything in it —
    # form fields, bookmarks, links, metadata, attachments — is carried over.
    doc = fitz.open("pdf", src.tobytes(garbage=1, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE))
    try:
        # Only a permissions password: the file opens without a password but stays restricted.
        # Only an open password: that password also grants full rights.
        owner = settings.owner_password or settings.user_password
        user = settings.user_password
        doc.save(
            destination.as_posix(),
            encryption=settings.encryption_constant(),
            user_pw=user,
            owner_pw=owner,
            permissions=settings.permissions.to_bitmask(),
            garbage=3,
            deflate=True,
            incremental=False,
        )
    finally:
        doc.close()
    return destination


def remove_password_protection(
    document: PdfDocument,
    destination: Path,
    *,
    password: str,
    content: PdfDocument | None = None,
) -> Path:
    """
    Remove encryption only when a valid password authorizing the operation is supplied.
    Never silently strips protection. The password is always checked against the file of
    ``document``; ``content`` (e.g. the document with its unsaved edits) is what gets written.
    """
    if not password:
        raise PasswordRequiredError("Owner/user password required to remove protection")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Re-open from path to verify password explicitly (do not trust empty password)
    path = document.path
    try:
        probe = fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise DocumentError(str(exc)) from exc
    try:
        if probe.needs_pass or probe.is_encrypted:
            # authenticate() > 0 for a valid user or owner password; 0 = wrong.
            if not probe.authenticate(password):
                raise PasswordRequiredError("Incorrect password — protection not removed")
        # Save the authenticated document itself (not a page copy) so form fields,
        # bookmarks, links, attachments and metadata are all kept.
        source = content._backend._doc if content is not None else probe  # noqa: SLF001
        source.save(
            destination.as_posix(),
            encryption=fitz.PDF_ENCRYPT_NONE,
            garbage=3,
            deflate=True,
        )
    finally:
        probe.close()
    return destination


def remove_metadata(document: PdfDocument, destination: Path) -> Path:
    """Write a copy with info dictionary / XML metadata cleared. Source unchanged."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src: fitz.Document = document._backend._doc  # noqa: SLF001
    doc = fitz.open()
    try:
        doc.insert_pdf(src)
        doc.set_metadata(
            {
                "title": "",
                "author": "",
                "subject": "",
                "keywords": "",
                "creator": "",
                "producer": "",
            }
        )
        try:
            doc.del_xml_metadata()
        except Exception:  # noqa: BLE001
            pass
        # Keep encryption as-is for the copy of content; do not strip passwords here
        encrypt = fitz.PDF_ENCRYPT_KEEP if src.is_encrypted else fitz.PDF_ENCRYPT_NONE
        doc.save(
            destination.as_posix(),
            encryption=encrypt,
            garbage=3,
            deflate=True,
            incremental=False,
        )
    finally:
        doc.close()
    return destination


def warn_signed_document(document: PdfDocument) -> str | None:
    meta = document.metadata()
    if meta.has_digital_signatures:
        return (
            "This PDF appears to contain digital signature fields or signature dictionaries. "
            "Editing, annotating, redacting, or re-saving may invalidate existing cryptographic "
            "signatures. Visual (typed/drawn/image) signatures are not digital certificates."
        )
    return None
