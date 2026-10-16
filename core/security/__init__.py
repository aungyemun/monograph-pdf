"""PDF security: encryption, permissions, metadata, attachments."""

from core.security.ops import (
    AttachmentInfo,
    EncryptionSettings,
    PermissionFlags,
    apply_password_protection,
    inspect_attachments,
    inspect_metadata,
    inspect_permissions,
    remove_metadata,
    remove_password_protection,
    warn_signed_document,
)

__all__ = [
    "AttachmentInfo",
    "EncryptionSettings",
    "PermissionFlags",
    "apply_password_protection",
    "inspect_attachments",
    "inspect_metadata",
    "inspect_permissions",
    "remove_metadata",
    "remove_password_protection",
    "warn_signed_document",
]
