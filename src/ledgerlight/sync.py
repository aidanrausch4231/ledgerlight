"""Shared link/sync operations. Each item commits atomically and independently."""

import json
import time
from datetime import date, datetime, timedelta, timezone

from ledgerlight import money, plaid_client
from ledgerlight.account_names import account_name_fallback, clean_account_name
from ledgerlight.crypto import decrypt, encrypt
from ledgerlight.db import atomic, connect

HISTORY_COMPLETE = "HISTORICAL_UPDATE_COMPLETE"
HISTORY_INTERVAL = 60
HISTORY_WINDOW = 30 * 60


class DuplicateLinkError(ValueError):
    """A new Link repeats accounts that a current Plaid Item already holds."""

    def __init__(self, duplicate_of, institution, accounts):
        self.duplicate_of = duplicate_of
        self.institution = institution
        self.accounts = accounts
        self.cleanup_failed = False
        shown = ", ".join(f"{row['name']} ••{row['mask']}" for row in accounts)
        super().__init__(
            f"{institution} is already linked ({shown}). "
            "Remove the old link first if you want to link it again."
        )

    def payload(self):
        body = {
            "error": str(self),
            "duplicate_of": self.duplicate_of,
            "institution": self.institution,
            "accounts": self.accounts,
        }
        if self.cleanup_failed:
            # The refused new Item could not be removed at Plaid.
            body["cleanup_failed"] = True
        return body


def _text(value):
    return None if value is None else str(value)


def _account_key(account):
    """(mask, type, subtype) compared as text; NULL or empty masks never match."""
    mask = _text(account.get("mask"))
    if not mask:
        return None
    return (mask, _text(account.get("type")), _text(account.get("subtype")))


UNKNOWN_INSTITUTION = "Unknown institution"


def _known_name(name):
    name = (name or "").strip()
    return name if name and name.casefold() != UNKNOWN_INSTITUTION.casefold() else None


def _same_institution(a_id, a_name, b_id, b_name):
    if a_id and b_id:
        return a_id == b_id
    # Items stored before institution_id existed fall back to the display name,
    # but a missing or placeholder name never identifies an institution.
    a_name, b_name = _known_name(a_name), _known_name(b_name)
    return bool(a_name and b_name) and a_name.casefold() == b_name.casefold()


def _linked(db):
    linked = [
        dict(row)
        for row in db.execute(
            "SELECT id, institution, institution_id, created_at, "
            "(SELECT COUNT(*) FROM transactions t JOIN accounts a "
            "ON a.id=t.account_id WHERE a.item_id=p.id) AS transaction_count "
            "FROM plaid_items p ORDER BY id"
        )
    ]
    for item in linked:
        item["accounts"] = [
            dict(row)
            for row in db.execute(
                "SELECT name, mask, type, subtype FROM accounts WHERE item_id=? "
                "ORDER BY id",
                (item["id"],),
            )
        ]
    return linked


def _matching(existing, accounts):
    keys = {_account_key(account) for account in accounts} - {None}
    return [
        {key: account.get(key) for key in ("name", "mask", "type", "subtype")}
        for account in existing
        if _account_key(account) in keys
    ]


def find_duplicate(db, institution_id, institution, accounts, exclude=None):
    """DuplicateLinkError for the first current Item that the rule matches."""
    for item in _linked(db):
        if item["id"] == exclude or not _same_institution(
            item["institution_id"], item["institution"], institution_id, institution
        ):
            continue
        matches = _matching(item["accounts"], accounts)
        if matches:
            return DuplicateLinkError(item["id"], item["institution"], matches)
    return None


def _check_metadata(metadata):
    if not isinstance(metadata, dict):
        return
    institution = metadata.get("institution")
    accounts = metadata.get("accounts")
    if not isinstance(institution, dict) or not isinstance(accounts, list):
        return
    accounts = [account for account in accounts if isinstance(account, dict)]
    institution_id = _text(institution.get("institution_id"))
    name = _text(institution.get("name"))
    if not accounts or not (institution_id or name):
        return
    with connect() as db:
        duplicate = find_duplicate(db, institution_id, name, accounts)
    if duplicate:
        raise duplicate


