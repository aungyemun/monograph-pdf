"""PDF compression: lossless optimisation, image recompression, and an exact target-size search.

Units: KB = 1,000 bytes, MB = 1,000,000 bytes, GB = 1,000,000,000 bytes (decimal SI units). Note that
Windows Explorer shows sizes in binary units (1 KB there = 1,024 bytes); KiB/MiB/GiB are accepted for
those. Every comparison is done in bytes.

What compression may change, and what it never changes
------------------------------------------------------
* Lossless (always first): identical objects are merged, unused objects dropped, uncompressed
  streams (content, fonts, images) deflated, objects packed into object streams (PDF 1.5). Pixels,
  text, vector drawings, fonts, annotations, forms, bookmarks, links, page labels and metadata are
  unchanged.
* Lossy (Balanced, Smallest, Target size): only raster images are touched — downsampled to a pixel
  density (ppi, measured at the size the image is *shown* on the page) and/or re-encoded as JPEG at a
  quality. Text stays text, vectors stay vectors; nothing is rasterised. Images that would suffer or
  that compress better losslessly are left alone: 1-bit images (scans in black and white, barcodes,
  QR codes — usually CCITT/JBIG2 already), image masks, images with a /Decode array or a colour-key
  mask, CMYK and other non-RGB/grey colour spaces, and small images (< 64 px).
* Quality floors: an image is never reduced below 100 ppi, or below 150 ppi when it fills a page
  (a scanned page, so small print stays readable), and JPEG quality never goes below 40.
* Target size: lossless first; if that is not small enough, a bounded binary search over a ladder of
  image settings (best quality first) picks the best-quality candidate whose *measured* size is at or
  below the target. If even the floor settings are too large, the result says so (``target_met`` is
  False) and carries the smallest acceptable candidate — it is never reported as a success.
"""

from __future__ import annotations

import io
import math
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz

KB = 1_000
MB = 1_000_000
GB = 1_000_000_000
UNITS = {"B": 1, "KB": KB, "MB": MB, "GB": GB, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3}

MIN_PPI = 100.0
MIN_PPI_SCAN = 150.0
MIN_QUALITY = 40
MIN_IMAGE_PX = 64

# Target-size ladder, best quality first: (ppi, JPEG quality)
LADDER: tuple[tuple[float, int], ...] = (
    (300, 90), (220, 85), (200, 80), (180, 75), (150, 75), (150, 65),
    (130, 60), (120, 55), (110, 50), (100, 45), (100, 40),
)
REFINE_STEPS = 3
MODES = ("lossless", "balanced", "smallest", "target")
MODE_SETTINGS = {"balanced": (150, 75), "smallest": (110, 55)}
MODE_LABELS = {"lossless": "Lossless", "balanced": "Balanced", "smallest": "Smallest file", "target": "Target size"}


class CompressCancelled(Exception):
    pass


# ---------------------------------------------------------------- sizes

_SIZE_RE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-z]*)\s*$")


def parse_size(text: str, default_unit: str = "KB") -> int:
    """'956 KB' -> 956000; '1.99 MB' -> 1990000; '1,5 MB' -> 1500000; bytes are rounded down so the
    limit is never exceeded by rounding."""
    m = _SIZE_RE.match(str(text))
    if not m:
        raise ValueError(f"not a file size: {text!r}")
    value = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or default_unit).upper()
    if unit in ("K", "M", "G"):
        unit += "B"
    if unit not in UNITS:
        raise ValueError(f"unknown unit {m.group(2)!r} (use KB, MB or GB)")
    n = math.floor(value * UNITS[unit] + 1e-6)
    if n <= 0:
        raise ValueError("the size must be greater than zero")
    return n


def format_size(n: int, *, exact: bool = False) -> str:
    """Decimal units, three significant digits: 948213 -> '948 KB'; exact adds the byte count."""
    n = int(n)
    if n < KB:
        s = f"{n} bytes"
    else:
        for unit, size in (("GB", GB), ("MB", MB), ("KB", KB)):
            if n >= size:
                v = n / size
                s = f"{v:.3g} {unit}" if v < 100 else f"{v:.0f} {unit}"
                break
    if exact and n >= KB:
        s += f" ({n:,} bytes)"
    return s


