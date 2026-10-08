import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import charts, dashboard, dashboard_api, demo
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.db import connect


def geometry(snapshot):
    return [
        {k: c[k] for k in ("id", "kind", "props", "x", "y", "w", "h")}
        for c in snapshot["cards"]
    ]


def test_seed_versions_undo_and_empty_layout():
    demo.seed()
    initial = dashboard.snapshot()
    assert initial["version"] == 1 and len(initial["cards"]) == 9
    assert dashboard.snapshot() == initial
    changed = dashboard.change("move", id="net_worth", x=0, y=0)
    assert changed["version"] == 2
    assert changed["cards"][0]["id"] == "net_worth"
    assert changed["event"]["type"] == "dashboard.move"
    assert changed["event"]["actor"] == "cli"
    assert geometry(dashboard.change("undo")) == geometry(initial)
    assert geometry(dashboard.change("undo")) == geometry(changed)
    for card in initial["cards"]:
        dashboard.change("remove", id=card["id"])
    assert (
        dashboard.snapshot()["cards"] == []
    )  # Never re-seed an intentionally empty layout.
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 124
        rows = db.execute(
            "SELECT * FROM dashboard_versions ORDER BY version"
        ).fetchall()
        assert [r["version"] for r in rows] == list(range(1, 14))
        assert rows[-1]["actor"] == "cli"
        assert len(dashboard.events()) == 12


def test_undo_restores_full_stored_cards_including_timestamps():
    initial = dashboard.snapshot()
    changed = dashboard.change("move", id="cashflow", x=0, y=0)
    with connect() as db:
        prior_cards = json.loads(
            db.execute(
                "SELECT layout FROM dashboard_versions WHERE version=?",
                (initial["version"],),
            ).fetchone()["layout"]
        )
    assert prior_cards == initial["cards"]
    restored = dashboard.change("undo")
    assert restored["cards"] == prior_cards
    assert restored["event"]["payload"]["cards"] == prior_cards
    assert dashboard.snapshot()["cards"] == prior_cards
    with connect() as db:
        assert json.loads(
            db.execute(
                "SELECT layout FROM dashboard_versions WHERE version=?",
                (restored["version"],),
            ).fetchone()["layout"]
        ) == prior_cards
    assert dashboard.change("undo")["cards"] == changed["cards"]


def test_list_journals_version_and_event_without_changing_geometry():
    initial = dashboard.snapshot()
    listed = dashboard.snapshot(emit_event=True)
    assert listed["version"] == initial["version"] + 1
    assert geometry(listed) == geometry(initial)
    event = dashboard.events()[0]
    assert event["type"] == "dashboard.list"
    assert event["payload"]["version"] == listed["version"]
    assert event["payload"]["cards"] == listed["cards"]
    assert dashboard.snapshot() == listed  # Browser GET does not journal reads.


def test_concurrent_changes_and_stale_undo():
    dashboard.snapshot()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: dashboard.change("add", kind="cashflow"), range(4))
        )
    assert sorted(r["version"] for r in results) == [2, 3, 4, 5]
    assert len(dashboard.snapshot()["cards"]) == 13
    before = dashboard.snapshot()
    with pytest.raises(ValueError, match="Layout changed"):
        dashboard.change("undo", expected_version=2)
    assert dashboard.snapshot() == before


def test_layout_atomicity_collision_and_actors():
    before = dashboard.snapshot()
    layout = [{k: c[k] for k in ("id", "x", "y", "w", "h")} for c in before["cards"]]
    layout[0]["y"] = 50
    changed = dashboard.change(
        "layout", actor="user", layout=layout, expected_version=1
    )
    assert changed["event"]["actor"] == "user"
    assert next(c for c in changed["cards"] if c["id"] == layout[0]["id"])["y"] == 50
    layout[1].update(x=layout[0]["x"], y=50)
    with pytest.raises(ValueError, match="overlap"):
        dashboard.change("layout", layout=layout)
    assert dashboard.snapshot()["version"] == 2
    with pytest.raises(ValueError):
        dashboard.change("layout", layout=layout[:-1])
    layout[1]["id"] = []
    with pytest.raises(ValueError):
        dashboard.change("layout", layout=layout)
    assert (
        dashboard.change("resize", id="cashflow", w=5, h=6, actor="agent")["event"][
            "actor"
        ]
        == "agent"
    )


