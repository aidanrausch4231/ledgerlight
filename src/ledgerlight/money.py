"""Money-management operations shared by CLI, API and sync.

Mutations validate before writing and accept apply=False for change descriptions.
Amounts are calculated with Decimal(str(value)); SQLite retains its REAL schema.
"""

import calendar
import json
import os
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from ledgerlight.db import connect


def today():
    return (
        date.fromisoformat(os.environ["LEDGERLIGHT_TODAY"])
        if os.environ.get("LEDGERLIGHT_TODAY")
        else date.today()
    )


def decimal(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid amount") from exc
    if not result.is_finite():
        raise ValueError("Amount must be finite")
    if Decimal(str(float(result))) != result:
        raise ValueError("Amount exceeds supported storage precision")
    return result


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Text must not be empty")
    return value.strip()


def require(db, table, id, column="id"):
    row = db.execute(f"SELECT * FROM {table} WHERE {column}=?", (id,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown {table}: {id}")
    return dict(row)


def matches(rule, row):
    value = (row.get(rule["match_field"]) or "").casefold()
    pattern = rule["pattern"].casefold()
    return value == pattern if rule["match_type"] == "exact" else pattern in value


def effective_category(db, row):
    for rule in db.execute("SELECT * FROM merchant_rules ORDER BY priority, id"):
        if matches(rule, row):
            return rule["category"]
    return (
        row.get("plaid_category")
        or row.get("base_category")
        or row.get("category")
        or "Uncategorized"
    )


def _apply_rules(db, apply=True):
    changed = 0
    for raw in db.execute("SELECT * FROM transactions").fetchall():
        row = dict(raw)
        category = effective_category(db, row)
        changed += category != row["category"]
        if apply:
            db.execute(
                "UPDATE transactions "
                "SET base_category=COALESCE(base_category, category), "
                "category=? WHERE id=?",
                (category, row["id"]),
            )
    return changed


def rules_apply(apply=True):
    with connect() as db:
        return {"changed": _apply_rules(db, apply), "applied": apply}


def rules_list():
    with connect() as db:
        rows = [
            dict(r)
            for r in db.execute("SELECT * FROM merchant_rules ORDER BY priority, id")
        ]
        transactions = [dict(r) for r in db.execute("SELECT * FROM transactions")]
    return [
        {**r, "match_count": sum(matches(r, t) for t in transactions)} for r in rows
    ]


def rule_values(match_field, match_type, pattern, category, priority):
    if match_field not in ("merchant", "name") or match_type not in (
        "exact",
        "contains",
    ):
        raise ValueError("Invalid rule match field or type")
    return dict(
        match_field=match_field,
        match_type=match_type,
        pattern=text(pattern),
        category=text(category),
        priority=int(priority),
    )


def rules_preview(match_field, match_type, pattern, category="Preview", priority=100):
    rule = rule_values(match_field, match_type, pattern, category, priority)
    with connect() as db:
        return {
            "match_count": sum(
                matches(rule, dict(t)) for t in db.execute("SELECT * FROM transactions")
            )
        }


def rules_add(match_field, match_type, pattern, category, priority=100, apply=True):
    values = rule_values(match_field, match_type, pattern, category, priority)
    with connect() as db:
        result = {**values, "applied": apply}
        if apply:
            result["id"] = db.execute(
                "INSERT INTO merchant_rules "
                "(match_field,match_type,pattern,category,priority) VALUES (?,?,?,?,?)",
                tuple(values.values()),
            ).lastrowid
            result["changed"] = _apply_rules(db)
        return result


def rules_remove(id, apply=True):
    with connect() as db:
        require(db, "merchant_rules", id)
        result = {"removed": id, "applied": apply}
        if apply:
            db.execute("DELETE FROM merchant_rules WHERE id=?", (id,))
            result["changed"] = _apply_rules(db)
        return result


def txn_change(id, action, note=None, tags=(), parts=(), apply=True):
    if action not in ("note", "hide", "unhide", "tag", "untag", "split", "unsplit"):
        raise ValueError("Invalid transaction action")
    with connect() as db:
        row = require(db, "transactions", id)
        values = {}
        if action == "note":
            if not isinstance(note, str):
                raise ValueError("note must be text")
            values = {"note": note}
        if action in ("tag", "untag"):
            if not tags:
                raise ValueError("At least one tag required")
            values = {"tags": sorted({text(t) for t in tags})}
        if action == "split":
            parsed = []
            for part in parts:
                if isinstance(part, str):
                    if "=" not in part:
                        raise ValueError("Parts must be CATEGORY=AMOUNT")
                    category, amount = part.rsplit("=", 1)
                else:
                    category, amount = part["category"], part["amount"]
                parsed.append((text(category), decimal(amount)))
            if not parsed or sum((p[1] for p in parsed), Decimal(0)) != decimal(
                row["amount"]
            ):
                raise ValueError("Split amounts must sum exactly to transaction amount")
            values = {"parts": [{"category": c, "amount": float(a)} for c, a in parsed]}
        if apply:
            if action == "note":
                db.execute("UPDATE transactions SET note=? WHERE id=?", (note, id))
            elif action in ("hide", "unhide"):
                db.execute(
                    "UPDATE transactions SET hidden=? WHERE id=?",
                    (action == "hide", id),
                )
            elif action in ("tag", "untag"):
                for tag in values["tags"]:
                    if action == "tag":
                        db.execute(
                            "INSERT OR IGNORE INTO transaction_tags VALUES (?,?)",
                            (id, tag),
                        )
                    else:
                        db.execute(
                            "DELETE FROM transaction_tags "
                            "WHERE transaction_id=? AND tag=?",
                            (id, tag),
                        )
            else:
                db.execute(
                    "DELETE FROM transaction_splits WHERE transaction_id=?", (id,)
                )
                if action == "split":
                    db.executemany(
                        "INSERT INTO transaction_splits "
                        "(transaction_id,category,amount) VALUES (?,?,?)",
                        [(id, p["category"], p["amount"]) for p in values["parts"]],
                    )
        return {"id": id, "action": action, **values, "applied": apply}


def month_start(month=None):
    month = month or today().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("month must be YYYY-MM")
    return date.fromisoformat(month + "-01")


def shift_month(start, delta):
    year, month = divmod(start.year * 12 + start.month - 1 + delta, 12)
    return date(year, month + 1, 1)


def entries(db, start, end):
    # Select parent rows once; split categories replace, never duplicate, the parent.
    for row in db.execute(
        "SELECT * FROM transactions WHERE date>=? AND date<? "
        "AND hidden=0 AND pending=0",
        (str(start), str(end)),
    ).fetchall():
        splits = db.execute(
            "SELECT category,amount FROM transaction_splits "
            "WHERE transaction_id=? ORDER BY id",
            (row["id"],),
        ).fetchall()
        for part in splits or [row]:
            yield {
                "date": row["date"],
                "merchant": row["merchant"] or row["name"],
                "category": part["category"],
                "amount": decimal(part["amount"]),
            }


def _spending(db, start, end):
    categories, merchants, days = (
        defaultdict(Decimal),
        defaultdict(Decimal),
        defaultdict(Decimal),
    )
    income = Decimal(0)
    for row in entries(db, start, end):
        if row["amount"] < 0:
            amount = -row["amount"]
            categories[row["category"]] += amount
            merchants[row["merchant"]] += amount
            days[int(row["date"][8:10])] += amount
        else:
            income += row["amount"]
    return categories, merchants, days, income


def spending_summary(month=None):
    start = month_start(month)
    previous = shift_month(start, -1)
    with connect() as db:
        categories, merchants, days, _ = _spending(db, start, shift_month(start, 1))
        _, _, last_days, _ = _spending(db, previous, start)
    # Current month stops today; historical months show their whole calendar.
    end_day = (
        today().day
        if start == today().replace(day=1)
        else calendar.monthrange(start.year, start.month)[1]
    )
    current = last = Decimal(0)
    line = []
    for day in range(1, end_day + 1):
        current += days[day]
        last += last_days[day]
        line.append(
            {"day": day, "this_month": float(current), "last_month": float(last)}
        )
    return {
        "month": start.strftime("%Y-%m"),
        "total_out": float(sum(categories.values(), Decimal(0))),
        "by_category": [
            {"category": c, "spent": float(a)} for c, a in sorted(categories.items())
        ],
        "top_merchants": [
            {"merchant": m, "spent": float(a)}
            for m, a in sorted(merchants.items(), key=lambda p: (-p[1], p[0]))[:10]
        ],
        "cumulative": line,
    }


def cashflow(months=6):
    if not 1 <= months <= 1200:
        raise ValueError("months must be between 1 and 1200")
    result = []
    with connect() as db:
        for offset in range(1 - months, 1):
            start = shift_month(today().replace(day=1), offset)
            categories, _, _, income = _spending(db, start, shift_month(start, 1))
            result.append(
                {
                    "month": start.strftime("%Y-%m"),
                    "income": float(income),
                    "spending": float(sum(categories.values(), Decimal(0))),
                }
            )
    return result


def budgets_set(category, monthly_limit, apply=True):
    category, amount = text(category), decimal(monthly_limit)
    if amount <= 0:
        raise ValueError("monthly_limit must be positive")
    if apply:
        with connect() as db:
            db.execute(
                "INSERT INTO budgets (category,monthly_limit) VALUES (?,?) "
                "ON CONFLICT(category) DO UPDATE SET "
                "monthly_limit=excluded.monthly_limit,updated_at=CURRENT_TIMESTAMP",
                (category, float(amount)),
            )
    return {"category": category, "monthly_limit": float(amount), "applied": apply}


def budgets_list():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM budgets ORDER BY category")]


def budgets_remove(category, apply=True):
    with connect() as db:
        require(db, "budgets", category, "category")
        if apply:
            db.execute("DELETE FROM budgets WHERE category=?", (category,))
    return {"removed": category, "applied": apply}


def budgets_report(month=None):
    spent = {
        r["category"]: decimal(r["spent"])
        for r in spending_summary(month)["by_category"]
    }
    return [
        {
            "category": b["category"],
            "limit": b["monthly_limit"],
            "spent": float(spent.get(b["category"], 0)),
            "remaining": float(
                decimal(b["monthly_limit"]) - spent.get(b["category"], 0)
            ),
            "percent": float(
                spent.get(b["category"], 0) / decimal(b["monthly_limit"]) * 100
            ),
        }
        for b in budgets_list()
    ]


def recurring_mark(id, status=None, apply=True):
    if status not in (None, "cancel_intent", "ignored"):
        raise ValueError("Invalid recurring user status")
    with connect() as db:
        require(db, "recurring_streams", id)
        if apply:
            db.execute(
                "UPDATE recurring_streams SET user_status=? WHERE id=?", (status, id)
            )
    return {"id": id, "user_status": status, "applied": apply}


def bills_upcoming(days=30):
    if not 0 <= days <= 36500:
        raise ValueError("days must be between 0 and 36500")
    with connect() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT r.id,r.predicted_next_date AS due_date,"
                "ABS(COALESCE(r.last_amount,r.average_amount,0)) AS amount,"
                "COALESCE(r.merchant,r.description) AS merchant,r.account_id,"
                "a.name AS account,r.user_status FROM recurring_streams r "
                "JOIN accounts a ON a.id=r.account_id "
                "WHERE r.direction='out' AND r.is_active=1 "
                "AND (r.user_status IS NULL OR r.user_status!='ignored') "
                "AND r.predicted_next_date BETWEEN ? AND ? "
                "ORDER BY r.predicted_next_date,r.id",
                (str(today()), str(today() + timedelta(days=days))),
            )
        ]


DEFAULTS = {
    "bill_days": 3,
    "low_balance_threshold": 100.0,
    "llm_provider": "local",
    "history_days": 365,
}


def validate_history_days(value):
    try:
        days = int(str(value))
    except (ValueError, TypeError):
        raise ValueError("history_days must be an integer from 30 to 730") from None
    if not 30 <= days <= 730:
        raise ValueError("history_days must be an integer from 30 to 730")
    return days


def history_days():
    """Effective link-time depth; environment overrides the saved setting."""
    return validate_history_days(
        os.environ.get(
            "LEDGERLIGHT_HISTORY_DAYS", settings_get("history_days")["value"]
        )
    )


def settings_get(key=None):
    with connect() as db:
        values = {
            **DEFAULTS,
            **{
                r["key"]: json.loads(r["value"])
                for r in db.execute("SELECT * FROM settings")
            },
        }
    if key is not None:
        if key not in values:
            if key.startswith("low_balance_threshold:"):
                with connect() as db:
                    require(db, "accounts", key.split(":", 1)[1])
                return {"key": key, "value": values["low_balance_threshold"]}
            raise ValueError("Unknown setting")
        return {"key": key, "value": values[key]}
    return values


def settings_set(key, value, apply=True):
    amount = None if key in {"llm_provider", "history_days"} else decimal(value)
    if key == "history_days":
        value = validate_history_days(value)
    elif key == "llm_provider":
        if value not in {"local", "claude", "openai"}:
            raise ValueError("Provider must be local, claude or openai")
    elif key == "bill_days":
        if amount != int(amount) or not 0 <= amount <= 36500:
            raise ValueError("bill_days must be an integer from 0 to 36500")
        value = int(amount)
    elif key == "low_balance_threshold" or key.startswith("low_balance_threshold:"):
        if amount < 0:
            raise ValueError("Threshold must not be negative")
        value = float(amount)
    else:
        raise ValueError("Unknown setting")
    with connect() as db:
        if ":" in key:
            require(db, "accounts", key.split(":", 1)[1])
        if apply:
            db.execute(
                "INSERT INTO settings VALUES (?,?) ON CONFLICT(key) "
                "DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
    return {"key": key, "value": value, "applied": apply}


def alerts_list(all=False):
    with connect() as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT * FROM alerts"
                + ("" if all else " WHERE dismissed_at IS NULL")
                + " ORDER BY id DESC"
            )
        ]


