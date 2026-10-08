"""The agent-facing interface. Put --json before the command."""

import json
import sqlite3
import sys
from importlib.metadata import version as package_version

import click
import uvicorn

from ledgerlight import (
    charts,
    dashboard_cli,
    data,
    demo,
    holdings_cli,
    money_cli,
    plaid_client,
    sync,
    systemd,
)


def emit(value):
    click.echo(json.dumps(value, allow_nan=False))


class JsonGroup(click.Group):
    def main(self, args=None, **kwargs):
        args = list(sys.argv[1:] if args is None else args)
        kwargs["standalone_mode"] = False
        try:
            return super().main(args, **kwargs)
        except (click.ClickException, ValueError, sqlite3.Error, OSError) as exc:
            message = (
                exc.format_message()
                if isinstance(exc, click.ClickException)
                else str(exc)
            )
            if "--json" in args:
                # Duplicate links carry the same body as the API's HTTP 409.
                emit(
                    exc.payload()
                    if isinstance(exc, sync.DuplicateLinkError)
                    else {"error": message}
                )
            else:
                click.echo(f"Error: {message}", err=True)
            raise SystemExit(1) from exc
        except click.Abort as exc:
            if "--json" in args:
                emit({"error": "Aborted"})
            raise SystemExit(1) from exc


@click.group(cls=JsonGroup)
@click.option(
    "--json", "json_output", is_flag=True, help="Machine-readable output/errors."
)
def cli(json_output):
    """Local, self-hosted personal finance tools."""


@cli.command()
def version():
    """Show the installed version."""
    emit({"version": package_version("ledgerlight")})


@cli.group("demo")
def demo_group():
    """Clearly synthetic sample data."""


@demo_group.command("seed")
def demo_seed():
    """Idempotently insert 90 days of synthetic transactions."""
    emit(demo.seed())


@cli.group("chart")
def chart():
    """Manage saved Vega-Lite charts."""


@chart.command("add")
@click.option("--title", required=True)
@click.option("--sql", required=True)
@click.option(
    "--type",
    "chart_type",
    required=True,
    type=click.Choice(["bar", "line", "area", "arc", "html"]),
)
@click.option("--html", default="")
def chart_add(title, sql, chart_type, html):
    """Validate and save a read-only SQL chart."""
    emit(charts.add(title, sql, chart_type, html=html))


def chart_options(function):
    for decorator in (
        click.option("--title", required=True),
        click.option("--sql", required=True),
        click.option(
            "--type",
            "chart_type",
            required=True,
            type=click.Choice(["bar", "line", "area", "arc", "html"]),
        ),
        click.option("--html", default=""),
    ):
        function = decorator(function)
    return function


@chart.command("preview")
@chart_options
def chart_preview(title, sql, chart_type, html):
    emit(charts.preview(title, sql, chart_type, html))


@chart.command("save")
@chart_options
def chart_save(title, sql, chart_type, html):
    emit(charts.add(title, sql, chart_type, html=html))


@chart.command("edit")
@click.argument("id", type=int)
@chart_options
def chart_edit(id, title, sql, chart_type, html):
    emit(charts.add(title, sql, chart_type, chart_id=id, html=html))


@chart.command("history")
@click.argument("id", type=int)
def chart_history(id):
    emit(charts.history(id))


@chart.command("list")
def chart_list():
    """List charts, specs and current query results."""
    emit(charts.list_charts())


@chart.command("show")
@click.argument("id", type=int)
def chart_show(id):
    """Show one chart and its current query results."""
    emit(charts.show(id))


@chart.command("remove")
@click.argument("id", type=int)
def chart_remove(id):
    """Delete one saved chart (not its source transactions)."""
    charts.remove(id)
    emit({"removed": id})


