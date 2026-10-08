"""Manual loans paid down by matched linked transactions (synthetic, offline)."""

import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import (
    agent_tools,
    data,
    holdings,
    money,
    plaid_client,
    proposals,
    sync,
)
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.db import connect
from ledgerlight.plaid_client import FakePlaidClient

TODAY = "2026-03-15"


class ScriptedClient(FakePlaidClient):
    """Fake Plaid: each Item's next sync returns the queued rows for its accounts.

    Removed ids go to every Item's sync (sync only deletes the Item's own rows).
    """

    def __init__(self):
        self.added, self.removed, self.calls = [], [], 0

    def transactions_sync(self, access_token, cursor):
        self.calls += 1
        own = {a["account_id"] for a in self.accounts(access_token)}
        added = [row for row in self.added if row["account_id"] in own]
        self.added = [row for row in self.added if row["account_id"] not in own]
        removed = self.removed
        return {
            "added": added,
            "modified": [],
            "removed": [{"transaction_id": id} for id in removed],
            "next_cursor": f"scripted-{self.calls}",
            "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE",
        }

    def recurring(self, access_token):
        return {"inflow_streams": [], "outflow_streams": []}


@pytest.fixture
def plaid(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    monkeypatch.setenv("LEDGERLIGHT_TODAY", TODAY)
    client = ScriptedClient()
    monkeypatch.setattr(plaid_client, "get_client", lambda: client)
    sync.link("synthetic-loan-match")
    with connect() as db:
        client.account = db.execute(
            "SELECT id FROM accounts WHERE type='depository' AND item_id IS NOT NULL"
        ).fetchone()[0]
    return client


def checking(public_token):
    """The fake checking account id a public token's Item will have."""
    fake = FakePlaidClient()
    return fake.accounts(fake.exchange_public_token(public_token)[1])[0]["account_id"]


def txn(client, id, date, name, amount, merchant=None, pending=False, account=None):
    """Queue a Plaid-signed row: positive amount is money leaving the account."""
    client.added.append(
        {
            "transaction_id": id,
            "account_id": account or client.account,
            "date": date,
            "name": name,
            "merchant_name": merchant,
            "amount": amount,
            "pending": pending,
            "personal_finance_category": {"primary": "LOAN_PAYMENTS"},
        }
    )


def invoke(*args, success=True):
    result = CliRunner().invoke(cli, ["--json", *args])
    assert (result.exit_code == 0) is success, result.output
    return json.loads(result.output)


def balance(id):
    with connect() as db:
        return db.execute("SELECT balance FROM accounts WHERE id=?", (id,)).fetchone()[
            0
        ]


def applied():
    with connect() as db:
        return {
            (r["account_id"], r["transaction_id"]): r["amount"]
            for r in db.execute("SELECT * FROM loan_payments")
        }


def overview_row(id):
    for group in data.accounts_overview()["groups"]:
        for account in group["accounts"]:
            if account["id"] == id:
                return account
    raise AssertionError(id)


def loan(name="Sample plan", balance="1000", **kwargs):
    return holdings.manual_add("personal_loan", name, balance, **kwargs)["id"]


def test_payment_match_name_merchant_filters_once_and_snapshot(plaid):
    id = loan()
    txn(
        plaid,
        "by-name",
        "2026-03-05",
        "ACME PAYLATER INSTALLMENT ACME.EXAMPLE",
        150.0,
        merchant="Sample Market",
    )
    txn(plaid, "by-merchant", "2026-03-06", "Installment", 100, merchant="Acme")
    txn(plaid, "pending", "2026-03-07", "ACME* PENDING", 50, pending=True)
    txn(plaid, "inflow", "2026-03-07", "ACME REFUND", -40)
    txn(plaid, "before-since", "2026-02-27", "ACME* OLD", 60)
    txn(plaid, "hidden", "2026-03-08", "ACME* HIDDEN", 30)
    txn(plaid, "other", "2026-03-08", "Synthetic Grocer", 25)
    # Import first, hide one row, then set the match (explicit earlier since).
    assert sync.sync_all()["ok"]
    money.txn_change("hidden", "hide")
    holdings.manual_update(id, payment_match="acme", payment_match_since="2026-03-01")
    result = sync.sync_all()
    assert result["ok"]
    assert applied() == {(id, "by-name"): 150.0, (id, "by-merchant"): 100}
    assert balance(id) == pytest.approx(750.0)
    # Repeated syncs and explicit runs never apply a transaction twice.
    assert sync.sync_all()["ok"]
    assert holdings.manual_apply_payments()["loans"] == []
    assert balance(id) == pytest.approx(750.0)
    with connect() as db:
        snap = db.execute(
            "SELECT current FROM balance_snapshots WHERE account_id=? AND date=?",
            (id, TODAY),
        ).fetchone()[0]
    assert snap == pytest.approx(750.0)
    assert data.networth(1)[0]["date"] == TODAY
    row = overview_row(id)
    assert row["balance"] == pytest.approx(-750.0)
    assert row["payment_match"] == "acme"
    assert row["payment_match_since"] == "2026-03-01"
    assert row["payments_applied"] == 2
    assert row["last_payment"] == {"date": "2026-03-06", "amount": 100}
    payments = invoke("manual", "payments", id)
    assert [p["transaction_id"] for p in payments] == ["by-merchant", "by-name"]
    assert payments[1]["name"] == "ACME PAYLATER INSTALLMENT ACME.EXAMPLE"
    assert payments[1]["amount"] == 150.0 and payments[1]["date"] == "2026-03-05"


def test_sync_applies_new_transactions_and_floor_at_zero(plaid):
    id = loan(balance="150", payment_match="AFFIRM")
    assert holdings.manual_list()[0]["payment_match_since"] == TODAY
    txn(plaid, "a1", TODAY, "AFFIRM.COM PAYMENTS 1", 100)
    txn(plaid, "a2", TODAY, "AFFIRM.COM PAYMENTS 2", 100)
    assert sync.sync_all()["ok"]
    assert balance(id) == 0
    # The second payment records only what was deducted.
    assert applied() == {(id, "a1"): 100, (id, "a2"): 50}
    txn(plaid, "a3", TODAY, "AFFIRM.COM PAYMENTS 3", 100)
    assert sync.sync_all()["ok"]
    assert balance(id) == 0 and applied()[(id, "a3")] == 0
    assert overview_row(id)["payments_applied"] == 3


def test_plaid_removed_transaction_restores_loan_payment(plaid):
    id = loan(balance="500", payment_match="acme")
    txn(plaid, "k1", TODAY, "ACME* ONE", 120)
    txn(plaid, "k2", TODAY, "ACME* TWO", 80)
    txn(plaid, "unrelated", TODAY, "Synthetic Shop", 10)
    assert sync.sync_all()["ok"]
    assert balance(id) == 300
    plaid.removed = ["k1", "unrelated"]
    assert sync.sync_all()["ok"]
    assert balance(id) == 420
    assert applied() == {(id, "k2"): 80}
    with connect() as db:
        assert (
            db.execute(
                "SELECT current FROM balance_snapshots WHERE account_id=? AND date=?",
                (id, TODAY),
            ).fetchone()[0]
            == 420
        )
    assert overview_row(id)["payments_applied"] == 1


def test_removed_restore_rolls_back_with_failed_item_sync(plaid):
    id = loan(balance="500", payment_match="acme")
    txn(plaid, "k1", TODAY, "ACME* ONE", 120)
    assert sync.sync_all()["ok"]
    plaid.removed = ["k1"]
    plaid.recurring = lambda token: {"inflow_streams": [{"account_id": "bad"}]}
    assert not sync.sync_all()["ok"]
    # The failed Item rolled back its removal, so the payment stays applied.
    assert balance(id) == 380 and applied() == {(id, "k1"): 120}


def test_two_loans_one_transaction_most_specific_then_oldest(plaid):
    broad = loan("Acme", payment_match="acme")
    specific = loan("Acme PayLater", payment_match="Acme PayLater")
    first = loan("Affirm A", payment_match="affirm")
    second = loan("Affirm B", payment_match="AFFIRM")
    txn(plaid, "paylater", TODAY, "ACME PAYLATER INSTALLMENT ACME.EXAMPLE", 150.0)
    txn(plaid, "plain", TODAY, "ACME* SHOP", 20)
    txn(plaid, "affirm", TODAY, "AFFIRM.COM PAYMENTS", 30)
    assert sync.sync_all()["ok"]
    assert applied() == {
        (specific, "paylater"): 150.0,
        (broad, "plain"): 20,
        (first, "affirm"): 30,
    }
    assert balance(second) == 1000
    with connect() as db, pytest.raises(Exception, match="UNIQUE"):
        db.execute(
            "INSERT INTO loan_payments (account_id,transaction_id,amount,applied_at)"
            " VALUES (?,?,?,?)",
            (second, "affirm", 1, "x"),
        )


@pytest.mark.parametrize(
    "kwargs,message",
    [
        (
            {"monthly_payment": "50", "auto_paydown": True, "payment_match": "x"},
            "not both",
        ),
        ({"payment_match_since": "2026-01-01"}, "requires payment_match"),
        ({"payment_match": "x", "payment_match_since": "03/01/2026"}, "ISO date"),
        ({"payment_match": "x" * 101}, "at most 100"),
    ],
)
def test_payment_match_validation(monkeypatch, kwargs, message):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", TODAY)
    with pytest.raises(ValueError, match=message):
        holdings.manual_add("student_loan", "Loan", "10", **kwargs)


def test_payment_match_conflicts_and_kinds(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", TODAY)
    with pytest.raises(ValueError, match="loans only"):
        holdings.manual_add("cash", "Wallet", "10", payment_match="x")
    auto = loan(monthly_payment="50", auto_paydown=True)
    with pytest.raises(ValueError, match="not both"):
        holdings.manual_update(auto, payment_match="acme")
    matched = loan(monthly_payment="50", payment_match="acme")
    with pytest.raises(ValueError, match="not both"):
        holdings.manual_update(matched, auto_paydown=True)
    # Clearing the match first allows auto-paydown.
    holdings.manual_update(matched, payment_match="")
    cleared = holdings.manual_update(matched, auto_paydown=True)
    assert cleared["payment_match"] is None and cleared["payment_match_since"] is None
    error = invoke(
        "manual",
        "add",
        "--kind",
        "auto_loan",
        "--name",
        "X",
        "--balance",
        "5",
        "--payment",
        "5",
        "--auto-paydown",
        "--payment-match",
        "x",
        success=False,
    )
    assert "not both" in error["error"]


def test_setting_or_changing_match_never_retro_applies(plaid, monkeypatch):
    txn(plaid, "old", "2026-03-10", "ACME* OLD", 50)
    assert sync.sync_all()["ok"]
    id = loan(payment_match="acme")
    assert sync.sync_all()["ok"]
    assert balance(id) == 1000 and applied() == {}
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-20")
    # Unchanged text keeps its date; changed text restarts from today.
    assert (
        holdings.manual_update(id, payment_match="acme")["payment_match_since"]
        == TODAY
    )
    changed = holdings.manual_update(id, payment_match="acme*")
    assert changed["payment_match_since"] == "2026-03-20"
    txn(plaid, "new", "2026-03-19", "ACME* NEW", 25)
    assert sync.sync_all()["ok"]
    assert applied() == {}
    # An explicit earlier date is the user's choice and applies from then.
    holdings.manual_update(id, payment_match_since="2026-03-01")
    assert holdings.manual_apply_payments()["loans"][0]["to"] == 925
    assert set(applied()) == {(id, "old"), (id, "new")}


def test_cli_propose_and_apply_payments(plaid):
    added = invoke(
        "manual",
        "add",
        "--kind",
        "personal_loan",
        "--name",
        "Sample plan",
        "--balance",
        "400",
        "--payment-match",
        "ACME",
        "--payment-match-since",
        "2026-03-01",
    )
    id = added["id"]
    assert added["payment_match"] == "ACME"
    assert added["payment_match_since"] == "2026-03-01"
    [listed] = invoke("manual", "list")
    assert listed["payment_match"] == "ACME"
    # Import without running the end-of-sync hook, to exercise apply-payments.
    txn(plaid, "k1", "2026-03-02", "ACME* ONE", 100)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(holdings, "manual_apply_payments", lambda: None)
        assert sync.sync_all()["ok"]
    assert balance(id) == 400
    proposal = invoke("manual", "apply-payments", "--propose")
    assert proposal["diff"]["applied"] is False
    assert proposal["diff"]["loans"][0]["payments"][0]["transaction_id"] == "k1"
    assert balance(id) == 400 and applied() == {}
    result = proposals.apply(proposal["proposal_id"])
    assert result["applied"] is True and balance(id) == 300
    assert invoke("manual", "apply-payments")["loans"] == []
    updated = invoke("manual", "update", id, "--payment-match", "")
    assert updated["payment_match"] is None
    assert invoke("manual", "payments", "manual-missing", success=False)["error"]


def test_agent_allowlist_payment_commands():
    assert ("manual", "payments") in agent_tools.READS
    assert ("manual", "apply-payments") in agent_tools.WRITES
    with pytest.raises(ValueError, match="--propose"):
        agent_tools.validate_args(["manual", "apply-payments"])
    assert agent_tools.validate_args(["manual", "apply-payments", "--propose"])
    with pytest.raises(ValueError, match="--propose"):
        agent_tools.validate_args(["manual", "update", "M", "--payment-match", "x"])


def test_api_payment_match_routes(plaid):
    client = TestClient(app)
    created = client.post(
        "/api/manual",
        json={
            "kind": "student_loan",
            "name": "Synthetic Student",
            "balance": 900,
            "payment_match": "Synthetic Servicer",
            "payment_match_since": "2026-03-01",
        },
    ).json()
    id = created["id"]
    assert created["payment_match_since"] == "2026-03-01"
    txn(plaid, "s1", "2026-03-03", "SYNTHETIC SERVICER PMT", 150)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(holdings, "manual_apply_payments", lambda: None)
        assert sync.sync_all()["ok"]
    result = client.post("/api/manual/apply-payments").json()
    assert result["loans"][0]["to"] == 750
    payments = client.get(f"/api/manual/{id}/payments").json()
    assert [p["transaction_id"] for p in payments] == ["s1"]
    patched = client.patch(
        f"/api/manual/{id}", json={"payment_match": "servicer"}
    ).json()
    assert patched["payment_match"] == "servicer"
    assert patched["payment_match_since"] == TODAY
    bad = client.patch(f"/api/manual/{id}", json={"payment_match_since": "soon"})
    assert bad.status_code == 400 and "ISO date" in bad.json()["error"]
    assert client.get("/api/manual/manual-missing/payments").status_code == 400
    overview = client.get("/api/accounts/overview").json()
    row = next(a for g in overview["groups"] for a in g["accounts"] if a["id"] == id)
    assert row["payments_applied"] == 1
    assert row["last_payment"] == {"date": "2026-03-03", "amount": 150}
    # Removing the loan cascades its applied payments.
    assert client.delete(f"/api/manual/{id}").status_code == 200
    assert applied() == {}


def test_reads_do_not_apply_payments(plaid):
    id = loan(payment_match="acme")
    txn(plaid, "k1", TODAY, "ACME* ONE", 100)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(holdings, "manual_apply_payments", lambda: None)
        assert sync.sync_all()["ok"]
    data.accounts_overview()
    invoke("manual", "list")
    invoke("manual", "payments", id)
    holdings.manual_apply_payments(apply=False)
    assert balance(id) == 1000 and applied() == {}


def test_loan_payment_relink_replay_does_not_deduct_twice(plaid):
    id = loan(payment_match="acme")
    txn(plaid, "k1", TODAY, "ACME PAYLATER INSTALLMENT ACME.EXAMPLE", 150.0)
    assert sync.sync_all()["ok"]
    assert balance(id) == pytest.approx(850.0)
    [item] = sync.items()
    sync.remove_item(item["id"])  # Keeps local transactions, detaches accounts.
    # Fresh Link: new Item, new account and transaction ids, same payment.
    relinked = checking("synthetic-loan-match-relink")
    assert relinked != plaid.account
    txn(
        plaid,
        "k1-new",
        TODAY,
        "ACME PAYLATER INSTALLMENT ACME.EXAMPLE",
        150.0,
        account=relinked,
    )
    sync.link("synthetic-loan-match-relink")
    assert sync.sync_all()["ok"]
    assert balance(id) == pytest.approx(850.0)
    assert applied() == {(id, "k1"): 150.0}
    # Stored fingerprint: the original still lists with its own date and name.
    [payment] = holdings.manual_payments(id)
    assert payment["date"] == TODAY
    assert payment["name"] == "ACME PAYLATER INSTALLMENT ACME.EXAMPLE"
    assert payment["source_account_id"] == plaid.account
    assert overview_row(id)["last_payment"] == {"date": TODAY, "amount": 150.0}


def test_loan_payment_identical_same_day_in_one_account_both_apply(plaid):
    id = loan(payment_match="affirm")
    txn(plaid, "a1", TODAY, "AFFIRM.COM PAYMENTS", 100)
    txn(plaid, "a2", TODAY, "AFFIRM.COM PAYMENTS", 100)
    assert sync.sync_all()["ok"]
    assert balance(id) == 800
    assert applied() == {(id, "a1"): 100, (id, "a2"): 100}
    # A later identical payment from the same account also applies.
    txn(plaid, "a3", TODAY, "affirm.com payments", 100)
    assert sync.sync_all()["ok"]
    assert balance(id) == 700


def test_loan_payment_duplicate_link_single_batch_applies_once(plaid):
    id = loan(payment_match="acme")
    duplicate = checking("synthetic-loan-match-dup")
    sync.link("synthetic-loan-match-dup")
    txn(plaid, "d1", TODAY, "ACME* ONE", 100)
    txn(plaid, "d2", TODAY, "Acme* One", 100, account=duplicate)
    with pytest.MonkeyPatch.context() as m:
        m.setattr(holdings, "manual_apply_payments", lambda: None)
        assert sync.sync_all()["ok"]
    [change] = holdings.manual_apply_payments()["loans"]
    assert [p["transaction_id"] for p in change["payments"]] == ["d1"]
    assert balance(id) == 900 and applied() == {(id, "d1"): 100}
    assert sync.sync_all()["ok"]
    assert balance(id) == 900


def test_loan_payment_skips_paid_off_loans_while_another_owes(plaid):
    older = loan("Acme old", balance="50", payment_match="acme")
    newer = loan("Acme new", balance="100", payment_match="ACME")
    # Tie by text: the older loan wins until it reaches zero, then the next.
    txn(plaid, "k1", TODAY, "ACME* ONE", 50)
    txn(plaid, "k2", TODAY, "ACME* TWO", 60)
    assert sync.sync_all()["ok"]
    assert applied() == {(older, "k1"): 50, (newer, "k2"): 60}
    txn(plaid, "k3", TODAY, "ACME* THREE", 70)
    assert sync.sync_all()["ok"]
    assert balance(older) == 0 and balance(newer) == 0
    assert applied()[(newer, "k3")] == 40
    # Every matching loan at zero: the tie winner records it once with 0.
    txn(plaid, "k4", TODAY, "ACME* FOUR", 10)
    assert sync.sync_all()["ok"]
    assert applied()[(older, "k4")] == 0
    assert sum(1 for key in applied() if key[1] == "k4") == 1
    assert holdings.manual_apply_payments()["loans"] == []


def test_loan_payment_replay_never_moves_to_another_loan(plaid):
    paid = loan("Acme paid", balance="100", payment_match="acme")
    other = loan("Acme other", balance="500", payment_match="acme")
    txn(plaid, "k1", TODAY, "ACME* ONE", 100)
    assert sync.sync_all()["ok"]
    assert balance(paid) == 0 and balance(other) == 500
    [item] = sync.items()
    sync.remove_item(item["id"])
    relinked = checking("synthetic-loan-match-relink")
    txn(plaid, "k1-new", TODAY, "ACME* ONE", 100, account=relinked)
    sync.link("synthetic-loan-match-relink")
    assert sync.sync_all()["ok"]
    assert balance(other) == 500 and applied() == {(paid, "k1"): 100}


def test_update_since_without_payment_match_is_refused(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", TODAY)
    id = loan()
    with pytest.raises(ValueError, match="payment_match_since requires payment_match"):
        holdings.manual_update(id, payment_match_since="2026-03-01")
    matched = loan(payment_match="acme")
    with pytest.raises(ValueError, match="payment_match_since requires payment_match"):
        holdings.manual_update(
            matched, payment_match="", payment_match_since="2026-03-01"
        )
