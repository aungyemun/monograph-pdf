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
    def __init__(self, model: "EditableDocument", object_ids: list[str], offset: float = 12.0) -> None:
        self.model = model
        self.source_ids = list(object_ids)
        self.offset = offset
        self._created: list[TextBox] = []

    @property
    def name(self) -> str:
        return "Duplicate"

    def execute(self) -> None:
        self._created = []
        for oid in self.source_ids:
            src = self.model.get(oid)
            if src is None:
                continue
            dup = src.copy()
            dup.rect = src.rect.translated(self.offset, self.offset)
            dup.z_index = self.model.next_z()
            apply_layout_to_box(dup)
            self.model.add_object(dup, record_dirty=True)
            self._created.append(dup.clone_same_id())

    def undo(self) -> None:
        for box in self._created:
            self.model.remove_object(box.object_id, record_dirty=True)


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
        self._before = {oid: self.model.get(oid).z_index for oid in self.object_ids if self.model.get(oid)}
        self.model.change_layer(self.object_ids, self.direction)
        self._after = {oid: self.model.get(oid).z_index for oid in self.object_ids if self.model.get(oid)}

    def undo(self) -> None:
        for oid, z in self._before.items():
            self.model.set_z(oid, z, record_dirty=True)


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
