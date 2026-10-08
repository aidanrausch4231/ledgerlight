"""Offline first-connection races, transaction boundaries and migration retries."""

import multiprocessing
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier
from unittest.mock import Mock

import pytest

from ledgerlight import db
from ledgerlight.config import db_path


def legacy_database():
    """Synthetic stage-7 schema: all additions except stage-8 credit_limit."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(db.SCHEMA)
        for table, columns in db.ADDITIONS.items():
            for column, definition in columns.items():
                if column != "credit_limit":
                    connection.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                    )
        connection.execute(
            "INSERT INTO accounts (id,name,balance,subtype,mask) VALUES (?,?,?,?,?)",
            ("synthetic", "SYNTHETIC\ufffd SAVINGS", 42, "savings", "1234"),
        )


def assert_current(connection):
    assert connection.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30_000
    assert not connection.in_transaction
    for table, columns in db.ADDITIONS.items():
        actual = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        for column in columns:
            assert actual.count(column) == 1


def connect_together(barrier):
    barrier.wait(timeout=30)
    with db.connect() as connection:
        assert_current(connection)


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "stage7"])
def test_sixteen_first_connections(legacy, monkeypatch):
    if legacy:
        legacy_database()
    clean = Mock(wraps=db.clean_account_name)
    migrate = Mock(wraps=db.migrate)
    monkeypatch.setattr(db, "clean_account_name", clean)
    monkeypatch.setattr(db, "migrate", migrate)
    barrier = Barrier(16)
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(connect_together, barrier) for _ in range(16)]
        for future in futures:
            future.result(timeout=40)
    assert migrate.call_count == 1
    assert clean.call_count == int(legacy)
    if legacy:
        with db.connect() as connection:
            row = connection.execute("SELECT name,balance FROM accounts").fetchone()
            assert tuple(row) == ("Synthetic Savings", 42)
            connection.execute("UPDATE accounts SET name='KEEP UPPERCASE'")
        for _ in range(3):
            with db.connect() as connection:
                name = connection.execute("SELECT name FROM accounts").fetchone()[0]
                assert name == "KEEP UPPERCASE"
        assert clean.call_count == 1


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "stage7"])
def test_two_processes_first_connections(legacy):
    if legacy:
        legacy_database()
    # Spawn gives each process an independent interpreter and migration lock.
    # Both inherit only the fixture's temporary environment storage paths.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    processes = [
        context.Process(target=connect_together, args=(barrier,)) for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=45)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
    with db.connect() as connection:
        assert_current(connection)
        if legacy:
            assert connection.execute("SELECT name FROM accounts").fetchone()[0] == (
                "Synthetic Savings"
            )


def test_current_connections_skip_schema_and_migration(monkeypatch):
    with db.connect() as connection:
        assert_current(connection)
    statements = []
    original = sqlite3.connect

    def traced(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(sqlite3, "connect", traced)
    migrate = Mock(side_effect=AssertionError("Migration must not run again"))
    monkeypatch.setattr(db, "migrate", migrate)
    for _ in range(5):
        with db.connect() as connection:
            assert connection.total_changes == 0
    migrate.assert_not_called()
    assert statements == ["PRAGMA foreign_keys = ON", "PRAGMA user_version"] * 5


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "stage7"])
def test_failed_upgrade_rolls_back_schema_data_and_version(legacy, monkeypatch):
    if legacy:
        legacy_database()
    original = db.migrate

    def fail(connection):
        assert connection.in_transaction
        # A separate writer cannot enter while schema/migration is in progress.
        with closing(sqlite3.connect(db_path(), timeout=0)) as competitor:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                competitor.execute("BEGIN IMMEDIATE")
        original(connection)
        raise RuntimeError("Synthetic migration failure")

    monkeypatch.setattr(db, "migrate", fail)
    with pytest.raises(RuntimeError, match="Synthetic migration failure"):
        with db.connect():
            pytest.fail("Failed migration must not yield")
    with closing(sqlite3.connect(db_path())) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        columns = [row[1] for row in connection.execute("PRAGMA table_info(accounts)")]
        assert "credit_limit" not in columns
        if legacy:
            assert connection.execute("SELECT name FROM accounts").fetchone()[0] == (
                "SYNTHETIC\ufffd SAVINGS"
            )
        else:
            assert connection.execute("SELECT name FROM sqlite_master").fetchall() == []
    monkeypatch.setattr(db, "migrate", original)
    with db.connect() as connection:
        assert_current(connection)


def test_replaced_database_at_same_path_is_initialized(tmp_path):
    with db.connect() as connection:
        assert_current(connection)
    # Retain the first synthetic DB rather than deleting it; next open is fresh.
    db_path().rename(tmp_path / "previous.db")
    with db.connect() as connection:
        assert_current(connection)


def test_nested_atomic_connection_and_rollback():
    with pytest.raises(RuntimeError, match="Rollback"):
        with db.atomic() as outer:
            assert outer.in_transaction
            outer.execute("INSERT INTO settings VALUES ('synthetic', 'value')")
            with db.connect() as inner:
                assert inner is outer
                assert inner.execute("SELECT casefold('SYNTHETIC')").fetchone()[0] == (
                    "synthetic"
                )
            raise RuntimeError("Rollback")
    with db.connect() as connection:
        assert connection.execute("SELECT * FROM settings").fetchall() == []
