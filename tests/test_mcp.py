"""Offline MCP contracts against the real in-process client and stdio transport."""

import asyncio
import json
import os
import re
import selectors
import sqlite3
import subprocess
import sys
from importlib.resources import files

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from fastmcp import Client

from ledgerlight import charts, dashboard, data, demo, holdings, money, proposals
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.config import db_path
from ledgerlight.db import connect
from ledgerlight.mcp_server import CHART_URI, create_server

READS = {
    "accounts",
    "accounts_overview",
    "transactions",
    "recurring",
    "bills_upcoming",
    "budgets_report",
    "spending_summary",
    "spending_ask",
    "cashflow",
    "networth",
    "goals",
    "alerts",
    "rules",
    "chart_list",
    "chart_show",
    "chart_preview",
    "dashboard_list",
    "manual_list",
    "manual_payments",
    "holdings_list",
}
UI = {
    "ui_navigate",
    "ui_filter",
    "ui_highlight",
    "dashboard_add",
    "dashboard_move",
    "dashboard_resize",
    "dashboard_remove",
    "dashboard_undo",
    "dashboard_reset_default",
}
PROPOSE = {
    "propose_rules_add",
    "propose_rules_remove",
    "propose_rules_apply",
    "propose_txn_note",
    "propose_txn_hide",
    "propose_txn_unhide",
    "propose_txn_tag",
    "propose_txn_untag",
    "propose_txn_split",
    "propose_txn_unsplit",
    "propose_budgets_set",
    "propose_budgets_remove",
    "propose_recurring_mark",
    "propose_alerts_refresh",
    "propose_alerts_dismiss",
    "propose_settings_set",
    "propose_goals_add",
    "propose_goals_update",
    "propose_goals_archive",
    "propose_manual_add",
    "propose_manual_update",
    "propose_manual_remove",
    "propose_manual_apply_paydown",
    "propose_manual_apply_payments",
    "propose_holdings_add",
    "propose_holdings_update",
    "propose_holdings_remove",
    "propose_holdings_refresh",
}


def result_json(result):
    return json.loads(result.content[0].text)


def ledger_state():
    with connect() as db:
        tables = [
            r[0]
            for r in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name!='proposals'"
            )
        ]
        return {
            name: [tuple(r) for r in db.execute(f'SELECT * FROM "{name}"')]
            for name in tables
        }


def test_inventory_annotations_and_resource():
    async def check():
        async with Client(create_server()) as client:
            tools = {t.name: t for t in await client.list_tools()}
            assert set(tools) == READS | UI | PROPOSE | {"chart_save"}
            skill = files("ledgerlight").joinpath("SKILL.md").read_text()
            for name, tool in tools.items():
                assert f"`{name}`" in skill
                annotation = tool.annotations.model_dump(by_alias=True)
                assert annotation["readOnlyHint"] == (name in READS)
                assert annotation["destructiveHint"] is False
                assert annotation["openWorldHint"] is False
                assert not {"apply", "actor", "args", "command"} & set(
                    tool.input_schema.get("properties", {})
                )
            for name in ("chart_preview", "chart_show"):
                assert tools[name].meta["ui"]["resourceUri"] == CHART_URI
            resources = await client.list_resources()
            assert [str(r.uri) for r in resources] == [CHART_URI]
            content = (await client.read_resource(CHART_URI))[0]
            assert content.mime_type == "text/html;profile=mcp-app"
            assert all(v == [] for v in content.meta["ui"]["csp"].values())
            assert not re.search(
                r"https?://|(?:src|href)=[\"'](?://|https?:)", content.text
            )
            assert "connect-src 'none'" in content.text
            assert "ui/initialize" in content.text
            assert "ui/notifications/tool-result" in content.text
            assert (
                len(content.text) > 500_000
            )  # Includes Vega, Lite and Embed, not a CDN.

    asyncio.run(check())