def alerts_dismiss(id, apply=True):
    with connect() as db:
        require(db, "alerts", id)
        if apply:
            db.execute(
                "UPDATE alerts "
                "SET dismissed_at=COALESCE(dismissed_at,CURRENT_TIMESTAMP) "
                "WHERE id=?",
                (id,),
            )
    return {"dismissed": id, "applied": apply}


def alerts_refresh(apply=True):
    settings = settings_get()
    candidates = []
    for b in bills_upcoming(settings["bill_days"]):
        candidates.append(
            (
                "bill",
                f"bill:{b['id']}:{b['due_date']}",
                b["account_id"],
                f"Bill due: {b['merchant']}",
                f"{b['amount']:.2f} due {b['due_date']}",
                b["due_date"],
            )
        )
    with connect() as db:
        for a in db.execute("SELECT * FROM accounts ORDER BY id"):
            # Credit/loan balances are debt, not available cash.
            if a["type"] in ("credit", "loan"):
                continue
            threshold = settings.get(
                f"low_balance_threshold:{a['id']}", settings["low_balance_threshold"]
            )
            balance = a["available"] if a["available"] is not None else a["balance"]
            if balance < threshold:
                candidates.append(
                    (
                        "low_balance",
                        f"low_balance:{a['id']}",
                        a["id"],
                        f"Low balance: {a['name']}",
                        f"{balance:.2f} below {threshold:.2f}",
                        None,
                    )
                )
    for b in budgets_report():
        if b["percent"] > 100:
            candidates.append(
                (
                    "budget_over",
                    f"budget_over:{today():%Y-%m}:{b['category']}",
                    None,
                    f"Over budget: {b['category']}",
                    f"{b['spent']:.2f} spent of {b['limit']:.2f}",
                    None,
                )
            )
    created = 0
    with connect() as db:
        for candidate in candidates:
            if db.execute(
                "SELECT 1 FROM alerts WHERE key=?", (candidate[1],)
            ).fetchone():
                continue
            created += 1
            if apply:
                db.execute(
                    "INSERT INTO alerts (kind,key,account_id,title,detail,due_date) "
                    "VALUES (?,?,?,?,?,?)",
                    candidate,
                )
    return {"created": created, "applied": apply}


