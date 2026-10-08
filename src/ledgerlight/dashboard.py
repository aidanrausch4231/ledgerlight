"""Atomic, versioned layouts and durable UI events shared by CLI and HTTP."""

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from ledgerlight.db import connect

KINDS = (
    "spending_vs_last_month",
    "cashflow",
    "upcoming_bills",
    "net_worth",
    "budgets",
    "goals",
    "alerts",
    "recent_transactions",
    "top_merchants",
    "chart",
)
PAGES = (
    "home",
    "networth",
    "transactions",
    "recurring",
    "bills",
    "accounts",
    "budgets",
    "rules",
    "goals",
    "settings",
)
FILTERS = {
    "transactions": {"account", "since", "until", "category", "search", "limit", "tag"},
    "recurring": {"direction"},
    "bills": {"days"},
    "budgets": {"month"},
}


def _actor(actor):
    if actor not in ("user", "agent", "cli", "mcp"):
        raise ValueError("actor must be user, agent, cli or mcp")


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return value


def _geometry(card):
    for key, low, high in (("x", 0, 11), ("y", 0, 100000), ("w", 1, 12), ("h", 2, 30)):
        _integer(card[key], key, low, high)
    if card["x"] + card["w"] > 12:
        raise ValueError("Card extends beyond the 12-column grid")


def _props(db, kind, props):
    if kind not in KINDS:
        raise ValueError("Unknown card kind")
    if not isinstance(props, dict):
        raise ValueError("props must be an object")
    allowed = {"chart_id"} if kind == "chart" else set()
    if set(props) - allowed:
        raise ValueError("Unknown card props")
    if kind == "chart":
        id = _integer(props.get("chart_id"), "chart_id", 1, 2147483647)
        if not db.execute("SELECT 1 FROM charts WHERE id=?", (id,)).fetchone():
            raise ValueError("Chart not found")
    return props


def _cards(db):
    return [
        {**dict(row), "props": json.loads(row["props"])}
        for row in db.execute("SELECT * FROM dashboard_cards ORDER BY y,x,id")
    ]


def _event_row(row):
    result = dict(row)
    result["actor"] = result.pop("source_actor") or result["actor"]
    result["payload"] = json.loads(result["payload"])
    return result


def _stored_actor(actor):
    # Legacy SQLite CHECK constraints cannot be widened with ADD COLUMN.
    # Preserve old rows; the additive source_actor carries MCP attribution.
    return ("cli", "mcp") if actor == "mcp" else (actor, None)


def _event(db, type, payload, actor):
    seq = db.execute(
        "INSERT INTO ui_events(type,payload,actor,source_actor) VALUES(?,?,?,?)",
        (type, json.dumps(payload), *_stored_actor(actor)),
    ).lastrowid
    return _event_row(
        db.execute("SELECT * FROM ui_events WHERE seq=?", (seq,)).fetchone()
    )


def _save(db, cards, actor, action):
    # Replace only the layout, never financial data. Restoring snapshots preserves IDs.
    ids = {c["id"] for c in cards}
    for row in db.execute("SELECT id FROM dashboard_cards").fetchall():
        if row["id"] not in ids:
            db.execute("DELETE FROM dashboard_cards WHERE id=?", (row["id"],))
    for card in cards:
        db.execute(
            """INSERT INTO dashboard_cards VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,props=excluded.props,
            x=excluded.x,y=excluded.y,w=excluded.w,h=excluded.h,
            created_at=excluded.created_at,updated_at=excluded.updated_at""",
            (
                card["id"],
                card["kind"],
                json.dumps(card["props"]),
                card["x"],
                card["y"],
                card["w"],
                card["h"],
                card["created_at"],
                card["updated_at"],
            ),
        )
    return db.execute(
        "INSERT INTO dashboard_versions(layout,action,actor,source_actor) "
        "VALUES(?,?,?,?)",
        (json.dumps(_cards(db)), action, *_stored_actor(actor)),
    ).lastrowid


