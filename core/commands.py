"""Command/action architecture foundation for Undo/Redo-capable operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import Deque


class Command(ABC):
    """Base for document-changing operations. Open/view-only ops need not push."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def can_undo(self) -> bool:
        return True

    @abstractmethod
    def execute(self) -> None:
        raise NotImplementedError

    def undo(self) -> None:
        raise NotImplementedError(f"{self.name} does not support undo yet")


@dataclass
class CommandResult:
    ok: bool
    message: str = ""


class CommandStack:
    """Deterministic undo/redo stacks. Ready for later editing commands."""

    def __init__(self, limit: int = 100) -> None:
        self._undo: Deque[Command] = deque(maxlen=limit)
        self._redo: Deque[Command] = deque(maxlen=limit)

    def push_executed(self, command: Command) -> None:
        if command.can_undo:
            self._undo.append(command)
            self._redo.clear()

    def execute(self, command: Command) -> None:
        command.execute()
        self.push_executed(command)

    def undo(self) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.execute()
        self._undo.append(cmd)
        return True

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def top(self) -> Command | None:
        """The command Undo would revert next (None when there is none)."""
        return self._undo[-1] if self._undo else None

    @property
    def can_undo_now(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo_now(self) -> bool:
        return bool(self._redo)
