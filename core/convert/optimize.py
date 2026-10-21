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

    # One engine for every compression path (core.convert.compress): the document is compressed as it
    # is — forms, annotations, bookmarks, links, page labels and metadata stay — and written atomically.
    from core.convert.compress import CompressResult, _source_bytes, _Work, write_result

    work = _Work(_source_bytes(src), None, None, None)
    if downsample_images:
        cand = work.run(float(_PRESET_DPI[preset]), int(_PRESET_JPEG[preset]), label)
        lossless = work.run(None, None, "Lossless")
        if lossless.size <= cand.size:
            cand = lossless
    else:
        cand = work.run(None, None, "Lossless")
    if remove_metadata:
        doc = fitz.open("pdf", cand.data)
        try:
            doc.set_metadata({k: "" for k in ("title", "author", "subject", "keywords", "creator", "producer")})
            try:
                doc.del_xml_metadata()
            except Exception:  # noqa: BLE001
                pass
            cand.data = doc.tobytes(garbage=4, deflate=True)
        finally:
            doc.close()
    write_result(CompressResult("lossless", len(work.data), cand, work.profile), destination)
    downsampled = cand.images_changed
    garbage = 4
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