def link(public_token, link_token=None, metadata=None):
    if not public_token.strip():
        raise ValueError("public_token must not be empty")
    # Link metadata lets us refuse before exchange, so no Plaid Item is created.
    _check_metadata(metadata)
    client = plaid_client.get_client()
    days = client.link_history(public_token, link_token)
    plaid_client.remember_history(public_token, days)
    item_id, token = client.exchange_public_token(public_token)
    institution = client.institution_name(token)
    institution_id = None
    with connect() as db:
        others = db.execute(
            "SELECT COUNT(*) FROM plaid_items WHERE id<>?", (item_id,)
        ).fetchone()[0]
    if others:
        # Safety net for CLI exchange and missing metadata. With no other Item a
        # duplicate is impossible, and the first sync backfills institution_id.
        institution_id = client.institution_id(token)
        with connect() as db:
            duplicate = find_duplicate(
                db, institution_id, institution, client.item_accounts(token), item_id
            )
        if duplicate:
            try:
                client.remove_item(token)
            except plaid_client.PlaidError as exc:
                # Still refuse; nothing is stored, but the new Item may remain at
                # Plaid until removed in the Plaid dashboard.
                duplicate.cleanup_failed = True
                raise duplicate from exc
            raise duplicate
    encrypted = encrypt(token)
    with connect() as db:
        db.execute(
            "INSERT INTO plaid_items "
            "(id, institution, access_token_enc, created_at, history_days, "
            "institution_id) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "institution=excluded.institution, "
            "access_token_enc=excluded.access_token_enc, "
            "institution_id=COALESCE(excluded.institution_id, institution_id)",
            (item_id, institution, encrypted, days, institution_id),
        )
    sync_all(item_id=item_id)
    return {"id": item_id, "institution": institution}


def sandbox_link():
    plaid_client.require_sandbox()
    return link(plaid_client.get_client().sandbox_public_token())


def items():
    with connect() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT id, institution, created_at, last_synced_at, last_error, "
                "history_status, history_days, oldest_txn_date, "
                "(SELECT COUNT(*) FROM transactions t JOIN accounts a "
                "ON a.id=t.account_id WHERE a.item_id=p.id) AS transaction_count "
                "FROM plaid_items p ORDER BY id"
            )
        ]


def _snapshot(db, item_id=None, account_ids=None):
    where, params = "", ()
    if item_id is not None:
        where, params = " WHERE item_id = ?", (item_id,)
    elif account_ids is not None:
        account_ids = list(account_ids)
        where = f" WHERE id IN ({','.join('?' * len(account_ids))})"
        params = tuple(account_ids)
        if not account_ids:
            return 0
    rows = db.execute(
        "SELECT id, balance, available FROM accounts" + where, params
    ).fetchall()
    db.executemany(
        "INSERT INTO balance_snapshots (date, account_id, current, available) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(date, account_id) DO UPDATE SET "
        "current=excluded.current, available=excluded.available",
        [
            (str(money.today()), row["id"], row["balance"], row["available"])
            for row in rows
        ],
    )
    return len(rows)


def snapshot():
    # Loan auto-paydown is due before today's balances are recorded.
    from ledgerlight import holdings

    holdings.manual_apply_paydown()
    with connect() as db:
        count = _snapshot(db)
    return {"date": str(money.today()), "accounts": count}


def _category(row, db=None, previous=None):
    raw = (row.get("personal_finance_category") or {}).get("primary")
    if db is None:
        return raw
    return money.effective_category(
        db,
        {
            "merchant": row.get("merchant_name"),
            "name": row["name"],
            "plaid_category": raw,
            "base_category": (previous or {}).get("base_category"),
            "category": (previous or {}).get("category"),
        },
    )


