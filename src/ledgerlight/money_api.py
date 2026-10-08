"""HTTP adapters; all money-management behavior lives in money.py."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from ledgerlight import money

router = APIRouter(prefix="/api")


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rule(Body):
    match_field: Literal["merchant", "name"]
    match_type: Literal["exact", "contains"]
    pattern: str
    category: str
    priority: int = 100


class RulePreview(Rule):
    category: str = "Preview"


@router.get("/rules")
def rules_list():
    return money.rules_list()


@router.post("/rules/preview")
def rules_preview(body: RulePreview):
    return money.rules_preview(**body.model_dump())


@router.post("/rules")
def rules_add(body: Rule):
    return money.rules_add(**body.model_dump())


@router.post("/rules/apply")
def rules_apply():
    return money.rules_apply()


@router.post("/rules/{id}/remove")
def rules_remove(id: int):
    return money.rules_remove(id)


class Budget(Body):
    category: str
    monthly_limit: float


@router.get("/budgets")
def budgets_list():
    return money.budgets_list()


@router.post("/budgets")
def budgets_set(body: Budget):
    return money.budgets_set(**body.model_dump())


@router.post("/budgets/{category:path}/remove")
def budgets_remove(category: str):
    return money.budgets_remove(category)


@router.get("/budgets/report")
def budgets_report(month: str | None = None):
    return money.budgets_report(month)


class Part(Body):
    category: str
    amount: str | float


class TransactionChange(Body):
    note: str | None = None
    tags: list[str] = []
    parts: list[Part] = []


@router.post("/txn/{id}/{action}")
def txn_change(id: str, action: str, body: TransactionChange):
    return money.txn_change(id, action, **body.model_dump())


@router.get("/spending/ask")
def spending_ask(text: str, months: int = 12):
    from ledgerlight.spending import ask

    return ask(text, months)


@router.get("/spending/summary")
def spending_summary(month: str | None = None):
    return money.spending_summary(month)


@router.get("/cashflow")
def cashflow(months: int = 6):
    return money.cashflow(months)


@router.get("/bills/upcoming")
def bills_upcoming(days: int = 30):
    return money.bills_upcoming(days)


class Mark(Body):
    status: Literal["cancel_intent", "ignored"] | None = None


@router.post("/recurring/{id}/mark")
def recurring_mark(id: str, body: Mark):
    return money.recurring_mark(id, body.status)


@router.get("/alerts")
def alerts_list(all: bool = False):
    return money.alerts_list(all)


@router.post("/alerts/refresh")
def alerts_refresh():
    return money.alerts_refresh()


@router.post("/alerts/{id}/dismiss")
def alerts_dismiss(id: int):
    return money.alerts_dismiss(id)


@router.get("/settings")
def settings_get(key: str | None = None):
    return money.settings_get(key)


class Setting(Body):
    key: str
    value: str | int | float


@router.post("/settings")
def settings_set(body: Setting):
    return money.settings_set(**body.model_dump())


class Goal(Body):
    name: str
    target_amount: float
    account_ids: list[str]
    target_date: str | None = None


class GoalUpdate(Body):
    name: str | None = None
    target_amount: float | None = None
    account_ids: list[str] | None = None
    target_date: str | None = None


@router.get("/goals")
def goals_list():
    return money.goals_list()


@router.post("/goals")
def goals_add(body: Goal):
    return money.goals_add(**body.model_dump())


@router.post("/goals/{id}/update")
def goals_update(id: int, body: GoalUpdate):
    return money.goals_update(id, **body.model_dump())


@router.post("/goals/{id}/archive")
def goals_archive(id: int):
    return money.goals_archive(id)
