"""Thin Click adapters for manual accounts and price-tracked holdings."""

import click

from ledgerlight import holdings, proposals


def register(cli, emit):
    @cli.group()
    def manual():
        """Accounts Plaid does not cover: loans, cash and other assets."""

    @manual.command("add")
    @click.option(
        "--kind", type=click.Choice(sorted(holdings.MANUAL_KINDS)), required=True
    )
    @click.option("--name", required=True)
    @click.option("--balance", required=True, help="Loans: the amount owed.")
    @click.option("--apr", help="Loans: annual rate in percent, e.g. 5.5.")
    @click.option("--payment", "monthly_payment", help="Loans: monthly payment.")
    @click.option("--payment-day", help="Loans: day of month 1-28 (default 1).")
    @click.option("--auto-paydown", is_flag=True, help="Loans: apply payments monthly.")
    @click.option(
        "--payment-match",
        help="Loans: pay down from linked outflows whose name/merchant contains TEXT.",
    )
    @click.option(
        "--payment-match-since", help="Loans: match from this date (default today)."
    )
    @proposals.proposable
    def manual_add(**kwargs):
        emit(proposals.execute(holdings.manual_add, **kwargs))

    @manual.command("list")
    def manual_list():
        emit(holdings.manual_list())

    @manual.command("update")
    @click.argument("id")
    @click.option("--name")
    @click.option("--balance", help="Resets the paydown date to today.")
    @click.option("--apr", help="Empty string clears.")
    @click.option("--payment", "monthly_payment", help="Empty string clears.")
    @click.option("--payment-day", help="Empty string clears.")
    @click.option("--auto-paydown/--no-auto-paydown", default=None)
    @click.option("--payment-match", help="Empty string clears (and its since date).")
    @click.option(
        "--payment-match-since",
        help="Match from this date; default today when the match text changes.",
    )
    @proposals.proposable
    def manual_update(**kwargs):
        emit(proposals.execute(holdings.manual_update, **kwargs))

    @manual.command("remove")
    @click.argument("id")
    @proposals.proposable
    def manual_remove(id):
        emit(proposals.execute(holdings.manual_remove, id))

    @manual.command("apply-paydown")
    @proposals.proposable
    def manual_apply_paydown():
        emit(proposals.execute(holdings.manual_apply_paydown))

    @manual.command("payments")
    @click.argument("id")
    def manual_payments(id):
        """Transactions applied to a loan by payment matching (read-only)."""
        emit(holdings.manual_payments(id))

    @manual.command("apply-payments")
    @proposals.proposable
    def manual_apply_payments():
        """Deduct newly matched transactions from loan balances (also after sync)."""
        emit(proposals.execute(holdings.manual_apply_payments))

    @cli.group("holdings")
    def holdings_group():
        """Crypto and stock positions valued by live price."""

    @holdings_group.command("add")
    @click.argument("kind", type=click.Choice(sorted(holdings.HOLDING_KINDS)))
    @click.argument("symbol")
    @click.argument("quantity")
    @click.option("--coin-id", help="Crypto: explicit CoinGecko id, e.g. bitcoin.")
    @click.option("--name")
    @proposals.proposable
    def holdings_add(**kwargs):
        emit(proposals.execute(holdings.holdings_add, **kwargs))

    @holdings_group.command("list")
    def holdings_list():
        emit(holdings.holdings_list())

    @holdings_group.command("update")
    @click.argument("id")
    @click.option("--quantity")
    @click.option("--name")
    @proposals.proposable
    def holdings_update(**kwargs):
        emit(proposals.execute(holdings.holdings_update, **kwargs))

    @holdings_group.command("remove")
    @click.argument("id")
    @proposals.proposable
    def holdings_remove(id):
        emit(proposals.execute(holdings.holdings_remove, id))

    @holdings_group.command("refresh")
    @proposals.proposable
    def holdings_refresh():
        emit(proposals.execute(holdings.holdings_refresh))

    @holdings_group.command("search")
    @click.argument("symbol")
    def holdings_search(symbol):
        """CoinGecko candidates for a crypto symbol (sends only the symbol)."""
        emit(holdings.search(symbol))
