"""KanbanService: the only API the CLI and TUI use.

Everything in and out is a plain value from clio.models, and failures the user
can act on are raised as ClioError subclasses. Keeping to that is what lets a
remote implementation with the same methods replace this one later.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from clio.db.connection import connect, transaction
from clio.db.repo import Repo
from clio.models import (
    Board,
    BoardView,
    Card,
    Column,
    ColumnView,
    NotFound,
    Priority,
    Tag,
    ValidationError,
    parse_color,
)

DEFAULT_COLUMNS = ("Backlog", "Todo", "Doing", "Done")
DEFAULT_BOARD = "Main"

T = TypeVar("T", Board, Column)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean(value: str, what: str) -> str:
    value = value.strip()
    if not value:
        raise ValidationError(f"{what} cannot be empty")
    return value


def _match(items: Sequence[T], ref: str | int, kind: str) -> T:
    """Find by id (int), else exact name, else unique name prefix; case-insensitive."""
    if isinstance(ref, int):
        found = [item for item in items if item.id == ref]
    else:
        text = ref.strip().lower()
        found = [item for item in items if item.name.lower() == text]
        if not found and text:
            found = [item for item in items if item.name.lower().startswith(text)]
    if not found:
        raise NotFound(f"no {kind} matching {ref!r}")
    if len(found) > 1:
        names = ", ".join(item.name for item in found)
        raise ValidationError(f"{ref!r} is ambiguous: matches {kind}s {names}")
    return found[0]


def normalize_tag(name: str) -> str:
    name = name.strip().lstrip("#").lower()
    if not name or any(ch.isspace() or ch == "," for ch in name):
        raise ValidationError(f"invalid tag {name!r}: tags are single words")
    return name


class KanbanService:
    def __init__(self, db_path: str | Path) -> None:
        self._conn = connect(db_path)
        self._repo = Repo(self._conn)

    def close(self) -> None:
        self._conn.close()

    def _tx(self):
        return transaction(self._conn)

    # -- boards -------------------------------------------------------------

    def list_boards(self) -> list[Board]:
        return self._repo.boards()

    def current_board(self) -> Board:
        """The last-used board; creates the default board on first run."""
        boards = self._repo.boards()
        if not boards:
            return self.create_board(DEFAULT_BOARD)
        saved = self._repo.get_meta("current_board")
        return next((b for b in boards if str(b.id) == saved), boards[0])

    def get_board(self, ref: str | int | None = None) -> Board:
        if ref is None:
            return self.current_board()
        return _match(self._repo.boards(), ref, "board")

    def create_board(self, name: str, columns: Iterable[str] = DEFAULT_COLUMNS) -> Board:
        name = _clean(name, "board name")
        columns = [_clean(c, "column name") for c in columns]
        with self._tx():
            if any(b.name.lower() == name.lower() for b in self._repo.boards()):
                raise ValidationError(f"a board named {name!r} already exists")
            board_id = self._repo.insert_board(name, _now())
            for pos, col in enumerate(columns):
                # The last default column is where finished work goes.
                self._repo.insert_column(board_id, col, pos, is_done=pos == len(columns) - 1)
        return self.get_board(board_id)

    def use_board(self, ref: str | int) -> Board:
        board = self.get_board(ref)
        with self._tx():
            self._repo.set_meta("current_board", str(board.id))
        return board

    def rename_board(self, ref: str | int, new_name: str) -> Board:
        new_name = _clean(new_name, "board name")
        with self._tx():
            board = self.get_board(ref)
            for other in self._repo.boards():
                if other.id != board.id and other.name.lower() == new_name.lower():
                    raise ValidationError(f"a board named {new_name!r} already exists")
            self._repo.update_board(board.id, name=new_name)
        return self.get_board(board.id)

    def delete_board(self, ref: str | int) -> Board:
        """Delete a board and everything on it."""
        with self._tx():
            board = self.get_board(ref)
            self._repo.delete_board(board.id)
        return board

    def board_view(
        self,
        board: str | int | None = None,
        *,
        include_archived: bool = False,
        tags: Iterable[str] = (),
        priority: Priority | None = None,
        text: str | None = None,
    ) -> BoardView:
        """A board with its columns and cards. Filters combine; a card must carry every tag."""
        b = self.get_board(board)
        wanted = {normalize_tag(t) for t in tags}
        needle = text.strip().lower() if text else ""

        def keep(card: Card) -> bool:
            if not wanted <= {t.name for t in card.tags}:
                return False
            if priority is not None and card.priority != priority:
                return False
            if needle and needle not in f"{card.title}\n{card.description}".lower():
                return False
            return True

        cards = self._repo.cards(board_id=b.id, include_archived=include_archived)
        views = []
        for col in self._repo.columns(b.id):
            mine = [c for c in cards if c.column_id == col.id]
            views.append(
                ColumnView(
                    column=col,
                    cards=tuple(c for c in mine if keep(c)),
                    active_count=sum(not c.archived for c in mine),
                )
            )
        return BoardView(b, tuple(views))

    # -- columns ------------------------------------------------------------

    def list_columns(self, board: str | int | None = None) -> list[Column]:
        return self._repo.columns(self.get_board(board).id)

    def get_column(self, ref: str | int, board: str | int | None = None) -> Column:
        return _match(self.list_columns(board), ref, "column")

    def add_column(
        self, name: str, *, board: str | int | None = None, after: str | int | None = None
    ) -> Column:
        """Add a column at the right-hand end, or directly after `after`."""
        name = _clean(name, "column name")
        with self._tx():
            b = self.get_board(board)
            cols = self._repo.columns(b.id)
            self._check_column_name(cols, name)
            index = len(cols) if after is None else cols.index(_match(cols, after, "column")) + 1
            new_id = self._repo.insert_column(b.id, name, len(cols))
            ids = [c.id for c in cols]
            ids.insert(index, new_id)
            self._repo.set_column_order(ids)
        return self._repo.column(new_id)

    def rename_column(
        self, ref: str | int, new_name: str, *, board: str | int | None = None
    ) -> Column:
        new_name = _clean(new_name, "column name")
        with self._tx():
            cols = self.list_columns(board)
            col = _match(cols, ref, "column")
            self._check_column_name([c for c in cols if c.id != col.id], new_name)
            self._repo.update_column(col.id, name=new_name)
        return self._repo.column(col.id)

    def move_column(self, ref: str | int, index: int, *, board: str | int | None = None) -> Column:
        """Move a column to 0-based `index` (clamped) among its board's columns."""
        with self._tx():
            cols = self.list_columns(board)
            col = _match(cols, ref, "column")
            ids = [c.id for c in cols if c.id != col.id]
            ids.insert(max(0, min(index, len(ids))), col.id)
            self._repo.set_column_order(ids)
        return self._repo.column(col.id)

    def set_wip_limit(
        self, ref: str | int, limit: int | None, *, board: str | int | None = None
    ) -> Column:
        """Set an advisory WIP limit; None or 0 clears it."""
        if limit is not None and limit < 0:
            raise ValidationError("WIP limit cannot be negative")
        with self._tx():
            col = self.get_column(ref, board)
            self._repo.update_column(col.id, wip_limit=limit or None)
        return self._repo.column(col.id)

    def set_done_column(self, ref: str | int, *, board: str | int | None = None) -> Column:
        """Make this the board's one 'done' column."""
        with self._tx():
            col = self.get_column(ref, board)
            self._repo.clear_done_flag(col.board_id)
            self._repo.update_column(col.id, is_done=1)
        return self._repo.column(col.id)

    def delete_column(
        self,
        ref: str | int,
        *,
        board: str | int | None = None,
        move_to: str | int | None = None,
    ) -> Column:
        """Delete a column. If it holds cards (archived included) they must go to `move_to`."""
        with self._tx():
            cols = self.list_columns(board)
            col = _match(cols, ref, "column")
            if len(cols) == 1:
                raise ValidationError("a board needs at least one column")
            count = self._repo.count_cards(col.id)
            if count and move_to is None:
                raise ValidationError(
                    f"column {col.name!r} holds {count} card(s); say where to move them"
                )
            if count:
                target = _match(cols, move_to, "column")
                if target.id == col.id:
                    raise ValidationError("cannot move cards into the column being deleted")
                moving = self._repo.active_card_ids(col.id)
                self._repo.set_card_order(target.id, self._repo.active_card_ids(target.id) + moving)
                self._repo.move_archived_cards(col.id, target.id)
                for card_id in moving:
                    self._sync_completion(card_id, target)
            self._repo.delete_column(col.id)
            self._repo.set_column_order([c.id for c in cols if c.id != col.id])
        return col

    @staticmethod
    def _check_column_name(existing: Sequence[Column], name: str) -> None:
        if any(c.name.lower() == name.lower() for c in existing):
            raise ValidationError(f"this board already has a column named {name!r}")

    # -- cards --------------------------------------------------------------

    def get_card(self, card_id: int) -> Card:
        found = self._repo.cards(card_id=card_id, include_archived=True)
        if not found:
            raise NotFound(f"no card #{card_id}")
        return found[0]

    def column_of(self, card: Card) -> Column:
        return self._repo.column(card.column_id)

    def add_card(
        self,
        title: str,
        *,
        board: str | int | None = None,
        column: str | int | None = None,
        description: str = "",
        priority: Priority = Priority.NONE,
        tags: Iterable[str] = (),
        top: bool = False,
    ) -> Card:
        """Add a card to `column` (default: the board's first column)."""
        title = _clean(title, "card title")
        with self._tx():
            cols = self.list_columns(board)
            col = cols[0] if column is None else _match(cols, column, "column")
            siblings = self._repo.active_card_ids(col.id)
            now = _now()
            card_id = self._repo.insert_card(
                col.id,
                title,
                description.strip(),
                int(priority),
                len(siblings),
                now,
                completed_at=now if col.is_done else None,
            )
            if top:
                self._repo.set_card_order(col.id, [card_id, *siblings])
            self._replace_tags(card_id, tags)
        return self.get_card(card_id)

    def update_card(
        self,
        card_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: Priority | None = None,
        tags: Iterable[str] | None = None,
    ) -> Card:
        """Change the given fields; None leaves a field alone. `tags` replaces the set."""
        fields: dict = {}
        if title is not None:
            fields["title"] = _clean(title, "card title")
        if description is not None:
            fields["description"] = description.strip()
        if priority is not None:
            fields["priority"] = int(priority)
        with self._tx():
            self.get_card(card_id)
            self._repo.update_card(card_id, **fields, updated_at=_now())
            if tags is not None:
                self._replace_tags(card_id, tags)
        return self.get_card(card_id)

    def move_card(self, card_id: int, column: str | int, index: int | None = None) -> Card:
        """Move a card to a column on its own board, at 0-based `index` (None: bottom)."""
        with self._tx():
            card = self._active_card(card_id)
            cols = self._repo.columns(self.column_of(card).board_id)
            target = _match(cols, column, "column")
            dest = [i for i in self._repo.active_card_ids(target.id) if i != card_id]
            dest.insert(len(dest) if index is None else max(0, min(index, len(dest))), card_id)
            self._repo.set_card_order(target.id, dest)
            if target.id != card.column_id:
                # Close the gap the card left behind.
                self._repo.set_card_order(
                    card.column_id, self._repo.active_card_ids(card.column_id)
                )
            self._sync_completion(card_id, target)
            self._repo.update_card(card_id, updated_at=_now())
        return self.get_card(card_id)

    def complete_card(self, card_id: int) -> Card:
        """Move a card to the bottom of its board's done column."""
        card = self.get_card(card_id)
        cols = self._repo.columns(self.column_of(card).board_id)
        done = next((c for c in cols if c.is_done), None)
        if done is None:
            raise ValidationError("this board has no done column; set one with `column done`")
        return self.move_card(card_id, done.id)

    def archive_card(self, card_id: int) -> Card:
        """Hide a card from the board without deleting it."""
        with self._tx():
            card = self._active_card(card_id)
            self._repo.update_card(card_id, archived_at=_now())
            self._repo.set_card_order(card.column_id, self._repo.active_card_ids(card.column_id))
        return self.get_card(card_id)

    def unarchive_card(self, card_id: int) -> Card:
        """Bring an archived card back, at the bottom of its column."""
        with self._tx():
            card = self.get_card(card_id)
            if not card.archived:
                raise ValidationError(f"card #{card_id} is not archived")
            siblings = self._repo.active_card_ids(card.column_id)
            self._repo.update_card(card_id, archived_at=None)
            self._repo.set_card_order(card.column_id, [*siblings, card_id])
        return self.get_card(card_id)

    def delete_card(self, card_id: int) -> Card:
        with self._tx():
            card = self.get_card(card_id)
            self._repo.delete_card(card_id)
            self._repo.set_card_order(card.column_id, self._repo.active_card_ids(card.column_id))
        return card

    def _active_card(self, card_id: int) -> Card:
        card = self.get_card(card_id)
        if card.archived:
            raise ValidationError(f"card #{card_id} is archived; unarchive it first")
        return card

    def _sync_completion(self, card_id: int, column: Column) -> None:
        """completed_at is set while a card sits in a done column, and only then."""
        card = self.get_card(card_id)
        if column.is_done and card.completed_at is None:
            self._repo.update_card(card_id, completed_at=_now())
        elif not column.is_done and card.completed_at is not None:
            self._repo.update_card(card_id, completed_at=None)

    # -- tags ---------------------------------------------------------------

    def list_tags(self) -> list[tuple[Tag, int]]:
        """Every tag with the number of cards carrying it."""
        return self._repo.tags_with_counts()

    def add_tags(self, card_id: int, names: Iterable[str]) -> Card:
        with self._tx():
            current = [t.name for t in self.get_card(card_id).tags]
            self._replace_tags(card_id, [*current, *names])
            self._repo.update_card(card_id, updated_at=_now())
        return self.get_card(card_id)

    def remove_tags(self, card_id: int, names: Iterable[str]) -> Card:
        drop = {normalize_tag(n) for n in names}
        with self._tx():
            current = [t.name for t in self.get_card(card_id).tags]
            self._replace_tags(card_id, [n for n in current if n not in drop])
            self._repo.update_card(card_id, updated_at=_now())
        return self.get_card(card_id)

    def set_tag_color(self, name: str, color: str | None) -> Tag:
        """Pin a tag's color (#rrggbb or a known name); None goes back to automatic."""
        value = parse_color(color) if color else None
        with self._tx():
            tag = self._tag(name)
            self._repo.update_tag(tag.id, color=value)
        return self._tag(name)

    def delete_tag(self, name: str) -> Tag:
        """Delete a tag, removing it from every card."""
        with self._tx():
            tag = self._tag(name)
            self._repo.delete_tag(tag.id)
        return tag

    def _tag(self, name: str) -> Tag:
        tag = self._repo.tag_by_name(normalize_tag(name))
        if tag is None:
            raise NotFound(f"no tag {name!r}")
        return tag

    def _replace_tags(self, card_id: int, names: Iterable[str]) -> None:
        unique = list(dict.fromkeys(normalize_tag(n) for n in names))
        self._repo.set_card_tags(card_id, [self._repo.ensure_tag(n) for n in unique])

    # -- checklists ---------------------------------------------------------

    def set_checklist(self, card_id: int, items: Iterable[tuple[str, bool]]) -> Card:
        """Replace a card's checklist with (text, done) pairs, in order."""
        cleaned = [(_clean(text, "checklist item"), bool(done)) for text, done in items]
        with self._tx():
            self.get_card(card_id)
            self._repo.set_checklist(card_id, cleaned)
            self._repo.update_card(card_id, updated_at=_now())
        return self.get_card(card_id)

    def add_check(self, card_id: int, text: str) -> Card:
        with self._tx():
            return self.set_checklist(card_id, [*self._checks(card_id), (text, False)])

    def toggle_check(self, card_id: int, number: int) -> Card:
        """Flip checklist item `number` (1-based, as shown by `show`)."""
        with self._tx():
            items = self._checks(card_id)
            text, done = self._nth(items, number, card_id)
            items[number - 1] = (text, not done)
            return self.set_checklist(card_id, items)

    def remove_check(self, card_id: int, number: int) -> Card:
        with self._tx():
            items = self._checks(card_id)
            self._nth(items, number, card_id)
            del items[number - 1]
            return self.set_checklist(card_id, items)

    def _checks(self, card_id: int) -> list[tuple[str, bool]]:
        return [(item.text, item.done) for item in self.get_card(card_id).checklist]

    @staticmethod
    def _nth(items: list, number: int, card_id: int):
        if not 1 <= number <= len(items):
            raise NotFound(f"card #{card_id} has no checklist item {number}")
        return items[number - 1]
