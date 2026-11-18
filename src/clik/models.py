"""Plain data types shared by the service and both UIs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum


class ClikError(Exception):
    """Base class for errors the UIs should show to the user."""


class NotFound(ClikError):
    pass


class ValidationError(ClikError):
    pass


class Priority(IntEnum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, value: str | int | Priority) -> Priority:
        """Accept a Priority, 0-4, or a name / unique name prefix ("h", "urg")."""
        if isinstance(value, int):
            try:
                return cls(value)
            except ValueError:
                raise ValidationError(f"priority must be 0-4, got {value}") from None
        text = value.strip().lower()
        if text.isdigit():
            return cls.parse(int(text))
        matches = [p for p in cls if p.label.startswith(text)] if text else []
        if len(matches) != 1:
            names = ", ".join(p.label for p in cls)
            raise ValidationError(f"unknown priority {value!r} (expected one of: {names})")
        return matches[0]


# Names accepted wherever a tag color is set; stored as hex.
COLOR_NAMES = {
    "red": "#f38ba8",
    "orange": "#fab387",
    "yellow": "#f9e2af",
    "green": "#a6e3a1",
    "teal": "#94e2d5",
    "cyan": "#89dceb",
    "blue": "#89b4fa",
    "purple": "#cba6f7",
    "pink": "#f5c2e7",
    "lavender": "#b4befe",
}
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def parse_color(value: str) -> str:
    text = value.strip().lower()
    if text in COLOR_NAMES:
        return COLOR_NAMES[text]
    if _HEX.fullmatch(text):
        return text
    names = ", ".join(COLOR_NAMES)
    raise ValidationError(f"unknown color {value!r} (use #rrggbb or one of: {names})")


@dataclass(frozen=True)
class Board:
    id: int
    name: str
    created_at: str


@dataclass(frozen=True)
class Column:
    id: int
    board_id: int
    name: str
    position: int
    wip_limit: int | None
    is_done: bool


@dataclass(frozen=True)
class Tag:
    id: int
    name: str
    color: str | None


@dataclass(frozen=True)
class ChecklistItem:
    id: int
    text: str
    done: bool


@dataclass(frozen=True)
class Card:
    id: int
    column_id: int
    title: str
    description: str
    priority: Priority
    position: int
    created_at: str
    updated_at: str
    completed_at: str | None
    archived_at: str | None
    tags: tuple[Tag, ...] = ()
    checklist: tuple[ChecklistItem, ...] = ()

    @property
    def archived(self) -> bool:
        return self.archived_at is not None

    @property
    def checks_done(self) -> int:
        return sum(item.done for item in self.checklist)


@dataclass(frozen=True)
class ColumnView:
    column: Column
    cards: tuple[Card, ...]
    # Unfiltered count of active cards, which is what a WIP limit applies to.
    active_count: int

    @property
    def over_wip(self) -> bool:
        limit = self.column.wip_limit
        return limit is not None and self.active_count > limit


@dataclass(frozen=True)
class BoardView:
    board: Board
    columns: tuple[ColumnView, ...]