def _sync_item(db, client, item):
    token = decrypt(item["access_token_enc"])
    if not item.get("institution_id"):
        # Backfill Items linked before duplicate checks (one item/get per sync).
        db.execute(
            "UPDATE plaid_items SET institution_id=? WHERE id=?",
            (client.institution_id(token), item["id"]),
        )
        plaid_client.check_sync()
    accounts = client.accounts(token)
    plaid_client.check_sync()
    changes = client.transactions_sync(token, item["cursor"])
    plaid_client.check_sync()
    streams = client.recurring(token)
    plaid_client.check_sync()
    for account in accounts:
        balance = account["balances"]
        db.execute(
            "INSERT INTO accounts "
            "(id, name, balance, item_id, type, subtype, mask, available, "
            "currency, credit_limit) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name, balance=excluded.balance, item_id=excluded.item_id, "
            "type=excluded.type, subtype=excluded.subtype, mask=excluded.mask, "
            "available=excluded.available, currency=excluded.currency, "
            "credit_limit=excluded.credit_limit",
            (
                account["account_id"],
                clean_account_name(
                    account.get("name"),
                    clean_account_name(
                        account.get("official_name"),
                        account_name_fallback(
                            account.get("subtype"), account.get("mask")
                        ),
                    ),
                ),
                balance.get("current") or 0,
                item["id"],
                str(account["type"]),
                account.get("subtype"),
                account.get("mask"),
                balance.get("available"),
                balance.get("iso_currency_code")
                or balance.get("unofficial_currency_code"),
                balance.get("limit"),
            ),
        )
    # Only allow records for this item, including previously known accounts.
    account_ids = {
        row[0]
        for row in db.execute("SELECT id FROM accounts WHERE item_id=?", (item["id"],))
    }
    for row in changes["added"] + changes["modified"]:
        if row["account_id"] not in account_ids:
            raise ValueError("Unknown account in sync")
        previous = db.execute(
            "SELECT * FROM transactions WHERE id=?", (row["transaction_id"],)
        ).fetchone()
        previous = dict(previous) if previous else {}
        if previous and money.decimal(previous["amount"]) != money.decimal(
            -row["amount"]
        ):
            cleared = db.execute(
                "DELETE FROM transaction_splits WHERE transaction_id=?",
                (row["transaction_id"],),
            ).rowcount
            if cleared:
                db.execute(
                    "UPDATE transactions SET split_cleared_at=CURRENT_TIMESTAMP "
                    "WHERE id=?",
                    (row["transaction_id"],),
                )
        if previous:
            db.execute(
                "UPDATE transactions "
                "SET base_category=COALESCE(base_category,category) "
                "WHERE id=?",
                (row["transaction_id"],),
            )
        db.execute(
            "INSERT INTO transactions "
            "(id, account_id, date, name, merchant, amount, category, pending, "
            "plaid_category, base_category) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET account_id=excluded.account_id, "
            "date=excluded.date, name=excluded.name, merchant=excluded.merchant, "
            "amount=excluded.amount, category=excluded.category, "
            "pending=excluded.pending, plaid_category=excluded.plaid_category",
            (
                row["transaction_id"],
                row["account_id"],
                str(row["date"]),
                row["name"],
                row.get("merchant_name"),
                -row["amount"],
                _category(row, db, previous),
                bool(row.get("pending")),
                _category(row),
                previous.get("base_category")
                or previous.get("category")
                or _category(row)
                or "Uncategorized",
            ),
        )
    from ledgerlight import holdings

    for row in changes["removed"]:
        if db.execute(
            "SELECT 1 FROM transactions WHERE id=? AND account_id IN "
            "(SELECT id FROM accounts WHERE item_id=?)",
            (row["transaction_id"], item["id"]),
        ).fetchone():
            # A removed transaction that paid down a loan gives the amount back,
            # in this Item's sync transaction.
            holdings.restore_payments(db, row["transaction_id"])
        db.execute(
            "DELETE FROM transactions WHERE id=? AND account_id IN "
            "(SELECT id FROM accounts WHERE item_id=?)",
            (row["transaction_id"], item["id"]),
        )
    user_statuses = {
        r["id"]: r["user_status"]
        for r in db.execute(
            "SELECT id,user_status FROM recurring_streams WHERE account_id IN "
            "(SELECT id FROM accounts WHERE item_id=?)",
            (item["id"],),
        )
    }
    db.execute(
        "DELETE FROM recurring_streams WHERE account_id IN "
        "(SELECT id FROM accounts WHERE item_id=?)",
        (item["id"],),
    )
    for direction in ("in", "out"):
        for row in streams.get(f"{direction}flow_streams", []):
            if row["account_id"] not in account_ids:
                raise ValueError("Unknown recurring account")
            db.execute(
                "INSERT INTO recurring_streams "
                "(id, account_id, direction, description, merchant, frequency, "
                "average_amount, last_amount, last_date, predicted_next_date, "
                "is_active, status, category, user_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["stream_id"],
                    row["account_id"],
                    direction,
                    row["description"],
                    row.get("merchant_name"),
                    row.get("frequency"),
                    -row["average_amount"]["amount"],
                    -row["last_amount"]["amount"],
                    str(row["last_date"]) if row.get("last_date") else None,
                    str(row["predicted_next_date"])
                    if row.get("predicted_next_date")
                    else None,
                    bool(row.get("is_active")),
                    row.get("status"),
                    _category(row),
                    user_statuses.get(row["stream_id"]),
                ),
            )
    _snapshot(db, item["id"])
    db.execute(
        "UPDATE plaid_items SET cursor=?, last_synced_at=CURRENT_TIMESTAMP, "
        "last_error=NULL, history_status=?, oldest_txn_date=("
        "SELECT MIN(t.date) FROM transactions t JOIN accounts a ON a.id=t.account_id "
        "WHERE a.item_id=?) WHERE id=?",
        (
            changes["next_cursor"],
            changes.get("transactions_update_status") or item["history_status"],
            item["id"],
            item["id"],
        ),
    )