@pytest.mark.parametrize("kind", dashboard.KINDS)
def test_all_card_kinds(kind):
    chart = charts.add("Synthetic chart", "SELECT 'Example' AS name, 1 AS value", "bar")
    props = {"chart_id": chart["id"]} if kind == "chart" else {}
    result = dashboard.change("add", kind=kind, props=props)
    assert result["kind"] == kind
    assert next(c for c in result["cards"] if c["id"] == result["id"])["props"] == props
    assert dashboard.events(result["seq"] - 1)[0] == result["event"]


@pytest.mark.parametrize(
    "action,args",
    [
        ("add", {"kind": "unknown"}),
        ("add", {"kind": "chart"}),
        ("add", {"kind": "chart", "props": {"chart_id": 999}}),
        ("add", {"kind": "chart", "props": {"chart_id": True}}),
        ("add", {"kind": "cashflow", "props": {"unsafe": "x"}}),
        ("add", {"kind": "cashflow", "props": []}),
        ("add", {"kind": "cashflow", "w": 13}),
        ("add", {"kind": "cashflow", "x": 8}),
        ("move", {"id": "cashflow", "x": -1, "y": 0}),
        ("move", {"id": "cashflow", "x": 0.5, "y": 0}),
        ("move", {"id": "cashflow", "x": True, "y": 0}),
        ("move", {"id": "cashflow", "x": 0}),
        ("resize", {"id": "cashflow", "w": 1, "h": 0}),
        ("remove", {"id": "missing"}),
        ("undo", {}),
        ("add", {"kind": "cashflow", "actor": "invalid"}),
        ("remove", {"id": "cashflow", "extra": 1}),
        ("undo", {"expected_version": True}),
    ],
)
def test_invalid_changes_write_nothing(action, args):
    before = dashboard.snapshot()
    with pytest.raises(ValueError):
        dashboard.change(action, **args)
    assert dashboard.snapshot() == before
    assert dashboard.events() == []


@pytest.mark.parametrize(
    "action,payload",
    [
        ("navigate", {"page": "transactions"}),
        (
            "filter",
            {"page": "transactions", "filters": {"search": "Synthetic", "limit": "2"}},
        ),
        ("filter", {"page": "recurring", "filters": {"direction": "out"}}),
        ("filter", {"page": "budgets", "filters": {"month": "2026-03"}}),
        ("filter", {"page": "bills", "filters": {"days": "14"}}),
        ("highlight", {"target": "card:cashflow"}),
        ("clear", {}),
    ],
)
def test_ui_event_shapes(action, payload):
    event = dashboard.ui(action, actor="agent", **payload)
    assert set(event) == {"seq", "type", "payload", "actor", "created_at"}
    assert event["payload"] == payload
    assert event["type"] == f"ui.{action}"
    assert dashboard.events(event["seq"]) == []
    assert dashboard.events(event["seq"] - 1) == [event]


@pytest.mark.parametrize(
    "action,payload",
    [
        ("navigate", {"page": "bad"}),
        ("highlight", {"target": "<script>"}),
        ("filter", {"page": "accounts", "filters": {}}),
        ("filter", {"page": "transactions", "filters": {"sql": "x"}}),
        ("filter", {"page": "transactions", "filters": {"limit": "zero"}}),
        ("filter", {"page": "transactions", "filters": {"since": "bad"}}),
        ("filter", {"page": "bills", "filters": {"days": "-1"}}),
        ("filter", {"page": "recurring", "filters": {"direction": "bad"}}),
        ("filter", {"page": "budgets", "filters": {"month": "2026-99"}}),
        ("filter", {"page": "transactions", "filters": {"search": 1}}),
        ("clear", {"page": "home"}),
    ],
)
def test_invalid_ui_event(action, payload):
    with pytest.raises(ValueError):
        dashboard.ui(action, **payload)
    assert dashboard.events() == []


def test_every_cli_shape():
    runner = CliRunner()

    def run(*args):
        result = runner.invoke(cli, ["--json", *args])
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    assert set(run("dashboard", "list")) == {"cards", "version", "seq"}
    added = run("dashboard", "add", "cashflow", "--props", "{}")
    id = added["id"]
    assert set(added) == {"cards", "version", "id", "kind", "seq", "event"}
    assert run("dashboard", "move", id, "--x", "0", "--y", "0")["version"] == 4
    assert run("dashboard", "resize", id, "--w", "3", "--h", "4")["version"] == 5
    assert run("dashboard", "remove", id)["version"] == 6
    assert any(c["id"] == id for c in run("dashboard", "undo")["cards"])
    assert run("ui", "navigate", "transactions")["payload"] == {"page": "transactions"}
    assert run("ui", "filter", "transactions", "search=a=b")["payload"]["filters"] == {
        "search": "a=b"
    }
    assert run("ui", "highlight", "page:transactions")["type"] == "ui.highlight"
    assert run("ui", "clear")["type"] == "ui.clear"
    for args in [
        ["dashboard", "add", "chart", "--props", "{"],
        ["dashboard", "remove", "missing"],
        ["dashboard", "move", id, "--x", "0"],
        ["ui", "filter", "transactions", "search"],
        ["ui", "filter", "transactions", "search=a", "search=b"],
        ["ui", "navigate", "nope"],
    ]:
        result = runner.invoke(cli, ["--json", *args])
        assert result.exit_code != 0
        assert set(json.loads(result.output)) == {"error"}