def _goal_values(db, name, target_amount, target_date, account_ids):
    name, amount = text(name), decimal(target_amount)
    if amount <= 0:
        raise ValueError("target_amount must be positive")
    if target_date:
        target_date = str(date.fromisoformat(target_date))
    else:
        target_date = None
    ids = sorted(set(account_ids))
    if not ids:
        raise ValueError("At least one account required")
    for id in ids:
        require(db, "accounts", id)
    return dict(
        name=name, target_amount=float(amount), target_date=target_date, account_ids=ids
    )


def goals_add(name, target_amount, account_ids, target_date=None, apply=True):
    with connect() as db:
        values = _goal_values(db, name, target_amount, target_date, account_ids)
        result = {**values, "applied": apply}
        if apply:
            result["id"] = db.execute(
                "INSERT INTO goals "
                "(name,target_amount,target_date,account_ids,created_at) "
                "VALUES (?,?,?,?,?)",
                (
                    values["name"],
                    values["target_amount"],
                    values["target_date"],
                    json.dumps(values["account_ids"]),
                    str(today()),
                ),
            ).lastrowid
    return result


def goals_update(
    id, name=None, target_amount=None, account_ids=None, target_date=None, apply=True
):
    # None means unchanged; an empty target_date explicitly clears the date.
    with connect() as db:
        row = require(db, "goals", id)
        values = _goal_values(
            db,
            row["name"] if name is None else name,
            row["target_amount"] if target_amount is None else target_amount,
            row["target_date"] if target_date is None else target_date,
            # Stored ids may reference removed accounts; keep only existing ones.
            [
                i
                for i in json.loads(row["account_ids"])
                if db.execute("SELECT 1 FROM accounts WHERE id=?", (i,)).fetchone()
            ]
            if account_ids is None
            else account_ids,
        )
        if apply:
            db.execute(
                "UPDATE goals SET name=?,target_amount=?,target_date=?,account_ids=? "
                "WHERE id=?",
                (
                    values["name"],
                    values["target_amount"],
                    values["target_date"],
                    json.dumps(values["account_ids"]),
                    id,
                ),
            )
    return {"id": id, **values, "applied": apply}


