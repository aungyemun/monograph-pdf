"""Page-level abstractions in PDF coordinate space (points, 1/72 inch)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PageContentKind(str, Enum):
    TEXT = "text"
    IMAGE_SCANNED = "image_scanned"
    MIXED = "mixed"
    EMPTY = "empty"


@dataclass(frozen=True)
class PageContent:
    """What a page contains (text characters, pictures) — found by reading the page's text."""

    content_kind: PageContentKind
    has_text: bool
    has_images: bool
    char_count: int
    image_count: int


class PageInfo:
    """Immutable page metadata. Dimensions are in PDF points (unscaled) of the displayed page,
    i.e. with /Rotate applied.

    The page size is known at once; the content (text, pictures) is analysed only when first asked
    for, because extracting the text of every page made opening a 3000-page document take seconds
    although showing it needs only the page sizes.
    """

    __slots__ = ("index", "width_pt", "height_pt", "rotation", "_content", "_analyze")

    def __init__(self, index: int, width_pt: float, height_pt: float, rotation: int,
                 content_kind: PageContentKind | None = None, has_text: bool = False, has_images: bool = False,
                 char_count: int = 0, image_count: int = 0, *, analyze=None) -> None:
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "width_pt", width_pt)
        object.__setattr__(self, "height_pt", height_pt)
        object.__setattr__(self, "rotation", rotation)
        content = None
        if content_kind is not None:
            content = PageContent(content_kind, has_text, has_images, char_count, image_count)
        object.__setattr__(self, "_content", content)
        object.__setattr__(self, "_analyze", analyze)

    def __setattr__(self, name, value):  # frozen, like the dataclass it replaces
        raise AttributeError(f"PageInfo is immutable ({name})")

    @property
    def content(self) -> PageContent:
        if self._content is None:
            content = self._analyze() if self._analyze is not None else PageContent(
                PageContentKind.EMPTY, False, False, 0, 0)
            object.__setattr__(self, "_content", content)
            object.__setattr__(self, "_analyze", None)
        return self._content

    @property
    def content_analyzed(self) -> bool:
        return self._content is not None

    content_kind = property(lambda self: self.content.content_kind)
    has_text = property(lambda self: self.content.has_text)
    has_images = property(lambda self: self.content.has_images)
    char_count = property(lambda self: self.content.char_count)
    image_count = property(lambda self: self.content.image_count)

    # immutable: copies are the object itself; pickling stores the analysed content
    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __reduce__(self):
        c = self.content
        return (PageInfo, (self.index, self.width_pt, self.height_pt, self.rotation, c.content_kind, c.has_text,
                           c.has_images, c.char_count, c.image_count))

    def _key(self):
        return (self.index, self.width_pt, self.height_pt, self.rotation, self.content)

    def __eq__(self, other) -> bool:
        return isinstance(other, PageInfo) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash((self.index, self.width_pt, self.height_pt, self.rotation))

    def __repr__(self) -> str:
        return (f"PageInfo(index={self.index}, width_pt={self.width_pt}, height_pt={self.height_pt}, "
                f"rotation={self.rotation}, content={self._content!r})")

    @property
    def display_width_pt(self) -> float:
        """Width as displayed. ``width_pt`` is MuPDF's page rectangle, which already has /Rotate
        applied (a 90° page reports height × width), so it is not swapped again here."""
        return self.width_pt

    @property
    def display_height_pt(self) -> float:
        return self.height_pt
