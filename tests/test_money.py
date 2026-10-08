import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import data, money, plaid_client, sync
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.db import connect
from ledgerlight.plaid_client import FakePlaidClient


@pytest.fixture
def ledger(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-15")
    with connect() as db:
        db.executemany(
            "INSERT INTO accounts(id,name,balance,type,available) VALUES (?,?,?,?,?)",
            [
                ("a", "Synthetic Cash", 50, "depository", 40),
                ("b", "Synthetic Savings", 150, "depository", None),
                ("c", "Synthetic Credit", 0, "credit", None),
            ],
        )
        db.executemany(
            "INSERT INTO transactions "
            "(id,account_id,date,name,merchant,amount,category,plaid_category,pending) "
            "VALUES (?,'a',?,'Synthetic Shop','Shop',?,?,?,?)",
            [
                ("t", "2026-03-01", -100, "Old", "SHOPPING", 0),
                ("hidden", "2026-03-02", -200, "Food", None, 0),
                ("pending", "2026-03-03", -300, "Food", None, 1),
                ("last", "2026-02-28", -20, "Food", None, 0),
                ("last-early", "2026-02-05", -10, "Food", None, 0),
                ("next", "2026-04-01", -400, "Food", None, 0),
                ("pay", "2026-03-04", 1000, "Income", None, 0),
                ("cents", "2026-03-10", -0.3, "Food", None, 0),
            ],
        )
        db.execute("UPDATE transactions SET hidden=1 WHERE id='hidden'")
        db.executemany(
            "INSERT INTO recurring_streams "
            "(id,account_id,direction,description,average_amount,last_amount,"
            "predicted_next_date,is_active) "
            "VALUES (?,'a',?,'Synthetic Bill',-12,-10,?,?)",
            [
                ("due", "out", "2026-03-15", 1),
                ("edge", "out", "2026-03-18", 1),
                ("later", "out", "2026-03-19", 1),
                ("old", "out", "2026-03-14", 1),
                ("inactive", "out", "2026-03-16", 0),
                ("income", "in", "2026-03-16", 1),
            ],
        )


def invoke(*args, success=True):
    result = CliRunner().invoke(cli, ["--json", *args])
    assert (result.exit_code == 0) == success, (result.output, result.exception)
    return json.loads(result.output)


def test_rules_precedence_apply_undo_and_preview(ledger):
    first = money.rules_add("merchant", "contains", "SH", "First", 10)
    second = money.rules_add("name", "exact", "synthetic shop", "Second", 10)
    assert data.transactions(search="shop")[0]["category"] == "First"
    assert money.rules_preview("merchant", "exact", "sHoP")["match_count"] == 8
    best = money.rules_add("merchant", "exact", "shop", "Best", -1)
    assert {r["category"] for r in data.transactions()} == {"Best"}
    assert money.rules_apply()["changed"] == 0
    money.rules_remove(best["id"])
    money.rules_remove(first["id"])
    assert {r["category"] for r in data.transactions()} == {"Second"}
    money.rules_remove(second["id"])
    rows = {r["id"]: r for r in data.transactions()}
    assert rows["t"]["category"] == "SHOPPING"
    assert rows["last"]["category"] == "Food"
    assert rows["t"]["plaid_category"] == "SHOPPING"
    assert money.rules_apply()["changed"] == 0


def test_split_budget_spending_cashflow(ledger):
    money.txn_change("t", "split", parts=["Food=-60", "Home=-40"])
    money.txn_change("cents", "split", parts=["Food=-0.1", "Home=-0.2"])
    for parts in [
        [],
        ["Food=-99"],
        ["Food=NaN"],
        ["bad"],
        ["Food=-0.1000000001", "Home=-0.2"],
    ]:
        with pytest.raises(ValueError):
            money.txn_change("cents", "split", parts=parts)
    assert len(data.transactions(search="shop")[0]["splits"]) == 0
    for category, limit in [("Food", 50), ("Home", 100), ("Empty", 1)]:
        money.budgets_set(category, limit)
    report = {r["category"]: r for r in money.budgets_report("2026-03")}
    assert report["Food"] == {
        "category": "Food",
        "limit": 50,
        "spent": 60.1,
        "remaining": -10.1,
        "percent": 120.2,
    }
    assert report["Home"]["spent"] == 40.2
    assert report["Empty"]["spent"] == 0
    assert money.budgets_report("2026-02")[1]["spent"] == 30
    summary = money.spending_summary()
    assert summary["total_out"] == 100.3
    assert summary["top_merchants"] == [{"merchant": "Shop", "spent": 100.3}]
    assert summary["cumulative"][-1] == {
        "day": 15,
        "this_month": 100.3,
        "last_month": 10,
    }
    assert len(money.spending_summary("2026-02")["cumulative"]) == 28
    assert money.cashflow(2) == [
        {"month": "2026-02", "income": 0, "spending": 30},
        {"month": "2026-03", "income": 1000, "spending": 100.3},
    ]
    money.txn_change("t", "hide")
    assert money.spending_summary()["total_out"] == 0.3
    money.txn_change("pay", "hide")
    assert money.cashflow(1)[0]["income"] == 0
    money.txn_change("t", "unhide")
    money.txn_change("t", "unsplit")
    assert money.spending_summary()["total_out"] == 100.3
    money.txn_change("t", "note", note="Synthetic note")
    money.txn_change("t", "tag", tags=["work", "work", "tax"])
    assert data.transactions(tag="work")[0]["note"] == "Synthetic note"
    assert data.transactions(tag="work")[0]["tags"] == ["tax", "work"]
    money.txn_change("t", "untag", tags=["work"])
    assert data.transactions(tag="work") == []


def test_bills_alerts_thresholds_dismiss(ledger):
    assert [b["id"] for b in money.bills_upcoming(3)] == ["due", "edge"]
    assert len(money.bills_upcoming(0)) == 1
    money.recurring_mark("due", "cancel_intent")
    assert money.bills_upcoming(0)[0]["user_status"] == "cancel_intent"
    money.recurring_mark("edge", "ignored")
    assert len(money.bills_upcoming(3)) == 1
    money.budgets_set("Old", 99)
    assert money.alerts_refresh()["created"] == 3
    assert {a["kind"] for a in money.alerts_list()} == {
        "bill",
        "low_balance",
        "budget_over",
    }
    assert money.alerts_refresh()["created"] == 0
    for alert in money.alerts_list():
        money.alerts_dismiss(alert["id"])
    assert money.alerts_list() == []
    assert len(money.alerts_list(all=True)) == 3
    assert money.alerts_refresh()["created"] == 0
    money.settings_set("low_balance_threshold:b", 151)
    assert money.alerts_refresh()["created"] == 1
    assert money.settings_get("low_balance_threshold:a")["value"] == 100
    money.settings_set("bill_days", 4)
    assert money.alerts_refresh()["created"] == 1
    money.recurring_mark("edge", None)
    assert money.alerts_refresh()["created"] == 1


def test_alert_exact_thresholds(ledger):
    money.settings_set("low_balance_threshold", 40)
    money.settings_set("bill_days", 0)
    money.budgets_set("Old", 100)
    assert money.alerts_refresh()["created"] == 1  # only today's bill
    assert money.alerts_list()[0]["kind"] == "bill"


def test_goals_progress_dates_update_archive(ledger, monkeypatch):
    goal = money.goals_add("Synthetic Goal", 400, ["a", "b", "a"], "2026-04-14")
    report = money.goals_list()[0]
    assert report["progress"] == 200 and report["percent"] == 50
    assert report["remaining"] == 200 and report["on_track"] is True
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-30")
    assert money.goals_list()[0]["on_track"] is True
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-31")
    assert money.goals_list()[0]["on_track"] is False
    money.goals_update(goal["id"], target_amount=100)
    assert money.goals_list()[0]["remaining"] == 0
    money.goals_update(goal["id"], target_date="")
    assert money.goals_list()[0]["on_track"] is None
    money.goals_archive(goal["id"])
    assert money.goals_list()[0]["archived_at"]
    money.goals_add("Past", 500, ["a"], "2026-01-01")
    assert money.goals_list()[1]["on_track"] is False


def test_sync_preserves_extras_and_clears_changed_splits(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    rule = money.rules_add("merchant", "contains", "coffee", "Custom")
    sync.sandbox_link()
    assert sync.sync_all()["ok"]
    tx = data.transactions(search="Coffee")[0]
    assert tx["category"] == "Custom"
    id = tx["id"]
    money.txn_change(id, "note", note="Keep")
    money.txn_change(id, "hide")
    money.txn_change(id, "tag", tags=["Keep"])
    money.txn_change(id, "split", parts=["A=-2.5", "B=-3"])
    stream = data.recurring("out")[0]["id"]
    money.recurring_mark(stream, "ignored")
    assert sync.sync_all()["ok"]
    assert data.transactions(search="Coffee")[0]["splits"]
    assert data.recurring("out")[0]["user_status"] == "ignored"
    client = FakePlaidClient()
    original = client.transactions_sync
    changed_amount = False

    def changes(token, cursor):
        row = original(token, None)["added"][0]
        if changed_amount:
            row["amount"] = 6
        row["pending"] = False
        row["personal_finance_category"] = None
        return {"added": [], "modified": [row], "removed": [], "next_cursor": "next"}

    client.transactions_sync = changes
    monkeypatch.setattr(plaid_client, "get_client", lambda: client)
    assert sync.sync_all()["ok"]
    assert data.transactions(search="Coffee")[0]["splits"]
    changed_amount = True
    assert sync.sync_all()["ok"]
    tx = data.transactions(search="Coffee")[0]
    assert tx["note"] == "Keep" and tx["hidden"] and tx["tags"] == ["Keep"]
    assert tx["splits"] == [] and tx["split_cleared_at"]
    money.rules_remove(rule["id"])
    assert data.transactions(search="Coffee")[0]["category"] == "FOOD_AND_DRINK"
    money.settings_set("low_balance_threshold", 3000)
    assert sync.sync_all()["ok"]
    assert any(a["kind"] == "low_balance" for a in money.alerts_list())


def test_dry_runs_do_not_mutate(ledger):
    rule = money.rules_add("name", "contains", "shop", "Test")
    money.budgets_set("Test", 1)
    goal = money.goals_add("Goal", 100, ["a"])
    money.alerts_refresh()
    alert = money.alerts_list()[0]["id"]
    with connect() as db:
        before = list(db.iterdump())
    calls = [
        (money.rules_add, ("name", "exact", "Shop", "Other"), {}),
        (money.rules_remove, (rule["id"],), {}),
        (money.rules_apply, (), {}),
        (money.budgets_set, ("Test", 200), {}),
        (money.budgets_remove, ("Test",), {}),
        (money.txn_change, ("t", "split"), {"parts": ["A=-100"]}),
        (money.txn_change, ("t", "note"), {"note": "no write"}),
        (money.txn_change, ("t", "tag"), {"tags": ["no write"]}),
        (money.txn_change, ("t", "hide"), {}),
        (money.recurring_mark, ("due", "ignored"), {}),
        (money.settings_set, ("bill_days", 0), {}),
        (money.alerts_refresh, (), {}),
        (money.alerts_dismiss, (alert,), {}),
        (money.goals_add, ("Other", 200, ["b"]), {}),
        (money.goals_update, (goal["id"],), {"name": "Other"}),
        (money.goals_archive, (goal["id"],), {}),
    ]
    for fn, args, kwargs in calls:
        assert fn(*args, **kwargs, apply=False)["applied"] is False
    with connect() as db:
        assert list(db.iterdump()) == before


def test_cli_all_money_commands(ledger):
    rule = invoke(
        "rules",
        "add",
        "--match-field",
        "merchant",
        "--match-type",
        "exact",
        "--pattern",
        "Shop",
        "--category",
        "Food",
    )
    assert invoke("rules", "list")[0]["match_count"] == 8
    assert invoke("rules", "apply")["changed"] == 0
    assert invoke("rules", "remove", str(rule["id"]))["removed"] == rule["id"]
    assert invoke("budgets", "set", "Food", "20")["monthly_limit"] == 20
    assert invoke("budgets", "list")[0]["category"] == "Food"
    assert invoke("budgets", "report", "--month", "2026-02")[0]["spent"] == 30
    assert invoke("budgets", "remove", "Food")["removed"] == "Food"
    for args in [
        ("note", "t", "Note"),
        ("hide", "t"),
        ("unhide", "t"),
        ("tag", "t", "a", "b"),
        ("untag", "t", "a"),
        ("split", "t", "--part", "A=-40", "--part", "B=-60"),
        ("unsplit", "t"),
    ]:
        assert invoke("txn", *args)["action"] == args[0]
    assert invoke("transactions", "list", "--tag", "b")[0]["note"] == "Note"
    assert invoke("spending", "summary", "--month", "2026-03")["total_out"] == 100.3
    assert len(invoke("cashflow", "--months", "2")) == 2
    assert len(invoke("bills", "upcoming", "--days", "3")) == 2
    assert invoke("recurring", "mark", "due", "--status", "ignored")["user_status"]
    assert invoke("recurring", "mark", "due", "--status", "null")["user_status"] is None
    assert invoke("settings", "get")["bill_days"] == 3
    assert invoke("settings", "get", "bill_days")["value"] == 3
    assert invoke("settings", "set", "bill_days", "4")["value"] == 4
    assert invoke("alerts", "refresh")["created"] > 0
    alert = invoke("alerts", "list")[0]["id"]
    assert invoke("alerts", "dismiss", str(alert))["dismissed"] == alert
    assert any(a["dismissed_at"] for a in invoke("alerts", "list", "--all"))
    goal = invoke(
        "goals",
        "add",
        "--name",
        "Goal",
        "--target-amount",
        "500",
        "--account",
        "a",
        "--account",
        "b",
        "--target-date",
        "2026-04-01",
    )
    assert invoke("goals", "list")[0]["progress"] == 200
    assert invoke("goals", "update", str(goal["id"]), "--name", "New")["name"] == "New"
    assert invoke("goals", "archive", str(goal["id"]))["archived"] == goal["id"]


@pytest.mark.parametrize(
    "args",
    [
        ("rules", "add", "--match-field", "invalid"),
        ("rules", "remove", "99"),
        ("budgets", "remove", "missing"),
        ("budgets", "set", "A", "0"),
        ("budgets", "set", "A", "nan"),
        ("budgets", "report", "--month", "2026-13"),
        ("txn", "note", "missing", "x"),
        ("txn", "hide", "missing"),
        ("txn", "unhide", "missing"),
        ("txn", "tag", "t"),
        ("txn", "untag", "missing", "x"),
        ("txn", "unsplit", "missing"),
        ("txn", "split", "t", "--part", "A=-99"),
        ("spending", "summary", "--month", "2026-1"),
        ("cashflow", "--months", "0"),
        ("bills", "upcoming", "--days", "-1"),
        ("recurring", "mark", "due", "--status", "invalid"),
        ("alerts", "dismiss", "99"),
        ("settings", "get", "unknown"),
        ("settings", "set", "bill_days", "1.2"),
        ("settings", "set", "low_balance_threshold", "-1"),
        ("settings", "set", "low_balance_threshold:missing", "1"),
        ("goals", "add", "--name", "G", "--target-amount", "-1", "--account", "a"),
        ("goals", "update", "99", "--name", "G"),
        ("goals", "archive", "99"),
    ],
)
def test_cli_money_errors(ledger, args):
    assert invoke(*args, success=False)["error"]


def test_every_money_api_route(ledger):
    with TestClient(app) as client:

        def post(path, body=None):
            r = client.post("/api/" + path, json=body or {})
            assert r.status_code == 200, r.text
            return r.json()

        rule = {
            "match_field": "merchant",
            "match_type": "exact",
            "pattern": "SHOP",
            "category": "Food",
            "priority": 1,
        }
        assert post("rules/preview", rule)["match_count"] == 8
        id = post("rules", rule)["id"]
        assert client.get("/api/rules").json()[0]["id"] == id
        assert post("rules/apply")["changed"] == 0
        assert post(f"rules/{id}/remove")["removed"] == id
        post("budgets", {"category": "Food", "monthly_limit": 10})
        assert client.get("/api/budgets").json()[0]["monthly_limit"] == 10
        assert client.get("/api/budgets/report?month=2026-02").json()[0]["spent"] == 30
        post("budgets/Food/remove")
        for action, body in [
            ("note", {"note": "Hello"}),
            ("hide", {}),
            ("unhide", {}),
            ("tag", {"tags": ["tag"]}),
            ("untag", {"tags": ["tag"]}),
            ("split", {"parts": [{"category": "Food", "amount": -100}]}),
            ("unsplit", {}),
        ]:
            assert post(f"txn/t/{action}", body)["action"] == action
        post("txn/t/tag", {"tags": ["tag"]})
        assert client.get("/api/transactions?tag=tag").json()[0]["note"] == "Hello"
        assert (
            client.get("/api/spending/summary?month=2026-03").json()["total_out"]
            == 100.3
        )
        assert len(client.get("/api/cashflow?months=2").json()) == 2
        assert len(client.get("/api/bills/upcoming?days=3").json()) == 2
        post("recurring/due/mark", {"status": "ignored"})
        assert client.get("/api/recurring").json()[1]["user_status"] == "ignored"
        assert client.get("/api/settings").json()["bill_days"] == 3
        post("settings", {"key": "bill_days", "value": 4})
        assert client.get("/api/settings?key=bill_days").json()["value"] == 4
        assert post("alerts/refresh")["created"] > 0
        alert = client.get("/api/alerts").json()[0]["id"]
        post(f"alerts/{alert}/dismiss")
        assert any(a["dismissed_at"] for a in client.get("/api/alerts?all=true").json())
        goal = post("goals", {"name": "G", "target_amount": 100, "account_ids": ["a"]})
        post(f"goals/{goal['id']}/update", {"target_amount": 200})
        assert client.get("/api/goals").json()[0]["percent"] == 25
        post(f"goals/{goal['id']}/archive")
        assert client.get("/api/goals").json()[0]["archived_at"]


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "rules", {"match_field": "bad"}),
        (
            "post",
            "rules/preview",
            {"match_field": "name", "match_type": "exact", "pattern": ""},
        ),
        ("post", "rules/99/remove", {}),
        ("post", "budgets", {"category": "", "monthly_limit": 1}),
        ("post", "budgets/unknown/remove", {}),
        ("get", "budgets/report?month=bad", None),
        ("post", "txn/t/note", {}),
        ("post", "txn/t/split", {"parts": []}),
        ("post", "txn/t/tag", {"tags": [""]}),
        ("post", "txn/t/unknown", {}),
        ("post", "txn/missing/hide", {}),
        ("get", "spending/summary?month=2026-02-01", None),
        ("get", "cashflow?months=0", None),
        ("get", "bills/upcoming?days=-1", None),
        ("post", "recurring/due/mark", {"status": "bad"}),
        ("post", "alerts/99/dismiss", {}),
        ("get", "settings?key=unknown", None),
        ("post", "settings", {"key": "bill_days", "value": "bad"}),
        (
            "post",
            "goals",
            {"name": "G", "target_amount": 1, "account_ids": ["unknown"]},
        ),
        ("post", "goals/99/update", {}),
        ("post", "goals/99/archive", {}),
    ],
)
def test_money_api_errors(ledger, method, path, body):
    with TestClient(app) as client:
        response = client.request(method, "/api/" + path, json=body)
        assert 400 <= response.status_code < 500
        assert response.json()["error"]


