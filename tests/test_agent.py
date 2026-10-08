"""Offline stage 4 contracts and security boundaries; all credentials synthetic."""

import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from types import SimpleNamespace

import httpx
import pytest
from ag_ui.core import RunAgentInput
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import (
    agent,
    agent_tools,
    charts,
    holdings,
    llm_client,
    money,
    proposals,
    voice,
)
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.config import db_path
from ledgerlight.db import connect

client = TestClient(app)


def invoke(*args):
    result = CliRunner().invoke(cli, ["--json", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.mark.parametrize(
    "args",
    [
        ["serve"],
        ["plaid", "exchange", "public-synthetic"],
        ["plaid", "sandbox-link"],
        ["plaid", "link-token"],
        ["mcp"],
        ["sync"],
        ["snapshot"],
        ["demo", "seed"],
        ["budgets", "set", "Dining", "400"],
        ["chart", "remove", "1"],
        ["settings", "set", "llm_provider", "openai", "--propose"],
        ["settings", "set", "OPENAI_API_KEY", "synthetic", "--propose"],
        ["txn", "note", "t", "--", "--propose"],
        ["dashboard", "list"],
        ["dashboard", "move", "cashflow", "--x", "0", "--y", "0"],
    ],
)
def test_agent_allowlist_denies(args):
    assert "error" in agent_tools.run_ledgerlight(args)


def application_dump():
    # Use raw SQLite so the assertion itself cannot run migrations/backfills.
    with closing(sqlite3.connect(db_path())) as db:
        return list(db.iterdump())


@pytest.mark.parametrize("path", sorted(agent_tools.READS))
@pytest.mark.parametrize("seeded", [False, True])
def test_every_allowlisted_read_leaves_application_tables_unchanged(path, seeded):
    if seeded:
        invoke("demo", "seed")
        invoke("dashboard", "list")
    chart = charts.add("Synthetic", "SELECT 'Dining' AS category, 42 AS amount", "bar")
    loan = holdings.manual_add(
        "personal_loan", "Synthetic Loan", "10", payment_match="synthetic"
    )["id"]
    extra = {
        ("manual", "payments"): [loan],
        ("spending", "ask"): ["coffee"],
        ("chart", "show"): [str(chart["id"])],
        ("chart", "history"): [str(chart["id"])],
        ("chart", "preview"): [
            "--title", "Preview", "--sql", chart["sql"], "--type", "bar",
        ],
    }
    before = application_dump()
    for _ in range(2):
        result = agent_tools.run_ledgerlight([*path, *extra.get(path, [])])
        assert not isinstance(result, dict) or "error" not in result, result
        assert application_dump() == before


def test_legacy_chart_history_migrates_once_before_reads():
    path = db_path()
    path.parent.mkdir(parents=True)
    sql = "SELECT 'Dining' AS category, 42 AS amount"
    spec = json.dumps(charts.build_spec("bar", ["category", "amount"]))
    original = (1, "Legacy synthetic", sql, spec, 4, "2026-01-01", "2026-03-01")
    # A pre-stage-4 database has charts but no chart_versions table.
    with closing(sqlite3.connect(path)) as db, db:
        db.execute(
            "CREATE TABLE charts (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
            "sql TEXT NOT NULL, spec_json TEXT NOT NULL, version INTEGER NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        db.execute("INSERT INTO charts VALUES (?,?,?,?,?,?,?)", original)
    with connect() as db:
        assert tuple(db.execute("SELECT * FROM charts").fetchone()) == original
        assert tuple(db.execute("SELECT * FROM chart_versions").fetchone()) == (
            1, 4, "Legacy synthetic", sql, spec, "2026-03-01",
        )
    before = application_dump()
    for _ in range(2):
        with connect() as db:
            assert db.total_changes == 0
        result = agent_tools.run_ledgerlight(["chart", "history", "1"])
        assert [row["version"] for row in result] == [4]
        assert application_dump() == before
    charts.add("Edited synthetic", sql, "line", chart_id=1)
    history = charts.history(1)
    assert [row["version"] for row in history] == [4, 5]
    assert history[0]["title"] == "Legacy synthetic"
    assert history[0]["spec_json"] == spec
    assert history[0]["created_at"] == "2026-03-01"
    with pytest.raises(ValueError, match="not found"):
        charts.history(999)


def test_literal_metacharacters():
    value = "Dining; $(touch /never-created) | & >"
    result = agent_tools.run_ledgerlight(["budgets", "set", value, "400", "--propose"])
    assert result["diff"]["category"] == value
    assert money.budgets_list() == []
    assert agent_tools.run_ledgerlight(["version"]) == {"version": "0.1.0"}


@pytest.mark.parametrize(
    "script,expected",
    [
        ("import time; time.sleep(3)", "timed out"),
        ("import sys; sys.stdout.write('x'*70000); sys.stdout.flush()", "64 KiB"),
    ],
)
def test_cli_resource_caps(monkeypatch, script, expected):
    real = subprocess.Popen
    observed = []

    def process(argv, **kwargs):
        assert argv[:4] == [sys.executable, "-m", "ledgerlight.cli", "--json"]
        assert kwargs["shell"] is False
        p = real([sys.executable, "-c", script], **kwargs)
        observed.append(p)
        return p

    monkeypatch.setattr(agent_tools.subprocess, "Popen", process)
    monkeypatch.setattr(agent_tools, "TIMEOUT", 0.2)
    assert expected in agent_tools.run_ledgerlight(["version"])["error"]
    assert observed[0].poll() is not None


def test_proposal_apply_cancel_and_concurrency():
    p = invoke("budgets", "set", "Dining", "400", "--propose")
    assert set(p) == {"proposal_id", "summary", "diff"}
    assert money.budgets_list() == []
    assert client.get(f"/api/proposals/{p['proposal_id']}").json()["diff"] == p["diff"]
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(
                lambda _: (
                    client.post(f"/api/proposals/{p['proposal_id']}/apply").status_code
                ),
                range(2),
            )
        )
    assert sorted(results) == [200, 400]
    assert money.budgets_list()[0]["monthly_limit"] == 400
    p = invoke("budgets", "set", "Dining", "999", "--propose")
    assert client.post(f"/api/proposals/{p['proposal_id']}/cancel").status_code == 200
    assert client.post(f"/api/proposals/{p['proposal_id']}/apply").status_code == 400
    assert money.budgets_list()[0]["monthly_limit"] == 400


def test_proposal_revalidates_and_rolls_back():
    with connect() as db:
        db.execute("INSERT INTO accounts(id,name) VALUES ('a','Synthetic')")
        db.execute(
            "INSERT INTO transactions(id,account_id,date,name,amount,category) "
            "VALUES ('t','a','2026-03-01','Synthetic',-10,'Dining')"
        )
    p = invoke("txn", "split", "t", "--part", "Dining=-10", "--propose")
    with connect() as db:
        db.execute("UPDATE transactions SET amount=-20 WHERE id='t'")
    assert client.post(f"/api/proposals/{p['proposal_id']}/apply").status_code == 400
    with connect() as db:
        assert not db.execute("SELECT * FROM transaction_splits").fetchall()
        assert db.execute("SELECT applied_at FROM proposals").fetchone()[0] is None


def test_every_money_mutation_has_propose():
    for path in agent_tools.WRITES:
        command = cli.commands[path[0]].commands[path[1]]
        assert any(p.name == "propose" for p in command.params), path


def test_provider_precedence_and_status(monkeypatch):
    assert llm_client.status()["provider"] == "local"
    money.settings_set("llm_provider", "claude")
    assert llm_client.status()["model"] == "claude-sonnet-5-5"
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-private-key")
    result = client.get("/api/llm/status")
    assert result.json()["model"] == "gpt-5.5"
    assert result.json()["key_present"] is True
    assert "synthetic-private-key" not in result.text
    assert (
        client.post("/api/llm/provider", json={"provider": "local"}).json()["provider"]
        == "openai"
    )
    monkeypatch.delenv("LEDGERLIGHT_LLM_PROVIDER")
    assert llm_client.status()["provider"] == "local"
    assert (
        client.post("/api/llm/provider", json={"provider": "fake"}).status_code == 400
    )


def run_input(text="open budgets"):
    return {
        "threadId": "thread",
        "runId": "run",
        "state": {},
        "messages": [{"id": "u", "role": "user", "content": text}],
        "tools": [
            {"name": name, "description": name, "parameters": {"type": "object"}}
            for name in ("ui_navigate", "show_chart", "propose_change")
        ],
        "context": [],
    }


def sse(body):
    response = client.post("/api/agent", json=body)
    assert response.status_code == 200
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_agui_order_and_backend_results(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", "fake")
    events = sse(run_input())
    assert [e["type"] for e in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "RUN_FINISHED",
    ]
    assert events[4]["toolCallName"] == "ui_navigate"
    events = sse(run_input("set dining budget to 400"))
    assert [e["toolCallName"] for e in events if e["type"] == "TOOL_CALL_START"] == [
        "run_ledgerlight",
        "propose_change",
    ]
    assert any(e["type"] == "TOOL_CALL_RESULT" for e in events)
    assert events[-1]["type"] == "RUN_FINISHED"
    assert not money.budgets_list()


def test_keys_absent_from_split_stream_and_failure(monkeypatch):
    secret = "synthetic-private-key"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    def stream(*args):
        yield "text", "prefix " + secret[:8]
        yield "text", secret[8:] + " suffix"

    monkeypatch.setattr(llm_client, "stream", stream)
    events = sse(run_input())
    assert secret not in json.dumps(events)
    text = "".join(e.get("delta", "") for e in events)
    assert text == "prefix [redacted] suffix"

    def failure(*args):
        raise ValueError(secret)

    monkeypatch.setattr(llm_client, "stream", failure)
    events = sse(run_input())
    assert secret not in json.dumps(events)
    assert events[-1]["type"] == "RUN_ERROR"


@pytest.mark.parametrize("name", ["run_ledgerlight", "ui_navigate"])
@pytest.mark.parametrize("embedded", [False, True])
def test_provider_tool_call_ids_redacted_in_sse_and_continuations(
    monkeypatch, name, embedded
):
    secret = "synthetic-private-call-id-key"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    call_id = f"call-{secret}-suffix" if embedded else secret
    safe_id = call_id.replace(secret, "[redacted]")
    arguments = (
        {"args": ["version"]} if name == "run_ledgerlight" else {"page": "budgets"}
    )
    observed = []

    def stream(messages, *args):
        observed.append(json.loads(json.dumps(messages)))
        if len(observed) == 1:
            yield "call", {"id": call_id, "name": name, "arguments": arguments}
        else:
            yield "text", "Done."

    monkeypatch.setattr(llm_client, "stream", stream)
    monkeypatch.setattr(agent, "run_ledgerlight", lambda args: {"version": "test"})
    body = run_input()
    response = client.post("/api/agent", json=body)
    assert response.status_code == 200
    assert secret not in response.text
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1]["type"] == "RUN_FINISHED"
    tool_events = [e for e in events if e["type"].startswith("TOOL_CALL_")]
    assert [e["type"] for e in tool_events] == [
        "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END",
        *(["TOOL_CALL_RESULT"] if name == "run_ledgerlight" else []),
    ]
    assert all(e["toolCallId"] == safe_id for e in tool_events)

    if name == "ui_navigate":
        # Mirror HttpAgent's browser execution and subsequent continuation run.
        body["messages"].extend([
            {
                "id": "assistant", "role": "assistant", "toolCalls": [{
                    "id": tool_events[0]["toolCallId"], "type": "function",
                    "function": {"name": name, "arguments": tool_events[1]["delta"]},
                }],
            },
            {
                "id": "result", "role": "tool",
                "toolCallId": tool_events[-1]["toolCallId"], "content": '{"ok":true}',
            },
        ])
        continuation = client.post("/api/agent", json=body)
        assert continuation.status_code == 200
        assert secret not in continuation.text
        assert '"RUN_FINISHED"' in continuation.text

    assert len(observed) == 2
    assert secret not in json.dumps(observed)
    assert observed[1][-2]["tool_calls"][0]["id"] == safe_id
    assert observed[1][-1]["tool_call_id"] == safe_id


@pytest.mark.parametrize(
    "key", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PLAID_SECRET", "PLAID_CLIENT_ID"]
)
@pytest.mark.parametrize("secret", ["synthetic-tool-secret", 'synthetic-"\\-秘密'])
def test_secret_tool_arguments_refused_before_execution(monkeypatch, key, secret):
    monkeypatch.setenv(key, secret)
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", "fake")
    observed, executed = [], []
    original = agent.run_ledgerlight

    def execute(args):
        executed.append(args)
        return original(args)

    def provider(messages, state):
        observed.append(json.loads(json.dumps(messages)))
        if len(observed) == 1:
            return "Proposing a budget.", [llm_client.call(
                "run_ledgerlight",
                {"args": ["budgets", "set", f"Dining-{secret}-suffix", "400",
                          "--propose"]},
            )]
        assert "error" in json.loads(messages[-1]["content"])
        return "The tool refused the proposal.", []

    monkeypatch.setattr(agent, "run_ledgerlight", execute)
    monkeypatch.setattr(llm_client, "fake", provider)
    with connect():
        pass
    before = application_dump()
    response = client.post("/api/agent", json=run_input("set a budget"))
    assert response.status_code == 200
    assert secret not in response.text
    events = [json.loads(line[6:]) for line in response.text.splitlines()
              if line.startswith("data: ")]
    assert events[-1]["type"] == "RUN_FINISHED"
    results = [e for e in events if e["type"] == "TOOL_CALL_RESULT"]
    assert len(results) == 1
    assert "configured secret" in json.loads(results[0]["content"])["error"]
    assert "[redacted]" in next(
        e["delta"] for e in events if e["type"] == "TOOL_CALL_ARGS"
    )
    assert len(observed) == 2
    assert secret not in json.dumps(observed, ensure_ascii=False)
    assert executed == []
    assert application_dump() == before
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 0
    for method, suffix in [("get", ""), ("post", "/apply"), ("post", "/cancel")]:
        response = getattr(client, method)(f"/api/proposals/missing{suffix}")
        assert response.status_code == 400
        assert secret not in response.text


@pytest.mark.parametrize(
    "key", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PLAID_SECRET", "PLAID_CLIENT_ID"]
)
@pytest.mark.parametrize("secret", ["synthetic-stored-secret", 'synthetic-"\\-秘密'])
@pytest.mark.parametrize("location", ["arguments", "diff"])
def test_stored_secret_proposal_redacted_and_cannot_apply(
    monkeypatch, key, secret, location
):
    monkeypatch.setenv(key, secret)
    category = f"Dining-{secret}-suffix"
    command = {
        "function": "budgets_set",
        "arguments": {"category": category if location == "arguments" else "Dining",
                      "monthly_limit": 400},
        "diff": {"category": category, "nested": [{secret: secret}]},
    }
    with connect() as db:
        db.execute(
            "INSERT INTO proposals(id,command,summary) VALUES(?,?,?)",
            ("unsafe", json.dumps(command), f"Set budget: {secret}"),
        )
    before = application_dump()
    expected_diff = {
        "category": "Dining-[redacted]-suffix",
        "nested": [{"[redacted]": "[redacted]"}],
    }
    proposal = proposals.get("unsafe")
    assert proposal["summary"] == "Set budget: [redacted]"
    assert proposal["diff"] == expected_diff
    response = client.get("/api/proposals/unsafe")
    assert response.status_code == 200
    assert response.json() == proposal
    assert secret not in response.text
    response = client.post("/api/proposals/unsafe/apply")
    assert response.status_code == 400
    assert "configured secret" in response.json()["error"]
    assert secret not in response.text
    assert money.budgets_list() == []
    assert application_dump() == before
    response = client.post("/api/proposals/unsafe/cancel")
    assert response.status_code == 200
    assert secret not in response.text
    response = client.get("/api/proposals/unsafe")
    assert response.status_code == 200
    assert response.json()["cancelled_at"] is not None
    assert response.json()["diff"] == expected_diff
    assert secret not in response.text


def test_max_eight_tools_across_frontend_runs(monkeypatch):
    calls = []

    def looping(*args):
        calls.append(1)
        yield "call", llm_client.call("run_ledgerlight", {"args": ["version"]})

    monkeypatch.setattr(llm_client, "stream", looping)
    monkeypatch.setattr(agent, "run_ledgerlight", lambda args: {"version": "test"})
    events = sse(run_input())
    assert len(calls) == 8
    assert len([e for e in events if e["type"] == "TOOL_CALL_START"]) == 8
    assert events[-1]["type"] == "RUN_ERROR"
    body = run_input()
    body["messages"].append(
        {
            "role": "assistant",
            "id": "a",
            "toolCalls": [
                {
                    "id": str(i),
                    "type": "function",
                    "function": {"name": "ui_navigate", "arguments": "{}"},
                }
                for i in range(8)
            ],
        }
    )
    assert list(agent.events(RunAgentInput(**body)))[-1].type == "RUN_ERROR"
    assert len(calls) == 8


@pytest.mark.parametrize("provider", ["local", "openai", "claude"])
def test_httpx_provider_stream_adapters(monkeypatch, provider):
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", provider)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-anthropic")
    requests = []

    def respond(request):
        requests.append(request)
        if provider == "claude":
            events = [
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "Hello"},
                },
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {
                        "type": "tool_use",
                        "id": "t",
                        "name": "ui_navigate",
                    },
                },
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": '{"page":"budgets"}',
                    },
                },
            ]
        else:
            events = [
                {"choices": [{"delta": {"content": "Hello"}}]},
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "t",
                                        "function": {
                                            "name": "ui_navigate",
                                            "arguments": '{"page":',
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                },
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": '"budgets"}'},
                                    }
                                ]
                            }
                        }
                    ]
                },
            ]
        return httpx.Response(
            200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events)
        )

    real = httpx.Client
    monkeypatch.setattr(
        llm_client.httpx,
        "Client",
        lambda **kw: real(transport=httpx.MockTransport(respond)),
    )
    events = list(
        llm_client.stream(
            [{"role": "user", "content": "hello"}], [agent.BACKEND], "system"
        )
    )
    assert events[0] == ("text", "Hello")
    assert events[1][1]["arguments"] == {"page": "budgets"}
    payload = json.loads(requests[0].content)
    assert payload["stream"] is True
    assert "synthetic-openai" not in requests[0].content.decode()
    assert "synthetic-anthropic" not in requests[0].content.decode()
    assert (
        requests[0].url.host
        == {
            "local": "127.0.0.1",
            "claude": "api.anthropic.com",
            "openai": "api.openai.com",
        }[provider]
    )


