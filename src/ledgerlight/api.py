"""Loopback API and optional built web shell; business logic is shared with CLI."""

import asyncio
import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from ledgerlight import (
    agent,
    chart_api,
    charts,
    dashboard_api,
    data,
    holdings,
    holdings_api,
    money_api,
    plaid_client,
    price_client,
    proposals,
    sync,
    voice,
)


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    workers = [
        threading.Thread(target=target, args=(stop,), daemon=True)
        for target in (sync.history_worker, holdings.price_worker)
    ]
    for worker in workers:
        worker.start()
    try:
        yield
    finally:
        stop.set()
        for worker in workers:
            await asyncio.to_thread(worker.join)


app = FastAPI(title="ledgerlight", lifespan=lifespan)


@app.exception_handler(ValueError)
async def value_error(request: Request, exc: ValueError):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(sync.DuplicateLinkError)
async def duplicate_link(request: Request, exc: sync.DuplicateLinkError):
    return JSONResponse(exc.payload(), status_code=409)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Pydantic's default details can include submitted public tokens.
    return JSONResponse({"error": "Invalid request parameters"}, status_code=422)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)


@app.exception_handler(sqlite3.Error)
@app.exception_handler(OSError)
@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception):
    return JSONResponse(
        {"error": "Local operation failed; check storage and settings"}, status_code=500
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/charts")
def list_charts():
    return charts.list_charts()


@app.post("/api/plaid/link-token")
def link_token():
    return plaid_client.get_client().create_link_token()


class LinkInstitution(BaseModel):
    institution_id: str | None = None
    name: str | None = None


class LinkAccount(BaseModel):
    name: str | None = None
    mask: str | None = None
    type: str | None = None
    subtype: str | None = None


class LinkMetadata(BaseModel):
    """Subset of Plaid Link onSuccess metadata used for duplicate checks."""

    institution: LinkInstitution | None = None
    accounts: list[LinkAccount] = Field(default_factory=list)


class Exchange(BaseModel):
    public_token: str = Field(min_length=1)
    link_token: str | None = Field(default=None, min_length=1)
    metadata: LinkMetadata | None = None


@app.post("/api/plaid/exchange")
def exchange(body: Exchange):
    metadata = body.metadata.model_dump() if body.metadata else None
    return sync.link(body.public_token, body.link_token, metadata)


@app.get("/api/plaid/items")
def items():
    return sync.items()


class RemoveItem(BaseModel):
    delete_local: bool = False


@app.post("/api/plaid/items/{item_id}/remove")
def remove_item(item_id: str, body: RemoveItem | None = None):
    return sync.remove_item(item_id, delete_local=bool(body and body.delete_local))


@app.get("/api/plaid/duplicates")
def duplicates():
    return sync.duplicates()


@app.get("/api/sync/status")
def sync_status():
    return sync.sync_status()


@app.post("/api/sync")
def sync_items():
    result = sync.sync_all()
    if not result["ok"]:
        return JSONResponse(
            {**result, "error": "One or more items failed to sync"}, status_code=502
        )
    return result


@app.get("/api/accounts/overview")
def accounts_overview():
    return data.accounts_overview()


@app.get("/api/accounts")
def accounts():
    return data.accounts()


@app.get("/api/transactions")
def transactions(
    account: str | None = None,
    since: str | None = None,
    until: str | None = None,
    category: str | None = None,
    search: str | None = None,
    limit: int = 100,
    tag: str | None = None,
):
    return data.transactions(account, since, until, category, search, limit, tag)


@app.get("/api/recurring")
def recurring(direction: str | None = None):
    return data.recurring(direction)


@app.get("/api/networth")
def networth(days: int = 90):
    return data.networth(days)


@app.get("/api/status")
def status():
    status = plaid_client.status()
    fake_prices = price_client.fake_enabled()
    return {
        **status,
        "fake_prices": fake_prices,
        "test_mode": status["fake_plaid"]
        or fake_prices
        or os.environ.get("LEDGERLIGHT_LLM_PROVIDER") == "fake",
    }


app.include_router(agent.router)
app.include_router(proposals.router)
app.include_router(chart_api.router)
app.include_router(voice.router)
app.include_router(money_api.router)
app.include_router(dashboard_api.router)
app.include_router(holdings_api.router)


# Source-checkout deployment; wheels include the CLI skill, not the web build.
dist = Path(__file__).resolve().parents[2] / "web" / "dist"
if dist.is_dir():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
