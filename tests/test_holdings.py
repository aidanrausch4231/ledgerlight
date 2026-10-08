"""Manual accounts, price-tracked holdings and loan paydown (synthetic, offline)."""

import json
import sqlite3
import threading
from contextlib import closing

import httpx
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import agent_tools, data, holdings, price_client, proposals, sync
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.config import db_path
from ledgerlight.db import SCHEMA_VERSION, connect

# Saved before the autouse guard replaces it; tests patch httpx.get underneath.
REAL_REQUEST = price_client.PriceClient._request


@pytest.fixture
def prices(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PRICES", "1")
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-15")


def invoke(*args, success=True):
    result = CliRunner().invoke(cli, ["--json", *args])
    assert (result.exit_code == 0) is success, result.output
    return json.loads(result.output)


def snapshots(account_id):
    with connect() as db:
        return [
            tuple(r)
            for r in db.execute(
                "SELECT date,current FROM balance_snapshots WHERE account_id=? "
                "ORDER BY date",
                (account_id,),
            )
        ]


def overview_row(id):
    for group in data.accounts_overview()["groups"]:
        for account in group["accounts"]:
            if account["id"] == id:
                return group["key"], account
    raise AssertionError(id)


@pytest.mark.parametrize(
    "kind,group,type_,subtype,sign",
    [
        ("student_loan", "owed", "loan", "student", -1),
        ("auto_loan", "owed", "loan", "auto", -1),
        ("personal_loan", "owed", "loan", "personal", -1),
        ("cash", "cash", "depository", "cash", 1),
        ("other_asset", "other", "other", "other", 1),
    ],
)
def test_manual_kind_add_list_update_remove(prices, kind, group, type_, subtype, sign):
    added = invoke(
        "manual", "add", "--kind", kind, "--name", "Synthetic", "--balance", "1200"
    )
    id = added["id"]
    assert id.startswith("manual-") and len(id) == len("manual-") + 32
    assert (added["type"], added["subtype"], added["source"]) == (
        type_,
        subtype,
        "manual",
    )
    [listed] = invoke("manual", "list")
    assert listed["id"] == id and listed["kind"] == kind and listed["balance"] == 1200
    key, row = overview_row(id)
    assert key == group and row["balance"] == sign * 1200
    assert row["source"] == "manual" and row["manual_kind"] == kind
    assert {"apr", "monthly_payment", "auto_paydown"} <= set(row)
    assert data.networth(1) == [{"date": "2026-03-15", "total": sign * 1200}]
    assert snapshots(id) == [("2026-03-15", 1200)]
    invoke("manual", "update", id, "--balance", "900", "--name", "Renamed")
    assert overview_row(id)[1]["balance"] == sign * 900
    assert overview_row(id)[1]["name"] == "Renamed"
    assert snapshots(id) == [("2026-03-15", 900)]
    assert invoke("manual", "remove", id) == {
        "removed": id,
        "name": "Renamed",
        "goals_updated": [],
        "goals_archived": [],
        "applied": True,
    }
    assert invoke("manual", "list") == []
    with connect() as db:
        for table, column in (
            ("accounts", "id"),
            ("manual_details", "account_id"),
            ("balance_snapshots", "account_id"),
        ):
            assert not db.execute(
                f"SELECT 1 FROM {table} WHERE {column}=?", (id,)
            ).fetchone()
    assert "error" in invoke("manual", "remove", id, success=False)


@pytest.mark.parametrize(
    "args,message",
    [
        (["--kind", "cash", "--apr", "5"], "loans only"),
        (["--kind", "student_loan", "--payment-day", "29"], "1 to 28"),
        (["--kind", "student_loan", "--auto-paydown"], "monthly payment"),
        (["--kind", "auto_loan", "--apr", "101"], "at most"),
        (["--kind", "cash", "--balance", "-1"], "negative"),
        (["--kind", "cash", "--balance", "nan"], "finite"),
    ],
)
def test_manual_validation(args, message):
    base = ["manual", "add", "--name", "Synthetic"]
    if "--balance" not in args:
        base += ["--balance", "100"]
    assert message in invoke(*base, *args, success=False)["error"]
    assert invoke("manual", "list") == []


def test_overview_groups_ring_networth_and_stable_keys(prices):
    with connect() as db:
        db.execute(
            "INSERT INTO accounts (id,name,balance,type,credit_limit) "
            "VALUES ('card','Synthetic Card',500,'credit',1000)"
        )
        db.execute(
            "INSERT INTO accounts (id,name,balance,type) "
            "VALUES ('fund','Synthetic Fund',4000,'investment')"
        )
    btc = holdings.holdings_add("crypto", "BTC", "0.1")["id"]  # 6000
    aapl = holdings.holdings_add("stock", "AAPL", "10")["id"]  # 2000
    cash = holdings.manual_add("cash", "Wallet", "1000")["id"]
    car = holdings.manual_add("other_asset", "Synthetic Car", "3000")["id"]
    loan = holdings.manual_add("student_loan", "Synthetic Loan", "2500", apr="5")["id"]
    o = data.accounts_overview()
    assert [g["key"] for g in o["groups"]] == [
        "investments",
        "crypto",
        "other",
        "cash",
        "owed",
    ]
    labels = {g["key"]: g["label"] for g in o["groups"]}
    assert labels["crypto"] == "Crypto" and labels["other"] == "Other assets"
    assert overview_row(btc)[0] == "crypto" and overview_row(aapl)[0] == "investments"
    assert overview_row(cash)[0] == "cash" and overview_row(car)[0] == "other"
    assert overview_row(loan)[1]["balance"] == -2500
    assert o["invested_total"] == 12000 and o["crypto_total"] == 6000
    assert o["cash_total"] == 1000 and o["other_total"] == 3000
    assert o["held"] == 16000 and o["owed"] == 3000 and o["net_worth"] == 13000
    assert o["invested_share"] == 0.75 and o["other_share"] == pytest.approx(3 / 16)
    stable = {
        "net_worth",
        "held",
        "owed",
        "cash_total",
        "invested_total",
        "cash_share",
        "invested_share",
        "owed_ratio",
        "groups",
        "empty",
    }
    assert stable <= set(o)
    row = overview_row(btc)[1]
    assert {
        k: row[k]
        for k in ("quantity", "symbol", "price", "price_change_24h", "price_error")
    } == {
        "quantity": 0.1,
        "symbol": "BTC",
        "price": 60000,
        "price_change_24h": 1.5,
        "price_error": None,
    }
    assert row["price_as_of"]
    assert overview_row(loan)[1]["apr"] == 5
    # Card is a snapshot-less row inserted directly; manual rows snapshot on add.
    sync.snapshot()
    assert data.networth(1) == [{"date": "2026-03-15", "total": 13000}]


def test_crypto_symbol_resolution_explicit_id_and_stock(prices):
    # Two synthetic "BTC" coins: the highest market-cap rank wins.
    assert holdings.search("btc")["chosen"]["id"] == "bitcoin"
    added = invoke("holdings", "add", "crypto", "btc", "5")
    assert added["coin"] == {"id": "bitcoin", "name": "Bitcoin", "explicit": False}
    assert added["name"] == "Bitcoin (BTC)" and added["value"] == 300000
    explicit = invoke(
        "holdings",
        "add",
        "crypto",
        "BTC",
        "2",
        "--coin-id",
        "synthetic-bitcoin-clone",
        "--name",
        "Clone",
    )
    assert explicit["coin_id"] == "synthetic-bitcoin-clone"
    assert explicit["value"] == 1 and explicit["name"] == "Clone"
    stock = invoke("holdings", "add", "stock", "AAPL", "10")
    assert stock["value"] == 2000 and stock["coin_id"] is None
    assert snapshots(stock["id"]) == [("2026-03-15", 2000)]
    assert {h["symbol"] for h in invoke("holdings", "list")} == {"BTC", "AAPL"}
    assert (
        "No CoinGecko coin"
        in invoke("holdings", "add", "crypto", "NOPE", "1", success=False)["error"]
    )
    assert (
        "crypto"
        in invoke(
            "holdings", "add", "stock", "AAPL", "1", "--coin-id", "x", success=False
        )["error"]
    )
    assert (
        "positive"
        in invoke("holdings", "add", "stock", "AAPL", "0", success=False)["error"]
    )
    updated = invoke("holdings", "update", stock["id"], "--quantity", "3")
    assert updated["value"] == 600 and snapshots(stock["id"]) == [("2026-03-15", 600)]
    invoke("holdings", "remove", stock["id"])
    assert snapshots(stock["id"]) == []


def test_refresh_sets_value_snapshots_and_keeps_last_price_on_error(
    prices, monkeypatch
):
    btc = holdings.holdings_add("crypto", "ETH", "2")["id"]
    aapl = holdings.holdings_add("stock", "AAPL", "4")["id"]
    monkeypatch.setitem(
        price_client.FakePriceClient.CRYPTO,
        "ethereum",
        {"usd": 3500.0, "usd_24h_change": 4.0},
    )
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-16")
    result = invoke("holdings", "refresh")
    assert result["refreshed"] == 2 and result["errors"] == []
    assert overview_row(btc)[1]["balance"] == 7000
    assert snapshots(btc) == [("2026-03-15", 6000), ("2026-03-16", 7000)]
    assert snapshots(aapl)[-1] == ("2026-03-16", 800)

    class Failing(price_client.FakePriceClient):
        def crypto_prices(self, ids):
            raise price_client.PriceError("Price source returned HTTP 429")

    monkeypatch.setattr(price_client, "get_client", Failing)
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-17")
    result = invoke("holdings", "refresh")
    assert result["refreshed"] == 1
    assert result["errors"] == [
        {"id": btc, "symbol": "ETH", "error": "Price source returned HTTP 429"}
    ]
    row = overview_row(btc)[1]
    assert row["balance"] == 7000 and row["price"] == 3500
    assert row["price_error"] == "Price source returned HTTP 429"
    assert snapshots(btc)[-1] == ("2026-03-17", 7000)
    monkeypatch.setattr(price_client, "get_client", price_client.FakePriceClient)
    invoke("holdings", "refresh")
    assert overview_row(btc)[1]["price_error"] is None


def test_missing_quote_sets_error_without_zeroing(prices, monkeypatch):
    id = holdings.holdings_add("stock", "VTI", "2")["id"]
    monkeypatch.delitem(price_client.FakePriceClient.STOCKS, "VTI")
    holdings.holdings_refresh()
    [row] = holdings.holdings_list()
    assert row["value"] == 500 and row["price_error"] == "No price returned for VTI"
    assert overview_row(id)[1]["balance"] == 500


def loan(monkeypatch, today, balance="1000", apr="12", payment="100", day=None):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", today)
    return holdings.manual_add(
        "personal_loan",
        "Synthetic Loan",
        balance,
        apr=apr,
        monthly_payment=payment,
        payment_day=day,
        auto_paydown=True,
    )["id"]


def balance(id):
    with connect() as db:
        return db.execute("SELECT balance FROM accounts WHERE id=?", (id,)).fetchone()[
            0
        ]


def test_paydown_one_and_three_months_idempotent(monkeypatch):
    one = loan(monkeypatch, "2026-01-20", day=15)
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-02-15")
    preview = invoke("manual", "apply-paydown", "--propose")["diff"]
    assert preview["applied"] is False and balance(one) == 1000
    result = holdings.manual_apply_paydown()
    assert [(c["id"], c["payments"]) for c in result["loans"]] == [(one, 1)]
    assert balance(one) == 910  # 1000 × (1 + 12%/12) − 100
    assert holdings.manual_apply_paydown()["loans"] == []
    assert balance(one) == 910
    three = loan(monkeypatch, "2026-02-15")  # default payment day 1
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-05-01")
    result = holdings.manual_apply_paydown()
    assert {c["id"]: c["payments"] for c in result["loans"]} == {one: 2, three: 3}
    # Mar 1, Apr 1, May 1: 1000 → 910 → 819.10 → 727.29.
    assert balance(three) == pytest.approx(727.29)
    assert balance(one) == pytest.approx(727.29)  # 910 → Mar 15, Apr 15
    assert snapshots(three)[-1] == ("2026-05-01", pytest.approx(727.29))
    assert holdings.manual_apply_paydown()["loans"] == []
    assert balance(three) == pytest.approx(727.29)


def test_paydown_floor_reset_snapshot_and_refresh(prices, monkeypatch):
    id = loan(monkeypatch, "2026-01-01", balance="150", apr="", payment="100")
    other = loan(monkeypatch, "2026-01-01")
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-05")
    invoke("snapshot")
    assert balance(id) == 0
    assert snapshots(id)[-1] == ("2026-03-05", 0)
    # Still listed so it can be edited or removed once paid off.
    assert overview_row(id)[1]["balance"] == 0
    holdings.manual_update(other, balance="500")
    with connect() as db:
        through = db.execute(
            "SELECT paydown_applied_through FROM manual_details WHERE account_id=?",
            (other,),
        ).fetchone()[0]
    assert through == "2026-03-05"
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-04-02")
    assert other in {c["id"] for c in invoke("holdings", "refresh")["loans"]}
    assert balance(other) == 405
    # Reads never apply paydowns.
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-06-02")
    data.accounts_overview()
    invoke("manual", "list")
    assert balance(other) == 405


NEW_WRITES = [
    ["manual", "add", "--kind", "cash", "--name", "New", "--balance", "5"],
    ["manual", "update", "M", "--balance", "7"],
    ["manual", "remove", "M"],
    ["manual", "apply-paydown"],
    ["manual", "apply-payments"],
    ["holdings", "add", "crypto", "BTC", "1"],
    ["holdings", "update", "H", "--quantity", "2"],
    ["holdings", "remove", "H"],
    ["holdings", "refresh"],
]


def test_agent_allowlist_has_new_commands():
    assert {
        ("manual", "list"),
        ("manual", "payments"),
        ("holdings", "list"),
    } <= agent_tools.READS
    assert {tuple(args[:2]) for args in NEW_WRITES} <= agent_tools.WRITES
    assert ("holdings", "search") not in agent_tools.READS | agent_tools.WRITES


@pytest.mark.parametrize("args", NEW_WRITES)
def test_manual_holding_writes_need_propose_then_apply(prices, args):
    manual = holdings.manual_add(
        "student_loan", "Loan", "100", monthly_payment="10", auto_paydown=True
    )["id"]
    held = holdings.holdings_add("stock", "AAPL", "1")["id"]
    args = [{"M": manual, "H": held}.get(a, a) for a in args]
    with pytest.raises(ValueError, match="--propose"):
        agent_tools.validate_args(args)
    assert agent_tools.validate_args([*args, "--propose"])

    def financial():
        with connect() as db:
            return [line for line in db.iterdump() if '"proposals"' not in line]

    before = financial()
    value = invoke(*args, "--propose")
    assert value["diff"]["applied"] is False
    assert financial() == before
    result = proposals.apply(value["proposal_id"])
    assert result["applied"] is True
    assert proposals.get(value["proposal_id"])["applied_at"]


def test_agent_reads_do_not_write(prices):
    holdings.holdings_add("stock", "AAPL", "1")
    holdings.manual_add("cash", "Wallet", "5")

    def dump():
        with closing(sqlite3.connect(db_path())) as db:
            return list(db.iterdump())

    before = dump()
    for path in (["manual", "list"], ["holdings", "list"]):
        result = agent_tools.run_ledgerlight(path)
        assert isinstance(result, list) and len(result) == 1
    assert dump() == before


def test_api_routes(prices):
    client = TestClient(app)
    assert client.get("/api/status").json()["fake_prices"] is True
    loan = client.post(
        "/api/manual",
        json={
            "kind": "auto_loan",
            "name": "Synthetic Auto",
            "balance": 9000,
            "apr": 4.5,
            "monthly_payment": 300,
            "payment_day": 10,
            "auto_paydown": True,
        },
    ).json()
    assert loan["type"] == "loan" and loan["payment_day"] == 10
    assert client.get("/api/manual").json()[0]["id"] == loan["id"]
    patched = client.patch(f"/api/manual/{loan['id']}", json={"apr": ""}).json()
    assert patched["apr"] is None and patched["balance"] == 9000
    bad = client.post("/api/manual", json={"kind": "cash", "name": "X", "balance": "x"})
    assert bad.status_code == 400 and bad.json()["error"]
    assert client.post("/api/manual", json={"kind": "boat"}).status_code == 422
    search = client.get("/api/holdings/search", params={"symbol": "BTC"}).json()
    assert search["chosen"]["name"] == "Bitcoin" and len(search["candidates"]) == 2
    held = client.post(
        "/api/holdings", json={"kind": "crypto", "symbol": "ETH", "quantity": "1.5"}
    ).json()
    assert held["value"] == 4500
    assert (
        client.patch(f"/api/holdings/{held['id']}", json={"quantity": 1}).json()[
            "value"
        ]
        == 3000
    )
    assert client.post("/api/holdings/refresh").json()["refreshed"] == 1
    assert client.get("/api/holdings").json()[0]["value"] == 3000
    # A holding id is not a manual account and vice versa.
    assert client.delete(f"/api/manual/{held['id']}").status_code == 400
    assert client.delete(f"/api/holdings/{held['id']}").json()["removed"] == held["id"]
    assert client.delete(f"/api/manual/{loan['id']}").json()["applied"] is True
    assert client.get("/api/holdings").json() == []
    assert client.get("/api/manual").json() == []


def test_real_price_client_is_guarded_in_tests():
    # Without LEDGERLIGHT_FAKE_PRICES=1 the real client is selected and blocked.
    assert isinstance(price_client.get_client(), price_client.PriceClient)
    with pytest.raises(AssertionError, match="network"):
        holdings.holdings_add("stock", "AAPL", "1")
    with pytest.raises(AssertionError, match="network"):
        holdings.search("BTC")
    for value in ("true", "yes", "0"):
        with pytest.MonkeyPatch.context() as m:
            m.setenv("LEDGERLIGHT_FAKE_PRICES", value)
            assert not price_client.fake_enabled()


class Response:
    def __init__(self, body=None, text=""):
        self.body, self.text = body, text

    def json(self):
        if self.body is None:
            raise ValueError("not json")
        return self.body


YAHOO = {
    # 2026-03-13T20:00:00Z; (202 - 200) / 200 = +1%.
    "AAPL": {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "AAPL",
                        "regularMarketPrice": 202.0,
                        "regularMarketTime": 1773432000,
                        "chartPreviousClose": 200.0,
                    }
                }
            ],
            "error": None,
        }
    },
    "MSFT": {
        "chart": {
            "result": None,
            "error": {"code": "Not Found", "description": "synthetic detail"},
        }
    },
    "%5EGSPC": {"chart": {"result": [], "error": None}},
    "BAD": {"chart": {"result": [{"meta": {}}], "error": None}},
}