@pytest.mark.parametrize("seeded", [False, True])
def test_reads_match_cli_without_mutation(seeded, monkeypatch):
    if seeded:
        demo.seed()
        dashboard.snapshot()
        monkeypatch.setenv("LEDGERLIGHT_FAKE_PRICES", "1")
        holdings.holdings_add("crypto", "BTC", "0.5")
        holdings.manual_add("student_loan", "Synthetic Loan", "900", apr="4")
    loan = holdings.manual_add(
        "personal_loan", "Synthetic Match", "50", payment_match="Synthetic"
    )["id"]
    chart = charts.add("Synthetic", "SELECT 'a' AS category, 2 AS amount", "bar")
    cases = [
        ("accounts", {}, ["accounts", "list"]),
        ("accounts_overview", {}, ["accounts", "overview"]),
        (
            "transactions",
            {"search": "Coffee", "limit": 3},
            ["transactions", "list", "--search", "Coffee", "--limit", "3"],
        ),
        (
            "transactions",
            {
                "since": "2026-01-01",
                "until": "2026-03-31",
                "category": "Food",
                "tag": "test",
                "account": "demo-checking",
            },
            [
                "transactions",
                "list",
                "--since",
                "2026-01-01",
                "--until",
                "2026-03-31",
                "--category",
                "Food",
                "--tag",
                "test",
                "--account",
                "demo-checking",
            ],
        ),
        (
            "recurring",
            {"direction": "out"},
            ["recurring", "list", "--direction", "out"],
        ),
        ("bills_upcoming", {}, ["bills", "upcoming"]),
        (
            "budgets_report",
            {"month": "2026-03"},
            ["budgets", "report", "--month", "2026-03"],
        ),
        ("spending_summary", {}, ["spending", "summary"]),
        ("spending_ask", {"text": "coffee"}, ["spending", "ask", "coffee"]),
        ("cashflow", {}, ["cashflow"]),
        ("networth", {}, ["networth"]),
        ("goals", {}, ["goals", "list"]),
        ("alerts", {"all": True}, ["alerts", "list", "--all"]),
        ("rules", {}, ["rules", "list"]),
        ("manual_list", {}, ["manual", "list"]),
        ("manual_payments", {"id": loan}, ["manual", "payments", loan]),
        ("holdings_list", {}, ["holdings", "list"]),
        ("chart_list", {}, ["chart", "list"]),
        ("chart_show", {"id": chart["id"]}, ["chart", "show", str(chart["id"])]),
        (
            "chart_preview",
            {"title": "Preview", "sql": chart["sql"], "type": "line"},
            [
                "chart",
                "preview",
                "--title",
                "Preview",
                "--sql",
                chart["sql"],
                "--type",
                "line",
            ],
        ),
    ]
    before = ledger_state()

    async def check():
        async with Client(create_server(8765)) as client:
            for _ in range(2):
                for name, args, argv in cases:
                    expected = CliRunner().invoke(cli, ["--json", *argv])
                    assert expected.exit_code == 0, expected.output
                    actual = result_json(await client.call_tool(name, args))
                    if name in ("chart_preview", "chart_show"):
                        assert actual.pop("dashboard_url") == "http://127.0.0.1:8765/#/"
                    assert actual == json.loads(expected.output)
                snapshot = result_json(await client.call_tool("dashboard_list"))
                assert snapshot == dashboard.snapshot(seed=False)
            assert ledger_state() == before

    asyncio.run(check())
    # CLI list intentionally journals; the MCP read returns its resulting snapshot.
    expected = CliRunner().invoke(cli, ["--json", "dashboard", "list"])

    async def compare():
        async with Client(create_server()) as client:
            assert result_json(await client.call_tool("dashboard_list")) == json.loads(
                expected.output
            )

    asyncio.run(compare())


def test_ui_events_and_direct_chart_save():
    async def check():
        async with Client(create_server()) as client:
            saved = result_json(
                await client.call_tool(
                    "chart_save",
                    {
                        "title": "Synthetic",
                        "sql": "SELECT 'a' AS category, 2 AS amount",
                        "type": "bar",
                    },
                )
            )
            assert charts.show(saved["id"]) == saved
            added = result_json(
                await client.call_tool(
                    "dashboard_add",
                    {
                        "kind": "chart",
                        "props": {"chart_id": saved["id"]},
                    },
                )
            )
            id = added["id"]
            cases = [
                ("dashboard_move", {"id": id, "x": 0, "y": 0}),
                ("dashboard_resize", {"id": id, "w": 4, "h": 6}),
                ("dashboard_remove", {"id": id}),
                ("dashboard_undo", {}),
                ("dashboard_reset_default", {}),
                ("ui_navigate", {"page": "transactions"}),
                (
                    "ui_filter",
                    {"page": "transactions", "filters": {"search": "Coffee"}},
                ),
                ("ui_highlight", {"target": "card:cashflow"}),
            ]
            for name, args in cases:
                result = result_json(await client.call_tool(name, args))
                event = result.get("event", result)
                assert event["actor"] == "mcp"
                assert event["type"] == name.replace("_", ".", 1)
                assert dashboard.events(event["seq"] - 1)[0] == event
            assert all(e["actor"] == "mcp" for e in dashboard.events())
            with connect() as db:
                assert {
                    r[0]
                    for r in db.execute(
                        "SELECT COALESCE(source_actor,actor) FROM dashboard_versions "
                        "WHERE action!='seed'"
                    )
                } == {"mcp"}

    asyncio.run(check())


