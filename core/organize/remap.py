"""Helpers to build page-index remapping tables after structural edits."""

from __future__ import annotations


def map_after_delete(old_count: int, deleted: list[int]) -> dict[int, int | None]:
    deleted_set = set(deleted)
    mapping: dict[int, int | None] = {}
    new_i = 0
    for old in range(old_count):
        if old in deleted_set:
            mapping[old] = None
        else:
            mapping[old] = new_i
            new_i += 1
    return mapping


def map_after_insert(old_count: int, at_index: int, inserted_count: int) -> dict[int, int | None]:
    mapping: dict[int, int | None] = {}
    for old in range(old_count):
        if old < at_index:
            mapping[old] = old
        else:
            mapping[old] = old + inserted_count
    return mapping


def map_after_reorder(new_order: list[int]) -> dict[int, int | None]:
    """new_order[new_index] = old_index → invert to old→new."""
    mapping: dict[int, int | None] = {old: None for old in range(len(new_order))}
    for new_i, old_i in enumerate(new_order):
        mapping[old_i] = new_i
    return mapping


def map_after_move(old_count: int, from_index: int, to_index: int) -> dict[int, int | None]:
    order = list(range(old_count))
    item = order.pop(from_index)
    order.insert(to_index, item)
    return map_after_reorder(order)


def map_after_duplicate_block(old_count: int, insert_at: int, count: int) -> dict[int, int | None]:
    return map_after_insert(old_count, insert_at, count)