def test_real_price_client_parsing_without_network(monkeypatch):
    calls = []

    def fake_request(self, url, params, headers=None):
        calls.append((url, params, headers))
        if url.endswith("/search"):
            return Response(
                {
                    "coins": [
                        {
                            "id": "bitcoin",
                            "symbol": "BTC",
                            "name": "Bitcoin",
                            "market_cap_rank": 1,
                        },
                        {
                            "id": "other",
                            "symbol": "XBT",
                            "name": "Other",
                            "market_cap_rank": 9,
                        },
                    ]
                }
            )
        if url.endswith("/simple/price"):
            return Response({"bitcoin": {"usd": 61000, "usd_24h_change": None}})
        return Response(YAHOO[url.rsplit("/", 1)[1]])

    monkeypatch.setattr(price_client.PriceClient, "_request", fake_request)
    client = price_client.PriceClient()
    assert [c["id"] for c in client.search_coin("btc")] == ["bitcoin"]
    assert client.crypto_prices(["bitcoin"]) == {
        "bitcoin": {"usd": 61000.0, "usd_24h_change": None}
    }
    assert client.stock_prices(["aapl", "MSFT", "^GSPC", "BAD"]) == {
        "AAPL": {
            "price": 202.0,
            "as_of": "2026-03-13T20:00:00Z",
            "change_24h": pytest.approx(1.0),
        },
        # chart.error set, or no result: failed tickers carry a scrubbed error.
        "MSFT": {"error": "No quote returned for MSFT"},
        "^GSPC": {"error": "No quote returned for ^GSPC"},
        "BAD": {"error": "Price source returned invalid data"},
    }
    # Only symbols, ids and tickers are sent; never quantities or names.
    assert calls[0][1] == {"query": "BTC"}
    assert calls[1][1]["ids"] == "bitcoin"
    chart = "https://query1.finance.yahoo.com/v8/finance/chart/"
    assert [c[0] for c in calls[2:]] == [
        chart + "AAPL",
        chart + "BAD",
        chart + "MSFT",
        chart + "%5EGSPC",
    ]
    assert all(c[1] == {"range": "1d", "interval": "1d"} for c in calls[2:])
    assert all(
        c[2] == {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        for c in calls[2:]
    )
    with pytest.raises(ValueError):
        client.crypto_prices(["Bad Id!"])
    for bad in ("AAPL/../x", "A B", "AAPL?x=1", "A" * 16, ""):
        with pytest.raises(ValueError, match="Ticker"):
            client.stock_prices([bad])

    def invalid(self, url, params, headers=None):
        return Response(None)

    monkeypatch.setattr(price_client.PriceClient, "_request", invalid)
    with pytest.raises(price_client.PriceError, match="invalid data"):
        client.search_coin("BTC")


def test_real_request_scrubs_errors_and_retries_once(monkeypatch):
    # Exercise the saved real _request with httpx.get replaced: still no network.
    attempts = []

    def transport(url, params, headers, timeout):
        attempts.append(timeout)
        raise httpx.ConnectError("synthetic secret detail")

    monkeypatch.setattr(price_client.httpx, "get", transport)
    with pytest.raises(price_client.PriceError) as error:
        REAL_REQUEST(price_client.PriceClient(), "https://example.invalid", None)
    assert str(error.value) == "Price source unreachable"
    assert attempts == [10, 10]

    def status(url, params, headers, timeout):
        request = httpx.Request("GET", url)
        return httpx.Response(500, text="synthetic body", request=request)

    monkeypatch.setattr(price_client.httpx, "get", status)
    with pytest.raises(price_client.PriceError) as error:
        REAL_REQUEST(price_client.PriceClient(), "https://example.invalid", None)
    assert str(error.value) == "Price source returned HTTP 500"


def test_price_worker_refreshes_only_with_holdings(prices, monkeypatch):
    calls = []
    monkeypatch.setattr(holdings, "holdings_refresh", lambda: calls.append("refresh"))
    monkeypatch.setattr(
        holdings, "manual_apply_paydown", lambda: calls.append("paydown")
    )

    class Ticks:
        def __init__(self, n):
            self.n = n

        def wait(self, interval):
            assert interval == 900
            self.n -= 1
            return self.n < 0

    holdings.price_worker(Ticks(1))
    assert calls == ["paydown"]
    with connect() as db:
        db.execute("INSERT INTO accounts (id,name,source) VALUES ('h','H','holding')")
        db.execute(
            "INSERT INTO holdings (account_id,kind,symbol,quantity) "
            "VALUES ('h','stock','AAPL',1)"
        )
    holdings.price_worker(Ticks(2))
    assert calls == ["paydown", "refresh", "refresh"]
    stop = threading.Event()
    stop.set()
    holdings.price_worker(stop)  # Returns immediately when already stopped.


@pytest.mark.parametrize("version", [1, 2, 3])
def test_legacy_schema_upgrade_adds_source_and_tables(version):
    # v1: before duplicate-link checks; v2: with plaid_items.institution_id;
    # v3: manual accounts without payment matching columns.
    path = db_path()
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as db:
        db.execute(
            "CREATE TABLE plaid_items (id TEXT PRIMARY KEY, institution TEXT NOT NULL, "
            "access_token_enc TEXT NOT NULL"
            + (", institution_id TEXT" if version >= 2 else "")
            + ")"
        )
        db.execute(
            "CREATE TABLE accounts (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "balance REAL NOT NULL DEFAULT 0)"
        )
        db.execute("INSERT INTO accounts VALUES ('legacy','Legacy',5)")
        db.execute(
            "INSERT INTO plaid_items (id,institution,access_token_enc) "
            "VALUES ('item','Synthetic Bank','synthetic-unused')"
        )
        if version >= 2:
            db.execute("UPDATE plaid_items SET institution_id='ins_synthetic'")
        if version == 3:
            db.execute(
                "CREATE TABLE manual_details (account_id TEXT PRIMARY KEY "
                "REFERENCES accounts(id) ON DELETE CASCADE, kind TEXT NOT NULL, "
                "apr REAL, monthly_payment REAL, payment_day INTEGER, "
                "auto_paydown INTEGER NOT NULL DEFAULT 0, paydown_applied_through TEXT)"
            )
            db.execute(
                "INSERT INTO manual_details (account_id,kind,apr,auto_paydown) "
                "VALUES ('legacy','personal_loan',4.5,0)"
            )
        db.execute(f"PRAGMA user_version = {version}")
        db.commit()
    with connect() as db:
        assert SCHEMA_VERSION == 4
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert (
            db.execute("SELECT source FROM accounts WHERE id='legacy'").fetchone()[0]
            == "plaid"
        )
        assert db.execute("SELECT institution_id FROM plaid_items").fetchone()[0] == (
            "ins_synthetic" if version >= 2 else None
        )
        for name in (
            "manual_details",
            "holdings",
            "loan_payments",
            "loan_payments_transaction",
        ):
            assert db.execute(
                "SELECT 1 FROM sqlite_master WHERE name=?", (name,)
            ).fetchone()
        columns = {r[1] for r in db.execute("PRAGMA table_info(manual_details)")}
        assert {"payment_match", "payment_match_since"} <= columns
        if version == 3:
            row = db.execute(
                "SELECT kind,apr,payment_match,payment_match_since "
                "FROM manual_details WHERE account_id='legacy'"
            ).fetchone()
            assert tuple(row) == ("personal_loan", 4.5, None, None)