# ---------------------------------------------------------------- analysis

@dataclass
class ImageInfo:
    xref: int
    width: int
    height: int
    bpc: int
    components: int
    colorspace: str
    filters: str
    stream_bytes: int
    ppi: float  # lowest effective pixel density among its placements (largest shown size)
    page_fill: float  # largest fraction of a page it covers
    has_smask: bool
    eligible: bool
    reason: str = ""

    @property
    def scanned(self) -> bool:
        return self.page_fill >= 0.8


@dataclass
class DocProfile:
    file_bytes: int
    pages: int
    page_sizes: list[tuple[int, int]]
    text_chars: int
    images: list[ImageInfo]
    fonts: int
    embedded_fonts: int
    annotations: int
    form_fields: int
    signed: bool
    scanned_pages: int
    vector_pages: int

    @property
    def image_bytes(self) -> int:
        return sum(i.stream_bytes for i in self.images)

    @property
    def eligible_image_bytes(self) -> int:
        return sum(i.stream_bytes for i in self.images if i.eligible)

    def summary(self) -> str:
        parts = [f"{self.pages} page{'s' if self.pages != 1 else ''}"]
        if self.images:
            parts.append(f"{len(self.images)} image{'s' if len(self.images) != 1 else ''} "
                         f"({format_size(self.image_bytes)}, {sum(i.eligible for i in self.images)} reducible)")
        if self.scanned_pages:
            parts.append(f"{self.scanned_pages} scanned page{'s' if self.scanned_pages != 1 else ''}")
        if self.text_chars:
            parts.append("text")
        if self.annotations:
            parts.append(f"{self.annotations} annotation{'s' if self.annotations != 1 else ''}")
        if self.form_fields:
            parts.append(f"{self.form_fields} form field{'s' if self.form_fields != 1 else ''}")
        if self.signed:
            parts.append("digitally signed")
        return ", ".join(parts)


def _image_dict(doc: fitz.Document, xref: int) -> dict[str, str]:
    keys = {}
    for k in ("Filter", "ColorSpace", "BitsPerComponent", "ImageMask", "Decode", "Mask", "SMask", "Width", "Height"):
        t, v = doc.xref_get_key(xref, k)
        keys[k] = "" if t == "null" else v
    return keys


def _is_signed(doc: fitz.Document) -> bool:
    try:
        for page in doc:
            for w in page.widgets() or []:
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    t, _v = doc.xref_get_key(w.xref, "V")
                    if t != "null":
                        return True
    except Exception:  # noqa: BLE001
        pass
    return False


