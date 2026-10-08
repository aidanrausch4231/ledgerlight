"""The only Plaid network boundary. Fakes require explicit environment opt-in."""

import hashlib
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta
from importlib import import_module
from uuid import uuid4

import plaid
from plaid.api import plaid_api

from ledgerlight.db import connect
from ledgerlight.money import history_days, today


class PlaidError(ValueError):
    """Safe-to-display error; never include SDK bodies, credentials or tokens."""


def remember_history(token, days):
    """Persist immutable request metadata, never the short-lived token itself."""
    with connect() as db:
        db.execute(
            "INSERT INTO plaid_link_history (token_hash, history_days) VALUES (?, ?) "
            "ON CONFLICT(token_hash) DO NOTHING",
            (hashlib.sha256(token.encode()).hexdigest(), days),
        )
    return token


def requested_history(token):
    with connect() as db:
        row = db.execute(
            "SELECT history_days FROM plaid_link_history WHERE token_hash=?",
            (hashlib.sha256(token.encode()).hexdigest(),),
        ).fetchone()
    return row[0] if row else None


class SyncStopped(PlaidError):
    """Cooperative shutdown/deadline cancellation, not a failed Plaid Item."""


_limits = ContextVar("plaid_sync_limits", default=(None, None))


def check_sync():
    stop, deadline = _limits.get()
    if (stop is not None and stop.is_set()) or (
        deadline is not None and time.monotonic() >= deadline
    ):
        raise SyncStopped("History sync stopped; retry sync to continue")


@contextmanager
def sync_limits(stop=None, deadline=None):
    token = _limits.set((stop, deadline))
    try:
        check_sync()
        yield
        check_sync()  # Before committing data/cursor even if cancellation came late.
    finally:
        _limits.reset(token)


def status():
    return {
        "fake_plaid": os.environ.get("LEDGERLIGHT_FAKE_PLAID") == "1",
        "plaid_env": os.environ.get("PLAID_ENV", "sandbox"),
    }


def require_sandbox():
    if status()["plaid_env"] != "sandbox":
        raise PlaidError("sandbox-link requires PLAID_ENV=sandbox")


def identity_accounts(accounts):
    return [
        {
            "name": account.get("name"),
            "mask": None if account.get("mask") is None else str(account["mask"]),
            "type": None if account.get("type") is None else str(account["type"]),
            "subtype": None
            if account.get("subtype") is None
            else str(account["subtype"]),
        }
        for account in accounts
    ]


