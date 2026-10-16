"""Conversion capability registry with explicit fidelity labels."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Fidelity(str, Enum):
    HIGH = "high_confidence"
    BEST_EFFORT = "best_effort"
    UNSUPPORTED = "unsupported"


class UnsupportedConversionError(RuntimeError):
    """Raised when a conversion path is intentionally not implemented."""


@dataclass(frozen=True)
class ConversionCapability:
    key: str
    title: str
    fidelity: Fidelity
    notes: str
    implemented: bool = True


def _office_capability() -> ConversionCapability:
    from core.convert.office_bridge import office_availability

    avail = office_availability()
    if avail.any:
        return ConversionCapability(
            "office_to_pdf",
            "Word / Excel / PowerPoint → PDF",
            Fidelity.HIGH,
            f"Uses {avail.describe()} on this computer, so the layout matches what that application "
            "prints. Nothing is uploaded; macros are never run.",
            implemented=True,
        )
    return ConversionCapability(
        "office_to_pdf",
        "Word / Excel / PowerPoint → PDF",
        Fidelity.UNSUPPORTED,
        "Needs Microsoft Office or LibreOffice installed on this computer (not bundled). "
        "None was found.",
        implemented=False,
    )


def list_capabilities() -> list[ConversionCapability]:
    return [
        ConversionCapability(
            "images_to_pdf",
            "Images → PDF",
            Fidelity.HIGH,
            "One image per page; local files only.",
        ),
        ConversionCapability(
            "pdf_to_images",
            "PDF pages → PNG/JPEG/TIFF",
            Fidelity.HIGH,
            "Each page saved as a picture, at the resolution you choose (72–600 dpi).",
        ),
        ConversionCapability(
            "extract_images",
            "Extract embedded images",
            Fidelity.HIGH,
            "Saves the pictures contained in the PDF, at their original quality (not whole pages).",
        ),
        ConversionCapability(
            "pdf_to_text",
            "PDF → plain text",
            Fidelity.HIGH,
            "Text only, without layout. Scanned pages contain no text: run OCR first.",
        ),
        ConversionCapability(
            "scanned_to_searchable",
            "Scanned PDF → searchable PDF",
            Fidelity.HIGH,
            "Recognizes English and Japanese text on this computer; the scan looks exactly as before.",
        ),
        ConversionCapability(
            "pages_to_pdf",
            "Selected pages → PDF",
            Fidelity.HIGH,
            "Writes a new PDF with the chosen pages; the open document is not changed.",
        ),
        ConversionCapability(
            "flatten_pdf",
            "Flattened PDF",
            Fidelity.HIGH,
            "Form fields and comments become ordinary page content that can no longer be edited.",
        ),
        ConversionCapability(
            "metadata_copy",
            "Copy with metadata",
            Fidelity.HIGH,
            "An exact copy that keeps the title, author and other document information.",
        ),
        ConversionCapability(
            "pdf_to_docx",
            "PDF → Word",
            Fidelity.HIGH,
            "Fonts, colors, paragraphs, tables, images and page size become editable Word content. "
            "Complex layouts may need touching up. Scanned pages need OCR first.",
        ),
        ConversionCapability(
            "tables_to_xlsx",
            "PDF tables → Excel",
            Fidelity.BEST_EFFORT,
            "Tables drawn with lines are found and their cell text is copied; formatting is not kept.",
        ),
        ConversionCapability(
            "pdf_to_pptx",
            "PDF → PowerPoint",
            Fidelity.BEST_EFFORT,
            "Each page becomes a picture on its own slide; the text cannot be edited in PowerPoint.",
        ),
        _office_capability(),
        ConversionCapability(
            "optimize",
            "Reduce file size",
            Fidelity.HIGH,
            "Five levels from Lossless to Minimum file size; each level says whether image quality may drop.",
        ),
        ConversionCapability(
            "watermark_hf",
            "Watermark / header / footer / page numbers",
            Fidelity.HIGH,
            "Added to every chosen page of a new PDF; the open document is not changed.",
        ),
    ]