def goals_archive(id, apply=True):
    with connect() as db:
        require(db, "goals", id)
        if apply:
            db.execute(
                "UPDATE goals SET archived_at=COALESCE(archived_at,CURRENT_TIMESTAMP) "
                "WHERE id=?",
                (id,),
            )
    return {"archived": id, "applied": apply}


def goals_list():
    with connect() as db:
        balances = {
            r["id"]: decimal(r["balance"])
            for r in db.execute("SELECT id,balance FROM accounts")
        }
        rows = [dict(r) for r in db.execute("SELECT * FROM goals ORDER BY id")]
    for row in rows:
        row["account_ids"] = json.loads(row["account_ids"])
        progress = sum(
            (balances.get(id, Decimal(0)) for id in row["account_ids"]), Decimal(0)
        )
        target = decimal(row["target_amount"])
        on_track = None
        if row["target_date"]:
            start = date.fromisoformat(row["created_at"][:10])
            end = date.fromisoformat(row["target_date"])
            fraction = (
                Decimal(1)
                if end <= start
                else min(
                    Decimal(1),
                    max(
                        Decimal(0),
                        Decimal((today() - start).days) / Decimal((end - start).days),
                    ),
                )
            )
            on_track = progress >= target * fraction
        row.update(
            progress=float(progress),
            remaining=float(max(Decimal(0), target - progress)),
            percent=float(progress / target * 100),
            on_track=on_track,
        )
    return rows
