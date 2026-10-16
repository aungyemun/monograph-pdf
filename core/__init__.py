"""Core domain services (document model, commands, offline utilities)."""

from core.commands import Command, CommandStack
from core.document import (
    DocumentDiagnostics,
    DocumentError,
    DocumentMetadata,
    InvalidPdfError,
    PasswordRequiredError,
    PdfDocument,
    open_document,
)
from core.page_info import PageContentKind, PageInfo
from core.render_cache import RenderCache, RenderKey

__all__ = [
    "Command",
    "CommandStack",
    "DocumentDiagnostics",
    "DocumentError",
    "DocumentMetadata",
    "InvalidPdfError",
    "PasswordRequiredError",
    "PdfDocument",
    "PageContentKind",
    "PageInfo",
    "RenderCache",
    "RenderKey",
    "open_document",
]
