"""All SQL lives here. No business rules: the service decides, the repo stores."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from clik.models import Board, Card, ChecklistItem, Column, Priority, Tag


class Repo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _update(self, table: str, row_id: int, fields: dict[str, Any]) -> None:
        # `table` and the keys of `fields` only ever come from service code.
        if not fields:
            return
        sets = ", ".join(f"{name} = ?" for name in fields)
        self.conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*fields.values(), row_id))

    # -- meta ---------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # -- boards -------------------------------------------------------------

    def boards(self) -> list[Board]:
        rows = self.conn.execute("SELECT * FROM boards ORDER BY id")
        return [Board(r["id"], r["name"], r["created_at"]) for r in rows]

    def insert_board(self, name: str, now: str) -> int:
        cur = self.conn.execute("INSERT INTO boards(name, created_at) VALUES (?, ?)", (name, now))
        return cur.lastrowid

    def update_board(self, board_id: int, **fields: Any) -> None:
        self._update("boards", board_id, fields)

    def delete_board(self, board_id: int) -> None:
        self.conn.execute("DELETE FROM boards WHERE id = ?", (board_id,))

    # -- columns ------------------------------------------------------------

    @staticmethod
    def _column(r: sqlite3.Row) -> Column:
        return Column(
            r["id"], r["board_id"], r["name"], r["position"], r["wip_limit"], bool(r["is_done"])
        )

    def columns(self, board_id: int) -> list[Column]:
        rows = self.conn.execute(
            "SELECT * FROM columns WHERE board_id = ? ORDER BY position, id", (board_id,)
        )
        return [self._column(r) for r in rows]

    def column(self, column_id: int) -> Column | None:
        row = self.conn.execute("SELECT * FROM columns WHERE id = ?", (column_id,)).fetchone()
        return self._column(row) if row else None

    def insert_column(self, board_id: int, name: str, position: int, is_done: bool = False) -> int:
        cur = self.conn.execute(
            "INSERT INTO columns(board_id, name, position, is_done) VALUES (?, ?, ?, ?)",
            (board_id, name, position, int(is_done)),
        )
        return cur.lastrowid

    def update_column(self, column_id: int, **fields: Any) -> None:
        self._update("columns", column_id, fields)

    def delete_column(self, column_id: int) -> None:
        self.conn.execute("DELETE FROM columns WHERE id = ?", (column_id,))

    def set_column_order(self, column_ids: list[int]) -> None:
        self.conn.executemany(
            "UPDATE columns SET position = ? WHERE id = ?",
            [(pos, cid) for pos, cid in enumerate(column_ids)],
        )

    def clear_done_flag(self, board_id: int) -> None:
        self.conn.execute("UPDATE columns SET is_done = 0 WHERE board_id = ?", (board_id,))

    # -- cards --------------------------------------------------------------

    def cards(
        self,
        *,
        board_id: int | None = None,
        card_id: int | None = None,
        include_archived: bool = False,
    ) -> list[Card]:
        """Cards with tags and checklist attached, in board order."""
        where, params = [], []
        if board_id is not None:
            where.append("col.board_id = ?")
            params.append(board_id)
        if card_id is not None:
            where.append("c.id = ?")
            params.append(card_id)
        if not include_archived:
            where.append("c.archived_at IS NULL")
        rows = self.conn.execute(
            "SELECT c.* FROM cards c JOIN columns col ON col.id = c.column_id "
            f"WHERE {' AND '.join(where) or '1'} "
            "ORDER BY col.position, c.archived_at IS NOT NULL, c.position, c.id",
            params,
        ).fetchall()
        ids = [r["id"] for r in rows]
        marks = ",".join("?" * len(ids))

        tags: dict[int, list[Tag]] = defaultdict(list)
        for r in self.conn.execute(
            "SELECT ct.card_id, t.* FROM card_tags ct JOIN tags t ON t.id = ct.tag_id "
            f"WHERE ct.card_id IN ({marks}) ORDER BY t.name",
            ids,
        ):
            tags[r["card_id"]].append(Tag(r["id"], r["name"], r["color"]))

        checks: dict[int, list[ChecklistItem]] = defaultdict(list)
        for r in self.conn.execute(
            f"SELECT * FROM checklist_items WHERE card_id IN ({marks}) ORDER BY position, id",
            ids,
        ):
            checks[r["card_id"]].append(ChecklistItem(r["id"], r["text"], bool(r["done"])))

        return [
            Card(
                id=r["id"],
                column_id=r["column_id"],
                title=r["title"],
                description=r["description"],
                priority=Priority(r["priority"]),
                position=r["position"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                completed_at=r["completed_at"],
                archived_at=r["archived_at"],
                tags=tuple(tags[r["id"]]),
                checklist=tuple(checks[r["id"]]),
            )
            for r in rows
        ]

    def active_card_ids(self, column_id: int) -> list[int]:
        rows = self.conn.execute(
            "SELECT id FROM cards WHERE column_id = ? AND archived_at IS NULL "
            "ORDER BY position, id",
            (column_id,),
        )
        return [r["id"] for r in rows]

    def count_cards(self, column_id: int) -> int:
        """Every card in the column, archived ones included."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM cards WHERE column_id = ?", (column_id,)
        ).fetchone()
        return row[0]

    def insert_card(
        self,
        column_id: int,
        title: str,
        description: str,
        priority: int,
        position: int,
        now: str,
        completed_at: str | None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO cards(column_id, title, description, priority, position, "
            "created_at, updated_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (column_id, title, description, priority, position, now, now, completed_at),
        )
        return cur.lastrowid

    def update_card(self, card_id: int, **fields: Any) -> None:
        self._update("cards", card_id, fields)

    def delete_card(self, card_id: int) -> None:
        self.conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    def set_card_order(self, column_id: int, card_ids: list[int]) -> None:
        """Put exactly these cards in this column, in this order."""
        self.conn.executemany(
            "UPDATE cards SET column_id = ?, position = ? WHERE id = ?",
            [(column_id, pos, cid) for pos, cid in enumerate(card_ids)],
        )

    def move_archived_cards(self, from_column_id: int, to_column_id: int) -> None:
        self.conn.execute(
            "UPDATE cards SET column_id = ? WHERE column_id = ? AND archived_at IS NOT NULL",
            (to_column_id, from_column_id),
        )

    # -- tags ---------------------------------------------------------------

    def tags_with_counts(self) -> list[tuple[Tag, int]]:
        rows = self.conn.execute(
            "SELECT t.*, COUNT(ct.card_id) AS n FROM tags t "
            "LEFT JOIN card_tags ct ON ct.tag_id = t.id GROUP BY t.id ORDER BY t.name"
        )
        return [(Tag(r["id"], r["name"], r["color"]), r["n"]) for r in rows]

    def tag_by_name(self, name: str) -> Tag | None:
        row = self.conn.execute("SELECT * FROM tags WHERE name = ?", (name,)).fetchone()
        return Tag(row["id"], row["name"], row["color"]) if row else None

    def ensure_tag(self, name: str) -> int:
        tag = self.tag_by_name(name)
        if tag:
            return tag.id
        return self.conn.execute("INSERT INTO tags(name) VALUES (?)", (name,)).lastrowid

    def update_tag(self, tag_id: int, **fields: Any) -> None:
        self._update("tags", tag_id, fields)

    def delete_tag(self, tag_id: int) -> None:
        self.conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

    def set_card_tags(self, card_id: int, tag_ids: list[int]) -> None:
        self.conn.execute("DELETE FROM card_tags WHERE card_id = ?", (card_id,))
        self.conn.executemany(
            "INSERT INTO card_tags(card_id, tag_id) VALUES (?, ?)",
            [(card_id, tag_id) for tag_id in tag_ids],
        )

    # -- checklists ---------------------------------------------------------

    def set_checklist(self, card_id: int, items: list[tuple[str, bool]]) -> None:
        self.conn.execute("DELETE FROM checklist_items WHERE card_id = ?", (card_id,))
        self.conn.executemany(
            "INSERT INTO checklist_items(card_id, text, done, position) VALUES (?, ?, ?, ?)",
            [(card_id, text, int(done), pos) for pos, (text, done) in enumerate(items)],
        )
