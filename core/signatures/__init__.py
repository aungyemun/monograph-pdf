"""Visual signature insertion — distinct from cryptographic digital signatures."""

from core.signatures.ops import (
    SignatureKind,
    insert_drawn_signature,
    insert_image_signature,
    insert_typed_signature,
    signature_disclaimer,
)

__all__ = [
    "SignatureKind",
    "insert_drawn_signature",
    "insert_image_signature",
    "insert_typed_signature",
    "signature_disclaimer",
]