def test_every_api_shape(monkeypatch):
    client = TestClient(app)
    start = client.get("/api/dashboard").json()
    assert start["version"] == 1
    with connect() as db:
        assert db.execute("SELECT COUNT(*) FROM ui_events").fetchone()[0] == 0
    for action, body in [
        ("add", {"kind": "goals", "actor": "agent"}),
        ("move", {"id": "cashflow", "x": 0, "y": 0}),
        ("resize", {"id": "cashflow", "w": 3, "h": 4}),
        ("remove", {"id": "cashflow"}),
        ("undo", {}),
    ]:
        result = client.post(f"/api/dashboard/{action}", json=body)
        assert result.status_code == 200, result.text
        assert result.json()["event"]["type"] == f"dashboard.{action}"
        assert result.json()["event"]["actor"] == body.get("actor", "user")
    layout = [
        {k: c[k] for k in ("id", "x", "y", "w", "h")}
        for c in client.get("/api/dashboard").json()["cards"]
    ]
    assert (
        client.post("/api/dashboard/layout", json={"layout": layout}).status_code == 200
    )
    for action, body in [
        ("navigate", {"page": "home"}),
        ("filter", {"page": "transactions", "filters": {"search": "test"}}),
        ("highlight", {"target": "dashboard"}),
        ("clear", {}),
    ]:
        result = client.post(f"/api/ui/{action}", json=body)
        assert result.status_code == 200
        assert result.json()["payload"] == body
    for path, body in [
        ("dashboard/add", {"kind": "bad"}),
        ("dashboard/move", {}),
        ("dashboard/add", {"kind": "cashflow", "action": "remove"}),
        ("ui/clear", {"action": "clear"}),
        ("ui/filter", {}),
        ("ui/navigate", {"page": "invalid"}),
    ]:
        result = client.post(f"/api/{path}", json=body)
        assert result.status_code == 400
        assert set(result.json()) == {"error"}
    assert client.post("/api/dashboard/add", json=[]).status_code == 422
    assert client.get("/api/events?after=-1").status_code == 422
    assert (
        client.get("/api/events", headers={"Last-Event-ID": "bad"}).status_code == 400
    )
    assert client.get("/api/status").json()["test_mode"] is False
    monkeypatch.setenv("LEDGERLIGHT_LLM_PROVIDER", "fake")
    assert client.get("/api/status").json()["test_mode"] is True


def test_sse_replay_ping_disconnect_and_route(monkeypatch):
    first = dashboard.ui("navigate", page="home")
    second = dashboard.ui("highlight", target="dashboard")

    class Request:
        disconnected = False

        async def is_disconnected(self):
            return self.disconnected

    async def exercise():
        request = Request()
        stream = dashboard_api.event_stream(
            request, first["seq"], ping_seconds=0, poll_seconds=0
        )
        frame = await anext(stream)
        assert frame.startswith(f"id: {second['seq']}\ndata: ")
        assert json.loads(frame.split("data: ")[1]) == second
        assert await anext(stream) == ": ping\n\n"
        request.disconnected = True
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(exercise())
    cursors = []

    async def finite_stream(request, after):
        cursors.append(after)
        for row in dashboard.events(after):
            yield f"id: {row['seq']}\ndata: {json.dumps(row)}\n\n"
        yield ": ping\n\n"

    monkeypatch.setattr(dashboard_api, "event_stream", finite_stream)
    client = TestClient(app)
    result = client.get(f"/api/events?after={first['seq']}")
    assert result.headers["content-type"].startswith("text/event-stream")
    assert result.headers["cache-control"] == "no-cache"
    assert "ui.highlight" in result.text and "ui.navigate" not in result.text
    result = client.get(
        "/api/events?after=0", headers={"Last-Event-ID": str(second["seq"])}
    )
    assert result.text == ": ping\n\n"
    assert cursors == [first["seq"], second["seq"]]
