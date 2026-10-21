"""Editable placed-image overlay (add/replace/move/resize/crop/rotate/opacity)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.editing.geometry import Rect

# Pillow decoders allowed for placed pictures (matches the Add image file filters)
SAFE_IMAGE_FORMATS = ["PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP"]


@dataclass
class ImageBox:
    page_index: int
    rect: Rect
    source_path: str  # local file path (project/runtime cache OK)
    opacity: float = 1.0
    rotation: float = 0.0  # degrees
    lock_aspect: bool = True
    # Crop in normalized image coords 0..1 (left, top, right, bottom)
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    z_index: int = 0
    object_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # "signature" for a visual signature (a picture of a signature — not a certificate-based one)
    role: str = ""

    def copy(self) -> "ImageBox":
        return ImageBox(
            page_index=self.page_index,
            rect=Rect(*self.rect.as_tuple()),
            source_path=self.source_path,
            opacity=self.opacity,
            rotation=self.rotation,
            lock_aspect=self.lock_aspect,
            crop=self.crop,
            z_index=self.z_index,
            object_id=str(uuid.uuid4()),
            role=self.role,
        )

    def clone_same_id(self) -> "ImageBox":
        c = self.copy()
        c.object_id = self.object_id
        return c

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "image_box",
            "object_id": self.object_id,
            "page_index": self.page_index,
            "rect": self.rect.as_tuple(),
            "source_path": self.source_path,
            "opacity": self.opacity,
            "rotation": self.rotation,
            "lock_aspect": self.lock_aspect,
            "crop": list(self.crop),
            "z_index": self.z_index,
            "role": self.role,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ImageBox":
        crop = data.get("crop") or [0, 0, 1, 1]
        return ImageBox(
            page_index=int(data["page_index"]),
            rect=Rect(*data["rect"]),
            source_path=str(data["source_path"]),
            opacity=float(data.get("opacity", 1.0)),
            rotation=float(data.get("rotation", 0.0)),
            lock_aspect=bool(data.get("lock_aspect", True)),
            crop=(float(crop[0]), float(crop[1]), float(crop[2]), float(crop[3])),
            z_index=int(data.get("z_index", 0)),
            object_id=str(data.get("object_id") or uuid.uuid4()),
            role=str(data.get("role") or ""),
        )


def export_image_box(box: ImageBox, destination: Path) -> Path:
    """Export the source image (or cropped region) to destination."""
    from PIL import Image

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Only the everyday raster formats are decoded: Pillow's rarely used readers (PSD, FITS,
    # JPEG 2000, ...) are not needed for pictures placed in a PDF and are a larger attack surface.
    im = Image.open(box.source_path, formats=SAFE_IMAGE_FORMATS)
    w, h = im.size
    l, t, r, b = box.crop
    box_px = im.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
    if abs(box.rotation) > 0.01:
        box_px = box_px.rotate(-box.rotation, expand=True, fillcolor=(255, 255, 255))
    if box.opacity < 0.999:
        box_px = box_px.convert("RGBA")
        alpha = box_px.split()[-1].point(lambda p: int(p * max(0.0, min(1.0, box.opacity))))
        box_px.putalpha(alpha)
    box_px.save(destination.as_posix())
    return destination


def default_image_rect(width_px: int, height_px: int, page_w: float, page_h: float, *, x: float = 72.0, y: float = 72.0,
                       max_w: float = 240.0, max_h: float = 180.0):
    """Where a newly added picture goes: at (x, y), as large as fits max_w × max_h (and the page margins) with
    the picture's own proportions. Unknown size falls back to the old fixed box."""
    from core.editing.geometry import Rect

    avail_w = max(24.0, min(max_w, page_w - 2 * 48.0))
    avail_h = max(24.0, min(max_h, page_h - 2 * 48.0))
    if width_px <= 0 or height_px <= 0:
        return Rect(x, y, avail_w, avail_h)
    scale = min(avail_w / width_px, avail_h / height_px)
    return Rect(x, y, max(8.0, width_px * scale), max(8.0, height_px * scale))
