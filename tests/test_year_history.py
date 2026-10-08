"""Year import contract: synthetic data and isolated storage, no network."""

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import data, money, plaid_client, sync
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.db import connect


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-15")


@pytest.mark.parametrize("value", ["29", "731", "abc", "365.5", "", "NaN"])
def test_invalid_depth_is_clear_and_has_no_link_side_effects(fake, monkeypatch, value):
    with pytest.raises(ValueError, match="history_days.*30 to 730"):
        money.settings_set("history_days", value)
    monkeypatch.setenv("LEDGERLIGHT_HISTORY_DAYS", value)
    for args in (["plaid", "link-token"], ["plaid", "sandbox-link"]):
        result = CliRunner().invoke(cli, ["--json", *args])
        assert result.exit_code == 1
        assert "history_days" in json.loads(result.output)["error"]
    assert sync.items() == []


@pytest.mark.parametrize("value", [30, 365, 730, "30", "365", "730"])
def test_history_depth_settings_api_accepts_integer_and_string_values(value):
    with TestClient(app) as client:
        response = client.post(
            "/api/settings", json={"key": "history_days", "value": value}
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "key": "history_days", "value": int(value), "applied": True
        }
        saved = client.get("/api/settings", params={"key": "history_days"})
        assert saved.json() == {"key": "history_days", "value": int(value)}
        assert type(saved.json()["value"]) is int
        assert money.history_days() == int(value)


@pytest.mark.parametrize("value", [29, 731, 365.5, "29", "731", "365.5", "abc", ""])
def test_history_depth_settings_api_rejects_invalid_values_without_writing(value):
    money.settings_set("history_days", "540")
    with TestClient(app) as client:
        response = client.post(
            "/api/settings", json={"key": "history_days", "value": value}
        )
        assert response.status_code == 400
        assert response.json() == {
            "error": "history_days must be an integer from 30 to 730"
        }
        assert client.get("/api/settings", params={"key": "history_days"}).json() == {
            "key": "history_days", "value": 540
        }


@pytest.mark.parametrize("days", [30, 365, 730])
def test_saved_depth_env_precedence_and_fixed_item_depth(fake, monkeypatch, days):
    assert money.settings_get("history_days")["value"] == 365
    money.settings_set("history_days", str(days))
    assert money.history_days() == days
    monkeypatch.setenv("LEDGERLIGHT_HISTORY_DAYS", "540")
    assert money.history_days() == 540
    monkeypatch.delenv("LEDGERLIGHT_HISTORY_DAYS")
    sync.sandbox_link()
    money.settings_set("history_days", "90")
    sync.sync_all()
    assert sync.items()[0]["history_days"] == days
    assert sync.items()[0]["transaction_count"] == days


@pytest.mark.parametrize("sandbox", [False, True])
@pytest.mark.parametrize("days", [365, 540])
def test_sdk_token_depth_survives_settings_change(monkeypatch, sandbox, days):
    """Token creation and exchange can use separate clients/processes."""
    money.settings_set("history_days", str(days))
    seen = []

    def call(self, method, **kwargs):
        if method in {"link_token_create", "sandbox_public_token_create"}:
            options = kwargs["options"] if sandbox else kwargs
            assert options["transactions"].days_requested == days
            # Even a settings change during the upstream call cannot change metadata.
            money.settings_set("history_days", "90")
            return {"public_token" if sandbox else "link_token": "synthetic-issued"}
        seen.append(method)
        return {"item_id": "synthetic-item", "access_token": "synthetic-access"}

    monkeypatch.setattr(plaid_client.PlaidClient, "_call", call)
    monkeypatch.setattr(
        plaid_client.PlaidClient, "institution_name", lambda *args: "Synthetic Bank"
    )
    monkeypatch.setattr(
        plaid_client, "get_client", lambda: object.__new__(plaid_client.PlaidClient)
    )
    monkeypatch.setattr(sync, "sync_all", lambda **kwargs: {"ok": True})
    client = plaid_client.get_client()
    if sandbox:
        body = {"public_token": client.sandbox_public_token()}
    else:
        body = {"public_token": "synthetic-public", **client.create_link_token()}
    monkeypatch.setenv("LEDGERLIGHT_HISTORY_DAYS", "730")
    with TestClient(app) as api:
        assert api.post("/api/plaid/exchange", json=body).status_code == 200
    assert seen == ["item_public_token_exchange"]
    assert sync.items()[0]["history_days"] == days
    assert sync.sync_status()["history_days"] == 730
    with connect() as db:
        rows = db.execute("SELECT * FROM plaid_link_history").fetchall()
        assert all(len(row["token_hash"]) == 64 for row in rows)
        assert all(row["history_days"] == days for row in rows)