def test_every_proposal_changes_no_financial_data_and_web_resolves(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-15")
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PRICES", "1")
    demo.seed()
    manual = holdings.manual_add("cash", "Synthetic Wallet", "40")["id"]
    held = holdings.holdings_add("stock", "AAPL", "2")["id"]
    txn = data.transactions(limit=1)[0]
    account = data.accounts()[0]["id"]
    stream = data.recurring()[0]["id"]
    rule = money.rules_add("merchant", "contains", "Synthetic", "Food")
    money.budgets_set("Food", "100")
    goal = money.goals_add("Synthetic", "500", [account])
    money.alerts_refresh()
    with connect() as db:
        alert = db.execute(
            "INSERT INTO alerts(kind,key,title,detail) VALUES(?,?,?,?)",
            ("bill", "mcp-test", "Synthetic", "Synthetic"),
        ).lastrowid
    cases = [
        (
            "propose_rules_add",
            {
                "match_field": "merchant",
                "match_type": "contains",
                "pattern": "Synthetic",
                "category": "Food",
            },
        ),
        ("propose_rules_remove", {"id": rule["id"]}),
        ("propose_rules_apply", {}),
        ("propose_txn_note", {"id": txn["id"], "text": "Synthetic note"}),
        ("propose_txn_hide", {"id": txn["id"]}),
        ("propose_txn_unhide", {"id": txn["id"]}),
        ("propose_txn_tag", {"id": txn["id"], "tags": ["test"]}),
        ("propose_txn_untag", {"id": txn["id"], "tag": "test"}),
        ("propose_txn_split", {"id": txn["id"], "parts": [f"Food={txn['amount']}"]}),
        ("propose_txn_unsplit", {"id": txn["id"]}),
        ("propose_budgets_set", {"category": "MCP test", "monthly_limit": "250"}),
        ("propose_budgets_remove", {"category": "Food"}),
        ("propose_recurring_mark", {"id": stream, "status": "ignored"}),
        ("propose_alerts_refresh", {}),
        ("propose_alerts_dismiss", {"id": alert}),
        ("propose_settings_set", {"key": "bill_days", "value": "5"}),
        (
            "propose_goals_add",
            {"name": "New", "target_amount": "500", "account_ids": [account]},
        ),
        ("propose_goals_update", {"id": goal["id"], "name": "Updated"}),
        ("propose_goals_archive", {"id": goal["id"]}),
        (
            "propose_manual_add",
            {
                "kind": "student_loan",
                "name": "Synthetic Loan",
                "balance": "1000",
                "apr": "5",
                "monthly_payment": "100",
                "payment_day": 3,
                "auto_paydown": True,
            },
        ),
        ("propose_manual_update", {"id": manual, "balance": "55"}),
        ("propose_manual_remove", {"id": manual}),
        ("propose_manual_apply_paydown", {}),
        ("propose_manual_apply_payments", {}),
        ("propose_holdings_add", {"kind": "crypto", "symbol": "BTC", "quantity": "1"}),
        ("propose_holdings_update", {"id": held, "quantity": "3"}),
        ("propose_holdings_remove", {"id": held}),
        ("propose_holdings_refresh", {}),
    ]
    assert {name for name, _ in cases} == PROPOSE
    before = ledger_state()
    results = {}

    async def check():
        async with Client(create_server(8765)) as client:
            for name, args in cases:
                result = result_json(await client.call_tool(name, args))
                results[name] = result
                assert result["diff"]["applied"] is False
                assert (
                    result["url"]
                    == f"http://127.0.0.1:8765/#/proposals/{result['proposal_id']}"
                )
                assert "Confirm" in result["instruction"]
                assert (
                    proposals.get(result["proposal_id"])["summary"] == result["summary"]
                )
                assert ledger_state() == before

    asyncio.run(check())
    web = TestClient(app)
    assert len(web.get("/api/proposals").json()) == len(cases)
    budget = results["propose_budgets_set"]["proposal_id"]
    assert web.get(f"/api/proposals/{budget}").json()["applied_at"] is None
    assert web.post(f"/api/proposals/{budget}/apply").status_code == 200
    assert money.budgets_list()[-1]["monthly_limit"] == 250
    assert web.post(f"/api/proposals/{budget}/apply").status_code == 400
    note = results["propose_txn_note"]["proposal_id"]
    assert web.post(f"/api/proposals/{note}/cancel").status_code == 200
    assert web.post(f"/api/proposals/{note}/apply").status_code == 400
    assert len(web.get("/api/proposals").json()) == len(cases) - 2
    added = results["propose_holdings_add"]["proposal_id"]
    assert web.post(f"/api/proposals/{added}/apply").json()["coin_id"] == "bitcoin"
    assert len(holdings.holdings_list()) == 2


def test_boundaries_and_redaction(monkeypatch, caplog):
    demo.seed()
    secret = "synthetic-mcp-configured-secret"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    with connect() as db:
        db.execute("UPDATE accounts SET name=?", (secret,))
    before = ledger_state()

    async def check():
        async with Client(create_server()) as client:
            result = await client.call_tool("accounts")
            assert secret not in str(result)
            assert "[redacted]" in str(result)
            for name, args in [
                ("propose_budgets_set", {"category": secret, "monthly_limit": "25"}),
                ("chart_save", {"title": secret, "sql": "SELECT 1,2", "type": "bar"}),
                ("transactions", {"limit": [secret]}),
                ("ui_filter", {"page": "transactions", "filters": {"search": secret}}),
                ("propose_settings_set", {"key": "llm_provider", "value": "openai"}),
                (
                    "propose_budgets_set",
                    {"category": "Food", "monthly_limit": "20", "apply": True},
                ),
                ("dashboard_move", {"id": "cashflow", "x": 0, "y": 0, "actor": "user"}),
                (
                    "chart_preview",
                    {"title": "Bad", "sql": "DELETE FROM accounts", "type": "bar"},
                ),
                (
                    "chart_preview",
                    {
                        "title": "Bad",
                        "sql": "SELECT access_token_enc,cursor FROM plaid_items",
                        "type": "bar",
                    },
                ),
                ("run_ledgerlight", {"args": ["sync"]}),
                ("apply_proposal", {"id": "anything"}),
                ("proposals_apply", {"id": "anything"}),
            ]:
                result = await client.call_tool(name, args, raise_on_error=False)
                assert result.is_error, name
                assert secret not in str(result)
            assert not proposals.pending()
            assert ledger_state() == before

    asyncio.run(check())
    assert secret not in caplog.text


def test_legacy_actor_upgrade_is_additive_and_preserves_history():
    path = db_path()
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE ui_events (
                seq INTEGER PRIMARY KEY, type TEXT NOT NULL, payload JSON NOT NULL,
                actor TEXT NOT NULL CHECK(actor IN ('user','agent','cli')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE dashboard_versions (
                version INTEGER PRIMARY KEY, layout JSON NOT NULL,
                actor TEXT NOT NULL CHECK(actor IN ('user','agent','cli')),
                action TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO ui_events VALUES
                (7,'ui.navigate','{"page":"home"}','agent','2026-03-01');
            INSERT INTO dashboard_versions VALUES
                (5,'[]','cli','remove','2026-03-01');
        """)
    for _ in range(2):
        with connect() as db:
            assert tuple(db.execute("SELECT * FROM ui_events").fetchone()) == (
                7,
                "ui.navigate",
                '{"page":"home"}',
                "agent",
                "2026-03-01",
                None,
            )
            assert tuple(db.execute("SELECT * FROM dashboard_versions").fetchone()) == (
                5,
                "[]",
                "cli",
                "remove",
                "2026-03-01",
                None,
            )

    async def check():
        async with Client(create_server()) as client:
            event = result_json(await client.call_tool("ui_navigate", {"page": "home"}))
            assert event["seq"] == 8 and event["actor"] == "mcp"
            changed = result_json(
                await client.call_tool("dashboard_add", {"kind": "cashflow"})
            )
            assert changed["version"] == 6 and changed["event"]["actor"] == "mcp"

    asyncio.run(check())
    assert dashboard.events()[0]["actor"] == "agent"
    assert dashboard.events()[1]["actor"] == "mcp"
    with connect() as db:
        assert tuple(
            db.execute(
                "SELECT actor,source_actor FROM dashboard_versions WHERE version=6"
            ).fetchone()
        ) == ("cli", "mcp")
        assert (
            db.execute(
                "SELECT layout FROM dashboard_versions WHERE version=5"
            ).fetchone()[0]
            == "[]"
        )


@pytest.mark.parametrize("json_flag", [False, True])
def test_stdio_stdout_is_protocol_only(json_flag):
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ledgerlight.cli",
            *(["--json"] if json_flag else []),
            "mcp",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )

    def send(value):
        process.stdin.write(json.dumps(value) + "\n")
        process.stdin.flush()

    def receive():
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=30), "Timed out waiting for stdio protocol"
        line = process.stdout.readline()
        result = json.loads(line)
        assert result["jsonrpc"] == "2.0"
        return result

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "ledgerlight-test", "version": "1"},
                },
            }
        )
        assert receive()["id"] == 1
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        response = receive()
        assert response["id"] == 2
        assert {
            t["name"] for t in response["result"]["tools"]
        } == READS | UI | PROPOSE | {"chart_save"}
        process.stdin.close()
        process.stdin = None
        stdout, _ = process.communicate(timeout=30)
        assert stdout == ""
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
