"""Detect line-based table candidates; expose only when confidence is sufficient."""

from __future__ import annotations

from collections import defaultdict

import fitz

from core.editing.geometry import Rect
from core.page_space import point_to_display, rect_to_display
from core.tables.model import TableCell, TableModel

# Minimum confidence to expose a table model to the UI
MIN_TABLE_CONFIDENCE = 0.55


def _cluster(values: list[float], tol: float = 3.0) -> list[float]:
    if not values:
        return []
    values = sorted(values)
    clusters: list[list[float]] = [[values[0]]]
    for v in values[1:]:
        if abs(v - clusters[-1][-1]) <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


def detect_tables(doc: fitz.Document, page_index: int | None = None) -> list[TableModel]:
    pages = range(doc.page_count) if page_index is None else [page_index]
    out: list[TableModel] = []
    for pi in pages:
        page = doc.load_page(pi)
        drawings = page.get_drawings() or []
        hs: list[tuple[float, float, float]] = []  # y, x0, x1
        vs: list[tuple[float, float, float]] = []  # x, y0, y1
        def add_segment(p1, p2) -> None:
            if abs(p1.y - p2.y) < 1.2 and abs(p1.x - p2.x) >= 20:
                hs.append((p1.y, min(p1.x, p2.x), max(p1.x, p2.x)))
            elif abs(p1.x - p2.x) < 1.2 and abs(p1.y - p2.y) >= 12:
                vs.append((p1.x, min(p1.y, p2.y), max(p1.y, p2.y)))

        cell_rects: list[fitz.Rect] = []
        for d in drawings:
            for item in d.get("items") or []:
                if item[0] == "l":
                    add_segment(
                        point_to_display(page, item[1].x, item[1].y), point_to_display(page, item[2].x, item[2].y)
                    )
                elif item[0] == "re":
                    # Many generators draw cell borders as rectangles (outlined cells, or very thin filled
                    # bars). A thin bar is one rule; an ordinary cell contributes its four edges.
                    r = rect_to_display(page, item[1])
                    if r.height <= 1.5 and r.width >= 20:
                        add_segment(fitz.Point(r.x0, (r.y0 + r.y1) / 2), fitz.Point(r.x1, (r.y0 + r.y1) / 2))
                    elif r.width <= 1.5 and r.height >= 12:
                        add_segment(fitz.Point((r.x0 + r.x1) / 2, r.y0), fitz.Point((r.x0 + r.x1) / 2, r.y1))
                    elif 20 <= r.width <= page.rect.width * 0.5 and 12 <= r.height <= page.rect.height * 0.25:
                        cell_rects.append(r)
        # Outlined cells count as table rules only when they tile: enough of them share an edge both
        # sideways and top-to-bottom. Separate input boxes (forms) never do.
        side = stacked = 0
        for i, a in enumerate(cell_rects):
            for b in cell_rects[i + 1 :]:
                if abs(a.x1 - b.x0) < 1.5 or abs(b.x1 - a.x0) < 1.5:
                    side += min(a.y1, b.y1) - max(a.y0, b.y0) > 4
                if abs(a.y1 - b.y0) < 1.5 or abs(b.y1 - a.y0) < 1.5:
                    stacked += min(a.x1, b.x1) - max(a.x0, b.x0) > 4
        if side >= 3 and stacked >= 3:
            for r in cell_rects:
                for a, b in (((r.x0, r.y0), (r.x1, r.y0)), ((r.x0, r.y1), (r.x1, r.y1)),
                             ((r.x0, r.y0), (r.x0, r.y1)), ((r.x1, r.y0), (r.x1, r.y1))):
                    add_segment(fitz.Point(*a), fitz.Point(*b))

        if len(hs) < 3 or len(vs) < 2:
            continue

        y_lines = _cluster([h[0] for h in hs], tol=2.5)
        x_lines = _cluster([v[0] for v in vs], tol=2.5)
        if len(y_lines) < 3 or len(x_lines) < 3:
            continue

        # Confidence from regularity of spacing + coverage
        row_gaps = [y_lines[i + 1] - y_lines[i] for i in range(len(y_lines) - 1)]
        col_gaps = [x_lines[i + 1] - x_lines[i] for i in range(len(x_lines) - 1)]
        if not row_gaps or not col_gaps:
            continue
        row_var = max(row_gaps) / max(min(row_gaps), 1e-3)
        col_var = max(col_gaps) / max(min(col_gaps), 1e-3)
        conf = 0.9
        if row_var > 3 or col_var > 3:
            conf -= 0.25
        if len(y_lines) < 4:
            conf -= 0.1
        conf = max(0.0, min(1.0, conf))
        if conf < MIN_TABLE_CONFIDENCE:
            continue

        bounds = Rect(
            x_lines[0],
            y_lines[0],
            x_lines[-1] - x_lines[0],
            y_lines[-1] - y_lines[0],
        )
        col_widths = [x_lines[i + 1] - x_lines[i] for i in range(len(x_lines) - 1)]
        row_heights = [y_lines[i + 1] - y_lines[i] for i in range(len(y_lines) - 1)]
        table = TableModel(
            page_index=pi,
            bounds=bounds,
            col_widths=col_widths,
            row_heights=row_heights,
            confidence=conf,
        )
        # Associate contained text
        words = page.get_text("words") or []
        buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
        for w in words:
            wd = rect_to_display(page, (w[0], w[1], w[2], w[3]))
            x0, y0, x1, y1, text = wd.x0, wd.y0, wd.x1, wd.y1, w[4]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if not (bounds.x <= cx <= bounds.x1 and bounds.y <= cy <= bounds.y1):
                continue
            # find cell
            col = 0
            acc = bounds.x
            for i, cw in enumerate(col_widths):
                if cx <= acc + cw:
                    col = i
                    break
                acc += cw
            row = 0
            acc = bounds.y
            for i, rh in enumerate(row_heights):
                if cy <= acc + rh:
                    row = i
                    break
                acc += rh
            buckets[(row, col)].append(str(text))

        for r in range(len(row_heights)):
            for c in range(len(col_widths)):
                text = " ".join(buckets.get((r, c), []))
                table.cells[(r, c)] = TableCell(row=r, col=c, text=text)
        out.append(table)
    return out