def test_sync_all_and_worker_snapshot_unlinked_accounts(prices, monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    sync.sandbox_link()
    cash = holdings.manual_add("cash", "Synthetic Wallet", "75")["id"]
    loan = holdings.manual_add(
        "personal_loan", "Loan", "1000", monthly_payment="100", auto_paydown=True
    )["id"]
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-04-02")
    assert sync.sync_all()["ok"]
    assert snapshots(cash)[-1] == ("2026-04-02", 75)
    # Paydown (Apr 1) is applied before the snapshot.
    assert snapshots(loan)[-1] == ("2026-04-02", 900)
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-04-03")

    class Ticks:
        n = 1

        def wait(self, interval):
            self.n -= 1
            return self.n < 0

    holdings.price_worker(Ticks())
    assert snapshots(cash)[-1] == ("2026-04-03", 75)


def test_auto_paydown_enabled_later_does_not_back_charge(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-01-05")
    id = holdings.manual_add("student_loan", "Loan", "1000")["id"]
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-06-10")
    holdings.manual_update(id, monthly_payment="100", auto_paydown=True)
    assert holdings.manual_apply_paydown()["loans"] == []
    assert balance(id) == 1000
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-07-01")
    assert holdings.manual_apply_paydown()["loans"][0]["payments"] == 1
    assert balance(id) == 900
    # Changing payment terms also restarts the count from today.
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-09-20")
    holdings.manual_update(id, payment_day="15")
    assert holdings.manual_apply_paydown()["loans"] == []
    assert balance(id) == 900
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-10-15")
    holdings.manual_apply_paydown()
    assert balance(id) == 800
    # A rename alone keeps the existing paydown date.
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-11-20")
    holdings.manual_update(id, name="Renamed")
    assert holdings.manual_apply_paydown()["loans"][0]["payments"] == 1


def test_removing_goal_linked_account_updates_or_archives_goals(prices):
    from ledgerlight import money

    wallet = holdings.manual_add("cash", "Wallet", "100")["id"]
    car = holdings.manual_add("other_asset", "Car", "900")["id"]
    shared = money.goals_add("Shared", "500", [wallet, car])["id"]
    only = money.goals_add("Only wallet", "50", [wallet])["id"]
    # A legacy goal still pointing at an already-removed account.
    with connect() as db:
        db.execute(
            "UPDATE goals SET account_ids=? WHERE id=?",
            (json.dumps([car, "gone"]), shared),
        )
        db.execute(
            "UPDATE goals SET account_ids=? WHERE id=?",
            (json.dumps([wallet, car]), only),
        )
    money.goals_update(shared, name="Renamed shared")  # filters "gone"
    with connect() as db:
        db.execute(
            "UPDATE goals SET account_ids=? WHERE id=?", (json.dumps([wallet]), only)
        )
        db.execute(
            "UPDATE goals SET account_ids=? WHERE id=?",
            (json.dumps([wallet, car]), shared),
        )
    preview = invoke("manual", "remove", wallet, "--propose")["diff"]
    assert preview["goals_updated"] == [shared]
    assert preview["goals_archived"] == [only]
    result = invoke("manual", "remove", wallet)
    assert result["goals_archived"] == [only]
    goals = {g["id"]: g for g in money.goals_list()}
    assert goals[shared]["account_ids"] == [car] and not goals[shared]["archived_at"]
    assert goals[only]["account_ids"] == [] and goals[only]["archived_at"]
    renamed = invoke("goals", "update", str(shared), "--name", "After removal")
    assert renamed["name"] == "After removal" and renamed["account_ids"] == [car]


def test_proposal_pins_coin_and_apply_never_searches(prices, monkeypatch):
    created = invoke("holdings", "add", "crypto", "BTC", "1", "--propose")
    with connect() as db:
        stored = json.loads(
            db.execute(
                "SELECT command FROM proposals WHERE id=?", (created["proposal_id"],)
            ).fetchone()[0]
        )
    assert stored["arguments"]["coin_id"] == "bitcoin"
    assert stored["arguments"]["coin_name"] == "Bitcoin"
    assert created["diff"]["name"] == "Bitcoin (BTC)"

    def no_search(self, symbol):
        raise AssertionError("searched again on apply")

    monkeypatch.setattr(price_client.FakePriceClient, "search_coin", no_search)
    result = proposals.apply(created["proposal_id"])
    assert result["coin_id"] == "bitcoin" and result["name"] == "Bitcoin (BTC)"
    assert result["value"] == 60000


def test_stock_price_as_of_comes_from_quote(prices):
    holdings.holdings_add("stock", "AAPL", "1")
    [row] = holdings.holdings_list()
    assert row["price_as_of"] == "2026-03-13T20:00:00Z"
    assert row["price_change_24h"] == 1.0


@pytest.mark.parametrize("case", ["create_add", "apply_add", "apply_refresh", "direct"])
def test_price_fetch_never_holds_the_write_lock(prices, monkeypatch, case):
    holdings.holdings_add("stock", "AAPL", "1")
    started, release = threading.Event(), threading.Event()

    class Slow(price_client.FakePriceClient):
        def _wait(self):
            started.set()
            assert release.wait(10)

        def search_coin(self, symbol):
            self._wait()
            return super().search_coin(symbol)

        def crypto_prices(self, ids):
            self._wait()
            return super().crypto_prices(ids)

        def stock_prices(self, tickers):
            self._wait()
            return super().stock_prices(tickers)

    proposal = None
    if case == "apply_add":
        proposal = invoke("holdings", "add", "crypto", "ETH", "1", "--propose")
    elif case == "apply_refresh":
        proposal = invoke("holdings", "refresh", "--propose")
    monkeypatch.setattr(price_client, "get_client", Slow)
    work = {
        "create_add": lambda: proposals.create(
            holdings.holdings_add, "crypto", "ETH", "1"
        ),
        "apply_add": lambda: proposals.apply(proposal["proposal_id"]),
        "apply_refresh": lambda: proposals.apply(proposal["proposal_id"]),
        "direct": lambda: holdings.holdings_add("crypto", "BTC", "1"),
    }[case]
    errors = []

    def run():
        try:
            work()
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert started.wait(10)
        # A concurrent writer gets the lock while the request is in flight.
        with closing(sqlite3.connect(db_path(), timeout=1)) as other:
            other.execute("BEGIN IMMEDIATE")
            other.execute("INSERT INTO settings(key,value) VALUES ('probe','1')")
            other.commit()
    finally:
        release.set()
        thread.join(15)
    assert not errors, errors


def test_detached_plaid_accounts_get_no_new_snapshots_after_relink(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-15")
    # Distinct public tokens give new account ids, like a real Plaid relink.
    first = sync.link("public-synthetic-first")["id"]
    single = data.networth(1)[0]["total"]
    with connect() as db:
        detached = [
            r[0]
            for r in db.execute("SELECT id FROM accounts WHERE item_id=?", (first,))
        ]
    sync.remove_item(first)  # plain remove: accounts detached, history kept
    sync.link("public-synthetic-second")
    with connect() as db:
        assert all(
            db.execute("SELECT item_id FROM accounts WHERE id=?", (id,)).fetchone()[0]
            is None
            for id in detached
        )
    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-16")
    assert sync.sync_all()["ok"]
    assert data.networth(1) == [{"date": "2026-03-16", "total": single}]
    for id in detached:
        assert [d for d, _ in snapshots(id)] == ["2026-03-15"]

    class Ticks:
        n = 1

        def wait(self, interval):
            self.n -= 1
            return self.n < 0

    monkeypatch.setenv("LEDGERLIGHT_TODAY", "2026-03-17")
    holdings.price_worker(Ticks())
    assert holdings.snapshot_unlinked() == 0
    for id in detached:
        assert [d for d, _ in snapshots(id)] == ["2026-03-15"]
    # Overview still lists detached rows as Plaid rows (unchanged from main),
    # never as manual/holding rows with edit actions.
    rows = [a for g in data.accounts_overview()["groups"] for a in g["accounts"]]
    assert {a["source"] for a in rows if a["id"] in detached} == {"plaid"}


def test_one_failed_ticker_keeps_last_price_others_update(prices, monkeypatch):
    aapl = holdings.holdings_add("stock", "aapl", "2")["id"]
    msft = holdings.holdings_add("stock", "MSFT", "1")["id"]

    class PartlyFailing(price_client.FakePriceClient):
        def stock_prices(self, tickers):
            return {
                "AAPL": {"price": 210.0, "as_of": "2026-03-14T20:00:00Z"},
                "MSFT": {"error": "No quote returned for MSFT"},
            }

    monkeypatch.setattr(price_client, "get_client", PartlyFailing)
    result = holdings.holdings_refresh()
    assert result["refreshed"] == 1
    assert result["errors"] == [
        {"id": msft, "symbol": "MSFT", "error": "No quote returned for MSFT"}
    ]
    rows = {h["id"]: h for h in holdings.holdings_list()}
    assert rows[aapl]["symbol"] == "AAPL" and rows[aapl]["value"] == 420
    assert rows[aapl]["price_as_of"] == "2026-03-14T20:00:00Z"
    assert rows[msft]["value"] == 400 and rows[msft]["price"] == 400
    assert rows[msft]["price_error"] == "No quote returned for MSFT"
    assert (
        "Ticker"
        in invoke("holdings", "add", "stock", "AAPL/X", "1", success=False)["error"]
    )
