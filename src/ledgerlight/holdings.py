"""Manual accounts and price-tracked holdings, stored as ordinary `accounts` rows.

Rows use `item_id NULL` and `source` `manual`/`holding`, so overview, net worth
and snapshots use the shared paths. Loan balances are stored positive (owed),
like Plaid credit/loan accounts. Mutations accept apply=False for proposals.
Only coin ids/tickers reach price_client; never quantities, balances or names.
"""

import json
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from ledgerlight import money, price_client, sync
from ledgerlight.db import connect

LOAN_SUBTYPES = {
    "student_loan": "student",
    "auto_loan": "auto",
    "personal_loan": "personal",
}
MANUAL_KINDS = {
    **{kind: ("loan", subtype) for kind, subtype in LOAN_SUBTYPES.items()},
    "cash": ("depository", "cash"),
    "other_asset": ("other", "other"),
}
HOLDING_KINDS = {"crypto": ("investment", "crypto"), "stock": ("investment", "stock")}
MUTATIONS = {
    "manual_add",
    "manual_update",
    "manual_remove",
    "manual_apply_paydown",
    "manual_apply_payments",
    "holdings_add",
    "holdings_update",
    "holdings_remove",
    "holdings_refresh",
}
REFRESH_INTERVAL = 15 * 60
MATCH_MAX = 100


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cents(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _new_id():
    return f"manual-{uuid4().hex}"


def _amount(value, name, maximum=None):
    if value is None or value == "":
        return None
    amount = money.decimal(value)
    if amount < 0:
        raise ValueError(f"{name} must not be negative")
    if maximum is not None and amount > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return amount


def _payment_day(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("payment_day must be an integer from 1 to 28")
    try:
        day = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("payment_day must be an integer from 1 to 28") from exc
    if str(day) != str(value).strip() or not 1 <= day <= 28:
        raise ValueError("payment_day must be an integer from 1 to 28")
    return day


def _payment_match(value):
    """None leaves unchanged; empty clears; otherwise trimmed text (≤100 chars)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("payment_match must be text")
    value = value.strip()
    if len(value) > MATCH_MAX:
        raise ValueError(f"payment_match must be at most {MATCH_MAX} characters")
    return value


def _match_since(value):
    if value is None or value == "":
        return None
    try:
        return str(date.fromisoformat(str(value).strip()))
    except ValueError as exc:
        message = "payment_match_since must be an ISO date (YYYY-MM-DD)"
        raise ValueError(message) from exc


def _manual_values(
    kind,
    name,
    balance,
    apr,
    monthly_payment,
    payment_day,
    auto_paydown,
    payment_match=None,
    payment_match_since=None,
):
    if kind not in MANUAL_KINDS:
        raise ValueError("kind must be one of " + ", ".join(MANUAL_KINDS))
    loan = kind in LOAN_SUBTYPES
    balance = money.decimal(balance)
    if balance < 0:
        raise ValueError("balance must not be negative (loans store the amount owed)")
    apr = _amount(apr, "apr", 100)
    payment = _amount(monthly_payment, "monthly_payment")
    day = _payment_day(payment_day)
    auto = bool(auto_paydown)
    if not loan and (apr is not None or payment is not None or day is not None or auto):
        raise ValueError(
            "APR, payment, payment day and auto-paydown are for loans only"
        )
    if auto and not payment:
        raise ValueError("auto_paydown requires a positive monthly payment")
    match = payment_match or None
    since = _match_since(payment_match_since)
    if match and not loan:
        raise ValueError("payment_match is for loans only")
    if match and auto:
        raise ValueError(
            "Use either auto_paydown or payment_match for a loan, not both "
            "(one paydown mechanism per loan)"
        )
    if since and not match:
        raise ValueError("payment_match_since requires payment_match")
    type_, subtype = MANUAL_KINDS[kind]
    return {
        "kind": kind,
        "name": money.text(name),
        "balance": float(balance),
        "apr": None if apr is None else float(apr),
        "monthly_payment": None if payment is None else float(payment),
        "payment_day": day,
        "auto_paydown": auto,
        "payment_match": match,
        # The day the match is set unless given; never retro-applies before it.
        "payment_match_since": (since or str(money.today())) if match else None,
        "type": type_,
        "subtype": subtype,
    }


def _account_row(db, id, source):
    row = db.execute(
        "SELECT * FROM accounts WHERE id=? AND source=?", (id, source)
    ).fetchone()
    if row is None:
        label = "manual account" if source == "manual" else "holding"
        raise ValueError(f"Unknown {label}: {id}")
    return dict(row)


def manual_list():
    with connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT a.id,a.name,a.balance,a.type,a.subtype,d.kind,d.apr,"
                "d.monthly_payment,d.payment_day,d.auto_paydown,"
                "d.paydown_applied_through,d.payment_match,d.payment_match_since "
                "FROM accounts a "
                "JOIN manual_details d ON d.account_id=a.id "
                "WHERE a.source='manual' ORDER BY a.name, a.id"
            )
        ]
    for row in rows:
        row["auto_paydown"] = bool(row["auto_paydown"])
    return rows


def manual_add(
    kind,
    name,
    balance,
    apr=None,
    monthly_payment=None,
    payment_day=None,
    auto_paydown=False,
    payment_match=None,
    payment_match_since=None,
    apply=True,
):
    values = _manual_values(
        kind,
        name,
        balance,
        apr,
        monthly_payment,
        payment_day,
        auto_paydown,
        _payment_match(payment_match),
        payment_match_since,
    )
    result = {**values, "source": "manual", "applied": apply}
    if apply:
        id = _new_id()
        with connect() as db:
            db.execute(
                "INSERT INTO accounts "
                "(id,name,balance,available,type,subtype,currency,source) "
                "VALUES (?,?,?,?,?,?, 'USD', 'manual')",
                (
                    id,
                    values["name"],
                    values["balance"],
                    None if values["type"] == "loan" else values["balance"],
                    values["type"],
                    values["subtype"],
                ),
            )
            db.execute(
                "INSERT INTO manual_details (account_id,kind,apr,monthly_payment,"
                "payment_day,auto_paydown,paydown_applied_through,payment_match,"
                "payment_match_since) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    id,
                    kind,
                    values["apr"],
                    values["monthly_payment"],
                    values["payment_day"],
                    int(values["auto_paydown"]),
                    str(money.today()),
                    values["payment_match"],
                    values["payment_match_since"],
                ),
            )
            sync._snapshot(db, account_ids=[id])
        result["id"] = id
    return result


def manual_update(
    id,
    name=None,
    balance=None,
    apr=None,
    monthly_payment=None,
    payment_day=None,
    auto_paydown=None,
    payment_match=None,
    payment_match_since=None,
    apply=True,
):
    """None leaves a field unchanged; an empty string clears an optional loan field.

    Clearing payment_match also clears its since date. A new or changed match
    without an explicit since date starts matching from today.
    """
    with connect() as db:
        account = _account_row(db, id, "manual")
        details = dict(
            db.execute(
                "SELECT * FROM manual_details WHERE account_id=?", (id,)
            ).fetchone()
        )
        match = _payment_match(payment_match)
        old_match = details["payment_match"]
        if match is None:
            match = old_match
        since = payment_match_since
        if since not in (None, "") and not match:
            raise ValueError("payment_match_since requires payment_match")
        if since in (None, "") and match == old_match:
            since = details["payment_match_since"]
        values = _manual_values(
            details["kind"],
            account["name"] if name is None else name,
            account["balance"] if balance is None else balance,
            details["apr"] if apr is None else apr,
            details["monthly_payment"] if monthly_payment is None else monthly_payment,
            details["payment_day"] if payment_day is None else payment_day,
            details["auto_paydown"] if auto_paydown is None else auto_paydown,
            match,
            since if match else None,
        )
        if apply:
            db.execute(
                "UPDATE accounts SET name=?, balance=?, available=? WHERE id=?",
                (
                    values["name"],
                    values["balance"],
                    None if values["type"] == "loan" else values["balance"],
                    id,
                ),
            )
            db.execute(
                "UPDATE manual_details SET apr=?, monthly_payment=?, payment_day=?, "
                "auto_paydown=?, paydown_applied_through=?, payment_match=?, "
                "payment_match_since=? WHERE account_id=?",
                (
                    values["apr"],
                    values["monthly_payment"],
                    values["payment_day"],
                    int(values["auto_paydown"]),
                    # Never back-charge: a new balance, newly enabled auto-paydown
                    # or changed payment terms start counting from today.
                    str(money.today())
                    if (
                        values["balance"] != account["balance"]
                        or (values["auto_paydown"] and not details["auto_paydown"])
                        or values["payment_day"] != details["payment_day"]
                        or values["monthly_payment"] != details["monthly_payment"]
                    )
                    else details["paydown_applied_through"],
                    values["payment_match"],
                    values["payment_match_since"],
                    id,
                ),
            )
            sync._snapshot(db, account_ids=[id])
    return {"id": id, **values, "source": "manual", "applied": apply}


def _remove(id, source, apply):
    # Delete dependents and the account together; details/holdings cascade.
    # Goals drop the account; a goal left with no accounts is archived.
    with connect() as db:
        account = _account_row(db, id, source)
        goals = [
            (row["id"], [i for i in json.loads(row["account_ids"]) if i != id])
            for row in db.execute("SELECT id,account_ids FROM goals ORDER BY id")
            if id in json.loads(row["account_ids"])
        ]
        if apply:
            for goal, remaining in goals:
                db.execute(
                    "UPDATE goals SET account_ids=?, archived_at=CASE WHEN ? THEN "
                    "COALESCE(archived_at, CURRENT_TIMESTAMP) ELSE archived_at END "
                    "WHERE id=?",
                    (json.dumps(remaining), not remaining, goal),
                )
            db.execute("DELETE FROM balance_snapshots WHERE account_id=?", (id,))
            db.execute("DELETE FROM alerts WHERE account_id=?", (id,))
            db.execute("DELETE FROM accounts WHERE id=?", (id,))
    return {
        "removed": id,
        "name": account["name"],
        "goals_updated": [goal for goal, remaining in goals if remaining],
        "goals_archived": [goal for goal, remaining in goals if not remaining],
        "applied": apply,
    }


def manual_remove(id, apply=True):
    return _remove(id, "manual", apply)


def _payment_dates(after, until, day):
    """Payment dates strictly after `after`, up to and including `until`."""
    year, month = after.year, after.month
    current = date(year, month, day)
    while True:
        if current > after:
            if current > until:
                return
            yield current
        month += 1
        if month > 12:
            year, month = year + 1, 1
        current = date(year, month, day)


def _due_paydowns(db):
    today = money.today()
    changes = []
    for row in db.execute(
        "SELECT a.id,a.name,a.balance,d.apr,d.monthly_payment,d.payment_day,"
        "d.paydown_applied_through FROM accounts a "
        "JOIN manual_details d ON d.account_id=a.id "
        "WHERE a.source='manual' AND a.type='loan' AND d.auto_paydown=1 "
        "AND d.monthly_payment IS NOT NULL ORDER BY a.id"
    ):
        through = row["paydown_applied_through"]
        dates = (
            list(
                _payment_dates(
                    date.fromisoformat(through), today, row["payment_day"] or 1
                )
            )
            if through
            else []
        )
        if through and not dates:
            continue
        owed = money.decimal(row["balance"])
        rate = money.decimal(row["apr"] or 0) / 100 / 12
        payment = money.decimal(row["monthly_payment"])
        for _ in dates:
            owed = max(Decimal(0), _cents(owed * (1 + rate) - payment))
        changes.append(
            {
                "id": row["id"],
                "name": row["name"],
                "payments": len(dates),
                "payment_dates": [str(d) for d in dates],
                "from": row["balance"],
                "to": float(owed),
            }
        )
    return changes


def manual_apply_paydown(apply=True):
    """Apply each missed monthly payment once: owed × (1 + APR/12) − payment ≥ 0."""
    with connect() as db:
        changes = _due_paydowns(db)
        if apply and changes:
            for change in changes:
                db.execute(
                    "UPDATE accounts SET balance=? WHERE id=?",
                    (change["to"], change["id"]),
                )
                db.execute(
                    "UPDATE manual_details SET paydown_applied_through=? "
                    "WHERE account_id=?",
                    (str(money.today()), change["id"]),
                )
            sync._snapshot(db, account_ids=[c["id"] for c in changes])
    return {"loans": changes, "date": str(money.today()), "applied": apply}


def _match_loans(db):
    """Loans with a payment match, in the order that wins a shared transaction.

    A transaction pays down at most one loan: the longest (most specific) match
    text wins; a tie goes to the oldest loan (manual_details insertion order).
    _due_payments skips matching loans already at zero while another still owes.
    """
    return [
        dict(row)
        for row in db.execute(
            "SELECT a.id,a.name,a.balance,d.payment_match,d.payment_match_since "
            "FROM accounts a JOIN manual_details d ON d.account_id=a.id "
            "WHERE a.source='manual' AND a.type='loan' "
            "AND COALESCE(d.payment_match,'')<>'' "
            "AND d.payment_match_since IS NOT NULL "
            "ORDER BY LENGTH(d.payment_match) DESC, d.rowid, a.id"
        )
    ]


def _fingerprint(date_, amount, name):
    return (date_, str(_cents(money.decimal(amount))), (name or "").casefold())


def _due_payments(db):
    """Posted, visible outflows in linked accounts not yet applied to any loan.

    Each row goes to the first matching loan (priority order) that still owes
    money, else to the first matching loan with amount 0 so it is applied once.
    A row is skipped when an applied payment (stored or earlier in this batch)
    has the same date, amount and casefolded name from a different source
    account: that is the same real payment replayed by a relinked or duplicate
    Item under new ids. Identical payments in one account all apply.
    """
    loans = _match_loans(db)
    if not loans:
        return []
    for loan in loans:
        loan["needle"] = loan["payment_match"].casefold()
        loan["owed"] = money.decimal(loan["balance"])
        loan["payments"] = []
    seen = {}
    for stored in db.execute(
        "SELECT source_account_id,txn_date,txn_name,txn_amount FROM loan_payments "
        "WHERE source_account_id IS NOT NULL AND txn_date IS NOT NULL "
        "AND txn_amount IS NOT NULL"
    ):
        key = _fingerprint(
            stored["txn_date"], stored["txn_amount"], stored["txn_name"]
        )
        seen.setdefault(key, set()).add(stored["source_account_id"])
    rows = db.execute(
        "SELECT t.id,t.account_id,t.date,t.name,t.merchant,t.amount "
        "FROM transactions t JOIN accounts a ON a.id=t.account_id "
        "WHERE a.source='plaid' AND a.item_id IS NOT NULL AND t.pending=0 "
        "AND t.hidden=0 AND t.amount<0 AND t.date>=? AND NOT EXISTS "
        "(SELECT 1 FROM loan_payments p WHERE p.transaction_id=t.id) "
        "ORDER BY t.date, t.id",
        (min(loan["payment_match_since"] for loan in loans),),
    ).fetchall()
    for row in rows:
        text = [(row["name"] or "").casefold(), (row["merchant"] or "").casefold()]
        candidates = [
            loan
            for loan in loans
            if row["date"] >= loan["payment_match_since"]
            and row["account_id"] != loan["id"]
            and any(loan["needle"] in value for value in text)
        ]
        if not candidates:
            continue
        loan = next((c for c in candidates if c["owed"] > 0), candidates[0])
        key = _fingerprint(row["date"], row["amount"], row["name"])
        # Checked across all loans: a replay must not pay a different loan
        # just because the original's loan has since reached zero.
        if seen.get(key, set()) - {row["account_id"]}:
            continue
        seen.setdefault(key, set()).add(row["account_id"])
        # Deduct the outflow, floored at zero; record what was actually deducted.
        amount = min(loan["owed"], -money.decimal(row["amount"]))
        loan["owed"] = _cents(loan["owed"] - amount)
        loan["payments"].append(
            {
                "transaction_id": row["id"],
                "source_account_id": row["account_id"],
                "date": row["date"],
                "name": row["name"],
                "merchant": row["merchant"],
                "transaction_amount": row["amount"],
                "amount": float(_cents(amount)),
            }
        )
    return [
        {
            "id": loan["id"],
            "name": loan["name"],
            "payment_match": loan["payment_match"],
            "payments": loan["payments"],
            "from": loan["balance"],
            "to": float(loan["owed"]),
        }
        for loan in loans
        if loan["payments"]
    ]


def manual_apply_payments(apply=True):
    """Deduct matched transactions from loan balances, each transaction once.

    Runs at the end of every sync and on demand. Idempotent: loan_payments
    records every applied transaction.
    """
    with connect() as db:
        if apply and not db.in_transaction:
            # Read and write under one lock so concurrent runs cannot both apply.
            db.execute("BEGIN IMMEDIATE")
        changes = _due_payments(db)
        if apply and changes:
            applied_at = _now()
            for change in changes:
                db.execute(
                    "UPDATE accounts SET balance=? WHERE id=?",
                    (change["to"], change["id"]),
                )
                db.executemany(
                    "INSERT INTO loan_payments (account_id,transaction_id,amount,"
                    "applied_at,source_account_id,txn_date,txn_name,txn_amount) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    [
                        (
                            change["id"],
                            p["transaction_id"],
                            p["amount"],
                            applied_at,
                            p["source_account_id"],
                            p["date"],
                            p["name"],
                            p["transaction_amount"],
                        )
                        for p in change["payments"]
                    ],
                )
            sync._snapshot(db, account_ids=[c["id"] for c in changes])
    return {"loans": changes, "date": str(money.today()), "applied": apply}


def restore_payments(db, transaction_id):
    """Undo an applied payment when Plaid removes its transaction.

    Called inside the sync transaction before the transaction row is deleted.
    Adds the deducted amount back to the loan and drops the loan_payments row.
    """
    restored = []
    for row in db.execute(
        "SELECT p.account_id,p.amount,a.balance FROM loan_payments p "
        "JOIN accounts a ON a.id=p.account_id WHERE p.transaction_id=?",
        (transaction_id,),
    ).fetchall():
        balance = _cents(money.decimal(row["balance"]) + money.decimal(row["amount"]))
        db.execute(
            "UPDATE accounts SET balance=? WHERE id=?",
            (float(balance), row["account_id"]),
        )
        restored.append(row["account_id"])
    db.execute("DELETE FROM loan_payments WHERE transaction_id=?", (transaction_id,))
    return restored


def manual_payments(id):
    """Applied payments for one manual account, newest first (read-only)."""
    with connect() as db:
        _account_row(db, id, "manual")
        return [
            dict(row)
            for row in db.execute(
                # Stored fingerprint, so removed/deleted transactions still show.
                "SELECT transaction_id,txn_date AS date,txn_name AS name,amount,"
                "txn_amount AS transaction_amount,source_account_id,applied_at "
                "FROM loan_payments WHERE account_id=? "
                "ORDER BY date DESC, transaction_id DESC",
                (id,),
            )
        ]


def holdings_list():
    with connect() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT a.id,a.name,a.balance AS value,h.kind,h.symbol,h.coin_id,"
                "h.quantity,h.price,h.price_change_24h,h.price_as_of,h.price_error "
                "FROM accounts a JOIN holdings h ON h.account_id=a.id "
                "WHERE a.source='holding' ORDER BY a.name, a.id"
            )
        ]


def search(symbol):
    """CoinGecko candidates for a crypto symbol, plus the one adding would choose."""
    symbol = price_client.check_symbol(symbol)
    candidates = price_client.get_client().search_coin(symbol)
    candidates.sort(
        key=lambda c: (c["market_cap_rank"] is None, c["market_cap_rank"] or 0, c["id"])
    )
    return {
        "symbol": symbol,
        "candidates": candidates,
        "chosen": price_client.choose_coin(candidates),
    }


def _quantity(value):
    quantity = money.decimal(value)
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return quantity


def resolve_add(kind, symbol, quantity, coin_id=None, name=None, coin_name=None):
    """Network step for adding crypto: pin the chosen coin id and name.

    Runs before any write transaction (proposals.create pins the result into the
    stored arguments, so apply never searches again).
    """
    arguments = dict(
        kind=kind,
        symbol=symbol,
        quantity=quantity,
        coin_id=coin_id,
        name=name,
        coin_name=coin_name,
    )
    if kind == "crypto" and not coin_id:
        symbol = price_client.check_symbol(symbol)
        chosen = search(symbol)["chosen"]
        if chosen is None:
            raise ValueError(
                f"No CoinGecko coin matches symbol {symbol}; pass --coin-id"
            )
        arguments.update(coin_id=chosen["id"], coin_name=chosen["name"])
    return arguments


def holdings_add(
    kind,
    symbol,
    quantity,
    coin_id=None,
    name=None,
    coin_name=None,
    apply=True,
    prefetched=None,
):
    """Network (coin search, price) happens before the single write transaction.

    `prefetched` is the result of `fetch_prices` for this holding; callers inside
    a transaction (proposal apply) must pass it so no request holds the lock.
    """
    if kind not in HOLDING_KINDS:
        raise ValueError("kind must be crypto or stock")
    symbol = (
        price_client.check_ticker(symbol)
        if kind == "stock"
        else price_client.check_symbol(symbol)
    )
    quantity = _quantity(quantity)
    coin = None
    if kind == "crypto":
        if not coin_id:
            resolved = resolve_add(kind, symbol, quantity)
            coin_id, coin_name = resolved["coin_id"], resolved["coin_name"]
        coin_id = price_client.check_coin_id(coin_id)
        coin = {
            "id": coin_id,
            "name": coin_name or coin_id,
            "explicit": not coin_name,
        }
    elif coin_id:
        raise ValueError("coin_id applies to crypto holdings only")
    label = (
        money.text(name)
        if name not in (None, "")
        else f"{coin['name']} ({symbol})"
        if coin and not coin["explicit"]
        else symbol
    )
    type_, subtype = HOLDING_KINDS[kind]
    result = {
        "kind": kind,
        "symbol": symbol,
        "coin_id": coin_id,
        "coin": coin,
        "quantity": float(quantity),
        "name": label,
        "source": "holding",
        "applied": apply,
    }
    if apply:
        id = _new_id()
        row = {"account_id": id, "kind": kind, "symbol": symbol, "coin_id": coin_id}
        if prefetched is None:
            prefetched = fetch_prices([row])
        with connect() as db:
            db.execute(
                "INSERT INTO accounts "
                "(id,name,balance,available,type,subtype,currency,source) "
                "VALUES (?,?,0,NULL,?,?, 'USD', 'holding')",
                (id, label, type_, subtype),
            )
            db.execute(
                "INSERT INTO holdings (account_id,kind,symbol,coin_id,quantity) "
                "VALUES (?,?,?,?,?)",
                (id, kind, symbol, coin_id, float(quantity)),
            )
            _write_prices(db, prefetched, [id])
        result.update(next(h for h in holdings_list() if h["id"] == id))
    return result


def holdings_update(id, quantity=None, name=None, apply=True):
    with connect() as db:
        account = _account_row(db, id, "holding")
        holding = dict(
            db.execute("SELECT * FROM holdings WHERE account_id=?", (id,)).fetchone()
        )
        amount = _quantity(holding["quantity"] if quantity is None else quantity)
        label = account["name"] if name in (None, "") else money.text(name)
        value = (
            float(_cents(amount * money.decimal(holding["price"])))
            if holding["price"] is not None
            else account["balance"]
        )
        if apply:
            db.execute(
                "UPDATE holdings SET quantity=? WHERE account_id=?",
                (float(amount), id),
            )
            db.execute(
                "UPDATE accounts SET name=?, balance=?, available=? WHERE id=?",
                (label, value, value if holding["price"] is not None else None, id),
            )
            sync._snapshot(db, account_ids=[id])
    return {
        "id": id,
        "name": label,
        "quantity": float(amount),
        "value": value,
        "applied": apply,
    }


def holdings_remove(id, apply=True):
    return _remove(id, "holding", apply)


def _safe_error(exc):
    if isinstance(exc, price_client.PriceError):
        return str(exc)
    return "Price source failed"


def _key(row):
    return row["coin_id"] if row["kind"] == "crypto" else row["symbol"]


def load_holdings():
    """Read step: every holding row (no network)."""
    with connect() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT h.* FROM holdings h JOIN accounts a ON a.id=h.account_id "
                "ORDER BY h.account_id"
            )
        ]


def fetch_prices(rows):
    """Network step only (no database): one batched request per source.

    Returns {requested, quotes, failures, as_of}; failures keep last prices.
    """
    client = price_client.get_client() if rows else None
    requested = {
        kind: sorted({_key(r) for r in rows if r["kind"] == kind})
        for kind in HOLDING_KINDS
    }
    quotes, failures = {}, {}
    for kind, keys in requested.items():
        if not keys:
            continue
        fetch = client.crypto_prices if kind == "crypto" else client.stock_prices
        try:
            quotes[kind] = fetch(keys)
        except (price_client.PriceError, ValueError) as exc:
            failures[kind] = _safe_error(exc)
    return {
        "requested": requested,
        "quotes": quotes,
        "failures": failures,
        "as_of": _now(),
    }


def _write_prices(db, fetched, ids=None):
    """Write step: apply fetched quotes to current rows, then snapshot them.

    Rows whose key was not requested (added after the fetch) are left unchanged.
    """
    rows = [
        dict(row)
        for row in db.execute("SELECT * FROM holdings ORDER BY account_id")
        if ids is None or row["account_id"] in ids
    ]
    refreshed, errors, written = 0, [], []
    for row in rows:
        id, kind, key = row["account_id"], row["kind"], _key(row)
        if key not in fetched["requested"].get(kind, []):
            continue
        written.append(id)
        error = fetched["failures"].get(kind)
        quote = None
        if error is None:
            quote = fetched["quotes"].get(kind, {}).get(key)
            if quote is None:
                error = f"No price returned for {row['symbol']}"
            elif quote.get("error"):
                error = quote["error"]
        if error is not None:
            db.execute(
                "UPDATE holdings SET price_error=? WHERE account_id=?", (error, id)
            )
            errors.append({"id": id, "symbol": row["symbol"], "error": error})
            continue
        if kind == "crypto":
            price, change = quote["usd"], quote.get("usd_24h_change")
            as_of = fetched["as_of"]
        else:
            price, change = quote["price"], quote.get("change_24h")
            as_of = quote.get("as_of") or fetched["as_of"]
        value = float(_cents(money.decimal(row["quantity"]) * money.decimal(price)))
        db.execute(
            "UPDATE holdings SET price=?, price_change_24h=?, price_as_of=?, "
            "price_error=NULL WHERE account_id=?",
            (float(price), change, as_of, id),
        )
        db.execute(
            "UPDATE accounts SET balance=?, available=? WHERE id=?",
            (value, value, id),
        )
        refreshed += 1
    sync._snapshot(db, account_ids=written)
    return {"holdings": len(written), "refreshed": refreshed, "errors": errors}


def holdings_refresh(apply=True, prefetched=None):
    """Fetch all holding prices, then apply due loan paydowns and snapshot today.

    The fetch runs before any write; proposal apply passes `prefetched`.
    """
    if not apply:
        with connect() as db:
            count = db.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
            loans = _due_paydowns(db)
        return {"holdings": count, "loans": loans, "applied": False}
    if prefetched is None:
        prefetched = fetch_prices(load_holdings())
    loans = manual_apply_paydown()["loans"]
    with connect() as db:
        result = _write_prices(db, prefetched)
    return {**result, "loans": loans, "date": str(money.today()), "applied": True}


def prefetch(function, arguments):
    """Network work for a stored proposal, run before its write transaction."""
    if function == "holdings_add":
        row = {
            "kind": arguments["kind"],
            "symbol": (
                price_client.check_ticker
                if arguments["kind"] == "stock"
                else price_client.check_symbol
            )(arguments["symbol"]),
            "coin_id": arguments.get("coin_id"),
        }
        if row["kind"] == "crypto" and not row["coin_id"]:
            return {}  # Legacy unpinned argument; holdings_add will resolve.
        return {"prefetched": fetch_prices([row])}
    if function == "holdings_refresh":
        return {"prefetched": fetch_prices(load_holdings())}
    return {}


def snapshot_unlinked(db=None):
    """Today's snapshot for manual and holding accounts only.

    Plaid accounts detached by `plaid remove` also have item_id NULL; they keep
    their history but must not get new snapshots (a relink would double-count).
    """
    if db is None:
        with connect() as db:
            return snapshot_unlinked(db)
    ids = [
        r[0]
        for r in db.execute(
            "SELECT id FROM accounts "
            "WHERE item_id IS NULL AND source IN ('manual','holding')"
        )
    ]
    return sync._snapshot(db, account_ids=ids)


def price_worker(stop, interval=REFRESH_INTERVAL):
    """Server-owned refresh loop; the first tick waits a full interval.

    Shutdown interrupts the wait; an in-flight request finishes (≤10 s timeout,
    one retry) before the lifespan join returns. Every tick also records today's
    snapshot for unlinked (manual/holding) accounts.
    """
    while not stop.wait(interval):
        try:
            with connect() as db:
                held = db.execute("SELECT 1 FROM holdings LIMIT 1").fetchone()
            if held:
                holdings_refresh()
            else:
                manual_apply_paydown()
            snapshot_unlinked()
        except Exception:
            # Retry on the next tick; never log price-source or storage details.
            continue