def sync_all(item_id=None, *, stop=None, deadline=None):
    client = plaid_client.get_client()
    with connect() as db:
        linked = [
            dict(row)
            for row in db.execute(
                "SELECT id FROM plaid_items "
                + ("WHERE id=? " if item_id is not None else "")
                + "ORDER BY id",
                (item_id,) if item_id is not None else (),
            )
        ]
    results = []
    for item in linked:
        try:
            with atomic() as db, plaid_client.sync_limits(stop, deadline):
                # Serialize cursor reads and writes, including concurrent CLI/API syncs.
                current = db.execute(
                    "SELECT * FROM plaid_items WHERE id=?", (item["id"],)
                ).fetchone()
                if current is None:
                    continue
                _sync_item(db, client, dict(current))
            results.append({"id": item["id"], "ok": True})
        except plaid_client.SyncStopped:
            # Cancelled work rolls back, but is not a bank/configuration failure.
            return {"items": items(), "ok": False, "stopped": True}
        except Exception:
            # Neither SDK nor decryption errors are safe to expose verbatim.
            error = "Item sync failed; check Plaid settings or relink and retry"
            with connect() as db:
                db.execute(
                    "UPDATE plaid_items SET last_error=? WHERE id=?",
                    (error, item["id"]),
                )
            results.append({"id": item["id"], "ok": False, "error": error})
    # Manual/holding accounts have no Item: record today's balances for them too,
    # after due loan paydowns and matched loan payments, so daily net-worth
    # history stays complete and today's snapshot has the new loan balances.
    from ledgerlight import holdings

    holdings.manual_apply_paydown()
    holdings.manual_apply_payments()
    with connect() as db:
        holdings.snapshot_unlinked(db)
    money.alerts_refresh()
    statuses = {row["id"]: row for row in items()}
    for result in results:
        if result["id"] in statuses:
            result.update(statuses[result["id"]])
    return {"items": results, "ok": all(row["ok"] for row in results)}


