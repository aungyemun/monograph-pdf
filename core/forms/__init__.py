"""AcroForm fields, detection candidates, capabilities, and form bake/flatten."""

from core.forms.fields import FieldType, FormField
from core.forms.acroform import load_acroform_fields, apply_field_values_to_doc
from core.forms.detect import detect_field_candidates
from core.forms.display import (
    looks_like_internal_field_id,
    sanitize_field_value,
    should_paint_field_overlay,
    visible_field_content,
)
from core.forms.capabilities import (
    FormSupportLevel,
    PdfFormCapabilities,
    XfaKind,
    inspect_pdf_capabilities,
)

__all__ = [
    "FieldType",
    "FormField",
    "load_acroform_fields",
    "apply_field_values_to_doc",
    "detect_field_candidates",
    "looks_like_internal_field_id",
    "sanitize_field_value",
    "should_paint_field_overlay",
    "visible_field_content",
    "FormSupportLevel",
    "PdfFormCapabilities",
    "XfaKind",
    "inspect_pdf_capabilities",
]