def _seed_cards():
    now = datetime.now(timezone.utc).isoformat()
    kinds = [
        "spending_vs_last_month",
        "cashflow",
        "upcoming_bills",
        "net_worth",
        "budgets",
        "goals",
        "alerts",
        "recent_transactions",
        "top_merchants",
    ]
    cards = [
        dict(
            id=kind,
            kind=kind,
            props={},
            x=(i % 2) * 6,
            y=(i // 2) * 5,
            w=6,
            h=5,
            created_at=now,
            updated_at=now,
        )
        for i, kind in enumerate(kinds)
    ]
    return cards


def _seed(db):
    if not db.execute("SELECT 1 FROM dashboard_versions LIMIT 1").fetchone():
        _save(db, _seed_cards(), "user", "seed")


def default_show():
    with connect() as db:
        row = db.execute(
            "SELECT layout,saved_at FROM dashboard_default WHERE id=1"
        ).fetchone()
        return {
            "layout": json.loads(row["layout"]) if row else None,
            "saved_at": row["saved_at"] if row else None,
        }


def default_save(*, expected_version=None):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _seed(db)
        snapshot = _snapshot(db)
        if expected_version is not None:
            _integer(expected_version, "expected_version", 1, 9223372036854775807)
            if expected_version != snapshot["version"]:
                raise ValueError("Layout changed; refresh before saving default")
        db.execute(
            "INSERT INTO dashboard_default(id,layout) VALUES(1,?) "
            "ON CONFLICT(id) DO UPDATE SET layout=excluded.layout,"
            "saved_at=CURRENT_TIMESTAMP",
            (json.dumps(snapshot["cards"]),),
        )
        row = db.execute("SELECT saved_at FROM dashboard_default WHERE id=1").fetchone()
        return {"layout": snapshot["cards"], "saved_at": row["saved_at"]}


def _snapshot(db):
    return {
        "cards": _cards(db),
        "version": db.execute(
            "SELECT COALESCE(MAX(version),0) FROM dashboard_versions"
        ).fetchone()[0],
        "seq": db.execute("SELECT COALESCE(MAX(seq),0) FROM ui_events").fetchone()[0],
    }


def snapshot(*, emit_event=False, actor="cli", seed=True):
    _actor(actor)
    with connect() as db:
        if not seed:
            if emit_event:
                raise ValueError("Read-only snapshots cannot emit events")
            return _snapshot(db)
        db.execute("BEGIN IMMEDIATE")
        _seed(db)
        if emit_event:
            cards = _cards(db)
            version = _save(db, cards, actor, "list")
            _event(
                db,
                "dashboard.list",
                {
                    "cards": cards,
                    "version": version,
                    "id": None,
                    "kind": None,
                },
                actor,
            )
        return _snapshot(db)


def _overlap(a, b):
    return (
        a["x"] < b["x"] + b["w"]
        and b["x"] < a["x"] + a["w"]
        and a["y"] < b["y"] + b["h"]
        and b["y"] < a["y"] + a["h"]
    )


def _settle(cards, target):
    # Target stays where requested. Push colliding cards down, deterministically.
    placed = [target]
    for card in sorted(
        (c for c in cards if c is not target), key=lambda c: (c["y"], c["x"], c["id"])
    ):
        while collisions := [c for c in placed if _overlap(card, c)]:
            card["y"] = max(c["y"] + c["h"] for c in collisions)
        _geometry(card)
        placed.append(card)


def change(action, *, actor="cli", **args):
    _actor(actor)
    allowed = {
        "add": {"kind", "props", "x", "y", "w", "h"},
        "move": {"id", "x", "y"},
        "resize": {"id", "w", "h"},
        "remove": {"id"},
        "undo": set(),
        "reset_default": set(),
        "layout": {"layout"},
    }
    if action not in allowed or set(args) - allowed[action] - {"expected_version"}:
        raise ValueError("Unknown dashboard action or parameters")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _seed(db)
        before = _snapshot(db)
        if args.get("expected_version") is not None:
            expected = _integer(
                args["expected_version"], "expected_version", 1, 9223372036854775807
            )
            if expected != before["version"]:
                raise ValueError("Layout changed; refresh before editing or undoing")
        cards = before["cards"]
        target = None
        if action == "add":
            kind = args.get("kind")
            props = _props(db, kind, args.get("props", {}))
            now = datetime.now(timezone.utc).isoformat()
            target = dict(
                id=uuid4().hex,
                kind=kind,
                props=props,
                x=args.get("x", 0),
                y=args.get("y", max((c["y"] + c["h"] for c in cards), default=0)),
                w=args.get("w", 6),
                h=args.get("h", 5),
                created_at=now,
                updated_at=now,
            )
            _geometry(target)
            cards.append(target)
            _settle(cards, target)
        elif action in ("move", "resize", "remove"):
            target = next((c for c in cards if c["id"] == args.get("id")), None)
            if target is None:
                raise ValueError("Card not found")
            if action == "remove":
                cards.remove(target)
            else:
                keys = ("x", "y") if action == "move" else ("w", "h")
                for key in keys:
                    if key not in args:
                        raise ValueError(f"{key} is required")
                    target[key] = args[key]
                _geometry(target)
                _settle(cards, target)
        elif action == "layout":
            layout = args.get("layout")
            if not isinstance(layout, list) or len(layout) != len(cards):
                raise ValueError("layout must contain every card exactly once")
            if any(
                not isinstance(c, dict)
                or set(c) != {"id", "x", "y", "w", "h"}
                or not isinstance(c["id"], str)
                for c in layout
            ):
                raise ValueError("Invalid layout item")
            if {c["id"] for c in layout} != {c["id"] for c in cards}:
                raise ValueError("layout must contain every card exactly once")
            for card in cards:
                card.update(next(c for c in layout if c["id"] == card["id"]))
                _geometry(card)
            if any(_overlap(a, b) for i, a in enumerate(cards) for b in cards[i + 1 :]):
                raise ValueError("Layout cards overlap")
        elif action == "reset_default":
            saved = db.execute(
                "SELECT layout FROM dashboard_default WHERE id=1"
            ).fetchone()
            cards = json.loads(saved["layout"]) if saved else _seed_cards()
        elif action == "undo":
            previous = db.execute(
                "SELECT layout FROM dashboard_versions "
                "ORDER BY version DESC LIMIT 1 OFFSET 1"
            ).fetchone()
            if previous is None:
                raise ValueError("Nothing to undo")
            cards = json.loads(previous["layout"])
        if action != "undo":
            now = datetime.now(timezone.utc).isoformat()
            for card in cards:
                card["updated_at"] = now
        version = _save(db, cards, actor, action)
        payload = {
            "cards": _cards(db),
            "version": version,
            "id": target["id"] if target else None,
            "kind": target["kind"] if target else None,
        }
        event = _event(db, f"dashboard.{action}", payload, actor)
        return {**payload, "seq": event["seq"], "event": event}


def ui(action, *, actor="cli", **payload):
    _actor(actor)
    allowed = {
        "navigate": {"page"},
        "filter": {"page", "filters"},
        "highlight": {"target"},
        "clear": set(),
    }
    if action not in allowed or set(payload) != allowed[action]:
        raise ValueError("Unknown UI action or parameters")
    if "page" in payload and payload["page"] not in PAGES:
        raise ValueError("Unknown page")
    if action == "filter":
        filters = payload["filters"]
        if (
            payload["page"] not in FILTERS
            or not isinstance(filters, dict)
            or set(filters) - FILTERS[payload["page"]]
        ):
            raise ValueError("Unsupported page filter")
        if any(not isinstance(v, str) or len(v) > 500 for v in filters.values()):
            raise ValueError("Filter values must be strings of at most 500 characters")
        # Reuse read validators without emitting an event for invalid query values.
        from ledgerlight import data, money

        if payload["page"] == "transactions":
            values = dict(filters)
            if "limit" in values:
                values["limit"] = int(values["limit"])
            data.transactions(**values)
        elif payload["page"] == "recurring":
            data.recurring(**filters)
        elif payload["page"] == "bills":
            money.bills_upcoming(int(filters.get("days", 30)))
        elif payload["page"] == "budgets":
            money.budgets_report(filters.get("month"))
    if action == "highlight" and (
        not isinstance(payload["target"], str)
        or not re.fullmatch(r"[\w:.-]{1,150}", payload["target"])
    ):
        raise ValueError("Invalid highlight target")
    with connect() as db:
        return _event(db, f"ui.{action}", payload, actor)


def events(after=0):
    _integer(after, "after", 0, 9223372036854775807)
    with connect() as db:
        return [
            _event_row(row)
            for row in db.execute(
                "SELECT * FROM ui_events WHERE seq>? ORDER BY seq LIMIT 500", (after,)
            )
        ]