@pytest.mark.parametrize("sandbox", [False, True])
def test_fake_tokens_keep_independent_depth_through_cli(fake, sandbox):
    tokens = []
    for days in [365, 540]:
        money.settings_set("history_days", str(days))
        client = plaid_client.get_client()
        if sandbox:
            tokens.append((client.sandbox_public_token(), []))
        else:
            token = client.create_link_token()["link_token"]
            tokens.append((f"synthetic-{days}", ["--link-token", token]))
    money.settings_set("history_days", "730")
    for days, (public, options) in zip([365, 540], tokens):
        result = CliRunner().invoke(
            cli, ["--json", "plaid", "exchange", public, *options]
        )
        assert result.exit_code == 0, result.output
        item_id = json.loads(result.output)["id"]
        sync.sync_all()
        item = next(row for row in sync.items() if row["id"] == item_id)
        assert item["history_days"] == days
        assert item["transaction_count"] == days
        # Sandbox intentionally uses stable account/Item IDs for relink coverage.
        sync.remove_item(item_id)


def test_real_exchange_rejects_unknown_history_before_network(monkeypatch):
    client = object.__new__(plaid_client.PlaidClient)
    monkeypatch.setattr(plaid_client, "get_client", lambda: client)
    monkeypatch.setattr(client, "_call", lambda *a, **kw: pytest.fail("network call"))
    with pytest.raises(plaid_client.PlaidError, match="Unknown Link history"):
        sync.link("synthetic-unknown")
    assert sync.items() == []


def test_initial_sync_progress_and_api(fake):
    with TestClient(app) as client:
        response = client.post(
            "/api/plaid/exchange", json={"public_token": "synthetic"}
        )
        assert response.status_code == 200
        status = client.get("/api/sync/status").json()
        assert status["history_days"] == 365
        item = status["items"][0]
        assert item["history_status"] == "INITIAL_UPDATE_COMPLETE"
        assert item["transaction_count"] == 30
        assert item["oldest_txn_date"] == "2026-02-14"
        assert item["background_active"] is True
        assert client.post("/api/sync").json()["ok"]
        item = client.get("/api/sync/status").json()["items"][0]
        assert item["history_status"] == sync.HISTORY_COMPLETE
        assert item["oldest_txn_date"] == "2025-03-16"
        assert item["transaction_count"] == 365
        assert item["background_active"] is False
        assert "access_token" not in json.dumps(item)
        assert "cursor" not in item


def test_remove_and_fresh_link_keep_notes_tags_and_splits(fake):
    money.settings_set("history_days", "90")
    linked = sync.sandbox_link()
    row = data.transactions(search="Coffee")[0]
    money.txn_change(row["id"], "note", note="Synthetic annotation")
    # Exercise the existing services through CLI, including exact command shapes.
    for args in (
        ["txn", "tag", row["id"], "kept"],
        ["txn", "split", row["id"], "--part", "Food=-5.5"],
    ):
        assert CliRunner().invoke(cli, ["--json", *args]).exit_code == 0
    money.settings_set("history_days", "365")
    with TestClient(app) as client:
        assert client.post(f"/api/plaid/items/{linked['id']}/remove").json() == {
            "removed": linked["id"],
            "retained_transactions": True,
        }
        assert sync.items() == []
        assert client.post("/api/plaid/items/missing/remove").status_code == 400
    sync.sandbox_link()
    sync.sync_all()
    current = data.transactions(search="Coffee")[0]
    assert current["id"] == row["id"]
    assert current["note"] == "Synthetic annotation"
    assert current["tags"] == ["kept"]
    assert current["splits"][0]["amount"] == -5.5
    assert sync.items()[0]["history_days"] == 365
    assert len(data.transactions(limit=1000)) == 365


class Ticks:
    """No wall-clock sleep in worker tests; stop after a controlled number of ticks."""

    def __init__(self, ticks):
        self.ticks = ticks

    def wait(self, interval):
        assert interval == 60
        self.ticks -= 1
        return self.ticks < 0

    def is_set(self):
        return self.ticks < 0