def analyze(doc: fitz.Document, file_bytes: int | None = None) -> DocProfile:
    """Inspect what the document is made of (pages, text, images and how they are shown, fonts,
    annotations, forms, signatures)."""
    placements: dict[int, list[tuple[float, float]]] = {}
    text_chars = scanned = vector_pages = annots = widgets = 0
    sizes: list[tuple[int, int]] = []
    fonts: set[int] = set()
    embedded: set[int] = set()
    for page in doc:
        r = page.rect
        sizes.append((round(r.width), round(r.height)))
        area = max(1.0, r.width * r.height)
        text_chars += len(page.get_text("text").strip())
        page_scan = False
        for info in page.get_image_info(xrefs=True):
            xref = int(info.get("xref") or 0)
            if xref <= 0:
                continue
            a, b, c, d = info["transform"][:4]
            shown_w, shown_h = math.hypot(a, b), math.hypot(c, d)
            if shown_w <= 0 or shown_h <= 0:
                continue
            ppi = min(info["width"] / (shown_w / 72), info["height"] / (shown_h / 72))
            bbox = fitz.Rect(info["bbox"]) & r
            fill = (bbox.width * bbox.height) / area if not bbox.is_empty else 0.0
            placements.setdefault(xref, []).append((ppi, fill))
            page_scan = page_scan or fill >= 0.8
        scanned += page_scan
        try:
            if page.get_drawings():
                vector_pages += 1
        except Exception:  # noqa: BLE001
            pass
        annots += sum(1 for _ in page.annots() or [])
        widgets += sum(1 for _ in page.widgets() or [])
        for f in page.get_fonts(full=True):
            fonts.add(f[0])
            if f[1] and f[1] != "n/a":
                embedded.add(f[0])
    images: list[ImageInfo] = []
    for xref, uses in placements.items():
        keys = _image_dict(doc, xref)
        try:
            raw_len = len(doc.xref_stream_raw(xref) or b"")
        except Exception:  # noqa: BLE001
            raw_len = 0
        try:
            w, h = int(keys["Width"] or 0), int(keys["Height"] or 0)
        except ValueError:
            w = h = 0
        bpc = int(keys["BitsPerComponent"] or 8) if keys["BitsPerComponent"].isdigit() else 8
        cs = keys["ColorSpace"]
        comps = 0
        try:
            pix = fitz.Pixmap(doc, xref) if w * h <= 120_000_000 else None
            if pix is not None:
                comps = pix.n - pix.alpha
                pix = None
        except Exception:  # noqa: BLE001
            comps = 0
        filters = keys["Filter"]
        eligible, reason = True, ""
        if keys["ImageMask"] == "true" or bpc == 1:
            eligible, reason = False, "1-bit image (black-and-white scan, barcode or mask)"
        elif any(f in filters for f in ("JBIG2", "CCITT")):
            eligible, reason = False, "already bi-level compressed"
        elif keys["Decode"]:
            eligible, reason = False, "custom decode array"
        elif keys["Mask"].startswith("["):
            eligible, reason = False, "colour-key mask"
        elif comps not in (1, 3):
            eligible, reason = False, "colour space kept as is (CMYK or special)"
        elif min(w, h) < MIN_IMAGE_PX:
            eligible, reason = False, "small image"
        elif bpc not in (8, 16) and "Indexed" not in cs:
            eligible, reason = False, f"{bpc}-bit samples"
        images.append(ImageInfo(
            xref=xref, width=w, height=h, bpc=bpc, components=comps, colorspace=cs, filters=filters,
            stream_bytes=raw_len, ppi=min(u[0] for u in uses), page_fill=max(u[1] for u in uses),
            has_smask=bool(keys["SMask"]), eligible=eligible, reason=reason,
        ))
    return DocProfile(
        file_bytes=int(file_bytes or 0), pages=doc.page_count, page_sizes=sizes, text_chars=text_chars,
        images=images, fonts=len(fonts), embedded_fonts=len(embedded), annotations=annots,
        form_fields=widgets, signed=_is_signed(doc), scanned_pages=scanned, vector_pages=vector_pages,
    )


# ---------------------------------------------------------------- core operations

def _save_bytes(doc: fitz.Document, *, keep_encryption: bool) -> bytes:
    kwargs: dict[str, Any] = dict(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True)
    kwargs["encryption"] = fitz.PDF_ENCRYPT_KEEP if keep_encryption else fitz.PDF_ENCRYPT_NONE
    try:
        return doc.tobytes(use_objstms=1, **kwargs)
    except TypeError:  # older PyMuPDF without object streams
        return doc.tobytes(**kwargs)


def _settings_for(img: ImageInfo, ppi: float, quality: int) -> tuple[float, int]:
    floor = MIN_PPI_SCAN if img.scanned else MIN_PPI
    return max(ppi, floor), max(quality, MIN_QUALITY)


