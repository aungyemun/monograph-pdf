"""Command implementations for editable overlays (Undo/Redo)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.commands import Command
from core.editing.geometry import Rect
from core.editing.text_box import TextBox
from core.editing.text_layout import apply_layout_to_box
from core.editing.text_style import TextStyle

if TYPE_CHECKING:
    from core.editing.edit_model import EditableDocument


class AddTextBoxCommand(Command):
    def __init__(self, model: "EditableDocument", box: TextBox) -> None:
        self.model = model
        self.box = box.clone_same_id()

    @property
    def name(self) -> str:
        return "Add Text Box"

    def execute(self) -> None:
        apply_layout_to_box(self.box)
        self.model.add_object(self.box.clone_same_id(), record_dirty=True)

    def undo(self) -> None:
        self.model.remove_object(self.box.object_id, record_dirty=True)


class DeleteObjectsCommand(Command):
    def __init__(self, model: "EditableDocument", object_ids: list[str]) -> None:
        self.model = model
        self.object_ids = list(object_ids)
        self._snapshots: list[TextBox] = []
        self._shape_snaps: list[Any] = []
        self._image_snaps: list[Any] = []

    @property
    def name(self) -> str:
        return "Delete"

    def execute(self) -> None:
        self._snapshots = []
        self._shape_snaps = []
        self._image_snaps = []
        for oid in self.object_ids:
            obj = self.model.get(oid)
            if obj is not None:
                self._snapshots.append(obj.clone_same_id())
                self.model.remove_object(oid, record_dirty=True)
                continue
            shape = self.model.shapes.get(oid)
            if shape is not None:
                self._shape_snaps.append(shape.clone_same_id())
                self.model.shapes.pop(oid, None)
                self.model.selection = [s for s in self.model.selection if s != oid]
                self.model.mark_dirty()
                continue
            img = self.model.images.get(oid)
            if img is not None:
                self._image_snaps.append(img.clone_same_id())
                self.model.images.pop(oid, None)
                self.model.selection = [s for s in self.model.selection if s != oid]
                self.model.mark_dirty()

    def undo(self) -> None:
        for box in self._snapshots:
            self.model.add_object(box.clone_same_id(), record_dirty=True)
        for shape in self._shape_snaps:
            self.model.shapes[shape.object_id] = shape.clone_same_id()
            self.model.mark_dirty()
        for img in self._image_snaps:
            self.model.images[img.object_id] = img.clone_same_id()
            self.model.mark_dirty()


class TransformCommand(Command):
    """Move/resize — stores before/after rects for one or more objects."""

    def __init__(
        self,
        model: "EditableDocument",
        before: dict[str, Rect],
        after: dict[str, Rect],
        name: str = "Transform",
    ) -> None:
        self.model = model
        self.before = {k: Rect(*v.as_tuple()) for k, v in before.items()}
        self.after = {k: Rect(*v.as_tuple()) for k, v in after.items()}
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def execute(self) -> None:
        for oid, rect in self.after.items():
            self.model.set_rect(oid, rect, record_dirty=True)

    def undo(self) -> None:
        for oid, rect in self.before.items():
            self.model.set_rect(oid, rect, record_dirty=True)


class SetTextCommand(Command):
    def __init__(self, model: "EditableDocument", object_id: str, before: str, after: str) -> None:
        self.model = model
        self.object_id = object_id
        self.before = before
        self.after = after

    @property
    def name(self) -> str:
        return "Edit Text"

    def execute(self) -> None:
        self.model.set_text(self.object_id, self.after, record_dirty=True)

    def undo(self) -> None:
        self.model.set_text(self.object_id, self.before, record_dirty=True)


class SetStyleCommand(Command):
    def __init__(
        self,
        model: "EditableDocument",
        object_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        self.model = model
        self.object_id = object_id
        self.before = before
        self.after = after

    @property
    def name(self) -> str:
        return "Change Style"

    def execute(self) -> None:
        self.model.apply_style_dict(self.object_id, self.after, record_dirty=True)

    def undo(self) -> None:
        self.model.apply_style_dict(self.object_id, self.before, record_dirty=True)


class DuplicateCommand(Command):
    """Duplicate text boxes, shapes and pictures (offset down and right); Undo removes the copies."""

    def __init__(self, model: "EditableDocument", object_ids: list[str], offset: float = 12.0) -> None:
        self.model = model
        self.source_ids = list(object_ids)
        self.offset = offset
        self._created: list[Any] = []
        self._kinds: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "Duplicate"

    def execute(self) -> None:
        if self._created:  # Redo: the same copies again
            for obj in self._created:
                self._put(self._kinds[obj.object_id], obj.clone_same_id())
            return
        for oid in self.source_ids:
            found = self.model.overlay(oid)
            if found is None:
                continue
            kind, src = found
            dup = src.copy()
            self.model.translate_overlay(dup, self.offset, self.offset)
            dup.z_index = self.model.next_z()
            if kind == "text":
                apply_layout_to_box(dup)
            self._kinds[dup.object_id] = kind
            self._put(kind, dup)
            self._created.append(dup.clone_same_id())

    def _put(self, kind: str, obj: Any) -> None:
        if kind == "text":
            self.model.add_object(obj, record_dirty=True)
        else:
            getattr(self.model, "shapes" if kind == "shape" else "images")[obj.object_id] = obj
            self.model.mark_dirty()

    def undo(self) -> None:
        for obj in self._created:
            kind = self._kinds[obj.object_id]
            if kind == "text":
                self.model.remove_object(obj.object_id, record_dirty=True)
            else:
                getattr(self.model, "shapes" if kind == "shape" else "images").pop(obj.object_id, None)
                self.model.selection = [s for s in self.model.selection if s != obj.object_id]
                self.model.mark_dirty()


class LayerCommand(Command):
    def __init__(
        self,
        model: "EditableDocument",
        object_ids: list[str],
        direction: str,  # forward | backward | front | back
    ) -> None:
        self.model = model
        self.object_ids = list(object_ids)
        self.direction = direction
        self._before: dict[str, int] = {}
        self._after: dict[str, int] = {}

    @property
    def name(self) -> str:
        return f"Layer {self.direction}"

    def execute(self) -> None:
        self._before = self.model.z_snapshot(self.object_ids)
        self.model.change_layer(self.object_ids, self.direction)
        self._after = self.model.z_snapshot(self.object_ids)

    def undo(self) -> None:
        self.model.restore_z(self._before)


class ReplaceNativeTextCommand(Command):
    """Controlled redaction+reinsertion (or safe replace) — always undoable."""

    def __init__(
        self,
        model: "EditableDocument",
        box: TextBox,
        plan: dict[str, Any],
    ) -> None:
        self.model = model
        self.box = box.clone_same_id()
        self.plan = plan
        self._added = False

    @property
    def name(self) -> str:
        return "Replace Native Text"

    def execute(self) -> None:
        apply_layout_to_box(self.box)
        self.model.add_object(self.box.clone_same_id(), record_dirty=True)
        self.model.note_native_replacement(self.plan)
        self._added = True

    def undo(self) -> None:
        if self._added:
            self.model.remove_object(self.box.object_id, record_dirty=True)
            self.model.forget_native_replacement(self.plan.get("span_id"))


class AddOverlayCommand(Command):
    """Add a shape or an image (Undo removes it, Redo puts the same object back)."""

    def __init__(self, model: "EditableDocument", obj: Any, kind: str) -> None:
        self.model = model
        self.obj = obj
        self.kind = kind  # "shapes" or "images"
        self._snapshot: Any = None

    @property
    def name(self) -> str:
        return "Add Shape" if self.kind == "shapes" else "Add Image"

    def execute(self) -> None:
        obj = self.obj if self._snapshot is None else self._snapshot.clone_same_id()
        getattr(self.model, self.kind)[obj.object_id] = obj
        self.model.mark_dirty()

    def undo(self) -> None:
        current = getattr(self.model, self.kind).pop(self.obj.object_id, None)
        if current is not None:
            self._snapshot = current.clone_same_id()
        self.model.selection = [s for s in self.model.selection if s != self.obj.object_id]
        self.model.mark_dirty()


class SetOverlayAttrsCommand(Command):
    """Change properties of a shape or picture (colour, line width, opacity, rotation, ...).

    Consecutive changes of the same properties of the same object within a moment (a spin box being
    stepped or typed into) merge into one Undo step."""

    MERGE_SECONDS = 1.5

    def __init__(self, model: "EditableDocument", object_id: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        import time

        self.model = model
        self.object_id = object_id
        self.before = dict(before)
        self.after = dict(after)
        self.stamp = time.monotonic()

    @property
    def name(self) -> str:
        return "Change Properties"

    def _apply(self, values: dict[str, Any]) -> None:
        found = self.model.overlay(self.object_id)
        if found is None:
            return
        obj = found[1]
        for k, v in values.items():
            setattr(obj, k, v)
        if getattr(getattr(obj, "kind", None), "value", None) in ("line", "arrow"):
            obj.sync_rect_from_line()
        self.model.mark_dirty()

    def execute(self) -> None:
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)

    def can_merge(self, other: "SetOverlayAttrsCommand") -> bool:
        return (other.object_id == self.object_id and set(other.after) == set(self.after)
                and other.stamp - self.stamp <= self.MERGE_SECONDS)


class GroupCommand(Command):
    """Several commands that undo and redo as one step (one change applied to many objects)."""

    def __init__(self, name: str, commands: list[Command]) -> None:
        self._name = name
        self.commands = list(commands)

    @property
    def name(self) -> str:
        return self._name

    def execute(self) -> None:
        for cmd in self.commands:
            cmd.execute()

    def undo(self) -> None:
        for cmd in reversed(self.commands):
            cmd.undo()


# What a form field's look consists of (the inspector / toolbar settings and the words' own formats)
FIELD_STYLE_ATTRS = ("font_family", "font_size", "multiline", "bold", "italic", "align", "valign", "text_color")


def field_style_state(field: Any) -> dict[str, Any]:
    state = {key: getattr(field, key) for key in FIELD_STYLE_ATTRS}
    state["runs"] = [dict(r) for r in (field.runs or [])]
    state["appearance_dirty"] = bool(field.appearance_dirty)
    state["style_dirty"] = bool(field.style_dirty)
    return state


class FieldStyleCommand(Command):
    """Font, size, wrap, bold, italic, alignment or colour of one or more form fields (one undo step).

    ``before`` / ``after`` map field object ids to :func:`field_style_state`. Undo restores the
    saved-state flags too, so undoing every change leaves an untouched field's own appearance in
    the PDF (an entry typed since then still gets a new appearance)."""

    def __init__(self, model: "EditableDocument", before: dict[str, dict], after: dict[str, dict],
                 name: str = "Change Field Style") -> None:
        self.model = model
        self.before = before
        self.after = after
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def _apply(self, states: dict[str, dict]) -> None:
        for oid, state in states.items():
            field = self.model.fields.get(oid)
            if field is None:
                continue
            for key in FIELD_STYLE_ATTRS:
                setattr(field, key, state[key])
            field.runs = [dict(r) for r in state["runs"]]
            field.appearance_dirty = bool(state["appearance_dirty"] or field.value_dirty)
            field.style_dirty = bool(state["style_dirty"])
        self.model.dirty = True

    def execute(self) -> None:
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)