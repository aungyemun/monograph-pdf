"""Non-destructive editable document — overlays original PDF until explicit Save."""

from __future__ import annotations

import copy
import json
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

from core.commands import CommandStack
from core.document import PdfDocument
from core.editing.edit_commands import (
    AddTextBoxCommand,
    DeleteObjectsCommand,
    DuplicateCommand,
    FieldStyleCommand,
    GroupCommand,
    LayerCommand,
    ReplaceNativeTextCommand,
    SetStyleCommand,
    SetTextCommand,
    TransformCommand,
)
from core.editing.geometry import Point, Rect
from core.editing.native_text import NativeSpan, extract_spans, plan_replacement, span_to_textbox
from core.editing.snap import SnapGuide, snap_rect
from core.editing.style_clipboard import auto_match_nearby, copy_style, paste_style
from core.editing.text_box import SizeMode, TextBox
from core.editing.text_layout import apply_layout_to_box
from core.editing.text_style import TextStyle


class EditTool(str, Enum):
    SELECT = "select"
    TEXT_BOX = "text_box"
    IMAGE = "image"
    # Shape creation tools (overlay)
    SHAPE_RECT = "shape_rect"
    SHAPE_ELLIPSE = "shape_ellipse"
    SHAPE_LINE = "shape_line"
    SHAPE_ARROW = "shape_arrow"
    SHAPE_FREEHAND = "shape_freehand"
    # Forms mode tools
    FORM_SELECT = "form_select"
    FORM_TEXT = "form_text"
    FORM_MULTILINE = "form_multiline"
    FORM_CHECKBOX = "form_checkbox"
    FORM_RADIO = "form_radio"
    FORM_DROPDOWN = "form_dropdown"
    FORM_DATE = "form_date"
    FORM_SIGNATURE = "form_signature"
    FORM_DETECT = "form_detect"
    # Layout / table
    LAYOUT_SELECT = "layout_select"
    TABLE_SELECT = "table_select"


class WorkspaceMode(str, Enum):
    EDIT = "edit"  # text boxes
    FORMS = "forms"
    LAYOUT = "layout"
    TABLES = "tables"


Listener = Callable[[], None]