def _recompress_image(doc: fitz.Document, img: ImageInfo, ppi: float, quality: int) -> bool:
    """Downsample to ``ppi`` (only if the image is denser) and/or re-encode as JPEG ``quality``; the
    stream is replaced only when that makes it at least 10 % smaller. Returns True when replaced."""
    from PIL import Image

    ppi, quality = _settings_for(img, ppi, quality)
    scale = min(1.0, ppi / img.ppi) if img.ppi > 0 else 1.0
    already_jpeg = "DCT" in img.filters
    if scale > 0.97 and already_jpeg and quality >= 85:
        return False  # nothing worthwhile to gain without visible loss
    pix = fitz.Pixmap(doc, img.xref)
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)  # the soft mask is a separate object and is kept as it is
    n = pix.n
    if n == 1:
        im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    elif n == 3:
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        return False
    pix = None
    if scale <= 0.97:
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=int(quality), optimize=True, subsampling=0 if quality >= 85 else 2)
    data = buf.getvalue()
    if len(data) > 0.9 * img.stream_bytes:
        return False
    cs = "/DeviceGray" if n == 1 else "/DeviceRGB"
    keep_cs = img.colorspace.startswith("[") and "ICCBased" in img.colorspace and img.components == n \
        and "Indexed" not in img.colorspace
    doc.update_stream(img.xref, data, compress=False)
    doc.xref_set_key(img.xref, "Filter", "/DCTDecode")
    doc.xref_set_key(img.xref, "DecodeParms", "null")
    doc.xref_set_key(img.xref, "Width", str(im.width))
    doc.xref_set_key(img.xref, "Height", str(im.height))
    doc.xref_set_key(img.xref, "BitsPerComponent", "8")
    if not keep_cs:
        doc.xref_set_key(img.xref, "ColorSpace", cs)
    return True


@dataclass
class Candidate:
    label: str
    ppi: float | None
    quality: int | None
    data: bytes
    images_changed: int

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class CompressResult:
    mode: str
    source_bytes: int
    candidate: Candidate
    profile: DocProfile
    target_bytes: int | None = None
    tried: list[tuple[str, int]] = field(default_factory=list)  # (setting, measured bytes)
    notes: list[str] = field(default_factory=list)

    @property
    def data(self) -> bytes:
        return self.candidate.data

    @property
    def output_bytes(self) -> int:
        return self.candidate.size

    @property
    def lossy(self) -> bool:
        return self.candidate.images_changed > 0

    @property
    def target_met(self) -> bool | None:
        if self.target_bytes is None:
            return None
        return self.output_bytes <= self.target_bytes

    @property
    def reduction_pct(self) -> float:
        return (1 - self.output_bytes / self.source_bytes) * 100 if self.source_bytes else 0.0

    def status(self) -> str:
        size = format_size(self.output_bytes, exact=True)
        if self.target_bytes is None:
            return f"{MODE_LABELS[self.mode]}: {size} ({self.reduction_pct:+.1f}% smaller)".replace("+-", "-")
        if self.target_met:
            return f"Target {format_size(self.target_bytes)} achieved: actual {size}."
        return (f"Target {format_size(self.target_bytes)} cannot be achieved without unacceptable quality loss. "
                f"Smallest acceptable result: {size}.")


class _Work:
    """Re-runs settings on fresh copies of the source; results are cached per setting."""

    def __init__(self, data: bytes, password: str | None, cancel, progress) -> None:
        self.data = data
        self.password = password
        self.cancel = cancel or (lambda: False)
        self.progress = progress or (lambda text, frac: None)
        self.cache: dict[tuple, Candidate] = {}
        with self.open() as doc:
            self.encrypted = bool(doc.is_encrypted or doc.needs_pass)
            self.profile = analyze(doc, len(data))

    def open(self) -> fitz.Document:
        doc = fitz.open("pdf", self.data)
        if doc.needs_pass and not doc.authenticate(self.password or ""):
            doc.close()
            raise PermissionError("The document is password protected; open it with its password first.")
        return doc

    def check(self) -> None:
        if self.cancel():
            raise CompressCancelled()

    def run(self, ppi: float | None, quality: int | None, label: str) -> Candidate:
        key = (ppi, quality)
        if key in self.cache:
            return self.cache[key]
        self.check()
        with self.open() as doc:
            changed = 0
            if ppi is not None:
                eligible = [i for i in self.profile.images if i.eligible]
                for k, img in enumerate(eligible):
                    self.check()
                    self.progress(f"{label}: image {k + 1} of {len(eligible)}", k / max(1, len(eligible)))
                    try:
                        changed += _recompress_image(doc, img, ppi, quality or 75)
                    except Exception:  # noqa: BLE001 — an image that cannot be decoded is kept as it is
                        continue
            self.check()
            data = _save_bytes(doc, keep_encryption=self.encrypted)
        cand = Candidate(label, ppi, quality, data, changed)
        self.cache[key] = cand
        return cand


