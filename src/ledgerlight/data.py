"""Shared parameterized read models for the CLI and HTTP API."""

from datetime import date, timedelta

from ledgerlight.db import connect
from ledgerlight.money import today


def accounts():
    with connect() as db:
        return [
            dict(row) for row in db.execute("SELECT * FROM accounts ORDER BY name, id")
        ]


GROUP_LABELS = {
    "investments": "Investments",
    "crypto": "Crypto",
    "cash": "Cash",
    "other": "Other assets",
    "owed": "Owed",
}
KINDS = {
    "owed": ("credit", "Credit"),
    "investments": ("investment", "Investment"),
    "crypto": ("crypto", "Crypto"),
    "cash": ("cash", "Cash"),
    "other": ("other", "Other asset"),
}


def accounts_overview():
    """One ranked, signed account view for HTTP, CLI, agent and MCP readers."""
    with connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT a.*, COALESCE(p.institution, 'Manual') AS institution, "
                "h.kind AS holding_kind, h.symbol, h.coin_id, h.quantity, h.price, "
                "h.price_change_24h, h.price_as_of, h.price_error, "
                "d.kind AS manual_kind, d.apr, d.monthly_payment, d.payment_day, "
                "d.auto_paydown, d.payment_match, d.payment_match_since "
                "FROM accounts a LEFT JOIN plaid_items p ON p.id=a.item_id "
                "LEFT JOIN holdings h ON h.account_id=a.id AND a.source='holding' "
                "LEFT JOIN manual_details d ON d.account_id=a.id AND a.source='manual' "
                "ORDER BY a.name, a.id"
            )
        ]
        # Matched loan payments: count and the latest by transaction date.
        payments = {}
        for row in db.execute(
            "SELECT account_id, amount, txn_date AS date FROM loan_payments "
            "ORDER BY account_id, date DESC, transaction_id DESC"
        ):
            entry = payments.setdefault(
                row["account_id"],
                {"count": 0, "last": {"date": row["date"], "amount": row["amount"]}},
            )
            entry["count"] += 1
    grouped = {key: [] for key in GROUP_LABELS}
    empty = []
    for row in rows:
        identity = {key: row[key] for key in ("id", "name", "institution", "mask")}
        balance = row["balance"] or 0
        available = row["available"]
        source = row["source"]
        # Manual rows stay listed at zero so they can still be edited or removed.
        if balance == 0 and not available and source == "plaid":
            empty.append(identity)
            continue
        type_ = row["type"]
        key = (
            "owed"
            if type_ in ("credit", "loan")
            else "crypto"
            if type_ in ("investment", "brokerage") and row["subtype"] == "crypto"
            else "investments"
            if type_ in ("investment", "brokerage")
            else "other"
            if type_ == "other"
            else "cash"
        )
        kind, kind_label = KINDS[key]
        note = ""
        if type_ == "credit" and row["credit_limit"] is not None:
            note = f"${row['credit_limit'] - balance:,.2f} left"
        elif key == "cash":
            note = (
                f"${available:,.2f} available"
                if available is not None and available < balance
                else "all available"
            )
        account = {
            **identity,
            "type": type_,
            "subtype": row["subtype"],
            "kind": kind,
            "kind_label": kind_label,
            "balance": -balance if key == "owed" else balance,
            "available": available,
            "credit_limit": row["credit_limit"],
            "note": note,
            "source": source,
        }
        if source == "holding":
            account.update(
                {
                    name: row[name]
                    for name in (
                        "holding_kind",
                        "symbol",
                        "coin_id",
                        "quantity",
                        "price",
                        "price_change_24h",
                        "price_as_of",
                        "price_error",
                    )
                }
            )
        elif source == "manual":
            account.update(
                manual_kind=row["manual_kind"],
                apr=row["apr"],
                monthly_payment=row["monthly_payment"],
                payment_day=row["payment_day"],
                auto_paydown=bool(row["auto_paydown"]),
                payment_match=row["payment_match"],
                payment_match_since=row["payment_match_since"],
                payments_applied=payments.get(row["id"], {}).get("count", 0),
                last_payment=payments.get(row["id"], {}).get("last"),
            )
        grouped[key].append(account)
    totals = {key: sum(a["balance"] for a in group) for key, group in grouped.items()}
    cash, owed = totals["cash"], -totals["owed"]
    # Crypto counts toward the invested share; other assets only toward held.
    invested = totals["investments"] + totals["crypto"]
    held = cash + invested + totals["other"]

    def ratio(value, denominator):
        return min(1, max(0, value / denominator)) if denominator else 0

    maximum = max(
        (abs(a["balance"]) for group in grouped.values() for a in group), default=0
    )
    groups, rank = [], 0
    assets = ("investments", "crypto", "cash", "other")
    for key in [*sorted(assets, key=lambda k: -totals[k]), "owed"]:
        group = grouped[key]
        if not group:
            continue
        group.sort(key=lambda a: (-abs(a["balance"]), a["name"], a["id"]))
        for account in group:
            rank += 1
            account.update(rank=rank, bar=ratio(abs(account["balance"]), maximum))
        share_note = f"{ratio(totals[key], held):.0%} of held"
        if key == "owed":
            limits = [a["credit_limit"] for a in group]
            share_note = (
                f"{owed / sum(limits):.0%} of limit"
                if all(limit is not None for limit in limits) and sum(limits)
                else ""
            )
        groups.append(
            {
                "key": key,
                "label": GROUP_LABELS[key],
                "total": totals[key],
                "share_note": share_note,
                "accounts": group,
            }
        )
    return {
        "net_worth": held - owed,
        "held": held,
        "owed": owed,
        "cash_total": cash,
        "invested_total": invested,
        "cash_share": ratio(cash, held),
        "invested_share": ratio(invested, held),
        "owed_ratio": ratio(owed, held),
        "crypto_total": totals["crypto"],
        "other_total": totals["other"],
        "other_share": ratio(totals["other"], held),
        "groups": groups,
        "empty": empty,
    }


