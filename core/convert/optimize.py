"""PDF optimization / compression presets (offline)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import fitz

from core.document import PdfDocument
from core.organize.temputil import cleanup_dir, organize_temp_dir


class OptimizePreset(str, Enum):
    """
    User-facing quality modes:

    - LOSSLESS: structural cleanup only — never downsample or recompress rasters
    - HIGH_QUALITY: maximum practical fidelity (alias of conservative image policy)
    - STANDARD: default recommended balance
    - BALANCED: may carefully recompress/downsample oversized images (lossy — labeled)
    - MINIMUM: stronger size reduction (lossy — labeled)

    Legacy aliases CONSERVATIVE / DEFAULT / AGGRESSIVE remain for tests/API stability.
    """

    LOSSLESS = "lossless"
    HIGH_QUALITY = "high_quality"
    STANDARD = "standard"
    BALANCED = "balanced"
    MINIMUM = "minimum"
    # Legacy
    CONSERVATIVE = "conservative"
    DEFAULT = "default"
    AGGRESSIVE = "aggressive"


@dataclass
class OptimizeResult:
    destination: Path
    source_bytes: int
    output_bytes: int
    preset: OptimizePreset
    notes: str
    mode_label: str = ""
    is_lossy: bool = False
    images_touched: int = 0
    reduction_pct: float = 0.0


# Target max edge for raster downsample (approx letter width * dpi)
_PRESET_DPI = {
    OptimizePreset.LOSSLESS: 0,  # unused
    OptimizePreset.HIGH_QUALITY: 200,
    OptimizePreset.STANDARD: 150,
    OptimizePreset.BALANCED: 120,
    OptimizePreset.MINIMUM: 96,
    OptimizePreset.CONSERVATIVE: 150,
    OptimizePreset.DEFAULT: 120,
    OptimizePreset.AGGRESSIVE: 96,
}
_PRESET_JPEG = {
    OptimizePreset.LOSSLESS: 100,
    OptimizePreset.HIGH_QUALITY: 90,
    OptimizePreset.STANDARD: 85,
    OptimizePreset.BALANCED: 70,
    OptimizePreset.MINIMUM: 55,
    OptimizePreset.CONSERVATIVE: 85,
    OptimizePreset.DEFAULT: 70,
    OptimizePreset.AGGRESSIVE: 55,
}
# Only downsample when effective edge clearly exceeds this multiple of target
_OVERSIZE_FACTOR = {
    OptimizePreset.HIGH_QUALITY: 2.5,
    OptimizePreset.STANDARD: 2.0,
    OptimizePreset.BALANCED: 1.5,
    OptimizePreset.MINIMUM: 1.1,
    OptimizePreset.CONSERVATIVE: 2.0,
    OptimizePreset.DEFAULT: 1.5,
    OptimizePreset.AGGRESSIVE: 1.1,
}


def _mode_meta(preset: OptimizePreset) -> tuple[str, bool]:
    if preset == OptimizePreset.LOSSLESS:
        return "Lossless", False
    if preset in (OptimizePreset.HIGH_QUALITY, OptimizePreset.CONSERVATIVE):
        return "High Quality", False  # may skip recompress; still not labeled lossless if downsample on
    if preset in (OptimizePreset.STANDARD, OptimizePreset.DEFAULT):
        return "Standard / Recommended", True
    if preset == OptimizePreset.BALANCED:
        return "Balanced", True
    if preset in (OptimizePreset.MINIMUM, OptimizePreset.AGGRESSIVE):
        return "Minimum / Small File", True
    return preset.value, True


def preview_optimize_size(
    document: PdfDocument,
    preset: OptimizePreset = OptimizePreset.STANDARD,
) -> tuple[int, int]:
    """Return (source_bytes, estimated_output_bytes) via a temp optimize pass."""
    staging = organize_temp_dir(prefix="optprev")
    try:
        tmp = staging / "preview.pdf"
        result = optimize_pdf(document, tmp, preset=preset)
        return result.source_bytes, result.output_bytes
    finally:
        cleanup_dir(staging)


def optimize_pdf(
    document: PdfDocument,
    destination: Path,
    *,
    preset: OptimizePreset = OptimizePreset.STANDARD,
    remove_metadata: bool = False,
    downsample_images: bool | None = None,
) -> OptimizeResult:
    """
    Write an optimized PDF. Source unchanged.

    LOSSLESS never downsamples/recompresses images.
    Other presets may touch rasters only when downsample_images is True (default
    False for LOSSLESS/HIGH_QUALITY, True for STANDARD/BALANCED/MINIMUM).
    """
    preset = OptimizePreset(preset)  # the dialog's combo box hands over the plain value
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    src_path = document.path
    source_bytes = src_path.stat().st_size if src_path.is_file() else 0
    src: fitz.Document = document._backend._doc  # noqa: SLF001

    label, lossy_kind = _mode_meta(preset)
    if downsample_images is None:
        downsample_images = preset not in (
            OptimizePreset.LOSSLESS,
            OptimizePreset.HIGH_QUALITY,
        )

    # Lossless: hard-disable image mutation regardless of caller
    if preset == OptimizePreset.LOSSLESS:
        downsample_images = False

    doc = fitz.open()
    try:
        doc.insert_pdf(src)
        downsampled = 0
        if downsample_images and preset != OptimizePreset.LOSSLESS:
            downsampled = _downsample_images(
                doc,
                dpi=_PRESET_DPI[preset],
                quality=_PRESET_JPEG[preset],
                oversize_factor=_OVERSIZE_FACTOR.get(preset, 1.5),
            )
        if remove_metadata:
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

        garbage = 4 if preset in (OptimizePreset.LOSSLESS, OptimizePreset.MINIMUM, OptimizePreset.AGGRESSIVE) else 3
        save_kwargs: dict = {"garbage": garbage, "deflate": True}
        try:
            doc.save(destination.as_posix(), clean=True, **save_kwargs)
        except TypeError:
            doc.save(destination.as_posix(), **save_kwargs)
    finally:
        doc.close()

    out_bytes = destination.stat().st_size
    src_b = source_bytes or out_bytes
    reduction = (1.0 - (out_bytes / src_b)) * 100.0 if src_b else 0.0
    # True only when this write actually mutated raster streams (mode may still allow it).
    is_lossy = bool(downsampled > 0)
    notes = (
        f"Mode={label}; preset={preset.value}; "
        f"images_touched={downsampled}; garbage={garbage}; deflate=True."
    )
    if preset == OptimizePreset.LOSSLESS:
        notes += " No image downsample/recompress; structural cleanup only."
    elif downsample_images:
        notes += (
            f" Image policy ~{_PRESET_DPI[preset]} DPI / JPEG q={_PRESET_JPEG[preset]} "
            f"(only when clearly oversized)."
        )
    else:
        notes += " Image streams preserved."
    if remove_metadata:
        notes += " Metadata cleared."
    if abs(reduction) < 1.0 and preset == OptimizePreset.LOSSLESS:
        notes += " Little or no size reduction possible without quality loss."

    return OptimizeResult(
        destination=destination,
        source_bytes=src_b,
        output_bytes=out_bytes,
        preset=preset,
        notes=notes,
        mode_label=label,
        is_lossy=is_lossy,
        images_touched=downsampled,
        reduction_pct=reduction,
    )


def _downsample_images(
    doc: fitz.Document,
    *,
    dpi: int,
    quality: int,
    oversize_factor: float = 1.5,
) -> int:
    """Recompress only clearly oversized rasters. Never touch tiny icons."""
    if dpi <= 0:
        return 0
    count = 0
    max_edge = int(11 * dpi * oversize_factor)
    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        if not hasattr(page, "replace_image"):
            return count
        for img in page.get_images(full=True) or []:
            xref = int(img[0])
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
            except Exception:  # noqa: BLE001
                continue
            if pix.width < 64 or pix.height < 64:
                continue
            # Skip if already within policy envelope
            if max(pix.width, pix.height) <= max_edge and quality >= 85:
                continue
            scale = min(1.0, (11 * dpi) / float(max(pix.width, pix.height)))
            try:
                from PIL import Image
                import io

                png = pix.tobytes("png")
                im = Image.open(io.BytesIO(png)).convert("RGB")
                if scale < 0.99:
                    im = im.resize(
                        (max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                        Image.Resampling.LANCZOS,
                    )
                elif quality >= 88:
                    continue
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=quality, optimize=True)
                page.replace_image(xref, stream=buf.getvalue())
                count += 1
            except Exception:  # noqa: BLE001
                continue
    return count
