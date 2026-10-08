"""Versioned Vega-Lite charts backed by read-only SQLite queries."""

import json
import math
import sqlite3

from ledgerlight.config import db_path
from ledgerlight.db import connect


def _json_value(value):
    """Normalize SQLite scalar values for both CLI and API JSON output."""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def validate_sql(sql: str) -> tuple[list[str], list[dict]]:
    """Execute one read-only SELECT and return columns and JSON-safe rows."""
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
    connection = sqlite3.connect(f"{db_path().resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.create_function(
        "casefold", 1, lambda value: str(value).casefold(), deterministic=True
    )
    # mode=ro protects the main DB; the authorizer also blocks ATTACH and PRAGMA.
    connection.set_authorizer(
        lambda action, table, column, *_: (
            sqlite3.SQLITE_OK
            if action in allowed
            and not (
                action == sqlite3.SQLITE_READ
                and (table or "").lower() == "plaid_items"
                and (column or "").lower() in {"access_token_enc", "cursor"}
            )
            else sqlite3.SQLITE_DENY
        )
    )
    try:
        cursor = connection.execute(sql)
        if cursor.description is None:
            raise ValueError("SQL must be one SELECT statement")
        columns = [column[0] for column in cursor.description]
        if len(set(columns)) != len(columns):
            raise ValueError("SQL columns must have unique names; use AS aliases")
        # ponytail: materialize local demo queries; add budgets/paging for large data.
        return columns, [
            {name: _json_value(row[name]) for name in columns}
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as exc:
        raise ValueError(f"Invalid read-only SQL: {exc}") from exc
    finally:
        connection.close()


def build_spec(type: str, columns: list[str]) -> dict:
    if type not in {"bar", "line", "area", "arc"}:
        raise ValueError("Chart type must be bar, line, area or arc")
    if len(columns) < 2:
        raise ValueError("Chart SQL must return at least two columns")
    # Vega field references treat dots/brackets as paths unless escaped.
    fields = [
        name.replace("\\", "\\\\")
        .replace(".", "\\.")
        .replace("[", "\\[")
        .replace("]", "\\]")
        for name in columns[:2]
    ]
    category = {"field": fields[0], "type": "nominal", "title": columns[0]}
    value = {"field": fields[1], "type": "quantitative", "title": columns[1]}
    encoding = (
        {"color": category, "theta": value}
        if type == "arc"
        else {"x": category, "y": value}
    )
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "mark": type,
        "encoding": encoding,
    }


HTML_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; img-src data:; connect-src 'none'; "
    "form-action 'none'; base-uri 'none'"
)


def sandbox_document(html: str) -> str:
    # Always precede user markup: later policies cannot relax this CSP.
    return (
        '<meta http-equiv="Content-Security-Policy" content="' + HTML_CSP + '">' + html
    )


def preview(title: str, sql: str, type: str, html: str = "") -> dict:
    if not title.strip():
        raise ValueError("Chart title must not be blank")
    with connect():
        columns, rows = validate_sql(sql)
    if type == "html":
        if not html.strip():
            raise ValueError("HTML charts require --html markup")
        spec = {"kind": "html", "html": html}
    else:
        spec = build_spec(type, columns)
    result = {"title": title, "sql": sql, "spec": spec, "rows": rows}
    if type == "html":
        result["srcdoc"] = sandbox_document(html)
    return result


def add(
    title: str, sql: str, type: str, *, chart_id: int | None = None, html: str = ""
) -> dict:
    """Save a validated chart; replacing an existing chart increments its version."""
    value = preview(title, sql, type, html)
    spec_json = json.dumps(value["spec"])
    with connect() as connection:
        if chart_id is None:
            cursor = connection.execute(
                "INSERT INTO charts (title, sql, spec_json) VALUES (?, ?, ?)",
                (title, sql, spec_json),
            )
            chart_id = cursor.lastrowid
        else:
            cursor = connection.execute(
                "UPDATE charts SET title=?, sql=?, spec_json=?, version=version+1, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (title, sql, spec_json, chart_id),
            )
            if not cursor.rowcount:
                raise ValueError(f"Chart {chart_id} not found")
        connection.execute(
            "INSERT INTO chart_versions(chart_id,version,title,sql,spec_json) "
            "SELECT id,version,title,sql,spec_json FROM charts WHERE id=?",
            (chart_id,),
        )
    return show(chart_id)


def _chart(row: sqlite3.Row) -> dict:
    chart = dict(row)
    chart["spec"] = json.loads(chart.pop("spec_json"))
    _, chart["rows"] = validate_sql(chart["sql"])
    if chart["spec"].get("kind") == "html":
        chart["srcdoc"] = sandbox_document(chart["spec"]["html"])
    return chart


def list_charts() -> list[dict]:
    with connect() as connection:
        rows = connection.execute("SELECT * FROM charts ORDER BY id").fetchall()
    # Release the catalog read lock before querying on separate read-only
    # connections. Otherwise a waiting writer can block the second reader
    # while itself waiting for this cursor, causing a cross-connection deadlock.
    return [_chart(row) for row in rows]


def show(chart_id: int) -> dict:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM charts WHERE id=?", (chart_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Chart {chart_id} not found")
    return _chart(row)


def history(chart_id: int) -> list[dict]:
    with connect() as db:
        if not db.execute("SELECT 1 FROM charts WHERE id=?", (chart_id,)).fetchone():
            raise ValueError(f"Chart {chart_id} not found")
        return [
            dict(row)
            for row in db.execute(
                "SELECT * FROM chart_versions WHERE chart_id=? ORDER BY version",
                (chart_id,),
            )
        ]


def remove(chart_id: int) -> None:
    with connect() as connection:
        if not connection.execute(
            "DELETE FROM charts WHERE id=?", (chart_id,)
        ).rowcount:
            raise ValueError(f"Chart {chart_id} not found")
