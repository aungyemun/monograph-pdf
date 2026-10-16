"""Bake editable overlays into a MuPDF document at Save time (source untouched until then)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

from core.editing.edit_model import EditableDocument
from core.editing.font_resolver import resolve_font
from core.editing.text_box import TextAlign, VAlign
from core.editing.text_layout import layout_text_box


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
        if keep_encryption and password and _is_protected(live):
            try:
                data = live.tobytes(garbage=0, deflate=False, encryption=fitz.PDF_ENCRYPT_KEEP)
                doc = fitz.open("pdf", data)
                if doc.authenticate(password):
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
        runs=[],
        font_family=family or box.style.font_family,
        font_size=float(fontsize),
        bold=bool(box.style.bold),
        italic=bool(box.style.italic),
        text_color=box.style.text_color or "#000000",
        align=getattr(box.align, "value", "left"),
        valign=getattr(box.valign, "value", "top"),
        multiline=bool(getattr(box.style, "wrap", True)),
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
        )
        scratch.subset_fonts()
        page.show_pdf_page(rect, scratch, 0, keep_proportion=False, overlay=True)
    finally:
        scratch.close()


def bake_into_document(edit: EditableDocument, destination: Path, *, keep_encryption: bool = True) -> None:
    """
    Open a working copy of the live document (or source path), apply redactions + text boxes,
    write destination. Never writes the original path unless destination equals it (explicit Save).
    A password-protected document keeps its protection unless ``keep_encryption`` is False.
    """
    doc = _working_copy(edit, keep_encryption=keep_encryption)
    try:

        # Controlled native replacements first
        for plan in edit.native_replacements.values():
            if plan.get("mode") == "redaction_reinsert":
                page_index = None
                # find from span id p{n}-s{m}
                sid = str(plan.get("span_id") or "")
                if sid.startswith("p"):
                    try:
                        page_index = int(sid.split("-")[0][1:])
                    except Exception:  # noqa: BLE001
                        page_index = None
                rect_t = plan.get("rect")
                if page_index is not None and rect_t:
                    page = doc.load_page(page_index)
                    r = fitz.Rect(rect_t[0], rect_t[1], rect_t[0] + rect_t[2], rect_t[1] + rect_t[3])
                    page.add_redact_annot(r, fill=(1, 1, 1))
        # Apply redactions page-wise
        touched = {
            int(str(p.get("span_id", "p-1")).split("-")[0][1:])
            for p in edit.native_replacements.values()
            if str(p.get("span_id", "")).startswith("p")
        }
        for pi in touched:
            try:
                doc.load_page(pi).apply_redactions()
            except Exception:  # noqa: BLE001
                pass

        for box in edit.all_objects():
            page = doc.load_page(box.page_index)
            layout = layout_text_box(box)
            res = resolve_font(box.style.font_family, box.text)
            family = layout.resolved_font or res.resolved
            fontsize = layout.font_size
            pad = box.style.padding
            # Ensure bake rect is tall enough for MuPDF insert_textbox (needs slack).
            bake_h = max(box.rect.h, layout.content_height + 2 * pad + fontsize * 0.35)
            rect = fitz.Rect(box.rect.x, box.rect.y, box.rect.x1, box.rect.y + bake_h)

            bg = _parse_color(box.style.background_color)
            if bg is not None:
                page.draw_rect(rect, color=None, fill=bg, width=0)

            border = _parse_color(box.style.border_color)
            if border is not None and box.style.border_width > 0:
                page.draw_rect(rect, color=border, fill=None, width=box.style.border_width)

            text_rect = fitz.Rect(rect.x0 + pad, rect.y0 + pad, rect.x1 - pad, rect.y1 - pad)
            if box.text and text_rect.width > 1 and text_rect.height > 1:
                _draw_text_box(page, text_rect, box, family, fontsize)
            _ = family  # reserved for embedded-font path

        # Forms: create new widgets, apply values/geometry, optional flatten
        from core.forms.acroform import (
            apply_field_values_to_doc,
            create_widget_on_page,
            flatten_form_fields,
        )
        from core.forms.fields import FieldType
        from core.tables.model import TableModel

        for field in list(edit.fields.values()):
            if field.is_candidate:
                continue  # never bake unreviewed candidates
            if not field.is_acroform:
                try:
                    create_widget_on_page(doc, field)
                except Exception:  # noqa: BLE001
                    # Visual fallback for unsupported widget creation
                    page = doc.load_page(field.page_index)
                    r = fitz.Rect(field.rect.x, field.rect.y, field.rect.x1, field.rect.y1)
                    page.draw_rect(r, color=(0.2, 0.2, 0.2), width=0.6)
                    label = field.value or ("X" if field.checked else "")
                    if field.field_type == FieldType.SIGNATURE:
                        label = "[Signature — visual only]"
                    if label:
                        page.insert_textbox(r, label, fontsize=max(8, field.font_size))
        apply_field_values_to_doc(doc, [f for f in edit.fields.values() if not f.is_candidate])

        # Tables: draw reconstructed grid + cell text (layout-preserving bake)
        for table in edit.tables.values():
            if not isinstance(table, TableModel):
                continue
            page = doc.load_page(table.page_index)
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

        # Placed images
        for img in getattr(edit, "images", {}).values():
            try:
                page = doc.load_page(img.page_index)
                rect = fitz.Rect(img.rect.x, img.rect.y, img.rect.x1, img.rect.y1)
                path = Path(img.source_path)
                if not path.is_file():
                    continue
                # Optional crop via pixmap
                opacity = max(0.0, min(1.0, float(getattr(img, "opacity", 1.0))))
                if opacity < 0.999 or any(c != v for c, v in zip(img.crop, (0.0, 0.0, 1.0, 1.0))):
                    from PIL import Image
                    import io

                    pil = Image.open(path.as_posix()).convert("RGBA")
                    w, h = pil.size
                    l, t, r, b = img.crop
                    pil = pil.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
                    if abs(float(img.rotation)) > 0.01:
                        pil = pil.rotate(-float(img.rotation), expand=True)
                    if opacity < 0.999:
                        alpha = pil.split()[-1].point(lambda p: int(p * opacity))
                        pil.putalpha(alpha)
                    buf = io.BytesIO()
                    pil.save(buf, format="PNG")
                    page.insert_image(rect, stream=buf.getvalue())
                else:
                    page.insert_image(rect, filename=path.as_posix(), rotate=float(img.rotation))
            except Exception:  # noqa: BLE001
                continue

        # Vector shape overlays
        for shape in getattr(edit, "shapes", {}).values():
            try:
                page = doc.load_page(shape.page_index)
                stroke = _parse_color(getattr(shape, "stroke_color", "#000000")) or (0, 0, 0)
                fill = _parse_color(getattr(shape, "fill_color", "#00000000"))
                width = float(getattr(shape, "stroke_width", 1.5) or 1.5)
                dashes = None
                style = getattr(getattr(shape, "stroke_style", None), "value", "solid")
                if style == "dashed":
                    dashes = [3, 2]
                elif style == "dotted":
                    dashes = [1, 2]
                kind = getattr(getattr(shape, "kind", None), "value", "rectangle")
                if kind in ("line", "arrow"):
                    p0 = fitz.Point(float(shape.x0), float(shape.y0))
                    p1 = fitz.Point(float(shape.x1), float(shape.y1))
                    page.draw_line(p0, p1, color=stroke, width=width, dashes=dashes)
                    if kind == "arrow":
                        import math

                        ang = math.atan2(p1.y - p0.y, p1.x - p0.x)
                        ah = 8.0
                        for aoff in (2.6, -2.6):
                            ax = p1.x - ah * math.cos(ang + aoff)
                            ay = p1.y - ah * math.sin(ang + aoff)
                            page.draw_line(p1, fitz.Point(ax, ay), color=stroke, width=width)
                elif kind == "ellipse":
                    r = fitz.Rect(shape.rect.x, shape.rect.y, shape.rect.x1, shape.rect.y1)
                    page.draw_oval(r, color=stroke, fill=fill, width=width, dashes=dashes)
                elif kind == "freehand" and getattr(shape, "points", None):
                    pts = [fitz.Point(x, y) for x, y in shape.points]
                    if len(pts) >= 2:
                        page.draw_polyline(pts, color=stroke, width=width, dashes=dashes)
                else:
                    r = fitz.Rect(shape.rect.x, shape.rect.y, shape.rect.x1, shape.rect.y1)
                    page.draw_rect(r, color=stroke, fill=fill, width=width, dashes=dashes)
            except Exception:  # noqa: BLE001
                continue

        if edit.flatten_on_save:
            flatten_form_fields(doc)

        encrypt = fitz.PDF_ENCRYPT_KEEP if _is_protected(doc) else fitz.PDF_ENCRYPT_NONE
        doc.save(
            Path(destination).as_posix(),
            garbage=3,
            deflate=True,
            encryption=encrypt,
            incremental=False,
        )
    finally:
        doc.close()


def bake_via_backend(
    edit: EditableDocument, destination: Path, *, flatten: bool | None = None, keep_encryption: bool = True
) -> None:
    """Public entry used by UI save paths."""
    if flatten is not None:
        edit.flatten_on_save = flatten
    bake_into_document(edit, destination, keep_encryption=keep_encryption)
