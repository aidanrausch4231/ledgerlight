import json
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import data, plaid_client, sync, systemd
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.config import db_path
from ledgerlight.crypto import decrypt
from ledgerlight.db import connect
from ledgerlight.demo import seed
from ledgerlight.plaid_client import FakePlaidClient, PlaidClient, PlaidError


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    return FakePlaidClient()


def invoke(*args, success=True):
    result = CliRunner().invoke(cli, ["--json", *args])
    assert (result.exit_code == 0) == success, result.output
    return json.loads(result.output)


def test_old_schema_migration():
    path = db_path()
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE accounts(id TEXT PRIMARY KEY, name TEXT NOT NULL,
                                  balance REAL NOT NULL DEFAULT 0);
            CREATE TABLE transactions(id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                date TEXT NOT NULL, name TEXT NOT NULL, merchant TEXT,
                amount REAL NOT NULL, category TEXT NOT NULL);
            CREATE TABLE plaid_items(id TEXT PRIMARY KEY, institution TEXT NOT NULL,
                                     access_token_enc TEXT NOT NULL);
            INSERT INTO plaid_items VALUES ('old-item', 'Synthetic legacy bank',
                                             'synthetic-ciphertext');
            INSERT INTO accounts VALUES ('old', 'Preserved', 12.5);
            INSERT INTO transactions VALUES
                ('old-tx', 'old', '2026-01-01', 'Preserved', NULL, -2, 'Other');
        """)
    for _ in range(2):
        with connect() as db:
            row = dict(db.execute("SELECT * FROM accounts").fetchone())
            assert row["balance"] == 12.5 and row["item_id"] is None
            assert row["available"] is None
            row = dict(db.execute("SELECT * FROM transactions").fetchone())
            assert row["amount"] == -2 and row["pending"] == 0
            assert row["plaid_category"] is None
            item = dict(db.execute("SELECT * FROM plaid_items").fetchone())
            assert item["access_token_enc"] == "synthetic-ciphertext"
            assert item["history_days"] == 90
            assert item["history_status"] == "NOT_READY"
            assert item["oldest_txn_date"] is None
            assert {r[1] for r in db.execute("PRAGMA table_info(plaid_items)")} >= {
                "cursor",
                "created_at",
                "last_synced_at",
                "last_error",
                "history_status",
                "history_days",
                "oldest_txn_date",
            }


def test_fake_link_encrypted_and_repeatable(fake):
    assert isinstance(plaid_client.get_client(), FakePlaidClient)
    public = fake.sandbox_public_token()
    item_id, access = fake.exchange_public_token(public)
    assert sync.link(public) == sync.link(public)
    with connect() as db:
        row = dict(db.execute("SELECT * FROM plaid_items").fetchone())
        assert row["id"] == item_id and row["created_at"]
        assert decrypt(row["access_token_enc"]) == access
        assert access not in str(list(db.iterdump()))
        assert public not in str(list(db.iterdump()))
    assert "access_token" not in json.dumps(sync.items())
    assert len(sync.items()) == 1
    assert sync.sync_all()["ok"]
    assert sync.sync_all()["ok"]
    assert len(data.transactions(limit=1000)) == 365
    assert len(data.accounts()) == 2
    assert len(data.recurring()) == 2
    assert data.networth() == [{"date": str(date.today()), "total": 2400.0}]


def test_sync_deltas_replace_snapshots_and_rollback(fake, monkeypatch):
    item = sync.sandbox_link()
    assert sync.sync_all()["ok"]
    client = FakePlaidClient()
    calls = []

    def changes(token, cursor):
        calls.append(cursor)
        rows = client.transactions_sync(token, None)["added"]
        rows[0]["amount"] = 99
        rows[0]["pending"] = False
        new = {**rows[1], "transaction_id": "synthetic-new"}
        return {
            "added": [new],
            "modified": [rows[0]],
            "removed": [{"transaction_id": rows[2]["transaction_id"]}],
            "next_cursor": "second",
        }

    replacement = FakePlaidClient()
    replacement.transactions_sync = changes
    replacement.recurring = lambda token: {"inflow_streams": [], "outflow_streams": []}
    monkeypatch.setattr(plaid_client, "get_client", lambda: replacement)
    assert sync.sync_all()["ok"]
    assert calls == ["synthetic-cursor-2"]
    assert len(data.transactions(limit=1000)) == 365
    coffee = data.transactions(search="coffee")[0]
    assert coffee["amount"] == -99 and coffee["pending"] is False
    assert data.transactions(search="streaming") == []
    assert data.recurring() == []
    sync.snapshot()
    sync.snapshot()
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM balance_snapshots").fetchone()[0] == 2
        assert db.execute("SELECT cursor FROM plaid_items").fetchone()[0] == "second"
        db.execute("UPDATE accounts SET balance=42 WHERE type='depository'")
    sync.snapshot()
    assert data.networth()[0]["total"] == -58

    # Fail after account/transaction writes: the entire item, including cursor,
    # recurring replacement and snapshots, must roll back.
    replacement.recurring = lambda token: {"inflow_streams": [{"account_id": "bad"}]}
    assert not sync.sync_all()["ok"]
    with connect() as db:
        assert db.execute("SELECT cursor FROM plaid_items").fetchone()[0] == "second"
    assert data.accounts()[0]["balance"] == 42
    failed = sync.items()[0]
    assert failed["last_error"] and failed["last_synced_at"]
    replacement.recurring = client.recurring
    assert sync.sync_all()["ok"]
    assert sync.items()[0]["last_error"] is None
    assert sync.items()[0]["id"] == item["id"]


def test_failing_item_does_not_stop_other_items(fake, monkeypatch):
    first = sync.link("synthetic-first")
    second = sync.link("synthetic-second")
    with connect() as db:
        db.execute(
            "UPDATE plaid_items SET access_token_enc='invalid' WHERE id=?",
            (first["id"],),
        )
    result = sync.sync_all()
    assert not result["ok"]
    assert {r["id"]: r["ok"] for r in result["items"]} == {
        first["id"]: False,
        second["id"]: True,
    }
    # Initial exchange already imported 30 rows and streams for the failed Item.
    assert len(data.transactions(limit=1000)) == 395
    assert len(data.recurring()) == 4
    assert invoke("sync", success=False)["error"]
    with TestClient(app) as client:
        response = client.post("/api/sync")
        assert response.status_code == 502 and response.json()["error"]


def test_recurring_replacement_is_per_item(fake, monkeypatch):
    first = sync.link("synthetic-first")
    sync.link("synthetic-second")
    sync.sync_all()
    replacement = FakePlaidClient()
    original = replacement.recurring
    first_token = replacement.exchange_public_token("synthetic-first")[1]
    replacement.recurring = lambda token: (
        {} if token == first_token else original(token)
    )
    monkeypatch.setattr(plaid_client, "get_client", lambda: replacement)
    sync.sync_all()
    assert len(data.recurring()) == 2
    with connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM recurring_streams r JOIN accounts a "
                "ON r.account_id=a.id WHERE a.item_id=?",
                (first["id"],),
            ).fetchone()[0]
            == 0
        )


def test_sdk_pagination_and_safe_errors(monkeypatch):
    # No SDK network calls: exercise pagination, request models and sanitization.
    client = object.__new__(PlaidClient)
    seen = []

    def page(method, **kwargs):
        seen.append(kwargs)
        more = len(seen) == 1
        return {
            "added": [1] if more else [2],
            "modified": [3] if more else [],
            "removed": [] if more else [4],
            "has_more": more,
            "next_cursor": "page-1" if more else "page-2",
            "transactions_update_status": (
                "INITIAL_UPDATE_COMPLETE" if more else "HISTORICAL_UPDATE_COMPLETE"
            ),
        }

    monkeypatch.setattr(client, "_call", page)
    assert client.transactions_sync("synthetic-access", "start") == {
        "added": [1, 2],
        "modified": [3],
        "removed": [4],
        "next_cursor": "page-2",
        "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE",
    }
    assert [x["cursor"] for x in seen] == ["start", "page-1"]
    monkeypatch.setenv("PLAID_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("PLAID_SECRET", "synthetic-secret")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    real = PlaidClient()

    def fail(*args, **kwargs):
        raise RuntimeError("must-not-leak-synthetic-access")

    monkeypatch.setattr(real.api, "item_public_token_exchange", fail)
    with pytest.raises(PlaidError) as error:
        real.exchange_public_token("synthetic-public")
    assert "must-not-leak" not in str(error.value)
    assert "item_public_token_exchange failed" in str(error.value)


@pytest.mark.parametrize("days", [365, 540])
def test_real_client_request_contracts_without_network(monkeypatch, days):
    if days != 365:
        monkeypatch.setenv("LEDGERLIGHT_HISTORY_DAYS", str(days))
    monkeypatch.setenv("PLAID_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("PLAID_SECRET", "synthetic-secret")
    client = PlaidClient()
    seen = {}
    responses = {
        "link_token_create": {"link_token": "synthetic-link"},
        "item_public_token_exchange": {
            "item_id": "synthetic-item", "access_token": "synthetic-access",
        },
        "item_get": {"item": {"institution_id": "ins_109508"}},
        "institutions_get_by_id": {"institution": {"name": "Synthetic Bank"}},
        "accounts_get": {"accounts": []},
        "transactions_sync": {
            "added": [], "modified": [], "removed": [],
            "next_cursor": "next", "has_more": False,
        },
        "transactions_recurring_get": {"inflow_streams": [], "outflow_streams": []},
        "sandbox_public_token_create": {"public_token": "synthetic-public"},
    }

    class Response:
        def __init__(self, value):
            self.value = value

        def to_dict(self):
            return self.value

    def endpoint(method):
        def call(request, **kwargs):
            seen[method] = request.to_dict()
            assert kwargs["_request_timeout"] == 60
            return Response(responses[method])
        return call

    for method in responses:
        monkeypatch.setattr(client.api, method, endpoint(method))
    assert client.create_link_token() == {"link_token": "synthetic-link"}
    assert client.exchange_public_token("synthetic-public") == (
        "synthetic-item", "synthetic-access",
    )
    assert client.institution_name("synthetic-access") == "Synthetic Bank"
    assert client.accounts("synthetic-access") == []
    assert client.transactions_sync("synthetic-access", None)["next_cursor"] == "next"
    assert client.recurring("synthetic-access")["inflow_streams"] == []
    assert client.sandbox_public_token() == "synthetic-public"
    assert "cursor" not in seen["transactions_sync"]
    assert seen["sandbox_public_token_create"] == {
        "institution_id": "ins_109508", "initial_products": ["transactions"],
        "options": {"transactions": {"days_requested": days}},
    }
    assert seen["link_token_create"]["transactions"] == {"days_requested": days}
    assert seen["link_token_create"]["products"] == ["transactions"]
    monkeypatch.setenv("PLAID_ENV", "production")
    with pytest.raises(PlaidError, match="sandbox"):
        client.sandbox_public_token()


def test_cli_all_commands_and_filters(fake):
    assert invoke("plaid", "link-token")["link_token"]
    assert invoke("plaid", "exchange", "synthetic-cli")["institution"]
    assert invoke("plaid", "sandbox-link")["id"]
    assert len(invoke("plaid", "items")) == 2
    assert invoke("sync")["ok"]
    assert invoke("snapshot")["accounts"] == 4
    accounts = invoke("accounts", "list")
    assert len(accounts) == 4
    rows = invoke("transactions", "list", "--limit", "1000")
    assert len(rows) == 730 and any(row["pending"] for row in rows)
    account = next(row["account_id"] for row in rows)
    filtered = invoke(
        "transactions",
        "list",
        "--account",
        account,
        "--since",
        str(date.today()),
        "--until",
        str(date.today()),
        "--category",
        "FOOD_AND_DRINK",
        "--search",
        "COFFEE",
        "--limit",
        "1",
    )
    assert len(filtered) == 1 and filtered[0]["amount"] == -5.5
    assert invoke("transactions", "list", "--search", "' OR 1=1 --") == []
    assert len(invoke("recurring", "list")) == 4
    assert all(
        r["direction"] == "out"
        for r in invoke("recurring", "list", "--direction", "out")
    )
    assert invoke("networth", "--days", "1")[0]["total"] == 4800
    assert invoke("systemd", "print") == systemd.units()


@pytest.mark.parametrize(
    "args",
    [
        ("plaid", "exchange", ""),
        ("plaid", "exchange"),
        ("transactions", "list", "--since", "bad"),
        ("transactions", "list", "--since", "2026-02-01", "--until", "2026-01-01"),
        ("transactions", "list", "--limit", "0"),
        ("transactions", "list", "--limit", "10001"),
        ("recurring", "list", "--direction", "bad"),
        ("networth", "--days", "0"),
        ("networth", "--days", "bad"),
    ],
)
def test_cli_json_errors(fake, args):
    assert invoke(*args, success=False)["error"]


def test_missing_settings_and_sandbox_guard(monkeypatch):
    monkeypatch.delenv("LEDGERLIGHT_FAKE_PLAID", raising=False)
    monkeypatch.delenv("PLAID_CLIENT_ID", raising=False)
    monkeypatch.delenv("PLAID_SECRET", raising=False)
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    for args in [
        ("plaid", "link-token"),
        ("plaid", "exchange", "synthetic"),
        ("plaid", "sandbox-link"),
        ("sync",),
    ]:
        assert "PLAID_CLIENT_ID" in invoke(*args, success=False)["error"]
    with TestClient(app) as client:
        response = client.post("/api/plaid/link-token")
        assert response.status_code == 400 and response.json()["error"]
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    assert "sandbox" in invoke("plaid", "sandbox-link", success=False)["error"]
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "true")
    assert plaid_client.status()["fake_plaid"] is False


def test_every_api_route(fake):
    with TestClient(app) as client:
        assert client.get("/api/status").json() == {
            "fake_plaid": True,
            "fake_prices": False,
            "plaid_env": "sandbox",
            "test_mode": True,
        }
        assert client.post("/api/plaid/link-token").json()["link_token"]
        assert client.post(
            "/api/plaid/exchange",
            json={
                "public_token": fake.sandbox_public_token(),
            },
        ).json()["id"]
        assert client.get("/api/plaid/items").json()[0]["institution"]
        assert client.post("/api/sync").json()["ok"]
        accounts = client.get("/api/accounts").json()
        assert len(accounts) == 2
        rows = client.get("/api/transactions?limit=1000").json()
        assert len(rows) == 365
        filtered = client.get(
            "/api/transactions",
            params={
                "account": rows[0]["account_id"],
                "search": "coffee",
                "limit": 1,
                "since": str(date.today()),
                "until": str(date.today()),
                "category": "FOOD_AND_DRINK",
            },
        ).json()
        assert len(filtered) == 1 and filtered[0]["pending"]
        assert len(client.get("/api/recurring").json()) == 2
        assert len(client.get("/api/recurring?direction=in").json()) == 1
        assert client.get("/api/networth?days=1").json()[0]["total"] == 2400
        for route in [
            "transactions?limit=0",
            "transactions?since=invalid",
            "transactions?limit=no",
            "recurring?direction=bad",
            "networth?days=-1",
            "networth?days=bad",
        ]:
            response = client.get(f"/api/{route}")
            assert 400 <= response.status_code < 500 and response.json()["error"]
        for body in [{}, {"public_token": ""}, {"public_token": 5}]:
            response = client.post("/api/plaid/exchange", json=body)
            assert response.status_code == 422 and response.json()["error"]


def test_demo_snapshots_and_units():
    seed()
    seed()
    assert len(data.networth()) == 90
    assert len(data.recurring()) == 2
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM balance_snapshots").fetchone()[0] == 180
    for name, content in systemd.units().items():
        assert Path(f"deploy/systemd/ledgerlight.{name}").read_text() == content
    assert "OnCalendar=*-*-* 00/6:00:00" in systemd.TIMER
    assert "Persistent=true" in systemd.TIMER
    assert "ledgerlight sync" in systemd.SERVICE