def test_chart_preview_save_edit_history_html():
    args = [
        "--title",
        "Synthetic",
        "--sql",
        "SELECT 'Dining' AS category, 42 AS amount",
        "--type",
        "bar",
    ]
    preview = invoke("chart", "preview", *args)
    assert preview["rows"][0]["amount"] == 42
    assert charts.list_charts() == []
    saved = invoke("chart", "save", *args)
    edited = invoke("chart", "edit", str(saved["id"]), *args)
    assert edited["version"] == 2
    assert [h["version"] for h in invoke("chart", "history", str(saved["id"]))] == [
        1,
        2,
    ]
    html = '<script>fetch("https://example.invalid")</script>'
    p = charts.preview("HTML", "SELECT 1 AS x", "html", html)
    assert p["srcdoc"].startswith('<meta http-equiv="Content-Security-Policy"')
    assert p["srcdoc"].index("default-src 'none'") < p["srcdoc"].index(html)
    assert "allow-same-origin" not in p["srcdoc"]
    assert (
        client.post(
            "/api/charts/save",
            json={
                "title": "HTML",
                "sql": "SELECT 1 AS x",
                "type": "html",
                "html": html,
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/charts/preview",
            json={"title": "bad", "sql": "DELETE FROM budgets", "type": "bar"},
        ).status_code
        == 400
    )


def test_stt_status_extra_and_fake(monkeypatch):
    monkeypatch.setattr(voice.importlib.util, "find_spec", lambda name: None)
    assert client.get("/api/stt/status").json()["engine"] is None
    assert (
        client.post(
            "/api/stt", files={"audio": ("test.webm", b"synthetic")}
        ).status_code
        == 400
    )
    monkeypatch.setattr(voice.importlib.util, "find_spec", lambda name: object())
    assert voice.status()["engine"] == "faster-whisper"

    class Model:
        def __init__(self, model, **kwargs):
            assert (model, kwargs) == (
                "small.en",
                {"device": "cpu", "compute_type": "int8"},
            )

        def transcribe(self, audio):
            return [SimpleNamespace(text=" local transcript ")], None

    monkeypatch.setitem(
        sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model)
    )
    monkeypatch.setattr(voice, "_model", None)
    assert voice.transcribe(b"synthetic", "faster-whisper") == "local transcript"
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", "openai")
    assert voice.status()["engine"] is None
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    assert voice.status()["engine"] == "openai"
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", "fake")
    assert client.post(
        "/api/stt", files={"audio": ("test.webm", b"synthetic")}
    ).json() == {"text": "Show spending by category"}
    assert (
        client.post("/api/stt", files={"wrong": ("test", b"synthetic")}).status_code
        == 400
    )
    monkeypatch.setattr(voice, "MAX_AUDIO", 4)
    assert (
        client.post("/api/stt", files={"audio": ("test", b"synthetic")}).status_code
        == 400
    )