class EditableDocument:
    """
    Overlay model sitting on a PdfDocument.
    Source file is never modified until Save / Save As bakes overlays.
    """

    def __init__(self, pdf: PdfDocument) -> None:
        self.pdf = pdf
        self.objects: dict[str, TextBox] = {}
        self.selection: list[str] = []
        self.tool = EditTool.SELECT
        self.mode = WorkspaceMode.EDIT
        self.commands = CommandStack()
        self.dirty = False
        self._listeners: list[Listener] = []
        self._z_counter = 0
        self._native_replacements: dict[str, dict[str, Any]] = {}
        self._style_clip = None
        self.guides: list[SnapGuide] = []
        self.editing_object_id: str | None = None  # in-place typing target (text box)
        self.editing_field_id: str | None = None  # in-place typing target (form fill)
        # Forms / tables / layout
        self.fields: dict[str, Any] = {}  # FormField by id
        self.field_selection: list[str] = []
        self.tables: dict[str, Any] = {}  # TableModel by id
        self.table_selection: list[str] = []
        self.images: dict[str, Any] = {}  # ImageBox by id
        self.shapes: dict[str, Any] = {}  # ShapeBox by id
        self.layout_policy = "preserve_layout"
        self.flatten_on_save = False
        # UI-only: highlight fillable AcroForm widgets (never baked into Save/Export)
        self.highlight_fillable_fields: bool = True
        # Last OCR run: recognized words + boxes for review/editing (not baked until Save)
        self.last_ocr_result: Any | None = None
        self._load_acroform()

    def remap_page_indices(self, mapping: dict[int, int | None]) -> None:
        """
        After page insert/delete/reorder: remap overlay page_index values.
        mapping[old] = new index, or None to drop objects on that page.
        """
        drop_ids: list[str] = []
        for oid, box in self.objects.items():
            if box.page_index not in mapping:
                continue
            new_i = mapping[box.page_index]
            if new_i is None:
                drop_ids.append(oid)
            else:
                box.page_index = new_i
        for oid in drop_ids:
            self.objects.pop(oid, None)
            self.selection = [s for s in self.selection if s != oid]

        drop_fields: list[str] = []
        for fid, field in self.fields.items():
            if getattr(field, "page_index", None) not in mapping:
                continue
            new_i = mapping[field.page_index]
            if new_i is None:
                drop_fields.append(fid)
            else:
                field.page_index = new_i
        for fid in drop_fields:
            self.fields.pop(fid, None)

        drop_tables: list[str] = []
        for tid, table in self.tables.items():
            if getattr(table, "page_index", None) not in mapping:
                continue
            new_i = mapping[table.page_index]
            if new_i is None:
                drop_tables.append(tid)
            else:
                table.page_index = new_i
        for tid in drop_tables:
            self.tables.pop(tid, None)

        drop_images: list[str] = []
        for iid, image in self.images.items():
            if getattr(image, "page_index", None) not in mapping:
                continue
            new_i = mapping[image.page_index]
            if new_i is None:
                drop_images.append(iid)
            else:
                image.page_index = new_i
        for iid in drop_images:
            self.images.pop(iid, None)

        drop_shapes: list[str] = []
        for sid, shape in self.shapes.items():
            if getattr(shape, "page_index", None) not in mapping:
                continue
            new_i = mapping[shape.page_index]
            if new_i is None:
                drop_shapes.append(sid)
            else:
                shape.page_index = new_i
        for sid in drop_shapes:
            self.shapes.pop(sid, None)
            self.selection = [s for s in self.selection if s != sid]

        # Native replacement span ids: p{n}-s{m}
        new_native: dict[str, dict[str, Any]] = {}
        for sid, plan in self._native_replacements.items():
            if not sid.startswith("p"):
                new_native[sid] = plan
                continue
            try:
                old_page = int(sid.split("-")[0][1:])
            except Exception:  # noqa: BLE001
                new_native[sid] = plan
                continue
            if old_page not in mapping:
                new_native[sid] = plan
                continue
            new_i = mapping[old_page]
            if new_i is None:
                continue
            rest = sid.split("-", 1)[1] if "-" in sid else "s0"
            new_native[f"p{new_i}-{rest}"] = plan
        self._native_replacements = new_native
        self.mark_dirty()

    # --- observation -----------------------------------------------------

    def add_listener(self, fn: Listener) -> None:
        self._listeners.append(fn)

    def remove_listener(self, fn: Listener) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            fn()

    def mark_dirty(self) -> None:
        self.dirty = True
        self._notify()

    def mark_clean(self) -> None:
        self.dirty = False
        self._notify()

    # --- object CRUD -----------------------------------------------------

    def next_z(self) -> int:
        self._z_counter += 1
        return self._z_counter

    def add_object(self, box: TextBox, *, record_dirty: bool = True) -> None:
        apply_layout_to_box(box)
        self.objects[box.object_id] = box
        self._z_counter = max(self._z_counter, box.z_index)
        if record_dirty:
            self.mark_dirty()
        else:
            self._notify()

    def remove_object(self, object_id: str, *, record_dirty: bool = True) -> None:
        self.objects.pop(object_id, None)
        self.selection = [s for s in self.selection if s != object_id]
        if self.editing_object_id == object_id:
            self.editing_object_id = None
        if record_dirty:
            self.mark_dirty()
        else:
            self._notify()

    def get(self, object_id: str) -> TextBox | None:
        return self.objects.get(object_id)

    def overlay(self, object_id: str) -> tuple[str, Any] | None:
        """(kind, object) of a text box ("text"), shape ("shape") or picture ("image")."""
        if object_id in self.objects:
            return "text", self.objects[object_id]
        if object_id in self.shapes:
            return "shape", self.shapes[object_id]
        if object_id in self.images:
            return "image", self.images[object_id]
        return None

    def overlays_on_page(self, page_index: int) -> list[Any]:
        """Text boxes, pictures and shapes of a page, bottom first (the order they are drawn and saved)."""
        rank = {"text": 0, "image": 1, "shape": 2}
        items = [("text", o) for o in self.objects_on_page(page_index)]
        items += [("image", o) for o in self.images_on_page(page_index)]
        items += [("shape", o) for o in self.shapes_on_page(page_index)]
        items.sort(key=lambda it: (int(it[1].z_index), rank[it[0]]))
        return [o for _k, o in items]

    @staticmethod
    def translate_overlay(obj: Any, dx: float, dy: float) -> None:
        """Move any overlay, including a line's end points and a freehand stroke's points."""
        obj.rect = obj.rect.translated(dx, dy)
        kind = getattr(getattr(obj, "kind", None), "value", None)
        if kind in ("line", "arrow"):
            obj.x0 += dx
            obj.y0 += dy
            obj.x1 += dx
            obj.y1 += dy
        elif kind == "freehand" and getattr(obj, "points", None):
            obj.points = [(px + dx, py + dy) for px, py in obj.points]

    def objects_on_page(self, page_index: int) -> list[TextBox]:
        items = [o for o in self.objects.values() if o.page_index == page_index]
        return sorted(items, key=lambda o: o.z_index)

    def all_objects(self) -> list[TextBox]:
        return sorted(self.objects.values(), key=lambda o: (o.page_index, o.z_index))

    @staticmethod
    def _set_box_text(box, text: str, runs: list | None) -> None:
        """New text; word formats (runs) as given, else kept on the characters that stayed."""
        from core.forms.rich_text import normalize_runs, reconcile_runs

        if runs is not None:
            box.runs = normalize_runs([dict(r) for r in runs])
        elif box.runs:
            box.runs = reconcile_runs(box.runs, box.text, text)
        box.text = text

    def set_text(self, object_id: str, text: str, *, record_dirty: bool = True, runs: list | None = None) -> None:
        box = self.objects.get(object_id)
        if box is None:
            return
        self._set_box_text(box, text, runs)
        apply_layout_to_box(box)
        if record_dirty:
            self.mark_dirty()
        else:
            self._notify()

    def apply_style_dict(self, object_id: str, data: dict[str, Any], *, record_dirty: bool = True) -> None:
        box = self.objects.get(object_id)
        if box is None:
            return
        if "style" in data:
            box.style = TextStyle.from_dict(data["style"])
        if "align" in data:
            from core.editing.text_box import TextAlign

            box.align = TextAlign(data["align"])
        if "valign" in data:
            from core.editing.text_box import VAlign

            box.valign = VAlign(data["valign"])
        if "size_mode" in data:
            box.size_mode = SizeMode(data["size_mode"])
        if "runs" in data:
            box.runs = [dict(r) for r in (data["runs"] or [])]
        apply_layout_to_box(box)
        if record_dirty:
            self.mark_dirty()
        else:
            self._notify()

    def set_z(self, object_id: str, z: int, *, record_dirty: bool = True) -> None:
        box = self.objects.get(object_id)
        if box is None:
            return
        box.z_index = z
        if record_dirty:
            self.mark_dirty()
        else:
            self._notify()

    def change_layer(self, object_ids: list[str], direction: str) -> None:
        """Bring forward / send backward / to front / to back among all overlays of the same page
        (text boxes, pictures and shapes share one stacking order)."""
        found = [self.overlay(i) for i in object_ids]
        moved = [o for _k, o in (f for f in found if f)]
        if not moved:
            return
        ids = {o.object_id for o in moved}
        for page_index in sorted({o.page_index for o in moved}):
            order = self.overlays_on_page(page_index)
            sel = [o for o in order if o.object_id in ids]
            rest = [o for o in order if o.object_id not in ids]
            if direction == "front":
                order = rest + sel
            elif direction == "back":
                order = sel + rest
            elif direction == "forward":
                for i in range(len(order) - 2, -1, -1):
                    if order[i].object_id in ids and order[i + 1].object_id not in ids:
                        order[i], order[i + 1] = order[i + 1], order[i]
            elif direction == "backward":
                for i in range(1, len(order)):
                    if order[i].object_id in ids and order[i - 1].object_id not in ids:
                        order[i], order[i - 1] = order[i - 1], order[i]
            for z, obj in enumerate(order, start=1):
                obj.z_index = z
            self._z_counter = max(self._z_counter, len(order))
        self.mark_dirty()

    def z_snapshot(self, object_ids: list[str]) -> dict[str, int]:
        """z-order of every overlay on the pages of ``object_ids`` (for undo of a layer change)."""
        pages = {f[1].page_index for f in (self.overlay(i) for i in object_ids) if f}
        return {o.object_id: int(o.z_index) for p in pages for o in self.overlays_on_page(p)}

    def restore_z(self, snapshot: dict[str, int]) -> None:
        for oid, z in snapshot.items():
            found = self.overlay(oid)
            if found:
                found[1].z_index = z
        self.mark_dirty()

    def note_native_replacement(self, plan: dict[str, Any]) -> None:
        sid = plan.get("span_id")
        if sid:
            self._native_replacements[str(sid)] = plan

    def forget_native_replacement(self, span_id: str | None) -> None:
        if span_id:
            self._native_replacements.pop(str(span_id), None)

    @property
    def native_replacements(self) -> dict[str, dict[str, Any]]:
        return dict(self._native_replacements)

    # --- selection -------------------------------------------------------

    def select(self, object_ids: Iterable[str], *, additive: bool = False) -> None:
        ids = [
            i
            for i in object_ids
            if i in self.objects or i in self.shapes or i in self.images
        ]
        if additive:
            merged = list(dict.fromkeys(self.selection + ids))
            self.selection = merged
        else:
            self.selection = ids
        self.field_selection = []
        self._notify()

    def clear_selection(self) -> None:
        """Nothing selected: objects, form fields and tables (the blue boxes go away)."""
        self.selection = []
        self.field_selection = []
        self.table_selection = []
        self.editing_object_id = None
        self.editing_field_id = None
        self._notify()

    def selected_objects(self) -> list[TextBox]:
        return [self.objects[i] for i in self.selection if i in self.objects]

    def hit_test(self, page_index: int, point: Point) -> str | None:
        # Top-most across text / shapes / images
        candidates: list[tuple[int, str]] = []
        for box in self.objects_on_page(page_index):
            if box.rect.contains(point):
                candidates.append((box.z_index, box.object_id))
        for shape in self.shapes_on_page(page_index):
            if shape.rect.contains(point):
                candidates.append((shape.z_index, shape.object_id))
        for img in self.images_on_page(page_index):
            if img.rect.contains(point):
                candidates.append((img.z_index, img.object_id))
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[0])
        return candidates[-1][1]

    def shapes_on_page(self, page_index: int) -> list[Any]:
        items = [s for s in self.shapes.values() if s.page_index == page_index]
        return sorted(items, key=lambda s: s.z_index)

    def create_shape(self, page_index: int, rect: Rect, kind: str, **kwargs: Any) -> Any:
        from core.editing.shape_box import ShapeBox, ShapeKind

        sk = ShapeKind(kind)
        shape = ShapeBox(
            page_index=page_index,
            rect=rect.normalized(),
            kind=sk,
            z_index=self.next_z(),
            lock_aspect=bool(kwargs.get("lock_aspect", False)),
        )
        for key in ("start_head", "end_head", "head_size", "stroke_width", "stroke_style", "stroke_color", "fill_color"):
            if kwargs.get(key) is not None:
                setattr(shape, key, kwargs[key])
        if sk in (ShapeKind.LINE, ShapeKind.ARROW):
            shape.x0 = float(kwargs.get("x0", rect.x))
            shape.y0 = float(kwargs.get("y0", rect.y))
            shape.x1 = float(kwargs.get("x1", rect.x1))
            shape.y1 = float(kwargs.get("y1", rect.y1))
            shape.sync_rect_from_line()
        if sk == ShapeKind.FREEHAND:
            from core.editing.freehand import simplify

            # the mouse's jitter is removed; the stroke is drawn as smooth curves (core/editing/freehand.py)
            shape.points = simplify(list(kwargs.get("points") or []), float(kwargs.get("tolerance", 0.5)))
            if shape.points:
                xs = [p[0] for p in shape.points]
                ys = [p[1] for p in shape.points]
                shape.rect = Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).inflate(2)
        from core.editing.edit_commands import AddOverlayCommand

        self.commands.execute(AddOverlayCommand(self, shape, "shapes"))  # undoable
        self.selection = [shape.object_id]
        self.editing_object_id = None
        self.editing_field_id = None
        self.field_selection = []
        self.mark_dirty()
        return shape

    def update_shape(self, object_id: str, **kwargs: Any) -> None:
        """Change shape properties (undoable)."""
        self.set_overlay_attrs(object_id, **kwargs)

    def update_shapes(self, object_ids: Iterable[str], **kwargs: Any) -> None:
        """The same change (e.g. line or fill colour) on several shapes — one undo step."""
        from core.editing.edit_commands import SetOverlayAttrsCommand

        cmds = []
        for oid in dict.fromkeys(object_ids):
            found = self.overlay(oid)
            if found is None:
                continue
            obj = found[1]
            changes = {k: v for k, v in kwargs.items() if hasattr(obj, k) and v is not None and getattr(obj, k) != v}
            if changes:
                cmds.append(SetOverlayAttrsCommand(self, oid, {k: copy.deepcopy(getattr(obj, k)) for k in changes},
                                                   changes))
        if not cmds:
            return
        self.commands.execute(cmds[0] if len(cmds) == 1 else GroupCommand("Change Shapes", cmds))

    def set_overlay_attrs(self, object_id: str, **kwargs: Any) -> None:
        """Change properties of a shape or picture as one undoable step (merged with an immediately
        preceding change of the same properties of the same object)."""
        from core.editing.edit_commands import SetOverlayAttrsCommand

        found = self.overlay(object_id)
        if found is None:
            return
        obj = found[1]
        changes = {k: v for k, v in kwargs.items() if hasattr(obj, k) and v is not None and getattr(obj, k) != v}
        if not changes:
            return
        before = {k: copy.deepcopy(getattr(obj, k)) for k in changes}
        cmd = SetOverlayAttrsCommand(self, object_id, before, changes)
        last = self.commands._undo[-1] if self.commands._undo else None  # noqa: SLF001
        if isinstance(last, SetOverlayAttrsCommand) and last.can_merge(cmd) and not self.commands.can_redo_now:
            last.after = dict(changes)
            last.stamp = cmd.stamp
            last.execute()
            return
        self.commands.execute(cmd)

    # --- high-level ops via commands -------------------------------------

    def create_text_box(
        self,
        page_index: int,
        rect: Rect,
        *,
        text: str = "",
        auto_match: bool = True,
    ) -> TextBox:
        rect = rect.normalized()
        if rect.w < 8:
            rect = rect.with_size(160, max(rect.h, 36))
        if rect.h < 8:
            rect = rect.with_size(max(rect.w, 160), 36)
        box = TextBox(
            page_index=page_index,
            rect=rect,
            text=text,
            z_index=self.next_z(),
            size_mode=SizeMode.AUTO_HEIGHT,
            style=TextStyle(),
            min_h=rect.h,  # the drawn size stays while typing; longer text makes it taller
        )
        if auto_match:
            near = auto_match_nearby(self.objects_on_page(page_index), rect)
            if near is not None:
                from core.editing.style_clipboard import CopiedStyle

                paste_style(
                    box,
                    CopiedStyle(
                        style=near.style.copy(),
                        align=near.align,
                        valign=near.valign,
                        size_mode=near.size_mode,
                    ),
                )
        self.commands.execute(AddTextBoxCommand(self, box))
        self.select([box.object_id])
        self.editing_object_id = box.object_id
        self.editing_field_id = None
        self.field_selection = []
        return self.objects[box.object_id]

    def delete_selection(self) -> None:
        if not self.selection:
            return
        self.commands.execute(DeleteObjectsCommand(self, list(self.selection)))

    def duplicate_selection(self) -> None:
        if not self.selection:
            return
        self.commands.execute(DuplicateCommand(self, list(self.selection)))
        # Select newly created (last duplicates)
        # DuplicateCommand doesn't expose ids easily — select by newest on pages
        # Re-run: track via command
        created = []
        # Find objects not previously selected with high z — simpler: use command._created
        cmd = self.commands._undo[-1]  # noqa: SLF001
        if isinstance(cmd, DuplicateCommand):
            created = [c.object_id for c in cmd._created]  # noqa: SLF001
        if created:
            self.select(created)

    def nudge_selection(self, dx: float, dy: float) -> None:
        """Arrow-key nudge for selected text boxes, shapes, images, and form fields.

        Mirrors ``begin_transform_snapshot`` / mouse drag so rectangles, ellipses, lines, arrows,
        freehand shapes and free-text boxes all move (dimensions and style preserved). Clamped to
        the page; participates in undo/redo via ``TransformCommand``.
        """
        ids = list(dict.fromkeys([*self.selection, *self.field_selection]))
        if not ids:
            return
        before: dict[str, Rect] = {}
        for oid in ids:
            target = (
                self.objects.get(oid)
                or self.fields.get(oid)
                or self.images.get(oid)
                or self.shapes.get(oid)
            )
            if target is None:
                continue
            before[oid] = Rect(*target.rect.as_tuple())
        if not before:
            return
        dx, dy = self._move_kept_on_page(list(before), dx, dy)  # arrow keys stop at the page edge too
        if not dx and not dy:
            return
        after = {oid: before[oid].translated(dx, dy) for oid in before}
        self.commands.execute(TransformCommand(self, before, after, name="Nudge"))

    def begin_transform_snapshot(self) -> dict[str, Rect]:
        snap: dict[str, Rect] = {}
        for oid in self.selection:
            if oid in self.objects:
                snap[oid] = Rect(*self.objects[oid].rect.as_tuple())
            elif oid in self.images:
                snap[oid] = Rect(*self.images[oid].rect.as_tuple())
            elif oid in self.shapes:
                snap[oid] = Rect(*self.shapes[oid].rect.as_tuple())
        for oid in self.field_selection:
            if oid in self.fields:
                snap[oid] = Rect(*self.fields[oid].rect.as_tuple())
        return snap

    def commit_transform(self, before: dict[str, Rect], name: str = "Move") -> None:
        after: dict[str, Rect] = {}
        for oid in before:
            if oid in self.objects:
                after[oid] = Rect(*self.objects[oid].rect.as_tuple())
            elif oid in self.fields:
                after[oid] = Rect(*self.fields[oid].rect.as_tuple())
                self.fields[oid].appearance_dirty = True
            elif oid in self.images:
                after[oid] = Rect(*self.images[oid].rect.as_tuple())
            elif oid in self.shapes:
                after[oid] = Rect(*self.shapes[oid].rect.as_tuple())
        if before == after:
            self._notify()
            return
        # Live edits already applied — push for undo/redo without re-running execute now.
        self.commands.push_executed(TransformCommand(self, before, after, name=name))
        self.mark_dirty()

    def live_translate(
        self,
        object_ids: list[str],
        dx: float,
        dy: float,
        *,
        snap: bool = True,
        notify: bool = True,
    ) -> None:
        # Keep what is moved on its page: the PDF page ends at its edge, so a part dragged past it
        # would neither show in other PDF apps nor print (and the view has nowhere to draw it).
        # Moved together, the objects keep their arrangement; the move stops at the first edge.
        dx, dy = self._move_kept_on_page(object_ids, dx, dy)
        for oid in object_ids:
            target = (
                self.objects.get(oid)
                or self.fields.get(oid)
                or self.images.get(oid)
                or self.shapes.get(oid)
            )
            if target is None:
                continue
            rect = target.rect.translated(dx, dy)
            if snap and len(object_ids) == 1 and oid in self.objects:
                page = self.pdf.page(target.page_index)
                others = [o for o in self.objects_on_page(target.page_index) if o.object_id != oid]
                result = snap_rect(
                    rect,
                    page_width=page.display_width_pt,
                    page_height=page.display_height_pt,
                    others=others,
                )
                rect = self.keep_on_page(target.page_index, rect.translated(result.dx, result.dy))
                self.guides = result.guides
            elif oid in self.shapes and getattr(target, "kind", None) is not None:
                kind = getattr(target.kind, "value", str(target.kind))
                if kind in ("line", "arrow"):
                    target.x0 += dx
                    target.y0 += dy
                    target.x1 += dx
                    target.y1 += dy
                elif kind == "freehand" and getattr(target, "points", None):
                    target.points = [(px + dx, py + dy) for px, py in target.points]
            target.rect = rect
        if notify:
            self._notify()

    def keep_on_page(self, page_index: int, rect: Rect) -> Rect:
        """``rect`` moved (never resized) so it lies on its page; one larger than the page covers it."""
        try:
            page = self.pdf.page(page_index)
        except Exception:  # noqa: BLE001
            return rect
        pw, ph = float(page.display_width_pt), float(page.display_height_pt)
        r = rect.normalized()
        x = min(max(r.x, min(0.0, pw - r.w)), max(0.0, pw - r.w))
        y = min(max(r.y, min(0.0, ph - r.h)), max(0.0, ph - r.h))
        return rect.translated(x - r.x, y - r.y)

    def _move_kept_on_page(self, object_ids: list[str], dx: float, dy: float) -> tuple[float, float]:
        """The part of a move (dx, dy) that keeps every moved object on its page."""
        lo_x, hi_x, lo_y, hi_y = float("-inf"), float("inf"), float("-inf"), float("inf")
        for oid in object_ids:
            target = self.objects.get(oid) or self.fields.get(oid) or self.images.get(oid) or self.shapes.get(oid)
            if target is None:
                continue
            try:
                page = self.pdf.page(target.page_index)
            except Exception:  # noqa: BLE001
                continue
            pw, ph = float(page.display_width_pt), float(page.display_height_pt)
            r = target.rect.normalized()
            lo_x, hi_x = max(lo_x, min(0.0, pw - r.w) - r.x), min(hi_x, max(0.0, pw - r.w) - r.x)
            lo_y, hi_y = max(lo_y, min(0.0, ph - r.h) - r.y), min(hi_y, max(0.0, ph - r.h) - r.y)
        if lo_x <= hi_x:
            dx = min(max(dx, lo_x), hi_x)
        if lo_y <= hi_y:
            dy = min(max(dy, lo_y), hi_y)
        return dx, dy

    @staticmethod
    def keep_aspect(old: Rect, new: Rect) -> Rect:
        """``new`` reshaped to ``old``'s width:height ratio, following the larger relative change and
        keeping the corner opposite the dragged handle where ``old`` had it."""
        if old.w <= 0 or old.h <= 0 or new.w <= 0 or new.h <= 0:
            return new
        ratio = old.w / old.h
        if abs(new.w - old.w) / old.w >= abs(new.h - old.h) / old.h:
            w, h = new.w, new.w / ratio
        else:
            w, h = new.h * ratio, new.h
        left_moved = abs(new.x - old.x) > 1e-6 and abs(new.x1 - old.x1) <= 1e-6
        top_moved = abs(new.y - old.y) > 1e-6 and abs(new.y1 - old.y1) <= 1e-6
        x = new.x1 - w if left_moved else new.x
        y = new.y1 - h if top_moved else new.y
        return Rect(x, y, w, h)

    def live_resize(self, object_id: str, new_rect: Rect, *, notify: bool = True, constrained: bool = False) -> None:
        """Resize an object; ``constrained``: the caller already applied the aspect ratio (from the
        rectangle at the start of the drag), so it is not adjusted again against the current one."""
        if object_id in self.shapes:
            shape = self.shapes[object_id]
            nr = new_rect.normalized()
            if (not constrained and shape.lock_aspect and nr.w > 0 and nr.h > 0
                    and shape.kind.value not in ("line", "arrow", "freehand")):
                nr = self.keep_aspect(shape.rect, nr)
            shape.fit_to_rect(nr)  # line ends (keeping the direction) and freehand points follow
            if notify:
                self._notify()
            return
        box = self.objects.get(object_id) or self.images.get(object_id)
        if box is None:
            field = self.fields.get(object_id)
            if field is None:
                return
            field.rect = new_rect.normalized()
            if notify:
                self._notify()
            return
        nr = new_rect.normalized()
        if not constrained and object_id in self.images and getattr(box, "lock_aspect", False):
            nr = self.keep_aspect(box.rect, nr)
        box.rect = nr
        if object_id in self.objects:
            box.min_h = nr.h  # the size the user chose is kept (it still grows for more text)
            apply_layout_to_box(box)
        if notify:
            self._notify()

    def commit_text_edit(self, object_id: str, before: str, after: str, *,
                         before_runs: list | None = None, after_runs: list | None = None) -> None:
        if before == after and (before_runs or []) == (after_runs or []):
            self._notify()
            return
        # Text already applied live — push for undo/redo (execute reapplies on redo).
        self.commands.push_executed(SetTextCommand(self, object_id, before, after, before_runs, after_runs))
        self.mark_dirty()

    def live_set_text(self, object_id: str, text: str, *, notify: bool = True, runs: list | None = None) -> None:
        box = self.objects.get(object_id)
        if box is None:
            return
        self._set_box_text(box, text, runs)
        apply_layout_to_box(box)
        if notify:
            self._notify()

    def change_style(self, object_id: str, **kwargs: Any) -> None:
        cmd = self._restyle_box(object_id, **kwargs)
        if cmd is not None:
            self.commands.push_executed(cmd)
            self.mark_dirty()

    def change_style_many(self, object_ids: Iterable[str], **kwargs: Any) -> None:
        """The same style change on several text boxes — one undo step. Pass single settings
        (``font_family=…``), not a whole ``style``: each box keeps its other settings."""
        self.change_styles({oid: dict(kwargs) for oid in object_ids})

    def change_styles(self, changes: dict[str, dict[str, Any]]) -> None:
        """A style change per text box (e.g. each grows from its own size) — one undo step."""
        cmds = [c for c in (self._restyle_box(oid, **kw) for oid, kw in changes.items()) if c]
        if not cmds:
            return
        self.commands.push_executed(cmds[0] if len(cmds) == 1 else GroupCommand("Change Style", cmds))
        self.mark_dirty()

    def push_field_style_change(self, before: dict[str, dict], after: dict[str, dict]) -> None:
        """Record form-field style changes already made (see FieldStyleCommand) as one undo step."""
        changed = {oid: st for oid, st in after.items() if before.get(oid) != st}
        if changed:
            self.commands.push_executed(
                FieldStyleCommand(self, {oid: before[oid] for oid in changed}, changed)
            )

    def _restyle_box(self, object_id: str, **kwargs: Any) -> SetStyleCommand | None:
        """Apply a style change to one text box; the command that undoes it (not yet recorded)."""
        box = self.objects.get(object_id)
        if box is None:
            return None
        before = {
            "style": box.style.to_dict(),
            "align": box.align.value,
            "valign": box.valign.value,
            "size_mode": box.size_mode.value,
            "runs": [dict(r) for r in (box.runs or [])],
        }
        if box.runs:
            # A whole-box change reaches every word again (words given their own value follow the box)
            from core.forms.rich_text import apply_to_all

            names = {"font_family": "family", "font_size": "size", "bold": "bold", "italic": "italic",
                     "text_color": "color"}
            change = {names[k]: v for k, v in kwargs.items() if k in names}
            if "style" in kwargs and isinstance(kwargs["style"], TextStyle):  # only what actually changed
                new_style = kwargs["style"]
                change = {run_key: None for attr, run_key in names.items()
                          if getattr(new_style, attr, None) != getattr(box.style, attr, None)}
            if change:
                box.runs = apply_to_all(box.runs, **change)
        if "style" in kwargs and isinstance(kwargs["style"], TextStyle):
            box.style = kwargs["style"]
        else:
            style = box.style.copy()
            for k, v in kwargs.items():
                if hasattr(style, k):
                    setattr(style, k, v)
            box.style = style
        for key in ("align", "valign", "size_mode"):
            if key in kwargs:
                setattr(box, key, kwargs[key])
        apply_layout_to_box(box)
        after = {
            "style": box.style.to_dict(),
            "align": box.align.value,
            "valign": box.valign.value,
            "size_mode": box.size_mode.value,
            "runs": [dict(r) for r in (box.runs or [])],
        }
        return SetStyleCommand(self, object_id, before, after)

    def copy_style_selection(self) -> None:
        objs = self.selected_objects()
        if objs:
            self._style_clip = copy_style(objs[0])

    def paste_style_selection(self) -> None:
        from core.editing.style_clipboard import get_clipboard

        clip = self._style_clip or get_clipboard()
        if clip is None:
            return
        for box in self.selected_objects():
            before = {
                "style": box.style.to_dict(),
                "align": box.align.value,
                "valign": box.valign.value,
                "size_mode": box.size_mode.value,
            }
            paste_style(box, clip)
            apply_layout_to_box(box)
            after = {
                "style": box.style.to_dict(),
                "align": box.align.value,
                "valign": box.valign.value,
                "size_mode": box.size_mode.value,
            }
            self.commands.push_executed(SetStyleCommand(self, box.object_id, before, after))
        self.mark_dirty()

    def layer_selection(self, direction: str) -> None:
        if not any(self.overlay(i) for i in self.selection):
            return
        self.commands.execute(LayerCommand(self, list(self.selection), direction))

    def begin_native_edit(self, span: NativeSpan, new_text: str) -> TextBox:
        from core.editing.native_text import sample_background

        try:
            page = self.pdf._backend._doc.load_page(span.page_index)  # noqa: SLF001
            cover = sample_background(page, span.rect.as_tuple())
        except Exception:  # noqa: BLE001
            cover = "#ffffff"
        plan = plan_replacement(span, new_text, cover)
        box = span_to_textbox(span)
        box.text = new_text
        box.z_index = self.next_z()
        self.commands.execute(ReplaceNativeTextCommand(self, box, plan))
        self.select([box.object_id])
        self.editing_object_id = box.object_id
        return self.objects[box.object_id]

    def native_box_for(self, object_id: str) -> dict[str, Any] | None:
        box = self.objects.get(object_id)
        if box is None or not box.replaces_native or not box.native_span_id:
            return None
        return self._native_replacements.get(str(box.native_span_id))

    def discard_unchanged_native_edit(self, object_id: str) -> bool:
        """Undo a native-text edit that changed nothing (opened and closed without typing) so the
        original text stays exactly as it was, without an Undo entry. Returns True if discarded."""
        plan = self.native_box_for(object_id)
        box = self.objects.get(object_id)
        last = self.commands._undo[-1] if self.commands._undo else None  # noqa: SLF001
        if (plan is None or box is None or box.text != plan.get("original_text")
                or not isinstance(last, ReplaceNativeTextCommand) or last.box.object_id != object_id
                or box.style.to_dict() != last.box.style.to_dict()):
            return False
        self.commands._undo.pop()  # noqa: SLF001
        last.undo()
        if self.editing_object_id == object_id:
            self.editing_object_id = None
        self.selection = [s for s in self.selection if s != object_id]
        self._notify()
        return True

    def extract_native_spans(self, page_index: int) -> list[NativeSpan]:
        return extract_spans(self.pdf._backend, page_index)  # noqa: SLF001

    # --- undo/redo -------------------------------------------------------

    def undo(self) -> bool:
        ok = self.commands.undo()
        if ok:
            self.mark_dirty()
            self._notify()  # listeners saw the stacks mid-operation (page commands refresh the view themselves)
        return ok

    def redo(self) -> bool:
        ok = self.commands.redo()
        if ok:
            self.mark_dirty()
            self._notify()
        return ok

    # --- forms / tables / layout -----------------------------------------

    def _load_acroform(self) -> None:
        from core.forms.acroform import load_acroform_fields

        try:
            doc = self.pdf._backend._doc  # noqa: SLF001
            for f in load_acroform_fields(doc):
                f.z_index = self.next_z()
                self.fields[f.object_id] = f
        except Exception:  # noqa: BLE001
            pass

    def set_mode(self, mode: WorkspaceMode) -> None:
        self.mode = mode
        if mode == WorkspaceMode.FORMS:
            self.tool = EditTool.FORM_SELECT
        elif mode == WorkspaceMode.LAYOUT:
            self.tool = EditTool.LAYOUT_SELECT
        elif mode == WorkspaceMode.TABLES:
            self.tool = EditTool.TABLE_SELECT
        else:
            self.tool = EditTool.SELECT
        self._notify()

    def fields_on_page(self, page_index: int) -> list[Any]:
        return sorted(
            [f for f in self.fields.values() if f.page_index == page_index],
            key=lambda f: f.z_index,
        )

    def add_form_field(self, field: Any, *, record_dirty: bool = True) -> None:
        field.z_index = self.next_z()
        self.fields[field.object_id] = field
        if record_dirty:
            self.mark_dirty()
        else:
            self._notify()

    def create_form_field(self, page_index: int, rect: Rect, field_type: str) -> Any:
        from core.forms.fields import FieldType, FormField

        ft = FieldType(field_type)
        field = FormField(
            page_index=page_index,
            rect=rect.normalized().with_size(max(rect.w, 16), max(rect.h, 16)),
            field_type=ft,
            name=f"{ft.value}_{len(self.fields)+1}",
            multiline=ft == FieldType.MULTILINE,
            is_acroform=False,
            is_candidate=False,
        )
        if ft == FieldType.DROPDOWN:
            field.options = ["Option A", "Option B", "Option C"]
        self.add_form_field(field)
        self.field_selection = [field.object_id]
        return field

    def set_field_value(
        self,
        field_id: str,
        value: str = "",
        *,
        checked: bool | None = None,
        notify: bool = True,
    ) -> None:
        from core.forms.fields import FieldType

        f = self.fields.get(field_id)
        if f is None or f.readonly:
            return
        if checked is not None:
            f.checked = checked
            f.value_dirty = True
            # Radio groups are mutually exclusive — uncheck every other widget that shares the name.
            if checked and f.field_type == FieldType.RADIO and f.name:
                for other in self.fields.values():
                    if (
                        other is not f
                        and other.name == f.name
                        and other.field_type == FieldType.RADIO
                        and not other.readonly
                        and other.checked
                    ):
                        other.checked = False
                        other.value_dirty = True
        else:
            if f.runs and value != f.value:
                from core.forms.rich_text import reconcile_runs

                f.runs = reconcile_runs(f.runs, f.value, value)  # keep word formatting
                f.appearance_dirty = True
            f.value = value
            f.value_dirty = True
            # One PDF field can be shown in several places (same name, e.g. a name repeated on
            # every page): they share one value, so every copy shows and saves the new entry.
            for other in self.same_field_widgets(f):
                if not other.readonly:
                    other.value = value
                    other.runs = [dict(r) for r in f.runs]
                    other.value_dirty = True
        self.dirty = True
        if notify:
            self._notify()

    def set_field_rich_text(self, field_id: str, value: str, runs: list[dict], *, notify: bool = True) -> bool:
        """Text plus its mixed formatting (from the in-place editor). True when anything changed."""
        from core.forms.rich_text import normalize_runs

        f = self.fields.get(field_id)
        if f is None or f.readonly:
            return False
        runs = normalize_runs(runs)
        if runs and "".join(r["text"] for r in runs) != value:
            runs = []
        if value == f.value and runs == f.runs:
            return False
        for target in [f, *self.same_field_widgets(f)]:
            if target.readonly:
                continue
            target.value = value
            target.runs = [dict(r) for r in runs]
            target.value_dirty = True
            target.appearance_dirty = True
            target.style_dirty = True
        self.dirty = True
        if notify:
            self._notify()
        return True

    def same_field_widgets(self, field: Any) -> list[Any]:
        """Other widgets of the same text field (same full name), excluding ``field`` itself."""
        from core.forms.fields import FieldType

        name = str(getattr(field, "name", "") or "")
        text_kinds = (FieldType.TEXT, FieldType.MULTILINE, FieldType.DATE, FieldType.DROPDOWN)
        if not name or field.field_type not in text_kinds or getattr(field, "is_candidate", False):
            return []
        return [
            o for o in self.fields.values()
            if o is not field and o.name == name and o.field_type in text_kinds and not o.is_candidate
        ]

    def begin_field_edit(self, field_id: str) -> bool:
        """Start direct fill of an existing form field (Select mode)."""
        f = self.fields.get(field_id)
        if f is None or f.readonly or f.is_candidate:
            return False
        self.editing_field_id = field_id
        self.editing_object_id = None
        self.field_selection = [field_id]
        self.selection = []
        self._notify()
        return True

    def commit_field_edit(self, field_id: str | None = None) -> None:
        fid = field_id or self.editing_field_id
        if fid and fid in self.fields:
            self.fields[fid].value_dirty = True
            self.dirty = True
        self.editing_field_id = None
        self._notify()

    def fillable_fields_ordered(self) -> list[Any]:
        """Tab order: PDF order when available, else page then top-to-bottom / left-to-right."""
        items = [
            f
            for f in self.fields.values()
            if not f.is_candidate and not f.readonly and f.field_type.value
            not in ("signature",)
        ]
        return sorted(items, key=lambda f: (f.page_index, f.rect.y, f.rect.x, f.name))

    def tab_to_field(self, *, reverse: bool = False) -> str | None:
        ordered = self.fillable_fields_ordered()
        if not ordered:
            return None
        cur = self.editing_field_id or (self.field_selection[0] if self.field_selection else None)
        ids = [f.object_id for f in ordered]
        if cur not in ids:
            nxt = ids[-1] if reverse else ids[0]
        else:
            i = ids.index(cur)
            nxt = ids[(i - 1) % len(ids)] if reverse else ids[(i + 1) % len(ids)]
        self.begin_field_edit(nxt)
        return nxt

    def accept_candidates(self, field_ids: list[str] | None = None) -> int:
        """Promote detection candidates into real editable fields (user-reviewed)."""
        ids = field_ids or [i for i, f in self.fields.items() if f.is_candidate]
        n = 0
        for fid in ids:
            f = self.fields.get(fid)
            if f is None or not f.is_candidate:
                continue
            f.is_candidate = False
            n += 1
        if n:
            self.mark_dirty()
        return n

    def reject_candidates(self, field_ids: list[str] | None = None) -> None:
        ids = field_ids or [i for i, f in self.fields.items() if f.is_candidate]
        for fid in ids:
            self.fields.pop(fid, None)
        self.field_selection = [i for i in self.field_selection if i in self.fields]
        self._notify()

    def detect_form_fields(self, page_index: int | None = None) -> int:
        """Run candidate detection — does not alter PDF content."""
        from core.forms.detect import detect_field_candidates

        doc = self.pdf._backend._doc  # noqa: SLF001
        # Remove previous unreviewed candidates
        self.reject_candidates()
        found = detect_field_candidates(doc, page_index)
        for f in found:
            self.fields[f.object_id] = f
        self._notify()
        return len(found)

    def detect_tables(self, page_index: int | None = None) -> int:
        from core.tables.detect import detect_tables

        doc = self.pdf._backend._doc  # noqa: SLF001
        tables = detect_tables(doc, page_index)
        for t in tables:
            self.tables[t.object_id] = t
        self._notify()
        return len(tables)

    def align_selection(self, edge: str) -> None:
        from core.layout.ops import align_rects

        rects = self._selected_layout_rects()
        if len(rects) < 2:
            return
        before = {k: Rect(*v.as_tuple()) for k, v in rects.items()}
        after = align_rects(rects, edge)
        self._apply_layout_rects(after)
        self.commands.push_executed(TransformCommand(self, before, after, name=f"Align {edge}"))
        self.mark_dirty()

    def distribute_selection(self, axis: str) -> None:
        from core.layout.ops import distribute_rects

        rects = self._selected_layout_rects()
        if len(rects) < 3:
            return
        before = {k: Rect(*v.as_tuple()) for k, v in rects.items()}
        after = distribute_rects(rects, axis)
        self._apply_layout_rects(after)
        self.commands.push_executed(TransformCommand(self, before, after, name=f"Distribute {axis}"))
        self.mark_dirty()

    def _selected_layout_rects(self) -> dict[str, Rect]:
        rects: dict[str, Rect] = {}
        for oid in self.selection:
            if oid in self.objects:
                rects[oid] = self.objects[oid].rect
        for oid in self.field_selection:
            if oid in self.fields:
                rects[oid] = self.fields[oid].rect
        return rects

    def _apply_layout_rects(self, rects: dict[str, Rect]) -> None:
        for oid, rect in rects.items():
            if oid in self.objects:
                self.objects[oid].rect = rect
            elif oid in self.fields:
                self.fields[oid].rect = rect

    def set_rect(self, object_id: str, rect: Rect, *, record_dirty: bool = True) -> None:
        if object_id in self.objects:
            box = self.objects[object_id]
            box.rect = rect.normalized()
            box.min_h = box.rect.h  # a chosen height (Undo, Properties) is kept, not re-grown to the old one
            apply_layout_to_box(box)
        elif object_id in self.fields:
            field = self.fields[object_id]
            field.rect = rect.normalized()
            field.appearance_dirty = True
        elif object_id in self.images:
            self.images[object_id].rect = rect.normalized()
        elif object_id in self.shapes:
            shape = self.shapes[object_id]
            shape.fit_to_rect(rect)  # line ends (keeping the direction) and freehand points follow
        else:
            return
        if record_dirty:
            self.mark_dirty()
        else:
            self._notify()

    def add_image(self, image: Any, *, record_dirty: bool = True) -> None:
        from core.editing.edit_commands import AddOverlayCommand

        image.z_index = image.z_index or self.next_z()
        if record_dirty:
            self.commands.execute(AddOverlayCommand(self, image, "images"))  # undoable
        else:
            self.images[image.object_id] = image
        if record_dirty:
            self.mark_dirty()
        else:
            self._notify()

    def images_on_page(self, page_index: int) -> list[Any]:
        items = [o for o in self.images.values() if o.page_index == page_index]
        return sorted(items, key=lambda o: o.z_index)

    def replace_image_source(self, object_id: str, path: str) -> None:
        img = self.images.get(object_id)
        if img is None:
            return
        img.source_path = path
        self.mark_dirty()

    def set_image_opacity(self, object_id: str, opacity: float) -> None:
        self.set_overlay_attrs(object_id, opacity=max(0.0, min(1.0, opacity)))

    def set_image_rotation(self, object_id: str, degrees: float) -> None:
        self.set_overlay_attrs(object_id, rotation=float(degrees) % 360.0)

    def set_image_crop(self, object_id: str, crop: tuple[float, float, float, float]) -> None:
        self.set_overlay_attrs(object_id, crop=tuple(crop))

    def smart_layout_after_move(self, moved_id: str, before: Rect, after: Rect) -> None:
        from core.layout.ops import LayoutPolicy, smart_nudge_related

        if self.layout_policy != LayoutPolicy.SMART.value:
            return
        others = {**{i: o.rect for i, o in self.objects.items()}, **{i: f.rect for i, f in self.fields.items()}}
        updates = smart_nudge_related(moved_id, before, after, others)
        if not updates:
            return
        snap_before = {k: Rect(*others[k].as_tuple()) for k in updates}
        self._apply_layout_rects(updates)
        self.commands.push_executed(TransformCommand(self, snap_before, updates, name="Smart nudge"))

    # --- serialization / session -----------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.pdf.path),
            "objects": [o.to_dict() for o in self.all_objects()],
            "images": [o.to_dict() for o in self.images.values()],
            "shapes": [o.to_dict() for o in self.shapes.values()],
            "fields": [f.to_dict() for f in self.fields.values()],
            "tables": [t.to_dict() for t in self.tables.values()],
            "native_replacements": self._native_replacements,
            "layout_policy": self.layout_policy,
            "flatten_on_save": self.flatten_on_save,
            "dirty": self.dirty,
        }

    def load_objects(self, data: dict[str, Any]) -> None:
        from core.editing.image_box import ImageBox
        from core.forms.fields import FormField
        from core.tables.model import TableModel

        self.objects.clear()
        self.selection.clear()
        self.fields.clear()
        self.tables.clear()
        self.images.clear()
        self.shapes.clear()
        self._native_replacements = dict(data.get("native_replacements") or {})
        for item in data.get("objects") or []:
            box = TextBox.from_dict(item)
            apply_layout_to_box(box)
            self.objects[box.object_id] = box
            self._z_counter = max(self._z_counter, box.z_index)
        for item in data.get("images") or []:
            img = ImageBox.from_dict(item)
            self.images[img.object_id] = img
            self._z_counter = max(self._z_counter, img.z_index)
        from core.editing.shape_box import ShapeBox

        for item in data.get("shapes") or []:
            shape = ShapeBox.from_dict(item)
            self.shapes[shape.object_id] = shape
            self._z_counter = max(self._z_counter, shape.z_index)
        for item in data.get("fields") or []:
            f = FormField.from_dict(item)
            self.fields[f.object_id] = f
        for item in data.get("tables") or []:
            t = TableModel.from_dict(item)
            self.tables[t.object_id] = t
        self.layout_policy = str(data.get("layout_policy") or "preserve_layout")
        self.flatten_on_save = bool(data.get("flatten_on_save", False))
        self.dirty = bool(data.get("dirty", True))
        self._notify()

    def clipboard_copy(self) -> list[dict[str, Any]]:
        """Selected text boxes, shapes and pictures (text boxes as before; others tagged by kind)."""
        out: list[dict[str, Any]] = []
        for oid in self.selection:
            found = self.overlay(oid)
            if found is None:
                continue
            kind, obj = found
            data = obj.to_dict()
            if kind != "text":
                data = {"_overlay": kind, "data": data}
            out.append(data)
        return out

    def clipboard_paste(self, payload: list[dict[str, Any]], *, page_index: int | None = None) -> None:
        import uuid

        from core.editing.edit_commands import AddOverlayCommand
        from core.editing.image_box import ImageBox
        from core.editing.shape_box import ShapeBox

        created: list[str] = []
        for item in payload:
            kind = item.get("_overlay") if isinstance(item, dict) else None
            if kind in ("shape", "image"):
                obj = (ShapeBox if kind == "shape" else ImageBox).from_dict(item.get("data") or {})
                obj.object_id = str(uuid.uuid4())
                if page_index is not None:
                    obj.page_index = page_index
                self.translate_overlay(obj, 12, 12)
                obj.z_index = self.next_z()
                self.commands.execute(AddOverlayCommand(self, obj, "shapes" if kind == "shape" else "images"))
                created.append(obj.object_id)
                continue
            box = TextBox.from_dict(item)
            box.object_id = str(uuid.uuid4())
            if page_index is not None:
                box.page_index = page_index
            box.rect = box.rect.translated(12, 12)
            box.z_index = self.next_z()
            self.commands.execute(AddTextBoxCommand(self, box))
            created.append(box.object_id)
        if created:
            self.select(created)