def test_migration_extras_and_cascade_are_idempotent(ledger):
    money.txn_change("t", "note", note="Persist")
    money.txn_change("t", "tag", tags=["Persist"])
    money.txn_change("t", "split", parts=["A=-100"])
    for _ in range(3):
        with connect() as db:
            assert (
                db.execute("SELECT note FROM transactions WHERE id='t'").fetchone()[0]
                == "Persist"
            )
            assert (
                db.execute("SELECT COUNT(*) FROM transaction_tags").fetchone()[0] == 1
            )
            assert (
                db.execute("SELECT COUNT(*) FROM transaction_splits").fetchone()[0] == 1
            )
    with connect() as db:
        db.execute("DELETE FROM transactions WHERE id='t'")
        assert db.execute("SELECT COUNT(*) FROM transaction_tags").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM transaction_splits").fetchone()[0] == 0


def test_uncategorized_sync_rule_undo(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    client = FakePlaidClient()
    original = client.transactions_sync

    def uncategorized(token, cursor):
        changes = original(token, cursor)
        for row in changes["added"]:
            row["personal_finance_category"] = None
        return changes

    client.transactions_sync = uncategorized
    monkeypatch.setattr(plaid_client, "get_client", lambda: client)
    rule = money.rules_add("name", "contains", "Synthetic", "Rule")
    sync.sandbox_link()
    assert sync.sync_all()["ok"]
    assert {t["category"] for t in data.transactions()} == {"Rule"}
    money.rules_remove(rule["id"])
    assert {t["category"] for t in data.transactions()} == {"Uncategorized"}


def test_api_category_slash_and_required_rule_category(ledger):
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/budgets",
                json={
                    "category": "Food/Drink",
                    "monthly_limit": 100,
                },
            ).status_code
            == 200
        )
        assert client.post("/api/budgets/Food%2FDrink/remove").status_code == 200
        assert client.get("/api/budgets").json() == []
        response = client.post(
            "/api/rules",
            json={
                "match_field": "merchant",
                "match_type": "exact",
                "pattern": "Shop",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]
