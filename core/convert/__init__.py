"""Offline Convert / Export subsystem — no cloud dependencies.

Names are imported lazily on first use: importing this package (or a light module such as
``core.convert.office_bridge``) no longer loads every converter and its libraries
(python-docx, openpyxl, python-pptx, pdf2docx …), which kept File ▸ Open waiting.
"""

from __future__ import annotations

import importlib

_EXPORTS = {
    "ConversionCapability": "capabilities",
    "Fidelity": "capabilities",
    "UnsupportedConversionError": "capabilities",
    "list_capabilities": "capabilities",
    "copy_pdf_preserving_metadata": "copy_pdf",
    "extract_embedded_images": "extract_images",
    "export_flattened_pdf": "flatten_export",
    "images_to_pdf": "images_to_pdf",
    "office_to_pdf": "office_to_pdf",
    "pages_to_pdf": "pages_to_pdf",
    "pdf_to_docx": "pdf_to_docx",
    "pdf_pages_to_images": "pdf_to_images",
    "pdf_to_pptx": "pdf_to_pptx",
    "pdf_to_plain_text": "pdf_to_text",
    "tables_to_xlsx": "tables_to_xlsx",
    "apply_headers_footers": "watermark",
    "apply_page_numbers": "watermark",
    "apply_watermark": "watermark",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module 'core.convert' has no attribute {name!r}")
    value = getattr(importlib.import_module(f"core.convert.{module}"), name)
    globals()[name] = value
    return value
