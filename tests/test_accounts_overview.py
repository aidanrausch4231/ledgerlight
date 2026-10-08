"""Stage 8 synthetic read-model, migration and import regressions (offline)."""

import json
import sqlite3
from contextlib import closing

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import data, plaid_client, sync
from ledgerlight.account_names import clean_account_name
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.config import db_path
from ledgerlight.db import connect


def add(id, name, balance, type_, available=None, limit=None, item=None):
    with connect() as db:
        db.execute(
            "INSERT INTO accounts "
            "(id,name,balance,type,available,credit_limit,item_id,mask) "
            "VALUES (?,?,?,?,?,?,?, '1234')",
            (id, name, balance, type_, available, limit, item),
        )


def test_group_sign_rank_bar_empty_notes_and_interface_parity():
    with connect() as db:
        db.execute(
            "INSERT INTO plaid_items (id,institution,access_token_enc) "
            "VALUES ('bank','Synthetic Bank','synthetic-unused')"
        )
    add("invest", "Fund", 6000, "investment", item="bank")
    add("broker", "Brokerage", 1000, "brokerage")
    add("cash-a", "Alpha", 2000, "depository", 1800)
    add("cash-b", "Beta", 2000, "depository", 2000)
    add("other", "Other", 100, "other")
    add("unknown", "Unknown", 50, "new-bank-type")
    add("credit", "Credit", 3000, "credit", limit=5000)
    add("loan", "Loan", 1000, "loan")
    add("empty", "Empty", 0, "investment")
    add("available", "Available only", 0, "depository", 25)
    o = data.accounts_overview()
    assert o["held"] == 11150
    assert o["owed"] == 4000
    assert o["net_worth"] == 7150
    # Type "other" has its own "Other assets" group; it counts toward held only.
    assert o["cash_total"] == 4050 and o["invested_total"] == 7000
    assert o["other_total"] == 100
    assert o["cash_share"] == pytest.approx(4050 / 11150)
    assert o["invested_share"] == pytest.approx(7000 / 11150)
    assert o["owed_ratio"] == pytest.approx(4000 / 11150)
    assert [g["key"] for g in o["groups"]] == ["investments", "cash", "other", "owed"]
    assert [g["label"] for g in o["groups"]] == [
        "Investments",
        "Cash",
        "Other assets",
        "Owed",
    ]
    assert [g["total"] for g in o["groups"]] == [7000, 4050, 100, -4000]
    assert [g["share_note"] for g in o["groups"]] == [
        "63% of held",
        "36% of held",
        "1% of held",
        "",
    ]
    rows = [a for g in o["groups"] for a in g["accounts"]]
    assert [a["rank"] for a in rows] == list(range(1, 10))
    assert [a["id"] for a in rows] == [
        "invest",
        "broker",
        "cash-a",
        "cash-b",
        "unknown",
        "available",
        "other",
        "credit",
        "loan",
    ]
    by_id = {a["id"]: a for a in rows}
    assert by_id["invest"]["bar"] == 1
    assert by_id["credit"]["bar"] == 0.5
    assert by_id["available"]["bar"] == 0
    assert by_id["invest"]["institution"] == "Synthetic Bank"
    assert by_id["cash-a"]["institution"] == "Manual"
    assert by_id["cash-a"]["note"] == "$1,800.00 available"
    assert by_id["cash-b"]["note"] == "all available"
    assert by_id["credit"]["note"] == "$2,000.00 left"
    assert by_id["credit"]["balance"] == -3000
    assert by_id["loan"]["balance"] == -1000
    assert all(by_id[id]["note"] == "" for id in ("loan", "other", "invest", "broker"))
    assert [
        by_id[id]["kind_label"] for id in ("invest", "cash-a", "credit", "loan")
    ] == ["Investment", "Cash", "Credit", "Credit"]
    assert o["empty"] == [
        {"id": "empty", "name": "Empty", "institution": "Manual", "mask": "1234"}
    ]
    result = CliRunner().invoke(cli, ["--json", "accounts", "overview"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == o
    client = TestClient(app)
    assert client.get("/api/accounts/overview").json() == o
    assert client.get("/api/accounts").json() == data.accounts()
    # Legacy account reads retain Plaid's positive current balance.
    assert next(a for a in data.accounts() if a["id"] == "credit")["balance"] == 3000
    with connect() as db:
        db.execute("UPDATE accounts SET credit_limit=5000 WHERE id='loan'")
        db.execute("UPDATE accounts SET balance=9000 WHERE id='cash-a'")
    updated = data.accounts_overview()
    assert [g["key"] for g in updated["groups"]] == [
        "cash",
        "investments",
        "other",
        "owed",
    ]
    assert updated["groups"][-1]["share_note"] == "40% of limit"
    with connect() as db:
        db.execute("UPDATE accounts SET credit_limit=0 WHERE type IN ('credit','loan')")
    assert data.accounts_overview()["groups"][-1]["share_note"] == ""


def test_zero_held_empty_and_capped_ratio():
    o = data.accounts_overview()
    assert o["groups"] == [] and o["empty"] == []
    assert all(
        o[key] == 0
        for key in (
            "net_worth",
            "held",
            "owed",
            "cash_share",
            "invested_share",
            "owed_ratio",
        )
    )
    add("card", "Card", 900, "credit", limit=1000)
    add("empty", "Empty", 0, "depository", 0)
    o = data.accounts_overview()
    assert o["held"] == 0 and o["net_worth"] == -900
    assert o["cash_share"] == o["invested_share"] == o["owed_ratio"] == 0
    assert [g["key"] for g in o["groups"]] == ["owed"]
    assert o["groups"][0]["share_note"] == "90% of limit"
    add("cash", "Cash", 100, None)
    assert data.accounts_overview()["owed_ratio"] == 1


@pytest.mark.parametrize(
    "raw,fallback,expected",
    [
        ("SYNTH2SAVINGS\ufffd\ufffd SAVINGS", "Unused", "Synth2Savings Savings"),
        ("SYNTH2SAVINGS", "Unused", "Synth2Savings"),
        ("  SYNTHETIC   CHECKING  ", "Unused", "Synthetic Checking"),
        ("Mixed Case\x00\x1b\u200b", "Unused", "Mixed Case"),
        ("IRA", "Unused", "IRA"),
        ("Sample IRA", "Unused", "Sample IRA"),
        ("\ufffd\x00 ", "OFFICIAL SAVINGS", "Official Savings"),
        (None, "Checking ••1234", "Checking ••1234"),
    ],
)
def test_clean_account_name(raw, fallback, expected):
    assert clean_account_name(raw, fallback) == expected


def test_stage7_migration_cleans_once_and_preserves_data():
    path = db_path()
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
            CREATE TABLE accounts (id TEXT PRIMARY KEY, name TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 0, item_id TEXT, type TEXT, subtype TEXT,
                mask TEXT, available REAL, currency TEXT);
            INSERT INTO accounts VALUES ('a','SYNTH2SAVINGS�',42,NULL,'depository',
                'savings','1234',12,'USD');
            INSERT INTO accounts VALUES ('b','�',0,NULL,'depository',
                'checking','5678',NULL,'USD');
            CREATE TABLE transactions (id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                date TEXT NOT NULL, name TEXT NOT NULL, merchant TEXT,
                amount REAL NOT NULL, category TEXT NOT NULL);
            INSERT INTO transactions VALUES
                ('t','a','2026-01-01','Preserved',NULL,-2,'Other');
        """)
    with connect() as db:
        rows = list(db.execute("SELECT * FROM accounts ORDER BY id"))
        assert rows[0]["name"] == "Synth2Savings"
        assert rows[1]["name"] == "Checking ••5678"
        assert rows[0]["credit_limit"] is None
        assert rows[0]["balance"] == 42 and rows[0]["available"] == 12
        before = list(db.iterdump())
    for _ in range(2):
        with connect() as db:
            assert db.total_changes == 0
            assert list(db.iterdump()) == before
    # Cleaning is a migration, not a side effect of each subsequent read.
    with connect() as db:
        db.execute("UPDATE accounts SET name='NEW UPPERCASE' WHERE id='a'")
    assert data.accounts()[1]["name"] == "NEW UPPERCASE"


def test_sync_cleans_names_and_upserts_nullable_limit(monkeypatch):
    fake = plaid_client.FakePlaidClient()
    original = fake.accounts

    def accounts(token):
        rows = original(token)
        rows[0]["name"] = "SYNTH2SAVINGS\ufffd SAVINGS"
        rows[1].update(name="\ufffd", official_name="SYNTHETIC CREDIT")
        return rows

    fake.accounts = accounts
    monkeypatch.setattr(plaid_client, "get_client", lambda: fake)
    sync.link("public-synthetic-stage8")
    rows = {a["type"]: a for a in data.accounts()}
    assert rows["depository"]["name"] == "Synth2Savings Savings"
    assert rows["credit"]["name"] == "Synthetic Credit"
    assert rows["credit"]["credit_limit"] == 1000

    def without_limit(token):
        rows = original(token)
        rows[1]["balances"].pop("limit")
        rows[0].update(name="\ufffd", official_name="\ufffd")
        return rows

    fake.accounts = without_limit
    assert sync.sync_all()["ok"]
    rows = {a["type"]: a for a in data.accounts()}
    assert rows["credit"]["credit_limit"] is None
    assert rows["depository"]["name"] == "Checking ••0001"


@pytest.mark.parametrize(
    "status,oldest,short",
    [
        (sync.HISTORY_COMPLETE, "2025-10-03", False),
        (sync.HISTORY_COMPLETE, "2025-10-17", False),
        (sync.HISTORY_COMPLETE, "2025-10-18", True),
        (sync.HISTORY_COMPLETE, "2026-07-02", True),
        (sync.HISTORY_COMPLETE, None, True),
        ("INITIAL_UPDATE_COMPLETE", "2026-07-02", False),
    ],
)
def test_history_short_boundary(status, oldest, short):
    with connect() as db:
        db.execute(
            "INSERT INTO plaid_items (id,institution,access_token_enc,created_at,"
            "history_days,history_status,oldest_txn_date) VALUES "
            "('i','Synthetic Bank','unused','2026-10-03 12:00:00',365,?,?)",
            (status, oldest),
        )
    item = TestClient(app).get("/api/sync/status").json()["items"][0]
    assert item["history_from"] == oldest
    assert item["history_short"] is short
