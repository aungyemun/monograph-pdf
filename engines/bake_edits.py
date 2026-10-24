"""Bake editable overlays into a MuPDF document at Save time (source untouched until then)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from core.editing.edit_model import EditableDocument
from core.editing.image_box import SAFE_IMAGE_FORMATS
from core.editing.font_resolver import resolve_font
from core.editing.text_box import TextAlign, VAlign
from core.editing.text_layout import layout_text_box
from core.page_space import rect_to_page


def _parse_color(hex_color: str) -> tuple[float, float, float] | None:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) == 8:
        # ARGB
        a = int(h[0:2], 16)
        if a == 0:
            return None
        h = h[2:]
    if len(h) != 6:
        return None
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b)


def _is_protected(doc: fitz.Document) -> bool:
    """True for a password-protected PDF, also once it has been unlocked.

    Never uses ``doc.needs_pass`` on an unlocked document: with PyMuPDF 1.25 reading it resets
    the unlocked state, and a later save that keeps the encryption writes unreadable streams.
    """
    try:
        return bool((doc.metadata or {}).get("encryption"))
    except Exception:  # noqa: BLE001
        return False


def _working_copy(edit: EditableDocument, *, keep_encryption: bool = True) -> fitz.Document:
    """
    Prefer the live in-memory MuPDF document (includes unsaved page organize ops).
    Fall back to reopening the source path.

    Deep-copy via tobytes() — insert_pdf() can share xref state with the source so
    later edits (e.g. insert_textbox) would mutate/destroy the live AcroForm/XFA.

    A password-protected document stays protected (same passwords and permissions) unless
    ``keep_encryption`` is False (temporary copies for printing and exports).
    """
    backend = getattr(edit.pdf, "_backend", None)
    live = getattr(backend, "_doc", None) if backend is not None else None
    password = getattr(backend, "_password", None) if backend is not None else None
    if live is not None and not getattr(live, "is_closed", True):
        # Also a PDF with only a permissions (owner) password: it opens without a password, but
        # saving must keep its owner password and restrictions instead of silently removing them.
        if keep_encryption and _is_protected(live):
            try:
                data = live.tobytes(garbage=0, deflate=False, encryption=fitz.PDF_ENCRYPT_KEEP)
                doc = fitz.open("pdf", data)
                if not doc.needs_pass or (password and doc.authenticate(password)):
                    return doc
                doc.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            data = live.tobytes(garbage=0, deflate=False)
            return fitz.open("pdf", data)
        except Exception:  # noqa: BLE001
            # Last resort: path reopen (loses unsaved organize ops)
            pass
    src = edit.pdf.path
    doc = fitz.open(src)
    if doc.needs_pass:
        doc.close()
        raise RuntimeError("Encrypted document requires password for save bake.")
    return doc


def _draw_text_box(page: fitz.Page, rect: fitz.Rect, box, family: str, fontsize: float) -> None:
    """Write a text box's text: Japanese and other scripts, the box's font, bold, italic,
    underline, alignment and line spacing — the same renderer as form-field entries.

    Drawn on a scratch page cut down to the characters used, then placed on the page as one
    unit, so only those glyphs are embedded and the text stays selectable and searchable.
    """
    from types import SimpleNamespace

    from core.forms.appearance import draw_text

    entry = SimpleNamespace(
        value=box.text,
        runs=[dict(r) for r in (getattr(box, "runs", None) or [])],  # words with their own font / size / colour
        font_family=family or box.style.font_family,
        font_size=float(fontsize),
        bold=bool(box.style.bold),
        italic=bool(box.style.italic),
        text_color=box.style.text_color or "#000000",
        align=getattr(box.align, "value", "left"),
        valign=getattr(box.valign, "value", "top"),
        multiline=bool(getattr(box.style, "wrap", True)),
        character_spacing=float(getattr(box.style, "character_spacing", 0.0) or 0.0),
    )
    scratch = fitz.open()
    try:
        sp = scratch.new_page(width=rect.width, height=rect.height)
        draw_text(
            sp,
            sp.rect,
            entry,
            pad=0.0,
            multiline=True,  # a text box keeps its own line breaks
            wrap=entry.multiline,  # Wrap Text off: long lines run on (and are cut at the box edge)
            line_factor=float(getattr(box.style, "line_spacing", 1.2) or 1.2),
            underline=bool(getattr(box.style, "underline", False)),
            opacity=max(0.0, min(1.0, float(getattr(box.style, "opacity", 1.0)))),
        )
        scratch.subset_fonts()
        page.show_pdf_page(rect, scratch, 0, keep_proportion=False, overlay=True)
    finally:
        scratch.close()


def _span_page(span_id: str) -> int | None:
    if span_id.startswith("p"):
        try:
            return int(span_id.split("-")[0][1:])
        except ValueError:
            return None
    return None


def remove_native_spans(doc: fitz.Document, edit: EditableDocument) -> int:
    """Remove the glyphs of every replaced native span (``edit.native_replacements``). Returns the
    number of spans processed. Plans saved by earlier versions without a rectangle use the bound text
    box's rectangle."""
    from core.editing.native_text import removal_rect

    boxes = {b.native_span_id: b for b in edit.all_objects() if getattr(b, "replaces_native", False)}
    pages: set[int] = set()
    for plan in edit.native_replacements.values():
        sid = str(plan.get("span_id") or "")
        page_index = _span_page(sid)
        rect_t = plan.get("rect")
        if rect_t is None and sid in boxes:
            r = boxes[sid].rect
            rect_t = (r.x + 0.5, r.y + 0.5, max(0.1, r.w - 1), max(0.1, r.h - 1))
        if page_index is None or rect_t is None or not (0 <= page_index < doc.page_count):
            continue
        page = doc.load_page(page_index)
        x, y, w, h = removal_rect(tuple(rect_t))
        page.add_redact_annot(rect_to_page(page, fitz.Rect(x, y, x + w, y + h)), fill=False)
        pages.add(page_index)
    for pi in pages:
        doc.load_page(pi).apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                           graphics=getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0),
                                           text=getattr(fitz, "PDF_REDACT_TEXT_REMOVE", 0))
    return len(pages)


