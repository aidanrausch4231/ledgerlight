"""Dashboard HTTP adapters and native, replayable server-sent events."""

import asyncio
import json
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ledgerlight import dashboard

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def get_dashboard():
    return dashboard.snapshot()


@router.get("/dashboard/default/show")
def show_default():
    return dashboard.default_show()


@router.post("/dashboard/default/save")
def save_default(body: dict):
    if set(body) - {"expected_version"}:
        raise ValueError("Unknown default parameters")
    return dashboard.default_save(**body)


@router.post("/dashboard/default/reset")
def reset_default(body: dict):
    if set(body) - {"actor", "expected_version"}:
        raise ValueError("Unknown default parameters")
    return dashboard.change("reset_default", **{"actor": "user", **body})


@router.post("/dashboard/{action}")
def change_dashboard(action: str, body: dict):
    if "action" in body:
        raise ValueError("Unknown dashboard parameters")
    return dashboard.change(action, **{"actor": "user", **body})


@router.post("/ui/{action}")
def change_ui(action: str, body: dict):
    if "action" in body:
        raise ValueError("Unknown UI parameters")
    return dashboard.ui(action, **{"actor": "user", **body})


async def event_stream(request, after, *, ping_seconds=15, poll_seconds=0.25):
    last_ping = time.monotonic()
    while not await request.is_disconnected():
        rows = await asyncio.to_thread(dashboard.events, after)
        for row in rows:
            after = row["seq"]
            yield f"id: {after}\ndata: {json.dumps(row)}\n\n"
        if time.monotonic() - last_ping >= ping_seconds:
            yield ": ping\n\n"
            last_ping = time.monotonic()
        await asyncio.sleep(poll_seconds)


@router.get("/events")
def get_events(
    request: Request, after: int = Query(default=0, ge=0, le=9223372036854775807)
):
    # EventSource reconnects the same URL, advancing via Last-Event-ID.
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError as exc:
        raise ValueError("Invalid Last-Event-ID") from exc
    if not 0 <= cursor <= 9223372036854775807:
        raise ValueError("Invalid Last-Event-ID")
    return StreamingResponse(
        event_stream(request, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
