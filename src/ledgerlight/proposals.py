"""Stored, validated money changes. Only an explicit user apply commits them."""

import inspect
import json
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

import click
from fastapi import APIRouter

from ledgerlight import holdings, llm_client, money
from ledgerlight.db import atomic, connect

MUTATIONS = {
    "rules_add",
    "rules_remove",
    "rules_apply",
    "budgets_set",
    "budgets_remove",
    "txn_change",
    "recurring_mark",
    "alerts_dismiss",
    "alerts_refresh",
    "settings_set",
    "goals_add",
    "goals_update",
    "goals_archive",
    *holdings.MUTATIONS,
}
_proposing = ContextVar("proposing", default=False)
router = APIRouter()


def proposable(callback):
    @wraps(callback)
    def wrapper(*args, propose=False, **kwargs):
        token = _proposing.set(propose)
        try:
            return callback(*args, **kwargs)
        finally:
            _proposing.reset(token)

    return click.option("--propose", is_flag=True, help="Describe without applying.")(
        wrapper
    )


def execute(function, *args, **kwargs):
    if not _proposing.get():
        return function(*args, **kwargs)
    return create(function, *args, **kwargs)


def create(function, *args, **kwargs):
    """Validate and store a proposal; shared by --propose and MCP."""
    name = function.__name__
    if name not in MUTATIONS:
        raise ValueError("Unsupported proposal")
    params = dict(inspect.signature(function).bind(*args, **kwargs).arguments)
    if name == "settings_set" and params.get("key") in {"llm_provider", "history_days"}:
        raise ValueError("Provider and history-depth changes cannot be proposed")
    if name == "holdings_add":
        # Network before the write transaction; pin the coin so apply never
        # searches again and confirms exactly what the user reviewed.
        params = holdings.resolve_add(**params)
        params = {k: v for k, v in params.items() if v is not None}
    with atomic() as db:
        diff = function(**params, apply=False)
        summary = name.replace("_", " ") + ": " + json.dumps(diff, ensure_ascii=False)
        id = str(uuid4())
        db.execute(
            "INSERT INTO proposals(id,command,summary) VALUES(?,?,?)",
            (
                id,
                json.dumps({"function": name, "arguments": params, "diff": diff}),
                summary,
            ),
        )
    return {"proposal_id": id, "summary": summary, "diff": diff}


def get(id):
    with connect() as db:
        row = db.execute("SELECT * FROM proposals WHERE id=?", (id,)).fetchone()
        if row is None:
            raise ValueError("Proposal not found")
        command = json.loads(llm_client.redact(json.loads(row["command"])))
        return {
            "proposal_id": id,
            "summary": llm_client.redact(row["summary"]),
            "diff": command["diff"],
            "applied_at": row["applied_at"],
            "cancelled_at": row["cancelled_at"],
        }


@router.get("/api/proposals")
def pending():
    with connect() as db:
        ids = [
            row[0]
            for row in db.execute(
                "SELECT id FROM proposals WHERE applied_at IS NULL "
                "AND cancelled_at IS NULL ORDER BY rowid DESC"
            )
        ]
        return [get(id) for id in ids]


@router.get("/api/proposals/{id}")
def show(id: str):
    return get(id)


def _prefetch(id):
    """Price requests for a stored proposal, run before the write transaction."""
    with connect() as db:
        row = db.execute("SELECT command FROM proposals WHERE id=?", (id,)).fetchone()
    if row is None:
        return {}
    command = json.loads(row["command"])
    if command.get("function") not in holdings.MUTATIONS:
        return {}
    return holdings.prefetch(command["function"], command["arguments"])


@router.post("/api/proposals/{id}/apply")
def apply(id: str):
    extra = _prefetch(id)
    with atomic() as db:
        row = db.execute("SELECT * FROM proposals WHERE id=?", (id,)).fetchone()
        if row is None:
            raise ValueError("Proposal not found")
        if row["applied_at"] or row["cancelled_at"]:
            raise ValueError("Proposal is already resolved")
        command = json.loads(row["command"])
        if llm_client.redact(command) != json.dumps(command):
            raise ValueError("Proposal command contains a configured secret")
        if command["function"] not in MUTATIONS:
            raise ValueError("Unsupported proposal")
        module = holdings if command["function"] in holdings.MUTATIONS else money
        result = getattr(module, command["function"])(**command["arguments"], **extra)
        db.execute(
            "UPDATE proposals SET applied_at=CURRENT_TIMESTAMP WHERE id=?", (id,)
        )
        return result


@router.post("/api/proposals/{id}/cancel")
def cancel(id: str):
    with atomic() as db:
        if not db.execute(
            "UPDATE proposals SET cancelled_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND applied_at IS NULL AND cancelled_at IS NULL",
            (id,),
        ).rowcount:
            raise ValueError("Proposal missing or already resolved")
    return {"proposal_id": id, "cancelled": True}