def transactions(
    account=None,
    since=None,
    until=None,
    category=None,
    search=None,
    limit=100,
    tag=None,
):
    if not 1 <= limit <= 10000:
        raise ValueError("limit must be between 1 and 10000")
    for value in (since, until):
        if value:
            date.fromisoformat(value)
    if since and until and since > until:
        raise ValueError("since must not be after until")
    clauses, params = [], []
    for column, op, value in [
        ("account_id", "=", account),
        ("date", ">=", since),
        ("date", "<=", until),
        ("category", "=", category),
    ]:
        if value:
            clauses.append(f"{column} {op} ?")
            params.append(value)
    if search:
        clauses.append(
            "(instr(lower(name), lower(?)) > 0 OR "
            "instr(lower(COALESCE(merchant, '')), lower(?)) > 0)"
        )
        params.extend([search, search])
    if tag:
        clauses.append(
            "EXISTS (SELECT 1 FROM transaction_tags "
            "WHERE transaction_id=transactions.id AND tag=?)"
        )
        params.append(tag)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM transactions"
                + where
                + " ORDER BY date DESC, id LIMIT ?",
                [*params, limit],
            )
        ]
        for row in rows:
            row.pop("base_category", None)
            row["pending"] = bool(row["pending"])
            row["hidden"] = bool(row["hidden"])
            row["tags"] = [
                r[0]
                for r in db.execute(
                    "SELECT tag FROM transaction_tags "
                    "WHERE transaction_id=? ORDER BY tag",
                    (row["id"],),
                )
            ]
            row["splits"] = [
                dict(r)
                for r in db.execute(
                    "SELECT id,category,amount FROM transaction_splits "
                    "WHERE transaction_id=? ORDER BY id",
                    (row["id"],),
                )
            ]
    return rows


def recurring(direction=None):
    if direction is not None and direction not in ("in", "out"):
        raise ValueError("direction must be in or out")
    with connect() as db:
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM recurring_streams"
                + (" WHERE direction=?" if direction else "")
                + " ORDER BY predicted_next_date, id",
                (direction,) if direction else (),
            )
        ]
    for row in rows:
        row["is_active"] = bool(row["is_active"])
    return rows


def networth(days=90):
    if not 1 <= days <= 36500:
        raise ValueError("days must be between 1 and 36500")
    since = str(today() - timedelta(days=days - 1))
    with connect() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT s.date, SUM(CASE WHEN a.type IN ('credit', 'loan') "
                "THEN -s.current ELSE s.current END) AS total "
                "FROM balance_snapshots s JOIN accounts a ON a.id=s.account_id "
                "WHERE s.date BETWEEN ? AND ? GROUP BY s.date ORDER BY s.date",
                (since, str(today())),
            )
        ]