def _alpha(hex_color: str) -> float:
    """Alpha of #AARRGGBB (1.0 for #RRGGBB)."""
    h = (hex_color or "").strip().lstrip("#")
    return int(h[0:2], 16) / 255.0 if len(h) == 8 else 1.0


def _place_turned(page: fitz.Page, rect: fitz.Rect, scratch: fitz.Document, angle: float) -> None:
    """Place scratch page 0 (drawn upright at ``rect``'s size) turned clockwise by ``angle`` about the
    centre of ``rect``; the target grows to the turned outline so nothing is scaled."""
    import math

    a = math.radians(angle)
    w, h = rect.width, rect.height
    bw = abs(w * math.cos(a)) + abs(h * math.sin(a))
    bh = abs(w * math.sin(a)) + abs(h * math.cos(a))
    cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
    target = fitz.Rect(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
    # show_pdf_page turns counter-clockwise for positive angles
    page.show_pdf_page(target, scratch, 0, keep_proportion=True, overlay=True, rotate=-angle)


class _OverlayTargets:
    """Where overlays are drawn at Save.

    Editor geometry is in display space (the page as shown after /Rotate), but MuPDF draws into the
    unrotated page. On a turned page the overlays are therefore drawn upright on a scratch page of
    the displayed size and placed onto the real page turned back by the page's rotation, so every
    object lands exactly where it was on screen and reads the right way up. Unrotated pages are
    drawn on directly. The page's own content is never touched.
    """

    def __init__(self, doc: fitz.Document) -> None:
        self.doc = doc
        self._scratch: fitz.Document | None = None
        self._pages: dict[int, int] = {}

    def page(self, index: int) -> fitz.Page:
        real = self.doc.load_page(index)
        if not real.rotation:
            return real
        if self._scratch is None:
            self._scratch = fitz.open()
        if index not in self._pages:
            sp = self._scratch.new_page(width=real.rect.width, height=real.rect.height)
            self._pages[index] = sp.number
        return self._scratch.load_page(self._pages[index])

    def merge(self) -> None:
        for index, number in self._pages.items():
            real = self.doc.load_page(index)
            target = real.rect * real.derotation_matrix
            target.normalize()
            real.show_pdf_page(target, self._scratch, number, rotate=int(real.rotation), keep_proportion=False, overlay=True)

    def close(self) -> None:
        if self._scratch is not None:
            self._scratch.close()
            self._scratch = None


def overlays_in_order(edit: EditableDocument) -> list[tuple[str, Any]]:
    """Every text box, picture and shape, bottom first (by z-order; ties keep text, picture, shape)."""
    items = [("text", o) for o in edit.all_objects()]
    items += [("image", o) for o in getattr(edit, "images", {}).values()]
    items += [("shape", o) for o in getattr(edit, "shapes", {}).values()]
    rank = {"text": 0, "image": 1, "shape": 2}
    return sorted(items, key=lambda it: (int(getattr(it[1], "z_index", 0)), rank[it[0]]))


def _symbols_only(text: str) -> bool:
    """True for text made only of symbols, digits and punctuation (✓ ★ → ① 〒 …), no letters."""
    import unicodedata

    t = (text or "").strip()
    return bool(t) and all(unicodedata.category(c)[0] in "SNPZ" for c in t)


def _bake_text_box(targets: "_OverlayTargets", box) -> None:
    """Draw one text box overlay (opacity, letter spacing and a turn, as on screen)."""
    page = targets.page(box.page_index)
    layout = layout_text_box(box)
    res = resolve_font(box.style.font_family, box.text)
    family = layout.resolved_font or res.resolved
    # The font the user picked is used (and embedded) when it is installed and may be embedded;
    # characters it lacks (Japanese in a Latin font ...) fall back inside draw_text. Only when it
    # is missing does the resolver's substitute take over, and the user is told.
    from core.editing import system_fonts

    wanted = (box.style.font_family or "").strip()
    if wanted and system_fonts.find_font_file(wanted):
        family = wanted
    elif wanted and not _symbols_only(box.text):
        # (a symbol from Insert ▸ Symbol is drawn by the built-in font without a notice)
        system_fonts.note_fallback(wanted, f"this font is not installed; saved with {family}")
    fontsize = layout.font_size
    pad = box.style.padding
    # Ensure bake rect is tall enough for MuPDF insert_textbox (needs slack).
    bake_h = max(box.rect.h, layout.content_height + 2 * pad + fontsize * 0.35)
    rect = fitz.Rect(box.rect.x, box.rect.y, box.rect.x1, box.rect.y + bake_h)

    opacity = max(0.0, min(1.0, float(getattr(box.style, "opacity", 1.0) or 0.0)))
    angle = float(getattr(box.style, "rotation", 0.0) or 0.0) % 360.0
    turned = min(angle, 360.0 - angle) > 0.01
    # A turned box is drawn upright on a scratch page of its size and placed turned about its
    # centre (clockwise, as on screen), like a turned picture.
    scratch = fitz.open() if turned else None
    try:
        if scratch is not None:
            draw_on = scratch.new_page(width=rect.width, height=rect.height)
            local = fitz.Rect(0, 0, rect.width, rect.height)
        else:
            draw_on, local = page, rect
        bg = _parse_color(box.style.background_color)
        if bg is not None:
            draw_on.draw_rect(local, color=None, fill=bg, width=0, fill_opacity=opacity * _alpha(box.style.background_color))
        border = _parse_color(box.style.border_color)
        if border is not None and box.style.border_width > 0:
            draw_on.draw_rect(local, color=border, fill=None, width=box.style.border_width,
                              stroke_opacity=opacity * _alpha(box.style.border_color))
        text_rect = fitz.Rect(local.x0 + pad, local.y0 + pad, local.x1 - pad, local.y1 - pad)
        if box.text and text_rect.width > 1 and text_rect.height > 1:
            earlier = system_fonts.take_notes()
            _draw_text_box(draw_on, text_rect, box, family, fontsize)
            # only the font the user picked is worth reporting; the resolver's own stand-ins are not
            mine = system_fonts.take_notes()
            for fam, why in {**earlier, **{k: v for k, v in mine.items() if k == wanted}}.items():
                system_fonts.note_fallback(fam, why)
        if scratch is not None:
            _place_turned(page, rect, scratch, angle)
    finally:
        if scratch is not None:
            scratch.close()
    _ = family  # reserved for embedded-font path


def _bake_image(targets: "_OverlayTargets", img) -> None:
    """Draw one placed picture (opacity, crop and a turn, as on screen)."""
    try:
        page = targets.page(img.page_index)
        rect = fitz.Rect(img.rect.x, img.rect.y, img.rect.x1, img.rect.y1)
        path = Path(img.source_path)
        if not path.is_file():
            return
        # Opacity, crop or a turn: render the picture with Pillow, then place the result
        opacity = max(0.0, min(1.0, float(getattr(img, "opacity", 1.0))))
        angle = float(getattr(img, "rotation", 0.0)) % 360.0
        turned = min(angle, 360.0 - angle) > 0.01
        if opacity < 0.999 or turned or any(c != v for c, v in zip(img.crop, (0.0, 0.0, 1.0, 1.0))):
            from PIL import Image
            import io

            # Everyday raster formats only: Pillow's rarely used decoders are never run on a user file
            pil = Image.open(path.as_posix(), formats=SAFE_IMAGE_FORMATS).convert("RGBA")
            w, h = pil.size
            l, t, r, b = img.crop
            pil = pil.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
            target = rect
            if turned:
                # Same as the canvas: stretch the picture to its box, then turn it about the
                # box centre. The turned picture is larger than the box, so the rectangle it
                # is placed in grows around the same centre and nothing is squeezed or cut.
                k = max(0.5, min(8.0, pil.width / max(rect.width, 1.0)))
                k = min(k, 4000.0 / max(rect.width, rect.height, 1.0))
                pil = pil.resize(
                    (max(1, round(rect.width * k)), max(1, round(rect.height * k))), Image.Resampling.BICUBIC
                )
                pil = pil.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
                cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
                target = fitz.Rect(
                    cx - pil.width / k / 2, cy - pil.height / k / 2, cx + pil.width / k / 2, cy + pil.height / k / 2
                )
            if opacity < 0.999:
                alpha = pil.split()[-1].point(lambda p: int(p * opacity))
                pil.putalpha(alpha)
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            _place_image(page, target, {"stream": buf.getvalue()}, behind=getattr(img, "layer", "front") == "behind")
        else:
            _place_image(page, rect, {"filename": path.as_posix()}, behind=getattr(img, "layer", "front") == "behind")
    except Exception:  # noqa: BLE001
        return


_MULTIPLY_GS = "MPDFBehind"


def _add_ext_gstate(doc: fitz.Document, page_xref: int, name: str, value: str) -> None:
    """Add ExtGState ``name`` to a page's resources (inline or indirect dictionaries)."""
    kind, val = doc.xref_get_key(page_xref, "Resources")
    if kind == "xref":
        holder, prefix = int(val.split()[0]), ""
    else:
        holder, prefix = page_xref, "Resources/"
        if kind == "null":
            doc.xref_set_key(page_xref, "Resources", "<<>>")
    kind2, val2 = doc.xref_get_key(holder, prefix + "ExtGState")
    if kind2 == "xref":
        doc.xref_set_key(int(val2.split()[0]), name, value)
    elif kind2 == "null":
        doc.xref_set_key(holder, prefix + "ExtGState", f"<</{name} {value}>>")
    else:
        doc.xref_set_key(holder, prefix + "ExtGState/" + name, value)


def _place_image(page: fitz.Page, rect: fitz.Rect, source: dict, *, behind: bool) -> None:
    """Insert a picture. ``behind``: drawn with *multiply* blending, so the page's text, lines and
    any picture already there show through it as if the picture were printed beneath them. This
    also works on scanned pages and on pages whose content paints an opaque white background (a
    picture placed under the content would be hidden there). The page text stays selectable."""
    # keep_proportion=False: the picture fills its box exactly as on screen (a box stretched with
    # "Lock aspect ratio" off was saved letterboxed before)
    if not behind:
        page.insert_image(rect, keep_proportion=False, **source)
        return
    scratch = fitz.open()
    try:
        full = page.rect
        sp = scratch.new_page(width=full.width, height=full.height)
        sp.insert_image(rect - (full.x0, full.y0, full.x0, full.y0), keep_proportion=False, **source)
        for xref in sp.get_contents():
            scratch.update_stream(xref, b"q /" + _MULTIPLY_GS.encode() + b" gs\n" + scratch.xref_stream(xref) + b"\nQ")
        _add_ext_gstate(scratch, sp.xref, _MULTIPLY_GS, "<</Type/ExtGState/BM/Multiply>>")
        page.show_pdf_page(full, scratch, 0, keep_proportion=False, overlay=True)
    finally:
        scratch.close()


def _bake_shape(targets: "_OverlayTargets", shape) -> None:
    """Draw one vector shape (opacity, dash style and a turn about its box centre, as on screen)."""
    try:
        page = targets.page(shape.page_index)
        stroke = _parse_color(getattr(shape, "stroke_color", "#000000")) or (0, 0, 0)
        fill_hex = getattr(shape, "fill_color", "#00000000")
        fill = _parse_color(fill_hex)
        width = float(getattr(shape, "stroke_width", 1.5) or 1.5)
        opacity = max(0.0, min(1.0, float(getattr(shape, "opacity", 1.0))))
        ops = {
            "stroke_opacity": opacity * _alpha(getattr(shape, "stroke_color", "#000000")),
            "fill_opacity": opacity * max(0.0, min(1.0, float(getattr(shape, "fill_opacity", 1.0)))) * _alpha(fill_hex),
        }
        angle = float(getattr(shape, "rotation", 0.0) or 0.0) % 360.0
        morph = None
        if min(angle, 360.0 - angle) > 0.01:
            centre = fitz.Point((shape.rect.x + shape.rect.x1) / 2, (shape.rect.y + shape.rect.y1) / 2)
            morph = (centre, fitz.Matrix(-angle))  # MuPDF turns counter-clockwise on the page
        from core.editing.shape_box import dash_pattern, line_geometry

        pattern = dash_pattern(getattr(shape, "stroke_style", "solid"), width)
        dashes = ("[" + " ".join(f"{v:.2f}" for v in pattern) + "] 0") if pattern else None
        kind = getattr(getattr(shape, "kind", None), "value", "rectangle")
        if kind in ("line", "arrow"):
            # the same geometry as on screen (core.editing.shape_box.line_geometry)
            start, end = shape.heads() if hasattr(shape, "heads") else ("none", "filled" if kind == "arrow" else "none")
            a, b, marks = line_geometry(float(shape.x0), float(shape.y0), float(shape.x1), float(shape.y1),
                                        width=width, start=start, end=end,
                                        head_size=float(getattr(shape, "head_size", 0.0) or 0.0))
            draw = page.new_shape()
            draw.draw_line(fitz.Point(*a), fitz.Point(*b))
            draw.finish(color=stroke, width=width, dashes=dashes, lineCap=1, closePath=False, morph=morph,
                        stroke_opacity=ops["stroke_opacity"])
            for style, pts in marks:
                if style == "circle":
                    (cx, cy), (r, _r) = pts
                    draw.draw_circle(fitz.Point(cx, cy), r)
                    draw.finish(color=None, fill=stroke, morph=morph, fill_opacity=ops["stroke_opacity"])
                elif style == "open":
                    draw.draw_polyline([fitz.Point(x, y) for x, y in pts])
                    draw.finish(color=stroke, width=width, lineCap=1, lineJoin=1, closePath=False, morph=morph,
                                stroke_opacity=ops["stroke_opacity"])
                else:  # filled, stealth, bar
                    draw.draw_polyline([fitz.Point(x, y) for x, y in pts])
                    draw.finish(color=stroke, fill=stroke, width=max(0.2, width * 0.35), lineJoin=1, closePath=True,
                                morph=morph, stroke_opacity=ops["stroke_opacity"], fill_opacity=ops["stroke_opacity"])
            draw.commit()
        elif kind == "ellipse":
            r = fitz.Rect(shape.rect.x, shape.rect.y, shape.rect.x1, shape.rect.y1)
            page.draw_oval(r, color=stroke, fill=fill, width=width, dashes=dashes, morph=morph, **ops)
        elif kind == "freehand" and getattr(shape, "points", None):
            from core.editing.freehand import smooth_segments

            segs = smooth_segments(shape.points)  # the same smooth curves as on screen
            if segs:
                draw = page.new_shape()
                for p0, c1, c2, p3 in segs:
                    draw.draw_bezier(fitz.Point(*p0), fitz.Point(*c1), fitz.Point(*c2), fitz.Point(*p3))
                draw.finish(color=stroke, width=width, dashes=dashes, lineCap=1, lineJoin=1, closePath=False,
                            morph=morph, stroke_opacity=ops["stroke_opacity"])
                draw.commit()
        else:
            r = fitz.Rect(shape.rect.x, shape.rect.y, shape.rect.x1, shape.rect.y1)
            page.draw_rect(r, color=stroke, fill=fill, width=width, dashes=dashes, morph=morph, **ops)
    except Exception:  # noqa: BLE001
        return


def bake_into_document(edit: EditableDocument, destination: Path, *, keep_encryption: bool = True) -> None:
    """
    Open a working copy of the live document (or source path), apply redactions + text boxes,
    write destination. Never writes the original path unless destination equals it (explicit Save).
    A password-protected document keeps its protection unless ``keep_encryption`` is False.
    """
    doc = _working_copy(edit, keep_encryption=keep_encryption)
    targets = _OverlayTargets(doc)
    try:

        # Edited existing text: remove the original span's glyphs (text only — pictures, drawings and
        # the page background stay); the replacement text box is drawn below with the other overlays.
        remove_native_spans(doc, edit)

        # Text boxes, pictures and shapes in their stacking order (Bring Forward / Send Backward)
        for kind, obj in overlays_in_order(edit):
            {"text": _bake_text_box, "image": _bake_image, "shape": _bake_shape}[kind](targets, obj)

        # Forms: create new widgets, apply values/geometry, optional flatten
        from core.forms.acroform import (
            apply_field_values_to_doc,
            create_widget_on_page,
            flatten_form_fields,
        )
        from core.forms.fields import FieldType
        from core.tables.model import TableModel

        # (decided before the loop below: creating a widget marks its field as a PDF field)
        added_fields = any(not f.is_acroform and not f.is_candidate for f in edit.fields.values())
        for field in list(edit.fields.values()):
            if field.is_candidate:
                continue  # never bake unreviewed candidates
            if not field.is_acroform:
                try:
                    create_widget_on_page(doc, field)
                except Exception:  # noqa: BLE001
                    # Visual fallback for unsupported widget creation
                    page = targets.page(field.page_index)
                    r = fitz.Rect(field.rect.x, field.rect.y, field.rect.x1, field.rect.y1)
                    page.draw_rect(r, color=(0.2, 0.2, 0.2), width=0.6)
                    label = field.value or ("X" if field.checked else "")
                    if field.field_type == FieldType.SIGNATURE:
                        label = "[Signature — visual only]"
                    if label:
                        page.insert_textbox(r, label, fontsize=max(8, field.font_size))
        live_fields = [f for f in edit.fields.values() if not f.is_candidate]
        apply_field_values_to_doc(doc, live_fields)

        # Hybrid AcroForm/XFA forms: Acrobat shows the XFA copy of the fields, so it must carry the
        # same values (or be removed when that is not safely possible) — see core/forms/xfa_sync.py
        from core.forms.xfa_sync import sync_xfa

        try:
            sync_xfa(
                doc,
                live_fields,
                new_fields=added_fields,
                flattened=bool(edit.flatten_on_save),
            )
        except Exception:  # noqa: BLE001 — never lose the save over the XFA copy
            pass

        # Tables: draw reconstructed grid + cell text (layout-preserving bake)
        for table in edit.tables.values():
            if not isinstance(table, TableModel):
                continue
            page = targets.page(table.page_index)
            for r in range(table.nrows):
                for c in range(table.ncols):
                    cell = table.cells.get((r, c))
                    if cell is None:
                        continue
                    # Skip covered merged slaves
                    if any(
                        (rr, cc) != (r, c)
                        and (rr, cc) in table.cells
                        and table.cells[(rr, cc)].row_span > 1
                        and rr <= r < rr + table.cells[(rr, cc)].row_span
                        and cc <= c < cc + table.cells[(rr, cc)].col_span
                        for rr, cc in table.cells
                    ):
                        # Only draw master cells
                        pass
                    crect = table.cell_rect(r, c)
                    fr = fitz.Rect(crect.x, crect.y, crect.x1, crect.y1)
                    fill = _parse_color(cell.fill)
                    if fill:
                        page.draw_rect(fr, color=None, fill=fill, width=0)
                    border = _parse_color(cell.border_color) or (0, 0, 0)
                    page.draw_rect(fr, color=border, width=cell.border_width)
                    if cell.text:
                        page.insert_textbox(fr, cell.text, fontsize=9)

        targets.merge()
        if edit.flatten_on_save:
            flatten_form_fields(doc, comments=bool(getattr(edit, "flatten_comments", True)))

        encrypt = fitz.PDF_ENCRYPT_KEEP if _is_protected(doc) else fitz.PDF_ENCRYPT_NONE
        # Replacing an existing file is atomic: a temporary file beside it is written, then swapped in,
        # so the existing file stays intact if anything fails (disk full, locked). A new file is written
        # directly and removed again if writing fails, so no partial file is left behind.
        import os
        import uuid

        final = Path(destination)
        part = final.with_name(f".{final.stem}.{uuid.uuid4().hex[:8]}.part") if final.exists() else final
        try:
            doc.save(part.as_posix(), garbage=3, deflate=True, encryption=encrypt, incremental=False)
            if part != final:
                os.replace(part, final)
        except BaseException:
            try:
                part.unlink()
            except OSError:
                pass
            raise
    finally:
        targets.close()
        doc.close()


def bake_via_backend(
    edit: EditableDocument, destination: Path, *, flatten: bool | None = None, keep_encryption: bool = True
) -> None:
    """Public entry used by UI save paths."""
    if flatten is not None:
        edit.flatten_on_save = flatten
    bake_into_document(edit, destination, keep_encryption=keep_encryption)