_OWNED = "SELECT id FROM accounts WHERE item_id=?"
_OWNED_TXNS = "SELECT id FROM transactions WHERE account_id IN (" + _OWNED + ")"
# Every row that references the Item's accounts, children first.
_LOCAL_ROWS = (
    ("transaction_splits", "transaction_id IN (" + _OWNED_TXNS + ")"),
    ("transaction_tags", "transaction_id IN (" + _OWNED_TXNS + ")"),
    ("transactions", "account_id IN (" + _OWNED + ")"),
    ("recurring_streams", "account_id IN (" + _OWNED + ")"),
    ("balance_snapshots", "account_id IN (" + _OWNED + ")"),
    ("alerts", "account_id IN (" + _OWNED + ")"),
    ("accounts", "item_id=?"),
)


def _remap_goals(db, item):
    """Point goals at the remaining same-institution Item's matching accounts.

    goals.account_ids is a JSON list, not a foreign key. Each of the removed
    Item's account ids becomes the kept Item's account with the same
    mask/type/subtype, or is dropped; goals left with no account are archived.
    Returns the number of goals rewritten.
    """
    removed = {
        row["id"]: _account_key(dict(row))
        for row in db.execute(
            "SELECT id, mask, type, subtype FROM accounts WHERE item_id=?",
            (item["id"],),
        )
    }
    if not removed:
        return 0
    replacement = {}
    for kept in db.execute(
        "SELECT id, institution, institution_id FROM plaid_items WHERE id<>? "
        "ORDER BY id",
        (item["id"],),
    ).fetchall():
        if not _same_institution(
            kept["institution_id"],
            kept["institution"],
            item["institution_id"],
            item["institution"],
        ):
            continue
        for row in db.execute(
            "SELECT id, mask, type, subtype FROM accounts WHERE item_id=? "
            "ORDER BY id",
            (kept["id"],),
        ):
            key = _account_key(dict(row))
            if key is not None:
                replacement.setdefault(key, row["id"])
    updated = 0
    for goal in db.execute("SELECT id, account_ids FROM goals").fetchall():
        ids = json.loads(goal["account_ids"])
        if not any(account_id in removed for account_id in ids):
            continue
        remapped = []
        for account_id in ids:
            if account_id in removed:
                account_id = replacement.get(removed[account_id])
            if account_id is not None and account_id not in remapped:
                remapped.append(account_id)
        db.execute(
            "UPDATE goals SET account_ids=?, archived_at=CASE WHEN ? THEN "
            "archived_at ELSE COALESCE(archived_at, CURRENT_TIMESTAMP) END "
            "WHERE id=?",
            (json.dumps(sorted(remapped)), bool(remapped), goal["id"]),
        )
        updated += 1
    return updated


def remove_item(item_id, delete_local=False):
    """Disconnect an Item at Plaid.

    Default: retain its accounts (detached), transactions and all user annotations
    for a fresh Link. delete_local=True also deletes its accounts and every row
    that references them, in the same transaction as the Item row.
    """
    with atomic() as db:
        item = db.execute("SELECT * FROM plaid_items WHERE id=?", (item_id,)).fetchone()
        if item is None:
            raise ValueError("Unknown Plaid item")
        # Plaid first: if it fails, the transaction rolls back with no local change.
        plaid_client.get_client().remove_item(decrypt(item["access_token_enc"]))
        if not delete_local:
            db.execute("UPDATE accounts SET item_id=NULL WHERE item_id=?", (item_id,))
            db.execute("DELETE FROM plaid_items WHERE id=?", (item_id,))
            return {"removed": item_id, "retained_transactions": True}
        goals_updated = _remap_goals(db, dict(item))
        deleted = {
            table: db.execute(
                "DELETE FROM " + table + " WHERE " + where, (item_id,)
            ).rowcount
            for table, where in _LOCAL_ROWS
        }
        deleted["goals_updated"] = goals_updated
        db.execute("DELETE FROM plaid_items WHERE id=?", (item_id,))
    return {"removed": item_id, "retained_transactions": False, "deleted": deleted}


