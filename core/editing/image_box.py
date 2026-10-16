"""Editable placed-image overlay (add/replace/move/resize/crop/rotate/opacity)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.editing.geometry import Rect


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
        )


def export_image_box(box: ImageBox, destination: Path) -> Path:
    """Export the source image (or cropped region) to destination."""
    from PIL import Image

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(box.source_path)
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