class PlaidClient:
    def __init__(self):
        env = status()["plaid_env"]
        if env not in ("sandbox", "production"):
            raise PlaidError("PLAID_ENV must be sandbox or production")
        if not os.environ.get("PLAID_CLIENT_ID") or not os.environ.get("PLAID_SECRET"):
            raise PlaidError("Set PLAID_CLIENT_ID and PLAID_SECRET to use Plaid")
        configuration = plaid.Configuration(
            host=getattr(plaid.Environment, env.capitalize()),
            api_key={
                "clientId": os.environ["PLAID_CLIENT_ID"],
                "secret": os.environ["PLAID_SECRET"],
            },
        )
        self.api = plaid_api.PlaidApi(plaid.ApiClient(configuration))

    def _call(self, method, **kwargs):
        check_sync()
        deadline = _limits.get()[1]
        timeout = (
            60 if deadline is None else min(60, max(0.001, deadline - time.monotonic()))
        )
        # Generated SDK request types have the same stem as each endpoint.
        module_name = method + "_request"
        class_name = "".join(part.capitalize() for part in module_name.split("_"))
        try:
            model = getattr(import_module(f"plaid.model.{module_name}"), class_name)
            return getattr(self.api, method)(
                model(**kwargs), _request_timeout=timeout
            ).to_dict()
        except Exception as exc:
            check_sync()
            # SDK exceptions may embed request/response bodies containing secrets.
            raise PlaidError(
                f"Plaid {method} failed; check settings and retry"
            ) from exc

    def create_link_token(self):
        from plaid.model.country_code import CountryCode
        from plaid.model.link_token_create_request_user import (
            LinkTokenCreateRequestUser,
        )
        from plaid.model.link_token_transactions import LinkTokenTransactions
        from plaid.model.products import Products

        days = history_days()
        result = self._call(
            "link_token_create",
            transactions=LinkTokenTransactions(days_requested=days),
            client_name="ledgerlight",
            language="en",
            country_codes=[CountryCode("US")],
            products=[Products("transactions")],
            user=LinkTokenCreateRequestUser(client_user_id="ledgerlight-local-user"),
        )
        return {"link_token": remember_history(result["link_token"], days)}

    def link_history(self, public_token, link_token=None):
        days = requested_history(link_token or public_token)
        if days is None:
            raise PlaidError("Unknown Link history; create a new Link token and retry")
        return days

    def exchange_public_token(self, public_token):
        result = self._call("item_public_token_exchange", public_token=public_token)
        return result["item_id"], result["access_token"]

    def _item(self, access_token):
        # One item/get per access token and client, shared by name and id lookups.
        cache = self.__dict__.setdefault("_item_cache", {})
        if access_token not in cache:
            cache[access_token] = self._call("item_get", access_token=access_token)[
                "item"
            ]
        return cache[access_token]

    def institution_id(self, access_token):
        return self._item(access_token).get("institution_id") or None

    def institution_name(self, access_token):
        from plaid.model.country_code import CountryCode

        institution_id = self.institution_id(access_token)
        if not institution_id:
            return "Unknown institution"
        return self._call(
            "institutions_get_by_id",
            institution_id=institution_id,
            country_codes=[CountryCode("US")],
        )["institution"]["name"]

    def accounts(self, access_token):
        return self._call("accounts_get", access_token=access_token)["accounts"]

    def item_accounts(self, access_token):
        """Account identity only (no balances), for duplicate-link checks."""
        return identity_accounts(self.accounts(access_token))

    def transactions_sync(self, access_token, cursor):
        result = {"added": [], "modified": [], "removed": []}
        while True:
            check_sync()
            args = {"access_token": access_token}
            if cursor is not None:
                args["cursor"] = cursor
            page = self._call("transactions_sync", **args)
            for key in result:
                result[key].extend(page[key])
            cursor = page["next_cursor"]
            if not page["has_more"]:
                return {
                    **result,
                    "next_cursor": cursor,
                    "transactions_update_status": page.get(
                        "transactions_update_status"
                    ),
                }

    def recurring(self, access_token):
        return self._call("transactions_recurring_get", access_token=access_token)

    def remove_item(self, access_token):
        self._call("item_remove", access_token=access_token)

    def sandbox_public_token(self):
        require_sandbox()
        from plaid.model.products import Products
        from plaid.model.sandbox_public_token_create_request_options import (
            SandboxPublicTokenCreateRequestOptions,
        )
        from plaid.model.sandbox_public_token_create_request_options_transactions import (  # noqa: E501
            SandboxPublicTokenCreateRequestOptionsTransactions,
        )

        days = history_days()
        result = self._call(
            "sandbox_public_token_create",
            institution_id="ins_109508",
            initial_products=[Products("transactions")],
            options=SandboxPublicTokenCreateRequestOptions(
                transactions=SandboxPublicTokenCreateRequestOptionsTransactions(
                    days_requested=days
                )
            ),
        )
        return remember_history(result["public_token"], days)


