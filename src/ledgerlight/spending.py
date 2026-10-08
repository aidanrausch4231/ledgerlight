"""Read-only question matching and saveable local-data chart specifications."""

import difflib
import re
from decimal import Decimal

from ledgerlight import charts, money
from ledgerlight.data import today
from ledgerlight.db import connect

SYNONYMS = {
    "coffee": (
        "coffee",
        "cafe",
        "café",
        "espresso",
        "starbucks",
        "dunkin",
        "coffee co",
    ),
}
STOP_WORDS = set(
    (
        "hey hi how much what was were is are did do i my me on for the a an like "
        "spend spending spent show please total in last this month months year "
        "at to of by about us our"
    ).split()
)


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def ask(query: str, months: int = 12):
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ValueError("query must contain 1–500 characters")
    if type(months) is not int or not 1 <= months <= 120:
        raise ValueError("months must be between 1 and 120")
    words = [
        w
        for w in re.findall(r"[^\W_]+", query.casefold())
        if w not in STOP_WORDS and not w.isdigit()
    ]
    terms = list(
        dict.fromkeys(term for word in words for term in SYNONYMS.get(word, (word,)))
    )
    current = today().replace(day=1)
    labels = [
        str(money.shift_month(current, offset))[:7] for offset in range(1 - months, 1)
    ]
    fields = ["t.merchant", "t.name", "p.category", "t.note"]
    matches = []
    for term in terms:
        literal = _literal(term)
        matches.extend(
            f"instr(casefold(COALESCE({field},'')),{literal})>0" for field in fields
        )
        matches.append(
            "EXISTS (SELECT 1 FROM transaction_tags tag WHERE tag.transaction_id=t.id "
            f"AND instr(casefold(tag.tag),{literal})>0)"
        )
    # Each split replaces its parent. Only negative parts contribute, even for
    # mixed-sign splits. Matching categories applies to the part, not the parent.
    base = f"""WITH parts AS (
      SELECT transaction_id,category,amount FROM transaction_splits
      UNION ALL SELECT id,category,amount FROM transactions t
      WHERE NOT EXISTS (SELECT 1 FROM transaction_splits s WHERE s.transaction_id=t.id)
    ), matched AS (
      SELECT t.id,t.date,t.name,COALESCE(t.merchant,t.name) AS merchant,
             ROUND(SUM(-p.amount),10) AS total
      FROM transactions t JOIN parts p ON p.transaction_id=t.id
      WHERE t.hidden=0 AND t.pending=0 AND p.amount<0
        AND t.date>={_literal(labels[0] + "-01")} AND t.date<={_literal(str(today()))}
        AND ({" OR ".join(matches) or "0"})
      GROUP BY t.id
    ) """
    with connect() as db:
        transactions = [
            dict(r)
            for r in db.execute(
                base + "SELECT * FROM matched ORDER BY date DESC,id DESC"
            )
        ]
        candidates = [
            r[0]
            for r in db.execute(
                "SELECT category FROM transactions WHERE hidden=0 AND pending=0 "
                "UNION SELECT merchant FROM transactions WHERE hidden=0 AND pending=0 "
                "UNION SELECT s.category FROM transaction_splits s "
                "JOIN transactions t ON t.id=s.transaction_id "
                "WHERE t.hidden=0 AND t.pending=0"
            )
            if r[0]
        ]
    result = dict(
        query=query,
        matched_terms=terms,
        months=[],
        merchants=[],
        total=0.0,
        average_per_month=0.0,
        this_month=0.0,
        last_month=0.0,
        transactions=transactions[:10],
        charts=[],
    )
    if not transactions:
        ranked = sorted(
            candidates,
            key=lambda c: (
                -max(
                    (
                        difflib.SequenceMatcher(None, t, c.casefold()).ratio()
                        for t in terms
                    ),
                    default=0,
                ),
                c,
            ),
        )
        result["suggestions"] = ranked[:5]
        return result
    month_values = ",".join(f"({_literal(m)})" for m in labels)
    monthly_sql = (
        base
        + f""", calendar(month) AS (VALUES {month_values})
      SELECT calendar.month,ROUND(COALESCE(SUM(m.total),0),10) AS total,
             COUNT(m.id) AS count
      FROM calendar LEFT JOIN matched m ON substr(m.date,1,7)=calendar.month
      GROUP BY calendar.month ORDER BY calendar.month"""
    )
    merchant_sql = (
        base
        + "SELECT merchant AS name,ROUND(SUM(total),10) AS total,COUNT(*) AS count "
        "FROM matched GROUP BY merchant ORDER BY total DESC,name LIMIT 10"
    )
    for title, sql, key, column in [
        ("Monthly spending", monthly_sql, "months", "month"),
        ("Top merchants", merchant_sql, "merchants", "name"),
    ]:
        _, rows = charts.validate_sql(sql)
        spec = charts.build_spec("bar", [column, "total"])
        spec.update(data={"values": rows}, usermeta={"title": title, "sql": sql})
        result[key] = rows
        result["charts"].append(spec)
    total = sum((Decimal(str(t["total"])) for t in transactions), Decimal(0))
    result.update(
        total=float(total),
        average_per_month=float(total / months),
        this_month=result["months"][-1]["total"],
        last_month=next(
            (
                m["total"]
                for m in result["months"]
                if m["month"] == str(money.shift_month(current, -1))[:7]
            ),
            0.0,
        ),
    )
    return result
