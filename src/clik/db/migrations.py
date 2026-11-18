"""Schema migrations, tracked with PRAGMA user_version.

MIGRATIONS[i] upgrades a database from version i to i + 1. Never edit a
released entry; append a new one.
"""

import sqlite3

from clik.models import ClikError

MIGRATIONS: list[str] = [
    """
    CREATE TABLE boards (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
        created_at  TEXT NOT NULL
    );
    CREATE TABLE columns (
        id          INTEGER PRIMARY KEY,
        board_id    INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
        name        TEXT NOT NULL COLLATE NOCASE,
        position    INTEGER NOT NULL,
        wip_limit   INTEGER,
        is_done     INTEGER NOT NULL DEFAULT 0,
        UNIQUE (board_id, name)
    );
    CREATE TABLE cards (
        id           INTEGER PRIMARY KEY,
        column_id    INTEGER NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
        title        TEXT NOT NULL,
        description  TEXT NOT NULL DEFAULT '',
        priority     INTEGER NOT NULL DEFAULT 0,
        position     INTEGER NOT NULL,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL,
        completed_at TEXT,
        archived_at  TEXT
    );
    CREATE INDEX cards_by_column ON cards(column_id, position);
    CREATE TABLE tags (
        id     INTEGER PRIMARY KEY,
        name   TEXT NOT NULL UNIQUE COLLATE NOCASE,
        color  TEXT
    );
    CREATE TABLE card_tags (
        card_id  INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
        tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        PRIMARY KEY (card_id, tag_id)
    );
    CREATE TABLE checklist_items (
        id        INTEGER PRIMARY KEY,
        card_id   INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
        text      TEXT NOT NULL,
        done      INTEGER NOT NULL DEFAULT 0,
        position  INTEGER NOT NULL
    );
    CREATE TABLE meta (
        key    TEXT PRIMARY KEY,
        value  TEXT NOT NULL
    );
    """,
]


def migrate(conn: sqlite3.Connection, migrations: list[str] | None = None) -> None:
    migrations = MIGRATIONS if migrations is None else migrations
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > len(migrations):
        raise ClikError(
            f"database is at schema version {version}, but this clik only knows "
            f"version {len(migrations)}; upgrade clik"
        )
    for target in range(version + 1, len(migrations) + 1):
        try:
            conn.executescript(
                f"BEGIN;\n{migrations[target - 1]}\nPRAGMA user_version = {target};\nCOMMIT;"
            )
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