@pytest.mark.parametrize(
    "args",
    [
        [
            "rules",
            "add",
            "--match-field",
            "merchant",
            "--match-type",
            "contains",
            "--pattern",
            "Shop",
            "--category",
            "Dining",
        ],
        ["rules", "remove", "1"],
        ["rules", "apply"],
        ["budgets", "set", "Dining", "400"],
        ["budgets", "remove", "Dining"],
        ["txn", "note", "t", "Synthetic note"],
        ["txn", "hide", "t"],
        ["txn", "unhide", "t"],
        ["txn", "tag", "t", "new"],
        ["txn", "untag", "t", "old"],
        ["txn", "split", "t", "--part", "Dining=-10"],
        ["txn", "unsplit", "t"],
        ["recurring", "mark", "r", "--status", "ignored"],
        ["alerts", "dismiss", "1"],
        ["alerts", "refresh"],
        ["settings", "set", "bill_days", "4"],
        ["goals", "add", "--name", "New", "--target-amount", "40", "--account", "a"],
        ["goals", "update", "1", "--target-amount", "60"],
        ["goals", "archive", "1"],
    ],
)
def test_all_proposals_do_not_write_then_apply_same_function(args):
    with connect() as db:
        db.execute("INSERT INTO accounts(id,name) VALUES ('a','Synthetic')")
        db.execute(
            "INSERT INTO transactions "
            "(id,account_id,date,name,merchant,amount,category) "
            "VALUES ('t','a','2026-03-01','Synthetic','Shop',-10,'Dining')"
        )
        db.execute(
            "INSERT INTO recurring_streams(id,account_id,direction,description) "
            "VALUES ('r','a','out','Synthetic')"
        )
        db.execute(
            "INSERT INTO alerts(kind,key,title,detail) "
            "VALUES ('bill','synthetic','Synthetic','Synthetic')"
        )
    money.rules_add("merchant", "exact", "Other", "Other")
    money.budgets_set("Dining", "100")
    money.goals_add("Existing", "40", ["a"])
    money.txn_change("t", "tag", tags=["old"])
    money.txn_change("t", "split", parts=["Dining=-10"])

    def financial_dump():
        with connect() as db:
            return [line for line in db.iterdump() if '"proposals"' not in line]

    before = financial_dump()
    value = invoke(*args, "--propose")
    assert value["diff"]["applied"] is False
    assert before == financial_dump()
    result = proposals.apply(value["proposal_id"])
    assert result["applied"] is True
    assert proposals.get(value["proposal_id"])["applied_at"]


def test_provider_errors_and_remote_transcription_sanitized(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret-value")
    real = httpx.Client

    def response(request):
        assert request.headers["Authorization"] == "Bearer synthetic-secret-value"
        return httpx.Response(403, text="synthetic-secret-value")

    monkeypatch.setattr(
        llm_client.httpx,
        "Client",
        lambda **kw: real(transport=httpx.MockTransport(response)),
    )
    with pytest.raises(ValueError) as caught:
        list(llm_client.stream([{"role": "user", "content": "hello"}], [], "system"))
    assert "synthetic-secret-value" not in str(caught.value)
    with pytest.raises(ValueError) as caught:
        llm_client.transcribe_openai(b"synthetic", "test.webm")
    assert "synthetic-secret-value" not in str(caught.value)


def test_chart_queries_cannot_read_token_material():
    with connect():
        pass
    for column in ("access_token_enc", "cursor"):
        with pytest.raises(ValueError):
            charts.validate_sql(f"SELECT {column}, id FROM plaid_items")