def test_background_completes_once_then_stops_syncing(fake, monkeypatch):
    sync.sandbox_link()
    original = sync.sync_all
    calls = []

    def record(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(sync, "sync_all", record)
    sync.history_worker(Ticks(4))
    assert len(calls) == 1
    assert sync.items()[0]["history_status"] == sync.HISTORY_COMPLETE


def test_background_time_bound_and_restart_does_not_extend_window(fake, monkeypatch):
    sync.sandbox_link()
    now = datetime.now(timezone.utc)
    with connect() as db:
        db.execute(
            "UPDATE plaid_items SET created_at=?",
            ((now - timedelta(seconds=1800)).strftime("%Y-%m-%d %H:%M:%S"),),
        )
    monkeypatch.setattr(sync, "sync_all", lambda **kw: pytest.fail("expired retry"))
    sync.history_worker(Ticks(3))
    sync.history_worker(Ticks(3))
    assert sync.sync_status()["items"][0]["background_active"] is False


def test_background_stops_retrying_stalled_import_at_thirty_minutes(fake, monkeypatch):
    sync.sandbox_link()
    start = datetime.now(timezone.utc).replace(microsecond=0)
    with connect() as db:
        db.execute("UPDATE plaid_items SET created_at=?", (start.isoformat(),))
    clock = [start]

    class Clock:
        @staticmethod
        def now(tz):
            return clock[0]

        fromisoformat = datetime.fromisoformat

    class AdvancingTicks(Ticks):
        def wait(self, interval):
            clock[0] += timedelta(seconds=interval)
            return super().wait(interval)

    calls = []
    monkeypatch.setattr(sync, "datetime", Clock)
    monkeypatch.setattr(sync, "sync_all", lambda **kw: calls.append(kw))
    sync.history_worker(AdvancingTicks(35))
    assert len(calls) == 29  # ticks at 60..1740; none at or after 1800 seconds
    assert sync.items()[0]["history_status"] == "INITIAL_UPDATE_COMPLETE"


def test_background_shutdown_interrupts_wait_and_joins(fake, monkeypatch):
    started, stopped = threading.Event(), threading.Event()

    def worker(stop):
        started.set()
        stop.wait(60)
        stopped.set()

    monkeypatch.setattr(sync, "history_worker", worker)
    with TestClient(app):
        assert started.wait(1)
        assert not stopped.is_set()
    assert stopped.is_set()


def test_shutdown_during_sync_rolls_back_without_followup_calls(fake, monkeypatch):
    sync.sandbox_link()
    before = sync.items()[0]
    stop = threading.Event()
    client = plaid_client.FakePlaidClient()
    original = client.transactions_sync

    def cancel(token, cursor):
        changes = original(token, cursor)
        stop.set()
        return changes

    client.transactions_sync = cancel
    client.recurring = lambda token: pytest.fail("request after shutdown")
    monkeypatch.setattr(plaid_client, "get_client", lambda: client)
    result = sync.sync_all(stop=stop)
    assert result["stopped"] and not result["ok"]
    assert sync.items()[0] == before


def test_sdk_pagination_obeys_stop_and_remaining_deadline(monkeypatch):
    client = object.__new__(plaid_client.PlaidClient)
    calls = []
    stop = threading.Event()

    def page(method, **kwargs):
        calls.append(kwargs)
        stop.set()
        return {
            "added": [],
            "modified": [],
            "removed": [],
            "next_cursor": "next",
            "has_more": True,
        }

    monkeypatch.setattr(client, "_call", page)
    with pytest.raises(plaid_client.SyncStopped):
        with plaid_client.sync_limits(stop):
            client.transactions_sync("synthetic", None)
    assert len(calls) == 1

    # Real SDK model construction with a fake HTTP endpoint: deadline bounds timeout.
    monkeypatch.setenv("PLAID_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("PLAID_SECRET", "synthetic-secret")
    real = plaid_client.PlaidClient()
    monkeypatch.setattr(plaid_client.time, "monotonic", lambda: 100)

    class Response:
        def to_dict(self):
            return {"accounts": []}

    def accounts(request, **kwargs):
        assert kwargs["_request_timeout"] == 5
        return Response()

    monkeypatch.setattr(real.api, "accounts_get", accounts)
    with plaid_client.sync_limits(deadline=105):
        assert real.accounts("synthetic") == []
    with pytest.raises(plaid_client.SyncStopped):
        with plaid_client.sync_limits(deadline=99):
            pytest.fail("started after deadline")


def test_wait_history_cli_completion_timeout_errors_and_item_status(fake, monkeypatch):
    sync.sandbox_link()
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--json", "sync", "--wait-history", "--timeout", "600"]
    )
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["items"][0]["history_status"] == sync.HISTORY_COMPLETE
    assert body["items"][0]["transaction_count"] == 365
    assert body["timed_out"] is False
    client = plaid_client.FakePlaidClient()
    original = client.transactions_sync

    def not_ready(token, cursor):
        return {**original(token, cursor), "transactions_update_status": "NOT_READY"}

    client.transactions_sync = not_ready
    monkeypatch.setattr(plaid_client, "get_client", lambda: client)
    result = runner.invoke(cli, ["--json", "sync", "--wait-history", "--timeout", "0"])
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert body["timed_out"] and body["error"]
    assert body["items"][0]["history_status"] == "NOT_READY"
    assert runner.invoke(cli, ["--json", "sync", "--timeout", "-1"]).exit_code == 1


def test_wait_history_polls_incomplete_items_without_real_sleep(fake, monkeypatch):
    sync.sandbox_link()
    client = plaid_client.FakePlaidClient()
    original = client.transactions_sync
    calls = []

    def pending_once(token, cursor):
        calls.append(cursor)
        result = original(token, cursor)
        if len(calls) == 1:
            result["transactions_update_status"] = "INITIAL_UPDATE_COMPLETE"
        return result

    client.transactions_sync = pending_once
    monkeypatch.setattr(plaid_client, "get_client", lambda: client)
    clock = [0]
    monkeypatch.setattr(sync.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        sync.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    assert sync.wait_history(600)["ok"]
    assert clock[0] == 60 and len(calls) == 2
