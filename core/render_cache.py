"""Distance-aware render buffer cache — keeps visible/nearby pages only."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Generic, Hashable, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")



@dataclass(frozen=True)
class RenderKey:
    page_index: int
    # Discrete zoom bucket (zoom * 100 rounded) keeps cache stable under tiny jitter
    zoom_bucket: int
    rotation: int
    dpr_bucket: int  # devicePixelRatio * 100

    @staticmethod
    def make(page_index: int, zoom: float, rotation: int, dpr: float) -> "RenderKey":
        return RenderKey(
            page_index=page_index,
            zoom_bucket=int(round(zoom * 100)),
            rotation=int(rotation) % 360,
            dpr_bucket=int(round(dpr * 100)),
        )


class RenderCache(Generic[K, V]):
    """Ordered cache with explicit retain-window eviction relative to a focus page."""

    def __init__(self, max_entries: int = 24) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max = max_entries
        self._data: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: K, value: V) -> None:
        if key in self._data:
            self._data.move_to_end(key)
            self._data[key] = value
        else:
            self._data[key] = value
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def discard(self, key: K) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def retain_near_pages(
        self,
        focus_page: int,
        radius: int,
        page_of: Callable[[K], int],
    ) -> list[V]:
        """Drop entries whose page is farther than radius from focus. Returns evicted values."""
        keep = set(range(max(0, focus_page - radius), focus_page + radius + 1))
        evicted: list[V] = []
        for key in list(self._data.keys()):
            page = page_of(key)
            if page not in keep:
                evicted.append(self._data.pop(key))
        return evicted


    def keys(self) -> list[K]:
        return list(self._data.keys())
