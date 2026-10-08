"""Stage 6 uses isolated synthetic ledgers and the real CLI/fake AG-UI loop."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from ag_ui.core import RunAgentInput
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import agent, charts, dashboard, demo, spending
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.db import connect


def invoke(*args):
    result = CliRunner().invoke(cli, ["--json", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_matching_splits_dates_and_saveable_charts(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-15")
    with connect() as db:
        db.execute("INSERT INTO accounts(id,name) VALUES('a','Synthetic')")
        for id, date, name, merchant, category, note, amount, hidden, pending in [
            ("one", "2026-03-15", "Shop", "CAFÉ", "Food", "", -8, 0, 0),
            ("two", "2026-02-01", "Coffee purchase", "Shop", "Food", "", -10, 0, 0),
            ("split", "2026-03-01", "Shop", "Other", "Coffee", "", -20, 0, 0),
            ("tag", "2026-03-02", "Shop", "Other", "Food", "", -3, 0, 0),
            ("note", "2026-03-03", "Shop", "Other", "Food", "ESPRESSO", -4, 0, 0),
            (
                "hidden",
                "2026-03-02",
                "Coffee",
                "Secret merchant",
                "Secret",
                "",
                -50,
                1,
                0,
            ),
            ("pending", "2026-03-02", "Coffee", "Shop", "Food", "", -50, 0, 1),
            ("income", "2026-03-02", "Coffee", "Shop", "Food", "", 50, 0, 0),
            ("future", "2026-03-16", "Coffee", "Shop", "Food", "", -50, 0, 0),
            ("old", "2026-01-31", "Coffee", "Shop", "Food", "", -50, 0, 0),
        ]:
            db.execute(
                "INSERT INTO transactions(id,account_id,date,name,merchant,"
                "category,note,amount,hidden,pending) VALUES(?,'a',?,?,?,?,?,?,?,?)",
                (id, date, name, merchant, category, note, amount, hidden, pending),
            )
        db.execute("INSERT INTO transaction_tags VALUES('tag','STARBUCKS')")
        db.executemany(
            "INSERT INTO transaction_splits(transaction_id,category,amount) "
            "VALUES('split',?,?)",
            [("Coffee", -6), ("Home", -18), ("Coffee", 4)],
        )
    answer = spending.ask("hey what was my COFFEE spend like", 2)
    assert answer["total"] == 31
    assert answer["average_per_month"] == 15.5
    assert answer["this_month"] == 21
    assert answer["last_month"] == 10
    assert answer["months"] == [
        {"month": "2026-02", "total": 10, "count": 1},
        {"month": "2026-03", "total": 21, "count": 4},
    ]
    assert len(answer["transactions"]) == 5
    assert answer["transactions"][0]["id"] == "one"
    for spec in answer["charts"]:
        assert spec["mark"] == "bar"
        saved = charts.add(
            spec["usermeta"]["title"], spec["usermeta"]["sql"], spec["mark"]
        )
        assert saved["rows"] == spec["data"]["values"]
    assert invoke("spending", "ask", "coffee", "--months", "2")["total"] == 31
    client = TestClient(app)
    assert (
        client.get("/api/spending/ask", params={"text": "coffee", "months": 2}).json()[
            "total"
        ]
        == 31
    )
    empty = spending.ask("unicorn", 2)
    assert all(
        empty[k] == [] for k in ("months", "merchants", "transactions", "charts")
    )
    assert "Secret merchant" not in empty["suggestions"]
    assert empty["suggestions"]
    assert spending.ask("x' OR 1=1 --", 2)["total"] == 0


@pytest.mark.parametrize(
    "query,months", [("", 12), ("coffee", 0), ("coffee", 121), ("x" * 501, 12)]
)
def test_ask_errors(query, months):
    result = CliRunner().invoke(
        cli, ["--json", "spending", "ask", query, "--months", str(months)]
    )
    assert result.exit_code != 0
    assert "error" in json.loads(result.output)
    assert (
        TestClient(app)
        .get("/api/spending/ask", params={"text": query, "months": months})
        .status_code
        == 400
    )


def test_default_save_reset_undo_and_seed():
    assert invoke("dashboard", "default", "show") == {"layout": None, "saved_at": None}
    initial = dashboard.snapshot()
    dashboard.change("move", id="cashflow", x=0, y=30)
    saved = invoke("dashboard", "default", "save")
    assert saved["saved_at"]
    client = TestClient(app)
    assert client.get("/api/dashboard/default/show").json() == saved
    moved = dashboard.change("move", id="cashflow", x=6, y=40)
    reset = client.post("/api/dashboard/default/reset", json={}).json()
    assert reset["version"] > moved["version"]
    assert reset["event"]["actor"] == "user"

    def geometry(cards):
        return [(c["id"], c["x"], c["y"], c["w"], c["h"]) for c in cards]

    assert geometry(reset["cards"]) == geometry(saved["layout"])
    assert dashboard.change("undo")["cards"] == moved["cards"]
    with pytest.raises(ValueError):
        dashboard.default_save(expected_version=initial["version"])
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM dashboard_default").fetchone()[0] == 1
    dashboard.default_save()
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM dashboard_default").fetchone()[0] == 1
        db.execute("DELETE FROM dashboard_default")
    assert geometry(invoke("dashboard", "default", "reset")["cards"]) == geometry(
        initial["cards"]
    )
    # Intentionally empty defaults remain empty; never trigger first-run seeding.
    for card in dashboard.snapshot()["cards"]:
        dashboard.change("remove", id=card["id"])
    assert client.post("/api/dashboard/default/save", json={}).json()["layout"] == []
    dashboard.change("add", kind="cashflow")
    assert dashboard.change("reset_default")["cards"] == []
    assert dashboard.snapshot()["cards"] == []


def test_demo_is_relative_and_idempotent(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2030-06-15")
    assert demo.seed() == demo.seed()
    with connect() as db:
        row = db.execute(
            "SELECT MIN(date),MAX(date),COUNT(*) FROM transactions"
        ).fetchone()
        assert tuple(row) == ("2030-02-16", "2030-06-15", 124)
    answer = spending.ask("coffee")
    assert answer["this_month"] > 0
    assert len(answer["transactions"]) == 10
    assert len(answer["charts"]) == 2


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "stage5"])
def test_demo_stable_ids_across_dates_preserve_existing_data(monkeypatch, legacy):
    def rows():
        with connect() as db:
            return {
                row["id"]: dict(row)
                for row in db.execute("SELECT * FROM transactions")
            }

    if legacy:
        # Reproduce all 93 fixed-ID Jan–Mar stage-5 transactions independently
        # of the current seed, so an ID or merchant-rotation regression is caught.
        merchants = [
            ("Demo Coffee Co", "Food & Drink", -5.5),
            ("Demo Market", "Groceries", -42.0),
            ("Demo Transit", "Transport", -12.0),
            ("Demo Streaming", "Entertainment", -9.0),
        ]
        with connect() as db:
            db.execute(
                "INSERT INTO accounts(id,name,balance) "
                "VALUES('demo-checking','Synthetic Demo Checking',1234.5)"
            )
            for day in range(90):
                merchant, category, amount = merchants[day % 4]
                day_date = str(date(2026, 1, 1) + timedelta(days=day))
                db.execute(
                    "INSERT INTO transactions "
                    "(id,account_id,date,name,merchant,amount,category) "
                    "VALUES(?,'demo-checking',?,?,?,?,?)",
                    (
                        f"demo-expense-{day}", day_date, merchant, merchant,
                        amount, category,
                    ),
                )
                if day % 30 == 0:
                    db.execute(
                        "INSERT INTO transactions "
                        "(id,account_id,date,name,merchant,amount,category) "
                        "VALUES(?,'demo-checking',?,'Demo Payroll',"
                        "'Demo Employer',2500,'Income')",
                        (f"demo-income-{day}", day_date),
                    )
        old = rows()
        assert len(old) == 93

    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2030-06-15")
    assert demo.seed()["transactions"] == 124
    seeded = rows()
    expected_ids = {f"demo-expense-{day}" for day in range(120)} | {
        f"demo-income-{day}" for day in range(0, 120, 30)
    }
    assert set(seeded) == expected_ids
    if legacy:
        for id, row in old.items():
            assert seeded[id] == {**row, "date": seeded[id]["date"]}
    assert {"Demo Espresso", "Bean There Cafe"} <= {
        row["merchant"] for row in seeded.values()
    }

    with connect() as db:
        db.execute(
            "UPDATE transactions SET note='Synthetic note',hidden=1,"
            "category='Custom',base_category='Food & Drink' "
            "WHERE id='demo-expense-0'"
        )
        db.execute("INSERT INTO transaction_tags VALUES('demo-expense-0','custom')")
        db.executemany(
            "INSERT INTO transaction_splits(transaction_id,category,amount) "
            "VALUES('demo-expense-0',?,?)",
            [("Food", -3), ("Other", -2.5)],
        )
        # A non-demo row on the demo account must also remain untouched.
        db.execute(
            "INSERT INTO transactions(id,account_id,date,name,amount,category) "
            "VALUES('unrelated','demo-checking','2025-01-01','Synthetic',-7,'Other')"
        )
        extras = [
            [tuple(row) for row in db.execute(f"SELECT * FROM {table}")]
            for table in ("transaction_tags", "transaction_splits")
        ]
    before = rows()
    for current in ("2030-06-15", "2030-06-16", "2030-07-01", "2031-01-01"):
        monkeypatch.setenv("LEDGERLIGHT_TODAY", current)
        assert demo.seed()["transactions"] == 124
        after = rows()
        assert set(after) == expected_ids | {"unrelated"}
        for id, row in before.items():
            expected_date = row["date"]
            if id in expected_ids:
                slot = int(id.rsplit("-", 1)[1])
                expected_date = str(
                    date.fromisoformat(current) - timedelta(days=119 - slot)
                )
            assert after[id] == {**row, "date": expected_date}
        with connect() as db:
            assert extras == [
                [tuple(row) for row in db.execute(f"SELECT * FROM {table}")]
                for table in ("transaction_tags", "transaction_splits")
            ]
        # Same-day reseeding is an exact no-op for transactions, too.
        demo.seed()
        assert rows() == after


def test_chart_catalog_releases_lock_before_live_queries(monkeypatch):
    for i in range(3):
        charts.add(f"Synthetic {i}", "SELECT 'coffee' AS name, 5 AS total", "bar")
    original = charts._chart

    def query(row):
        # Simulate the concurrent layout/SSE writes made by a mounted dashboard.
        # A catalog cursor held across live queries deadlocks this writer.
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(dashboard.default_save).result(timeout=2)["saved_at"]
        return original(row)

    monkeypatch.setattr(charts, "_chart", query)
    assert len(charts.list_charts()) == 3


def test_fake_provider_exactly_ask_then_answer(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-15")
    demo.seed()
    body = RunAgentInput(
        thread_id="test",
        run_id="test",
        state={},
        messages=[
            {"id": "u", "role": "user", "content": "hey what was my coffee spend like"}
        ],
        tools=[
            {
                "name": "show_answer",
                "description": "Answer panel",
                "parameters": {"type": "object"},
            }
        ],
    )
    events = [e.model_dump(by_alias=True) for e in agent.events(body)]
    assert events[-1]["type"] == "RUN_FINISHED"
    assert [e["toolCallName"] for e in events if e["type"] == "TOOL_CALL_START"] == [
        "run_ledgerlight",
        "show_answer",
    ]
    args = [json.loads(e["delta"]) for e in events if e["type"] == "TOOL_CALL_ARGS"]
    assert args[0]["args"] == ["spending", "ask", "hey what was my coffee spend like"]
    result = spending.ask("hey what was my coffee spend like")
    assert args[1]["charts"] == result["charts"]
    assert f"${result['total']:.2f}" in args[1]["summary"]