class FakePlaidClient:
    """Synthetic Plaid-shaped responses; stable IDs, cursors and balances."""

    def create_link_token(self):
        days = history_days()
        return {"link_token": remember_history(f"link-synthetic-{uuid4()}", days)}

    def link_history(self, public_token, link_token=None):
        if link_token is not None:
            return PlaidClient.link_history(self, public_token, link_token)
        days = requested_history(public_token)
        # Direct arbitrary synthetic exchanges remain a test-only convenience.
        return days if days is not None else history_days()

    def remove_item(self, access_token):
        pass

    def sandbox_public_token(self):
        require_sandbox()
        days = history_days()
        return remember_history(f"public-synthetic-ledgerlight:{uuid4()}", days)

    def exchange_public_token(self, public_token):
        if not public_token.strip():
            raise PlaidError("public_token must not be empty")
        identity = public_token.split(":")[0]
        suffix = hashlib.sha256(identity.encode()).hexdigest()[:12]
        days = self.link_history(public_token)
        # "<identity>@<key>" links another synthetic Item at institution <key>
        # with the same account masks, so tests can create real duplicates.
        if "@" in identity:
            key = hashlib.sha256(identity.split("@", 1)[1].encode()).hexdigest()[:12]
            return f"item-synthetic-{suffix}", f"access-synthetic-{suffix}@{key}:{days}"
        return f"item-synthetic-{suffix}", f"access-synthetic-{suffix}:{days}"

    def institution_name(self, access_token):
        return "Synthetic Bank"

    def institution_id(self, access_token):
        # Each synthetic identity is its own institution unless it names one.
        head = access_token.removeprefix("access-synthetic-").split(":")[0]
        return f"ins_synthetic_{head.split('@')[-1]}"

    def item_accounts(self, access_token):
        return identity_accounts(self.accounts(access_token))

    def accounts(self, access_token):
        suffix = (
            access_token.removeprefix("access-synthetic-").split(":")[0].split("@")[0]
        )
        return [
            {
                "account_id": f"{suffix}-checking",
                "name": "Synthetic Checking",
                "type": "depository",
                "subtype": "checking",
                "mask": "0001",
                "balances": {
                    "current": 2500.0,
                    "available": 2400.0,
                    "iso_currency_code": "USD",
                },
            },
            {
                "account_id": f"{suffix}-credit",
                "name": "Synthetic Credit",
                "type": "credit",
                "subtype": "credit card",
                "mask": "0002",
                "balances": {
                    "current": 100.0,
                    "available": None,
                    "limit": 1000.0,
                    "iso_currency_code": "USD",
                },
            },
        ]

    def transactions_sync(self, access_token, cursor):
        account = self.accounts(access_token)[0]["account_id"]
        # Tokens from the former fake predate configurable link-time depth.
        depth = int(access_token.split(":")[1]) if ":" in access_token else 90
        rows = [
            {
                "transaction_id": f"{account}-{i}",
                "account_id": account,
                "date": str(today() - timedelta(days=i)),
                "name": name,
                "merchant_name": name,
                "amount": amount,
                "pending": i == 0,
                "personal_finance_category": {"primary": category},
            }
            for i, (name, amount, category) in enumerate(
                [
                    ("Synthetic Coffee", 5.5, "FOOD_AND_DRINK"),
                    ("Synthetic Payroll", -2500, "INCOME"),
                    ("Synthetic Streaming", 12, "ENTERTAINMENT"),
                ]
                + [("Synthetic History", 8, "GENERAL_MERCHANDISE")]
                * (depth - 3)
            )
        ]
        initial = cursor is None
        return {
            "added": rows[:30]
            if initial
            else (rows[30:] if cursor == "synthetic-cursor-1" else []),
            "modified": [],
            "removed": [],
            "next_cursor": "synthetic-cursor-1" if initial else "synthetic-cursor-2",
            "transactions_update_status": (
                "INITIAL_UPDATE_COMPLETE" if initial else "HISTORICAL_UPDATE_COMPLETE"
            ),
        }

    def recurring(self, access_token):
        account = self.accounts(access_token)[0]["account_id"]
        return {
            f"{direction}flow_streams": [
                {
                    "stream_id": f"{account}-{direction}",
                    "account_id": account,
                    "description": description,
                    "merchant_name": description,
                    "frequency": "MONTHLY",
                    "average_amount": {"amount": amount},
                    "last_amount": {"amount": amount},
                    "last_date": str(today()),
                    "predicted_next_date": str(
                        today() + timedelta(days=2 if direction == "out" else 30)
                    ),
                    "is_active": True,
                    "status": "MATURE",
                    "personal_finance_category": {"primary": category},
                }
            ]
            for direction, description, amount, category in [
                ("in", "Synthetic Payroll", -2500, "INCOME"),
                ("out", "Synthetic Streaming", 12, "ENTERTAINMENT"),
            ]
        }


def get_client():
    return FakePlaidClient() if status()["fake_plaid"] else PlaidClient()
