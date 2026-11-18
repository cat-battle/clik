import sqlite3

import pytest

from clik.db.connection import connect
from clik.db.migrations import MIGRATIONS, migrate
from clik.models import ClikError


def version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def test_fresh_database_is_migrated_to_latest(tmp_path):
    conn = connect(tmp_path / "nested" / "clik.db")
    assert version(conn) == len(MIGRATIONS)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"boards", "columns", "cards", "tags", "card_tags", "checklist_items", "meta"} <= tables
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_reopening_keeps_data(tmp_path):
    path = tmp_path / "clik.db"
    conn = connect(path)
    conn.execute("INSERT INTO boards(name, created_at) VALUES ('b', 'now')")
    conn.close()
    assert connect(path).execute("SELECT name FROM boards").fetchone()[0] == "b"


def test_upgrade_applies_only_new_migrations():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    steps = ["CREATE TABLE a (x);", "CREATE TABLE b (x);"]
    migrate(conn, steps[:1])
    conn.execute("INSERT INTO a VALUES (1)")
    migrate(conn, steps)
    assert version(conn) == 2
    assert conn.execute("SELECT x FROM a").fetchone()[0] == 1
    conn.execute("SELECT * FROM b")


def test_failed_migration_rolls_back():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    with pytest.raises(sqlite3.Error):
        migrate(conn, ["CREATE TABLE a (x); CREATE TABLE a (x);"])
    assert not conn.in_transaction
    assert version(conn) == 0
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0


def test_database_newer_than_code_is_refused():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    with pytest.raises(ClikError, match="upgrade clik"):
        migrate(conn)