def duplicates():
    """Read-only groups of current Items that break the duplicate-link rule."""
    with connect() as db:
        linked = _linked(db)
    parent = {item["id"]: item["id"] for item in linked}

    def root(item_id):
        while parent[item_id] != item_id:
            item_id = parent[item_id]
        return item_id

    for index, first in enumerate(linked):
        for second in linked[index + 1 :]:
            if _same_institution(
                first["institution_id"],
                first["institution"],
                second["institution_id"],
                second["institution"],
            ) and _matching(first["accounts"], second["accounts"]):
                parent[root(second["id"])] = root(first["id"])
    groups = {}
    for item in linked:
        groups.setdefault(root(item["id"]), []).append(item)
    result = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # Most transactions wins; ties go to the earliest link, then the id.
        keep = min(
            members,
            key=lambda item: (
                -item["transaction_count"],
                item["created_at"] is None,
                item["created_at"] or "",
                item["id"],
            ),
        )
        others = [item for item in members if item["id"] != keep["id"]]
        shared = {
            _account_key(account)
            for other in others
            for account in _matching(keep["accounts"], other["accounts"])
        }
        result.append(
            {
                "institution": keep["institution"],
                "keep": keep["id"],
                "duplicates": [item["id"] for item in others],
                "accounts": [
                    {key: account[key] for key in ("name", "mask", "subtype")}
                    for account in keep["accounts"]
                    if _account_key(account) in shared
                ],
            }
        )
    return sorted(result, key=lambda group: group["keep"])


def history_pending(item):
    return item["history_status"] != HISTORY_COMPLETE


def sync_status():
    rows = items()
    now = datetime.now(timezone.utc)
    for item in rows:
        item["background_active"] = _within_window(item, now)
        item["history_from"] = item["oldest_txn_date"]
        # Missing dates cannot substantiate a full-history claim either.
        item["history_short"] = not history_pending(item) and (
            not item["history_from"]
            or not item["created_at"]
            or date.fromisoformat(item["history_from"])
            > (
                datetime.fromisoformat(item["created_at"]).date()
                - timedelta(days=item["history_days"] - 14)
            )
        )
    return {"history_days": money.history_days(), "items": rows}


def _within_window(item, now):
    if not history_pending(item) or not item["created_at"]:
        return False
    started = datetime.fromisoformat(item["created_at"]).replace(tzinfo=timezone.utc)
    return 0 <= (now - started).total_seconds() < HISTORY_WINDOW


def history_worker(stop, interval=HISTORY_INTERVAL):
    """One server-owned worker; no retries beyond 30 minutes from link time.

    Shutdown interrupts the wait and joins any in-flight SDK request before exit.
    Existing incomplete Items resume only within their original link-time window.
    """
    while not stop.wait(interval):
        try:
            for item in items():
                if stop.is_set():
                    return
                now = datetime.now(timezone.utc)
                if _within_window(item, now):
                    started = datetime.fromisoformat(item["created_at"]).replace(
                        tzinfo=timezone.utc
                    )
                    remaining = HISTORY_WINDOW - (now - started).total_seconds()
                    sync_all(
                        item_id=item["id"],
                        stop=stop,
                        deadline=time.monotonic() + remaining,
                    )
        except Exception:
            # Retry on the next tick, never leak SDK/storage details to logs.
            continue


def wait_history(timeout=600):
    """Explicit CLI wait with a shared deadline across sync pages and polling."""
    if not isinstance(timeout, int) or timeout < 0:
        raise ValueError("timeout must be a nonnegative integer")
    deadline = time.monotonic() + timeout
    result = sync_all(deadline=deadline if timeout else None)
    while True:
        pending = any(history_pending(row) for row in result["items"])
        remaining = deadline - time.monotonic()
        if result.get("stopped") or (pending and remaining <= 0):
            return {
                **result,
                "ok": False,
                "timed_out": True,
                "error": "History import timed out; run sync --wait-history to retry",
            }
        if not result["ok"] or not pending:
            return {**result, "timed_out": False}
        time.sleep(min(HISTORY_INTERVAL, remaining))
        if time.monotonic() >= deadline:
            continue
        for item in result["items"]:
            if history_pending(item):
                synced = sync_all(item_id=item["id"], deadline=deadline)
                if not synced["ok"]:
                    result = {**synced, "items": items()}
                    break
        else:
            result = {"items": [{**row, "ok": True} for row in items()], "ok": True}
