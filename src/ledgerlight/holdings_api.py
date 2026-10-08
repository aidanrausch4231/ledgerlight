"""HTTP adapters; manual account and holding behavior lives in holdings.py."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from ledgerlight import holdings

router = APIRouter(prefix="/api")
Number = str | float | int


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManualAdd(Body):
    kind: Literal["student_loan", "auto_loan", "personal_loan", "cash", "other_asset"]
    name: str
    balance: Number
    apr: Number | None = None
    monthly_payment: Number | None = None
    payment_day: Number | None = None
    auto_paydown: bool = False
    payment_match: str | None = None
    payment_match_since: str | None = None


class ManualUpdate(Body):
    # Omitted/null fields are unchanged; "" clears optional loan fields.
    name: str | None = None
    balance: Number | None = None
    apr: Number | None = None
    monthly_payment: Number | None = None
    payment_day: Number | None = None
    auto_paydown: bool | None = None
    payment_match: str | None = None
    payment_match_since: str | None = None


class HoldingAdd(Body):
    kind: Literal["crypto", "stock"]
    symbol: str
    quantity: Number
    coin_id: str | None = None
    name: str | None = None


class HoldingUpdate(Body):
    quantity: Number | None = None
    name: str | None = None


@router.get("/manual")
def manual_list():
    return holdings.manual_list()


@router.post("/manual")
def manual_add(body: ManualAdd):
    return holdings.manual_add(**body.model_dump())


@router.post("/manual/apply-paydown")
def manual_apply_paydown():
    return holdings.manual_apply_paydown()


@router.post("/manual/apply-payments")
def manual_apply_payments():
    return holdings.manual_apply_payments()


@router.get("/manual/{id}/payments")
def manual_payments(id: str):
    return holdings.manual_payments(id)


@router.patch("/manual/{id}")
def manual_update(id: str, body: ManualUpdate):
    return holdings.manual_update(id, **body.model_dump())


@router.delete("/manual/{id}")
def manual_remove(id: str):
    return holdings.manual_remove(id)


@router.get("/holdings")
def holdings_list():
    return holdings.holdings_list()


@router.get("/holdings/search")
def holdings_search(symbol: str):
    return holdings.search(symbol)


@router.post("/holdings")
def holdings_add(body: HoldingAdd):
    return holdings.holdings_add(**body.model_dump())


@router.post("/holdings/refresh")
def holdings_refresh():
    return holdings.holdings_refresh()


@router.patch("/holdings/{id}")
def holdings_update(id: str, body: HoldingUpdate):
    return holdings.holdings_update(id, **body.model_dump())


@router.delete("/holdings/{id}")
def holdings_remove(id: str):
    return holdings.holdings_remove(id)
