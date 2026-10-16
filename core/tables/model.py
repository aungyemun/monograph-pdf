"""Editable table model reconstructed from line geometry (not Word reflow)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from core.editing.geometry import Rect


@dataclass
class TableCell:
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    text: str = ""
    align: str = "left"
    valign: str = "middle"
    fill: str = "#00000000"
    border_color: str = "#000000"
    border_width: float = 0.5
    wrap: bool = True


@dataclass
class TableModel:
    page_index: int
    bounds: Rect
    col_widths: list[float]
    row_heights: list[float]
    cells: dict[tuple[int, int], TableCell] = field(default_factory=dict)
    confidence: float = 0.0
    object_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def nrows(self) -> int:
        return len(self.row_heights)

    @property
    def ncols(self) -> int:
        return len(self.col_widths)

    def cell_rect(self, row: int, col: int) -> Rect:
        x = self.bounds.x + sum(self.col_widths[:col])
        y = self.bounds.y + sum(self.row_heights[:row])
        cell = self.cells.get((row, col))
        w = sum(self.col_widths[col : col + (cell.col_span if cell else 1)])
        h = sum(self.row_heights[row : row + (cell.row_span if cell else 1)])
        return Rect(x, y, w, h)

    def ensure_cells(self) -> None:
        for r in range(self.nrows):
            for c in range(self.ncols):
                if (r, c) not in self.cells:
                    self.cells[(r, c)] = TableCell(row=r, col=c)

    def set_row_height(self, row: int, height: float) -> None:
        if 0 <= row < self.nrows:
            self.row_heights[row] = max(8.0, height)
            self._refresh_bounds()

    def set_col_width(self, col: int, width: float) -> None:
        if 0 <= col < self.ncols:
            self.col_widths[col] = max(12.0, width)
            self._refresh_bounds()

    def add_row(self, index: int | None = None, height: float = 22.0) -> None:
        idx = self.nrows if index is None else max(0, min(self.nrows, index))
        self.row_heights.insert(idx, height)
        # shift cells
        new_cells: dict[tuple[int, int], TableCell] = {}
        for (r, c), cell in self.cells.items():
            nr = r + 1 if r >= idx else r
            cell.row = nr
            new_cells[(nr, c)] = cell
        self.cells = new_cells
        for c in range(self.ncols):
            self.cells[(idx, c)] = TableCell(row=idx, col=c)
        self._refresh_bounds()

    def delete_row(self, index: int) -> None:
        if self.nrows <= 1 or not (0 <= index < self.nrows):
            return
        self.row_heights.pop(index)
        new_cells: dict[tuple[int, int], TableCell] = {}
        for (r, c), cell in self.cells.items():
            if r == index:
                continue
            nr = r - 1 if r > index else r
            cell.row = nr
            new_cells[(nr, c)] = cell
        self.cells = new_cells
        self._refresh_bounds()

    def add_column(self, index: int | None = None, width: float = 60.0) -> None:
        idx = self.ncols if index is None else max(0, min(self.ncols, index))
        self.col_widths.insert(idx, width)
        new_cells: dict[tuple[int, int], TableCell] = {}
        for (r, c), cell in self.cells.items():
            nc = c + 1 if c >= idx else c
            cell.col = nc
            new_cells[(r, nc)] = cell
        self.cells = new_cells
        for r in range(self.nrows):
            self.cells[(r, idx)] = TableCell(row=r, col=idx)
        self._refresh_bounds()

    def delete_column(self, index: int) -> None:
        if self.ncols <= 1 or not (0 <= index < self.ncols):
            return
        self.col_widths.pop(index)
        new_cells: dict[tuple[int, int], TableCell] = {}
        for (r, c), cell in self.cells.items():
            if c == index:
                continue
            nc = c - 1 if c > index else c
            cell.col = nc
            new_cells[(r, nc)] = cell
        self.cells = new_cells
        self._refresh_bounds()

    def merge_cells(self, r0: int, c0: int, r1: int, c1: int) -> bool:
        if r1 < r0 or c1 < c0:
            return False
        if r0 == r1 and c0 == c1:
            return False
        master = self.cells.get((r0, c0)) or TableCell(row=r0, col=c0)
        texts = []
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                cell = self.cells.get((r, c))
                if cell and cell.text:
                    texts.append(cell.text)
                if (r, c) != (r0, c0):
                    self.cells.pop((r, c), None)
        master.row_span = r1 - r0 + 1
        master.col_span = c1 - c0 + 1
        master.text = " ".join(texts) if texts else master.text
        self.cells[(r0, c0)] = master
        return True

    def split_cell(self, row: int, col: int) -> bool:
        cell = self.cells.get((row, col))
        if cell is None or (cell.row_span == 1 and cell.col_span == 1):
            return False
        rs, cs = cell.row_span, cell.col_span
        cell.row_span = 1
        cell.col_span = 1
        for r in range(row, row + rs):
            for c in range(col, col + cs):
                if (r, c) == (row, col):
                    continue
                self.cells[(r, c)] = TableCell(row=r, col=c)
        return True

    def _refresh_bounds(self) -> None:
        self.bounds = Rect(
            self.bounds.x,
            self.bounds.y,
            sum(self.col_widths),
            sum(self.row_heights),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "page_index": self.page_index,
            "bounds": list(self.bounds.as_tuple()),
            "col_widths": list(self.col_widths),
            "row_heights": list(self.row_heights),
            "confidence": self.confidence,
            "cells": [
                {
                    "row": cell.row,
                    "col": cell.col,
                    "row_span": cell.row_span,
                    "col_span": cell.col_span,
                    "text": cell.text,
                    "align": cell.align,
                    "valign": cell.valign,
                    "fill": cell.fill,
                    "border_color": cell.border_color,
                    "border_width": cell.border_width,
                    "wrap": cell.wrap,
                }
                for cell in self.cells.values()
            ],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TableModel":
        b = data.get("bounds") or [0, 0, 100, 100]
        t = TableModel(
            object_id=str(data.get("object_id") or uuid.uuid4()),
            page_index=int(data.get("page_index", 0)),
            bounds=Rect(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
            col_widths=[float(x) for x in data.get("col_widths") or [50]],
            row_heights=[float(x) for x in data.get("row_heights") or [20]],
            confidence=float(data.get("confidence") or 0),
        )
        for c in data.get("cells") or []:
            cell = TableCell(
                row=int(c["row"]),
                col=int(c["col"]),
                row_span=int(c.get("row_span", 1)),
                col_span=int(c.get("col_span", 1)),
                text=str(c.get("text") or ""),
                align=str(c.get("align") or "left"),
                valign=str(c.get("valign") or "middle"),
                fill=str(c.get("fill") or "#00000000"),
                border_color=str(c.get("border_color") or "#000000"),
                border_width=float(c.get("border_width", 0.5)),
                wrap=bool(c.get("wrap", True)),
            )
            t.cells[(cell.row, cell.col)] = cell
        t.ensure_cells()
        return t