def compress(
    source: bytes | fitz.Document | Any,
    *,
    mode: str = "lossless",
    target_bytes: int | None = None,
    safety_margin: float = 0.0,
    password: str | None = None,
    cancel: Callable[[], bool] | None = None,
    progress: Callable[[str, float], None] | None = None,
) -> CompressResult:
    """Compress ``source`` (PDF bytes, a fitz.Document or a PdfDocument) in memory; nothing is written.
    Use :func:`write_result` to save. ``safety_margin`` (0–0.2) aims that fraction below the target."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    data = _source_bytes(source)
    work = _Work(data, password, cancel, progress)
    result = None
    lossless = work.run(None, None, "Lossless")
    tried = [("lossless", lossless.size)]
    if mode == "lossless":
        result = CompressResult(mode, len(data), lossless, work.profile, tried=tried)
    elif mode in MODE_SETTINGS:
        ppi, q = MODE_SETTINGS[mode]
        cand = work.run(ppi, q, MODE_LABELS[mode])
        tried.append((f"{ppi:.0f} ppi / JPEG {q}", cand.size))
        best = cand if cand.size < lossless.size else lossless
        result = CompressResult(mode, len(data), best, work.profile, tried=tried)
    else:
        if not target_bytes or target_bytes <= 0:
            raise ValueError("target size mode needs target_bytes")
        aim = int(target_bytes * (1 - max(0.0, min(0.2, safety_margin))))
        if lossless.size <= aim:
            result = CompressResult(mode, len(data), lossless, work.profile, target_bytes, tried)
        elif not any(i.eligible for i in work.profile.images):
            result = CompressResult(mode, len(data), lossless, work.profile, target_bytes, tried)
            result.notes.append("The document has no images that can be reduced; text, fonts and vector "
                                "drawings are already stored losslessly at their smallest.")
        else:
            lo, hi = 0, len(LADDER) - 1
            found: Candidate | None = None
            evaluated: list[Candidate] = []
            # the floor first: if even that is too large, the target is out of reach (2 runs, not 11)
            floor = work.run(*LADDER[hi], f"{LADDER[hi][0]:.0f} ppi / JPEG {LADDER[hi][1]}")
            evaluated.append(floor)
            if floor.size <= aim:
                found = floor
                hi -= 1
                while lo <= hi:  # bounded: at most ceil(log2(len(LADDER))) more runs
                    mid = (lo + hi) // 2
                    c = work.run(*LADDER[mid], f"{LADDER[mid][0]:.0f} ppi / JPEG {LADDER[mid][1]}")
                    evaluated.append(c)
                    if c.size <= aim:
                        found, hi = c, mid - 1
                    else:
                        lo = mid + 1
            if found is not None:
                # refine between the best rung that fits and the next better one (which did not fit):
                # up to REFINE_STEPS runs on interpolated settings, so the result lands close below the target
                k = next(i for i, step in enumerate(LADDER) if (step[0], step[1]) == (found.ppi, found.quality))
                if k > 0:
                    (p_hi, q_hi), (p_lo, q_lo) = LADDER[k - 1], LADDER[k]
                    a, b = 0.0, 1.0  # 0 = fitting rung, 1 = better rung
                    for _ in range(REFINE_STEPS):
                        t = (a + b) / 2
                        ppi = round(p_lo + (p_hi - p_lo) * t)
                        q = round(q_lo + (q_hi - q_lo) * t)
                        if (ppi, q) in ((p_lo, q_lo), (p_hi, q_hi)):
                            break
                        c = work.run(float(ppi), q, f"{ppi} ppi / JPEG {q}")
                        if all(c is not e for e in evaluated):
                            evaluated.append(c)
                        if c.size <= aim:
                            found, a = c, t
                        else:
                            b = t
            tried += [(c.label, c.size) for c in evaluated]
            best = found or min([lossless, *evaluated], key=lambda c: c.size)
            result = CompressResult(mode, len(data), best, work.profile, target_bytes, tried)
            if found is None:
                result.notes.append(
                    f"Reaching the target would need images below {MIN_PPI:.0f} ppi (scanned pages "
                    f"{MIN_PPI_SCAN:.0f} ppi) or JPEG quality below {MIN_QUALITY}, which would make text and "
                    "detail hard to read.")
    skipped = [i for i in work.profile.images if not i.eligible]
    if skipped and mode != "lossless":
        reasons = sorted({i.reason for i in skipped})
        result.notes.append(f"{len(skipped)} image(s) kept unchanged: " + "; ".join(reasons) + ".")
    if work.profile.signed:
        result.notes.append("The document is digitally signed; the compressed copy no longer carries a valid "
                            "signature.")
    if result.output_bytes >= result.source_bytes and mode == "lossless":
        result.notes.append("The file is already stored compactly; lossless optimisation cannot make it smaller.")
    return result


def _source_bytes(source: Any) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    doc = source
    if not isinstance(doc, fitz.Document):
        doc = source._backend._doc
    enc = fitz.PDF_ENCRYPT_KEEP if (doc.is_encrypted or doc.needs_pass) else fitz.PDF_ENCRYPT_NONE
    return doc.tobytes(garbage=0, encryption=enc)


def validate_pdf(data: bytes, *, pages: int | None = None, password: str | None = None) -> None:
    """Raise ValueError unless ``data`` opens as a PDF (with ``pages`` pages) and every page renders."""
    try:
        doc = fitz.open("pdf", data)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"the compressed file is not a valid PDF ({exc})") from None
    try:
        if doc.needs_pass:
            doc.authenticate(password or "")
        if pages is not None and doc.page_count != pages:
            raise ValueError(f"the compressed file has {doc.page_count} pages instead of {pages}")
        for page in doc:
            page.get_pixmap(matrix=fitz.Matrix(0.05, 0.05), alpha=False)
    finally:
        doc.close()


def write_result(result: CompressResult, destination: Path, *, password: str | None = None) -> Path:
    """Validate, then write atomically (a temporary file in the same folder, flushed, then swapped in).
    An existing file at ``destination`` is untouched if anything fails (disk full, permission denied)."""
    destination = Path(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"the folder does not exist: {destination.parent}")
    validate_pdf(result.data, pages=result.profile.pages, password=password)
    part = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex[:8]}.part")
    try:
        with open(part, "wb") as fh:
            fh.write(result.data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(part, destination)
    except BaseException:
        try:
            part.unlink()
        except OSError:
            pass
        raise
    return destination


# ---------------------------------------------------------------- estimate (before running)

_BITS_PER_PIXEL = {90: 2.6, 85: 2.0, 80: 1.7, 75: 1.45, 65: 1.15, 60: 1.0, 55: 0.9, 50: 0.82, 45: 0.74, 40: 0.67}


def estimate_size(profile: DocProfile, ppi: float | None, quality: int | None) -> int:
    """A rough prediction from the analysis alone (no compression is run): non-image data assumed
    unchanged, reducible images at a typical JPEG bit rate. Shown as an *estimate*; the dialog measures
    the real size before anything is saved."""
    other = max(0, profile.file_bytes - profile.image_bytes)
    total = other
    for img in profile.images:
        if ppi is None or not img.eligible:
            total += img.stream_bytes
            continue
        p, q = _settings_for(img, ppi, quality or 75)
        scale = min(1.0, p / img.ppi) if img.ppi else 1.0
        px = img.width * img.height * scale * scale
        bpp = _BITS_PER_PIXEL.get(q) or _BITS_PER_PIXEL[min(_BITS_PER_PIXEL, key=lambda k: abs(k - q))]
        if img.components == 1:
            bpp *= 0.75
        total += min(img.stream_bytes, int(px * bpp / 8))
    return int(total)
