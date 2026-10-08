"""SQLite connection lifecycle and additive, idempotent schema upgrades."""

import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

from ledgerlight.account_names import account_name_fallback, clean_account_name
from ledgerlight.config import db_path

_transaction = ContextVar("ledgerlight_transaction", default=None)
_migration_lock = Lock()
# First version marker covers all upgrades through stage 8. Earlier DBs use 0.
# Version 2 adds plaid_items.institution_id for duplicate-link checks.
# Version 3 adds manual accounts and price-tracked holdings.
# Version 4 adds loan payment matching (manual_details columns, loan_payments).
# Bump whenever SCHEMA, ADDITIONS or migration data backfills change.
SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY, command JSON NOT NULL, summary TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at TEXT, cancelled_at TEXT
);
CREATE TABLE IF NOT EXISTS chart_versions (
    chart_id INTEGER NOT NULL REFERENCES charts(id) ON DELETE CASCADE,
    version INTEGER NOT NULL, title TEXT NOT NULL, sql TEXT NOT NULL,
    spec_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(chart_id, version)
);
CREATE TABLE IF NOT EXISTS dashboard_default (
    id INTEGER PRIMARY KEY CHECK(id=1), layout JSON NOT NULL,
    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dashboard_cards (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, props JSON NOT NULL,
    x INTEGER NOT NULL, y INTEGER NOT NULL, w INTEGER NOT NULL, h INTEGER NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dashboard_versions (
    version INTEGER PRIMARY KEY, layout JSON NOT NULL,
    actor TEXT NOT NULL CHECK(actor IN ('user','agent','cli')),
    action TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ui_events (
    seq INTEGER PRIMARY KEY, type TEXT NOT NULL, payload JSON NOT NULL,
    actor TEXT NOT NULL CHECK(actor IN ('user','agent','cli')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    merchant TEXT,
    amount REAL NOT NULL,
    category TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS charts (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    sql TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS plaid_link_history (
    token_hash TEXT PRIMARY KEY,
    history_days INTEGER NOT NULL CHECK(history_days BETWEEN 30 AND 730)
);
CREATE TABLE IF NOT EXISTS plaid_items (
    id TEXT PRIMARY KEY,
    institution TEXT NOT NULL,
    access_token_enc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recurring_streams (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    direction TEXT NOT NULL CHECK(direction IN ('in', 'out')),
    description TEXT NOT NULL,
    merchant TEXT,
    frequency TEXT,
    average_amount REAL,
    last_amount REAL,
    last_date TEXT,
    predicted_next_date TEXT,
    is_active INTEGER,
    status TEXT,
    category TEXT
);
CREATE TABLE IF NOT EXISTS merchant_rules (
    id INTEGER PRIMARY KEY,
    match_field TEXT NOT NULL CHECK(match_field IN ('merchant','name')),
    match_type TEXT NOT NULL CHECK(match_type IN ('exact','contains')),
    pattern TEXT NOT NULL, category TEXT NOT NULL, priority INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transaction_tags (
    transaction_id TEXT REFERENCES transactions(id) ON DELETE CASCADE,
    tag TEXT NOT NULL, PRIMARY KEY(transaction_id, tag)
);
CREATE TABLE IF NOT EXISTS transaction_splits (
    id INTEGER PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    category TEXT NOT NULL, amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS budgets (
    category TEXT PRIMARY KEY, monthly_limit REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('bill','low_balance','budget_over')),
    key TEXT NOT NULL UNIQUE, account_id TEXT REFERENCES accounts(id),
    title TEXT NOT NULL, detail TEXT NOT NULL, due_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, dismissed_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, target_amount REAL NOT NULL,
    target_date TEXT, account_ids TEXT NOT NULL,
    created_at TEXT NOT NULL, archived_at TEXT
);
CREATE TABLE IF NOT EXISTS manual_details (
    account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, apr REAL, monthly_payment REAL, payment_day INTEGER,
    auto_paydown INTEGER NOT NULL DEFAULT 0, paydown_applied_through TEXT
);
CREATE TABLE IF NOT EXISTS holdings (
    account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('crypto','stock')), symbol TEXT NOT NULL,
    coin_id TEXT, quantity REAL NOT NULL, price REAL, price_change_24h REAL,
    price_as_of TEXT, price_error TEXT
);
-- One row per transaction applied to a manual loan (payment matching). The
-- unique transaction index means a transaction pays down at most one loan.
-- amount is what was deducted (after the floor at zero), so a Plaid removal
-- restores exactly that amount. source_account_id/txn_* keep the transaction's
-- fingerprint (it survives the transaction row) so a relinked or duplicate Item
-- replaying the same payment under new ids is not deducted again.
CREATE TABLE IF NOT EXISTS loan_payments (
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    transaction_id TEXT NOT NULL, amount REAL NOT NULL, applied_at TEXT NOT NULL,
    source_account_id TEXT, txn_date TEXT, txn_name TEXT, txn_amount REAL,
    PRIMARY KEY(account_id, transaction_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS loan_payments_transaction
    ON loan_payments(transaction_id);
CREATE TABLE IF NOT EXISTS balance_snapshots (
    date TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    current REAL NOT NULL,
    available REAL,
    PRIMARY KEY(date, account_id)
);
"""

ADDITIONS = {
    # Preserve legacy CHECK-constrained actor columns and every historical row.
    # The optional source actor extends attribution without rebuilding tables.
    "dashboard_versions": {"source_actor": "TEXT CHECK(source_actor = 'mcp')"},
    "ui_events": {"source_actor": "TEXT CHECK(source_actor = 'mcp')"},
    "accounts": {
        "item_id": "TEXT REFERENCES plaid_items(id)",
        "type": "TEXT",
        "subtype": "TEXT",
        "mask": "TEXT",
        "available": "REAL",
        "currency": "TEXT",
        "credit_limit": "REAL",
        # Existing rows are Plaid (or demo) accounts; manual rows set it explicitly.
        "source": "TEXT NOT NULL DEFAULT 'plaid'",
    },
    "plaid_items": {
        "cursor": "TEXT",
        "created_at": "TEXT",
        "last_synced_at": "TEXT",
        "last_error": "TEXT",
        "history_status": "TEXT NOT NULL DEFAULT 'NOT_READY'",
        # Existing Items were linked with Plaid's former 90-day default.
        "history_days": "INTEGER NOT NULL DEFAULT 90",
        "oldest_txn_date": "TEXT",
        # Plaid institution_id; NULL for Items linked before duplicate checks
        # until their next sync backfills it.
        "institution_id": "TEXT",
    },
    "transactions": {
        "pending": "INTEGER NOT NULL DEFAULT 0",
        "plaid_category": "TEXT",
        "base_category": "TEXT",
        "note": "TEXT",
        "hidden": "INTEGER NOT NULL DEFAULT 0",
        "split_cleared_at": "TEXT",
    },
    "recurring_streams": {"user_status": "TEXT"},
    "manual_details": {
        # Case-insensitive substring of a linked transaction's name or merchant.
        "payment_match": "TEXT",
        # ISO date; only transactions dated on/after it are applied.
        "payment_match_since": "TEXT",
    },
}


def migrate(connection):
    """Apply legacy column checks/backfills while the caller holds the write lock."""
    clean_legacy_names = "credit_limit" not in {
        row[1] for row in connection.execute("PRAGMA table_info(accounts)")
    }
    for table, columns in ADDITIONS.items():
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )
    if clean_legacy_names:
        for row in connection.execute(
            "SELECT id,name,subtype,mask FROM accounts"
        ).fetchall():
            name = clean_account_name(row[1], account_name_fallback(row[2], row[3]))
            if name != row[1]:
                connection.execute(
                    "UPDATE accounts SET name=? WHERE id=?", (name, row[0])
                )
    # Stage 4: retain the current version of legacy charts during schema upgrade,
    # not as a side effect of the chart history query. Never replace saved history.
    connection.execute(
        "INSERT OR IGNORE INTO chart_versions "
        "(chart_id,version,title,sql,spec_json,created_at) "
        "SELECT id,version,title,sql,spec_json,updated_at FROM charts "
        "WHERE NOT EXISTS (SELECT 1 FROM chart_versions "
        "WHERE chart_id=charts.id AND version=charts.version)"
    )


def _ensure_schema(connection):
    # Read the database itself, not a cached path: replacement/restored databases
    # must also be upgraded. Current connections need no Python or write lock.
    def current():
        return connection.execute("PRAGMA user_version").fetchone()[0] >= SCHEMA_VERSION

    if current():
        return
    with _migration_lock:
        if current():
            return
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            # Another process may have finished while BEGIN waited for its lock.
            if current():
                return
            # executescript() implicitly commits an existing transaction. Execute
            # complete statements individually so schema, backfills and version
            # either all commit or all roll back under the same SQLite write lock.
            statement = ""
            for line in SCHEMA.splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    connection.execute(statement)
                    statement = ""
            if statement.strip():
                raise ValueError("Incomplete schema statement")
            migrate(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


@contextmanager
def connect():
    existing = _transaction.get()
    if existing is not None:
        yield existing
        return
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.create_function(
        "casefold", 1, lambda value: str(value).casefold(), deterministic=True
    )
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        _ensure_schema(connection)
        with connection:
            yield connection
    finally:
        connection.close()


@contextmanager
def atomic():
    """Reuse a single transaction across shared mutation functions."""
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        token = _transaction.set(connection)
        try:
            yield connection
        finally:
            _transaction.reset(token)