@cli.command()
@click.option("--port", default=8000, show_default=True, type=click.IntRange(1, 65535))
def serve(port):
    """Serve the API and built web UI on loopback only; stop with Ctrl-C."""
    # Uvicorn logs go to stderr; stdout remains machine-readable.
    emit({"host": "127.0.0.1", "port": port})
    try:
        uvicorn.run("ledgerlight.api:app", host="127.0.0.1", port=port)
    except SystemExit as exc:
        if exc.code:
            raise click.ClickException("Server failed to start; see stderr") from exc


@cli.command("mcp")
@click.option(
    "--port",
    default=8000,
    show_default=True,
    type=click.IntRange(1, 65535),
    help="Existing web server port for links; does not start HTTP.",
)
def mcp_command(port):
    """Run the MCP stdio protocol, with no startup JSON or stdout logging."""
    from ledgerlight.mcp_server import run

    run(port)


@cli.group("plaid")
def plaid_group():
    """Link and inspect Plaid items without exposing access tokens."""


@plaid_group.command("link-token")
def link_token():
    emit(plaid_client.get_client().create_link_token())


@plaid_group.command("exchange")
@click.argument("public_token")
@click.option("--link-token", help="Original Link token (not needed for sandbox-link).")
def exchange(public_token, link_token):
    emit(sync.link(public_token, link_token))


@plaid_group.command("items")
def plaid_items():
    emit(sync.items())


@plaid_group.command("sandbox-link")
def sandbox_link():
    emit(sync.sandbox_link())


@plaid_group.command("remove")
@click.argument("item_id")
@click.option(
    "--delete-local",
    is_flag=True,
    help="Also delete the Item's accounts, transactions, recurring and snapshots.",
)
def plaid_remove(item_id, delete_local):
    """Disconnect an Item; by default retain local transactions for fresh Link."""
    emit(sync.remove_item(item_id, delete_local=delete_local))


@plaid_group.command("duplicates")
def plaid_duplicates():
    """List groups of linked Items that hold the same accounts (read-only)."""
    emit(sync.duplicates())


@cli.command("sync")
@click.option("--wait-history", is_flag=True, help="Wait for historical import.")
@click.option("--timeout", default=600, show_default=True, type=click.IntRange(0))
def sync_command(wait_history, timeout):
    result = sync.wait_history(timeout) if wait_history else sync.sync_all()
    if not result["ok"]:
        result.setdefault("error", "One or more items failed to sync")
    emit(result)
    if not result["ok"]:
        raise SystemExit(1)


@cli.command("snapshot")
def snapshot_command():
    """Apply due loan paydowns, then snapshot today's cached balances (offline)."""
    emit(sync.snapshot())


@cli.group("accounts")
def accounts_group():
    """Local account balances."""


@accounts_group.command("overview")
def accounts_overview():
    emit(data.accounts_overview())


@accounts_group.command("list")
def accounts_list():
    emit(data.accounts())


@cli.group("transactions")
def transactions_group():
    """Query local transactions."""


@transactions_group.command("list")
@click.option("--account")
@click.option("--since")
@click.option("--until")
@click.option("--category")
@click.option("--search")
@click.option("--tag")
@click.option("--limit", default=100, show_default=True, type=int)
def transactions_list(**kwargs):
    emit(data.transactions(**kwargs))


@cli.group("recurring")
def recurring_group():
    """Local recurring streams."""


@recurring_group.command("list")
@click.option("--direction", type=click.Choice(["in", "out"]))
def recurring_list(direction):
    emit(data.recurring(direction))


@cli.command("networth")
@click.option("--days", default=90, show_default=True, type=int)
def networth(days):
    emit(data.networth(days))


@cli.group("systemd")
def systemd_group():
    """Print user units without installing anything."""


@systemd_group.command("print")
def systemd_print():
    emit(systemd.units())


money_cli.register(cli, recurring_group, emit)
dashboard_cli.register(cli, emit)
holdings_cli.register(cli, emit)


def main():
    cli()


if __name__ == "__main__":
    main()
