"""PyMuPDF backend — read-only open semantics; Save As writes a separate file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from core.document import DocumentMetadata, InvalidPdfError, PasswordRequiredError
from core.page_space import rect_to_display
from core.page_info import PageContent, PageContentKind, PageInfo

# Heuristic: mostly images + little text => scanned/image page
_SCAN_TEXT_THRESHOLD = 40


class MuPdfBackend:
    def __init__(
        self,
        doc: fitz.Document,
        path: Path,
        *,
        was_encrypted: bool = False,
        needs_password: bool = False,
    ) -> None:
        self._doc = doc
        self._path = path
        self._was_encrypted = was_encrypted
        self._needs_password = needs_password
        # Kept in memory only (never written to disk, logs or session data) so that Save can
        # keep the file's password protection.
        self._password: str | None = None
        # True once the permissions password was entered (core/security/protection.py)
        self._owner_unlocked = False
        # Any security handler, also a permissions-only (owner) password that MuPDF unlocks on open
        # (``is_encrypted`` is then False, but the restrictions still apply and must be kept).
        try:
            self._has_security = bool(was_encrypted or needs_password or (doc.metadata or {}).get("encryption"))
        except Exception:  # noqa: BLE001
            self._has_security = bool(was_encrypted or needs_password)

    @classmethod
    def open(cls, path: Path, password: str | None = None) -> "MuPdfBackend":
        path = Path(path)
        try:
            doc = fitz.open(path)
        except Exception as exc:  # noqa: BLE001
            raise InvalidPdfError(f"Cannot open PDF: {exc}") from exc

        # Opening must never modify the source file on disk (read + in-memory only).
        was_encrypted = bool(doc.is_encrypted)
        needs_password = bool(doc.needs_pass)

        if was_encrypted or needs_password:
            if not password:
                doc.close()
                raise PasswordRequiredError("Password required")
            ok = doc.authenticate(password)
            if not ok:
                doc.close()
                raise PasswordRequiredError("Incorrect password")
            owner = bool(int(ok) & 4)  # opened with the permissions (owner) password: every action allowed
        else:
            owner = False

        # Reject empty / non-PDF that somehow opened
        if doc.page_count < 0:
            doc.close()
            raise InvalidPdfError("Invalid PDF structure")

        backend = cls(
            doc,
            path,
            was_encrypted=was_encrypted,
            needs_password=needs_password,
        )
        if was_encrypted or needs_password:
            backend._password = password
        backend._owner_unlocked = owner
        return backend

    @property
    def page_count(self) -> int:
        return int(self._doc.page_count)

    def read_metadata(self) -> DocumentMetadata:
        meta = self._doc.metadata or {}
        perms = self._permissions_dict()
        return DocumentMetadata(
            title=str(meta.get("title") or ""),
            author=str(meta.get("author") or ""),
            subject=str(meta.get("subject") or ""),
            keywords=str(meta.get("keywords") or ""),
            creator=str(meta.get("creator") or ""),
            producer=str(meta.get("producer") or ""),
            creation_date=str(meta.get("creationDate") or ""),
            mod_date=str(meta.get("modDate") or ""),
            page_count=self.page_count,
            encrypted=bool(self._was_encrypted or self._doc.is_encrypted or self._has_security),
            needs_password=bool(self._needs_password),
            permissions=perms,
            has_acroform=self._detect_acroform(),
            has_digital_signatures=self._detect_signatures(),
            format="PDF",
        )

    def _permissions_dict(self) -> dict[str, bool]:
        # PyMuPDF exposes permissions bitmask after auth; map common flags.
        # Never bypass — UI must honor these.
        try:
            p = int(self._doc.permissions)
        except Exception:  # noqa: BLE001
            p = -1
        # Without any security handler every action is allowed. (A negative value is NOT "unknown":
        # MuPDF returns the signed permission bits, e.g. -3388 for "printing only".)
        if not getattr(self, "_has_security", False) and not self._doc.is_encrypted:
            return {
                "print": True,
                "copy": True,
                "edit": True,
                "annotate": True,
                "fill_forms": True,
                "assemble": True,
            }
        # fitz permission bits (PDF spec / MuPDF convention)
        return {
            "print": bool(p & fitz.PDF_PERM_PRINT),
            "copy": bool(p & fitz.PDF_PERM_COPY),
            "edit": bool(p & fitz.PDF_PERM_MODIFY),
            "annotate": bool(p & fitz.PDF_PERM_ANNOTATE),
            "fill_forms": bool(getattr(fitz, "PDF_PERM_FORM", 0) and (p & fitz.PDF_PERM_FORM)),
            "assemble": bool(getattr(fitz, "PDF_PERM_ASSEMBLE", 0) and (p & fitz.PDF_PERM_ASSEMBLE)),
        }

    def _detect_acroform(self) -> bool:
        try:
            if getattr(self._doc, "is_form_pdf", False):
                return True
        except Exception:  # noqa: BLE001
            pass
        try:
            # Fallback: look for widget annotations
            for i in range(min(self.page_count, 50)):
                page = self._doc.load_page(i)
                if page.widgets():
                    return True
        except Exception:  # noqa: BLE001
            pass
        try:
            xref = self._doc.pdf_catalog()
            if xref:
                obj = self._doc.xref_object(xref)
                if obj and "/AcroForm" in obj:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _detect_signatures(self) -> bool:
        try:
            for i in range(min(self.page_count, 100)):
                page = self._doc.load_page(i)
                for widget in page.widgets() or []:
                    field_type = getattr(widget, "field_type", None)
                    # PDF_WIDGET_TYPE_SIGNATURE == 7 in PyMuPDF
                    if field_type == getattr(fitz, "PDF_WIDGET_TYPE_SIGNATURE", 7):
                        return True
                    name = (getattr(widget, "field_name", None) or "").lower()
                    if "signature" in name or "sig" == name:
                        return True
        except Exception:  # noqa: BLE001
            pass
        try:
            # Document-level SigFlags / signature dictionaries
            for xref in range(1, self._doc.xref_length()):
                try:
                    obj = self._doc.xref_object(xref)
                except Exception:  # noqa: BLE001
                    continue
                if obj and "/Type /Sig" in obj.replace(" ", " "):
                    return True
                if obj and "/FT /Sig" in obj:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def analyze_page(self, index: int) -> PageInfo:
        """Page size at once; text / picture analysis on first use (see PageInfo)."""
        page = self._doc.load_page(index)
        rect = page.rect
        return PageInfo(
            index=index,
            width_pt=float(rect.width),
            height_pt=float(rect.height),
            rotation=int(page.rotation),
            analyze=lambda i=index: self._analyze_content(i),
        )

    def _analyze_content(self, index: int) -> PageContent:
        page = self._doc.load_page(index)
        text = page.get_text("text") or ""
        char_count = len(text.strip())
        images = page.get_images(full=True) or []
        image_count = len(images)
        has_text = char_count > 0
        has_images = image_count > 0

        if has_text and has_images:
            if char_count < _SCAN_TEXT_THRESHOLD and image_count >= 1:
                kind = PageContentKind.IMAGE_SCANNED
            else:
                kind = PageContentKind.MIXED
        elif has_text:
            kind = PageContentKind.TEXT
        elif has_images:
            kind = PageContentKind.IMAGE_SCANNED
        else:
            kind = PageContentKind.EMPTY
        return PageContent(kind, has_text, has_images, char_count, image_count)

    def page_text(self, index: int) -> str:
        return self._doc.load_page(index).get_text("text") or ""

    def search(self, query: str, *, case_sensitive: bool = False, cancelled=None) -> list[tuple[int, Any]]:
        """Hits in page text and in form-field values, as (page index, display rect), in page order.
        ``cancelled`` (a callable) stops a long search early."""
        hits: list[tuple[int, Any]] = []
        for i in range(self.page_count):
            if cancelled is not None and cancelled():
                break
            hits.extend((i, r) for r in self.search_page(i, query, case_sensitive=case_sensitive))
        return hits

    def search_page(self, index: int, query: str, *, case_sensitive: bool = False, fields: bool = True) -> list[Any]:
        """Display rects of *query* on one page: page text and form-field values.

        Letters, digits, symbols and Japanese text are found as typed; full-width and half-width forms
        (２月 / 2月, ＡＢＣ / ABC) find each other."""
        variants = search_variants(query)
        page = self._doc.load_page(index)
        # search_for is case-insensitive by default; optionally require exact casing in page text.
        rects: list = []
        textpage = page.get_textpage() if len(variants) > 1 else None  # extracted once for all forms
        if len(variants) > 2 and textpage is not None:
            # look only for the forms that occur on the page at all (a quick text test first)
            plain = " ".join((page.get_text("text", textpage=textpage) or "").split()).casefold()
            variants = [variants[0]] + [v for v in variants[1:] if v.casefold() in plain]
        for q in variants:
            for r in page.search_for(q, textpage=textpage) or []:
                if not any(abs(r.x0 - o.x0) < 0.5 and abs(r.y0 - o.y0) < 0.5 for o in rects):
                    rects.append(r)
        if case_sensitive and rects:
            text = page.get_text("text", textpage=textpage) or ""
            if not any(q in text for q in variants):
                rects = []
        out = [rect_to_display(page, r) for r in rects]
        # Text typed into form fields is not always page text, but users expect Find to find it
        # (``fields=False``: the window searches the values being edited instead of the saved ones)
        try:
            widgets = (page.widgets() or []) if fields else []
        except Exception:  # noqa: BLE001
            widgets = []
        for w in widgets:
            value = str(getattr(w, "field_value", "") or "")
            if not value or w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                continue
            if case_sensitive:
                found = any(q in value for q in variants)
            else:
                found = any(q.casefold() in value.casefold() for q in variants)
            if found:
                r = rect_to_display(page, w.rect)
                if not any(o.intersects(r) for o in out):
                    out.append(r)
        return out

    def render_png(
        self,
        page_index: int,
        *,
        zoom: float,
        dpr: float = 1.0,
        alpha: bool = False,
    ) -> bytes:
        page = self._doc.load_page(page_index)
        # PDF points stay independent; matrix scales for display pixels only.
        scale = max(0.05, float(zoom) * max(0.5, float(dpr)))
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=alpha)
        return pix.tobytes("png")

    def render_rgb(
        self,
        page_index: int,
        *,
        scale: float,
        clip: tuple[float, float, float, float] | None = None,
    ) -> tuple[bytes, int, int, int]:
        """RGB samples of the page (or of ``clip``, display space in points) at ``scale`` pixels per
        point: (samples, width, height, stride). No PNG encoding — used for the on-screen view."""
        page = self._doc.load_page(page_index)
        matrix = fitz.Matrix(scale, scale)
        area = fitz.Rect(clip) & page.rect if clip is not None else None
        pix = page.get_pixmap(matrix=matrix, alpha=False, clip=area, colorspace=fitz.csRGB)
        return bytes(pix.samples), pix.width, pix.height, pix.stride

    def render_thumbnail_png(self, page_index: int, max_edge_px: int = 160) -> bytes:
        page = self._doc.load_page(page_index)
        rect = page.rect
        edge = max(rect.width, rect.height) or 1.0
        zoom = max_edge_px / edge
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")

    def can_save(self) -> bool:
        # Authenticated open is required for encrypted docs; never bypass permissions.
        # Save As creates a new file; refuse only when MuPDF cannot write.
        return self._doc is not None and not self._doc.is_closed

    def save_as(self, destination: Path) -> None:
        destination = Path(destination)
        if destination.resolve() == self._path.resolve():
            # Still a deliberate write; incremental=False rewrites destination only.
            pass
        encrypt = (
            fitz.PDF_ENCRYPT_KEEP if (self._doc.is_encrypted or self._has_security) else fitz.PDF_ENCRYPT_NONE
        )
        # Always write a full new file (not an in-place incremental edit of the source).
        self._doc.save(
            destination.as_posix(),
            garbage=3,
            deflate=True,
            encryption=encrypt,
            incremental=False,
        )

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None  # type: ignore[assignment]


def snapshot_bytes(backend: "MuPdfBackend") -> bytes:
    """The live document as PDF bytes with every object number unchanged (no garbage collection) and
    its encryption kept, for undo of page operations."""
    doc = backend._doc  # noqa: SLF001
    keep = (bool(backend._password) or bool(getattr(backend, "_has_security", False))) \
        and bool((doc.metadata or {}).get("encryption"))  # noqa: SLF001 — also a permissions-only password
    return doc.tobytes(garbage=0, deflate=False, encryption=fitz.PDF_ENCRYPT_KEEP if keep else fitz.PDF_ENCRYPT_NONE)


def restore_bytes(backend: "MuPdfBackend", data: bytes) -> None:
    """Replace the live document with ``data`` from ``snapshot_bytes`` (re-unlocked with the same
    password). The previous document object is left to Python to close: a view may still hold it."""
    doc = fitz.open("pdf", data)
    if doc.needs_pass and backend._password:  # noqa: SLF001
        doc.authenticate(backend._password)  # noqa: SLF001
    backend._doc = doc  # noqa: SLF001


_FULLWIDTH = {c: chr(ord(c) + 0xFEE0) for c in map(chr, range(0x21, 0x7F))}
_FULLWIDTH[" "] = "\u3000"


_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st",
              "ﬆ": "st"}
_GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "zeta": "ζ", "eta": "η",
          "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
          "omicron": "ο", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
          "chi": "χ", "psi": "ψ", "omega": "ω"}
# characters PDFs use interchangeably for the same thing (each group: every member finds the others)
_SAME = [
    ("µ", "μ"),  # micro sign / Greek mu (µM, μm)
    ("Ω", "Ω"),  # ohm sign / Greek capital omega
    ("Å", "Å"),  # angstrom sign / A with ring
    ("-", "−", "–", "‐", "‑"),  # hyphen, minus sign, en dash, hyphen, no-break hyphen
    ("°", "º", "˚"),  # degree, ordinal, ring above
    ("'", "’", "‘", "′"),
    ('"', "“", "”", "″"),
    ("×", "⨯"),
]
_SUPER = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")
_UNSUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
MAX_SEARCH_VARIANTS = 24


def search_variants(query: str) -> list[str]:
    """Every form of *query* worth looking for, the typed one first, without duplicates (at most
    ``MAX_SEARCH_VARIANTS``).

    * spaces and line breaks in the query (pasted text) count as one space; MuPDF finds a phrase
      across line breaks
    * full-width / half-width letters, digits, punctuation and katakana (２月 / 2月, ＡＢＣ / ABC)
    * ligatures (ﬁ → fi: MuPDF extracts ligatures as letters)
    * scientific writing: Greek letters and their names (TNF-alpha / TNF-α, IL-1beta / IL-1β),
      micro sign and Greek mu (µM / μM), ohm / omega, angstrom, minus sign / en dash / hyphen
      (−20 / -20), degree signs, typographic quotes, unit exponents (cm2 / cm², s-1 / s⁻¹)
    * upper and lower case of non-Latin letters (MuPDF folds the case of ASCII letters only:
      Α / α, Β / β, Ü / ü)

    Not folded: other compatibility forms (① does not find every 1) and number formats (1,000 vs
    1000) — they would find unrelated text."""
    import re
    import unicodedata

    q0 = " ".join(str(query or "").split())
    if not q0:
        return []
    q0 = "".join(_LIGATURES.get(c, c) for c in q0)
    half = "".join(
        chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E
        else " " if c == "　"
        else c
        for c in q0
    )
    if any(0xFF61 <= ord(c) <= 0xFF9F for c in q0):  # half-width katakana → full-width
        kana = "".join(unicodedata.normalize("NFKC", c) if 0xFF61 <= ord(c) <= 0xFF9F else c for c in q0)
    else:
        kana = q0
    full = "".join(_FULLWIDTH.get(c, c) for c in half)
    out = list(dict.fromkeys(v for v in (q0, half, full, kana) if v))
    wide = {full} - {q0}  # the full-width form is not varied further (it would only multiply forms)

    def add(v: str) -> None:
        if v and v not in out and len(out) < MAX_SEARCH_VARIANTS:
            out.append(v)

    def spread(fn) -> None:
        for v in list(out):
            if v in wide:
                continue
            for w in fn(v):
                add(w)

    # Greek letters ⇄ their names (whole words or after a hyphen / digit, as in TNF-alpha, IL1beta)
    names = re.compile(r"(?i)(?<![a-z])(" + "|".join(sorted(_GREEK, key=len, reverse=True)) + r")(?![a-z])")
    letters = {v: k for k, v in _GREEK.items()}
    spread(lambda v: [names.sub(lambda m: _GREEK[m.group(1).lower()], v)] if names.search(v) else [])
    spread(lambda v: ["".join(letters.get(c.lower(), c) for c in v)] if any(c.lower() in letters for c in v) else [])
    for group in _SAME:
        present = [c for c in group if any(c in v for v in out)]
        for v in list(out):
            if v in wide:
                continue
            for src in present:
                if src in v:
                    for dst in group:
                        if dst != src:
                            add(v.replace(src, dst))
    # unit exponents: digits right after a letter ⇄ superscript digits
    exp = re.compile(r"(?<=[A-Za-zµμ])(-?[0-9]+)\b")
    spread(lambda v: [exp.sub(lambda m: m.group(1).translate(_SUPER), v)] if exp.search(v) else [])
    spread(lambda v: [v.translate(_UNSUPER)] if any(c in "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺" for c in v) else [])
    # case of non-ASCII letters (Greek, Cyrillic, accented Latin)
    def cased(c: str) -> bool:
        return ord(c) > 127 and c.isalpha() and not 0xFF00 <= ord(c) <= 0xFFEF and c.lower() != c.upper()

    spread(lambda v: [v.lower(), v.upper()] if any(cased(c) for c in v) else [])
    return out
