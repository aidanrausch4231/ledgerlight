"""Thin Click adapters for money-management operations."""

import click

from ledgerlight import money, proposals


def register(cli, recurring_group, emit):
    @cli.group()
    def rules():
        """Case-insensitive merchant/name category rules."""

    @rules.command("add")
    @click.option(
        "--match-field", type=click.Choice(["merchant", "name"]), required=True
    )
    @click.option(
        "--match-type", type=click.Choice(["exact", "contains"]), required=True
    )
    @click.option("--pattern", required=True)
    @click.option("--category", required=True)
    @click.option("--priority", default=100, type=int)
    @proposals.proposable
    def rules_add(**kwargs):
        emit(proposals.execute(money.rules_add, **kwargs))

    @rules.command("list")
    def rules_list():
        emit(money.rules_list())

    @rules.command("remove")
    @click.argument("id", type=int)
    @proposals.proposable
    def rules_remove(id):
        emit(proposals.execute(money.rules_remove, id))

    @rules.command("apply")
    @proposals.proposable
    def rules_apply():
        emit(proposals.execute(money.rules_apply))

    @cli.group()
    def budgets():
        """Monthly category limits and progress."""

    @budgets.command("set")
    @click.argument("category")
    @click.argument("monthly_limit")
    @proposals.proposable
    def budgets_set(**kwargs):
        emit(proposals.execute(money.budgets_set, **kwargs))

    @budgets.command("list")
    def budgets_list():
        emit(money.budgets_list())

    @budgets.command("remove")
    @click.argument("category")
    @proposals.proposable
    def budgets_remove(category):
        emit(proposals.execute(money.budgets_remove, category))

    @budgets.command("report")
    @click.option("--month")
    def budgets_report(month):
        emit(money.budgets_report(month))

    @cli.group()
    def txn():
        """Notes, visibility, tags and exact signed splits."""

    @txn.command("note")
    @click.argument("id")
    @click.argument("text")
    @proposals.proposable
    def txn_note(id, text):
        emit(proposals.execute(money.txn_change, id, "note", note=text))

    def simple_action(action):
        @txn.command(action)
        @click.argument("id")
        @proposals.proposable
        def command(id):
            emit(proposals.execute(money.txn_change, id, action))

    for action in ("hide", "unhide", "unsplit"):
        simple_action(action)

    @txn.command("tag")
    @click.argument("id")
    @click.argument("tags", nargs=-1, required=True)
    @proposals.proposable
    def txn_tag(id, tags):
        emit(proposals.execute(money.txn_change, id, "tag", tags=tags))

    @txn.command("untag")
    @click.argument("id")
    @click.argument("tag")
    @proposals.proposable
    def txn_untag(id, tag):
        emit(proposals.execute(money.txn_change, id, "untag", tags=[tag]))

    @txn.command("split")
    @click.argument("id")
    @click.option("--part", "parts", multiple=True, required=True)
    @proposals.proposable
    def txn_split(id, parts):
        emit(proposals.execute(money.txn_change, id, "split", parts=parts))

    @cli.group()
    def spending():
        """Posted, visible spending with splits."""

    @spending.command("ask")
    @click.argument("text")
    @click.option("--months", type=int, default=12)
    def spending_ask(text, months):
        from ledgerlight.spending import ask

        emit(ask(text, months))

    @spending.command("summary")
    @click.option("--month")
    def spending_summary(month):
        emit(money.spending_summary(month))

    @cli.command("cashflow")
    @click.option("--months", default=6, type=int)
    def cashflow(months):
        emit(money.cashflow(months))

    @cli.group()
    def bills():
        """Upcoming active outflow streams."""

    @bills.command("upcoming")
    @click.option("--days", default=30, type=int)
    def bills_upcoming(days):
        emit(money.bills_upcoming(days))

    @recurring_group.command("mark")
    @click.argument("id")
    @click.option(
        "--status",
        required=True,
        type=click.Choice(["cancel_intent", "ignored", "null"]),
    )
    @proposals.proposable
    def recurring_mark(id, status):
        emit(
            proposals.execute(
                money.recurring_mark, id, None if status == "null" else status
            )
        )

    @cli.group()
    def alerts():
        """In-app bill, balance and budget alerts."""

    @alerts.command("list")
    @click.option("--all", is_flag=True)
    def alerts_list(all):
        emit(money.alerts_list(all))

    @alerts.command("dismiss")
    @click.argument("id", type=int)
    @proposals.proposable
    def alerts_dismiss(id):
        emit(proposals.execute(money.alerts_dismiss, id))

    @alerts.command("refresh")
    @proposals.proposable
    def alerts_refresh():
        emit(proposals.execute(money.alerts_refresh))

    @cli.group()
    def settings():
        """Alert thresholds (not environment credentials)."""

    @settings.command("get")
    @click.argument("key", required=False)
    def settings_get(key):
        emit(money.settings_get(key))

    @settings.command("set")
    @click.argument("key")
    @click.argument("value")
    @proposals.proposable
    def settings_set(key, value):
        emit(proposals.execute(money.settings_set, key, value))

    @cli.group()
    def goals():
        """Savings tracking only; never moves money."""

    @goals.command("add")
    @click.option("--name", required=True)
    @click.option("--target-amount", required=True)
    @click.option("--target-date")
    @click.option("--account", "account_ids", multiple=True, required=True)
    @proposals.proposable
    def goals_add(**kwargs):
        emit(proposals.execute(money.goals_add, **kwargs))

    @goals.command("list")
    def goals_list():
        emit(money.goals_list())

    @goals.command("update")
    @click.argument("id", type=int)
    @click.option("--name")
    @click.option("--target-amount")
    @click.option("--target-date", help="Empty string clears the date.")
    @click.option("--account", "account_ids", multiple=True)
    @proposals.proposable
    def goals_update(**kwargs):
        kwargs["account_ids"] = kwargs["account_ids"] or None
        emit(proposals.execute(money.goals_update, **kwargs))

    @goals.command("archive")
    @click.argument("id", type=int)
    @proposals.proposable
    def goals_archive(id):
        emit(proposals.execute(money.goals_archive, id))
