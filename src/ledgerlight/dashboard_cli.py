"""Click adapters for the live UI command bus."""

import json

import click

from ledgerlight import dashboard


def register(cli, emit):
    @cli.group("dashboard")
    def group():
        """Inspect and change the live, versioned card layout."""

    @group.group("default")
    def default_group():
        """Save, restore or inspect the default Home layout."""

    @default_group.command("save")
    def default_save():
        emit(dashboard.default_save())

    @default_group.command("show")
    def default_show():
        emit(dashboard.default_show())

    @default_group.command("reset")
    def default_reset():
        emit(dashboard.change("reset_default"))

    @group.command("list")
    def list_cards():
        emit(dashboard.snapshot(emit_event=True))

    @group.command("add")
    @click.argument("kind", type=click.Choice(dashboard.KINDS))
    @click.option(
        "--props", default="{}", help="Validated JSON object; chart requires chart_id."
    )
    @click.option("--x", type=int, default=0)
    @click.option("--y", type=int)
    @click.option("--w", type=int, default=6)
    @click.option("--h", type=int, default=5)
    def add(kind, props, **geometry):
        try:
            props = json.loads(props)
        except json.JSONDecodeError as exc:
            raise ValueError("props must be valid JSON") from exc
        emit(
            dashboard.change(
                "add",
                kind=kind,
                props=props,
                **{k: v for k, v in geometry.items() if v is not None},
            )
        )

    @group.command("move")
    @click.argument("id")
    @click.option("--x", type=int, required=True)
    @click.option("--y", type=int, required=True)
    def move(**kwargs):
        emit(dashboard.change("move", **kwargs))

    @group.command("resize")
    @click.argument("id")
    @click.option("--w", type=int, required=True)
    @click.option("--h", type=int, required=True)
    def resize(**kwargs):
        emit(dashboard.change("resize", **kwargs))

    @group.command("remove")
    @click.argument("id")
    def remove(id):
        emit(dashboard.change("remove", id=id))

    @group.command("undo")
    def undo():
        emit(dashboard.change("undo"))

    @cli.group("ui")
    def ui_group():
        """Navigate, filter and mark every connected browser tab."""

    @ui_group.command("navigate")
    @click.argument("page", type=click.Choice(dashboard.PAGES))
    def navigate(page):
        emit(dashboard.ui("navigate", page=page))

    @ui_group.command("filter")
    @click.argument("page", type=click.Choice(dashboard.PAGES))
    @click.argument("pairs", nargs=-1, required=True)
    def filter_page(page, pairs):
        filters = {}
        for pair in pairs:
            if "=" not in pair:
                raise ValueError("Filters must use key=value")
            key, value = pair.split("=", 1)
            if key in filters:
                raise ValueError("Duplicate filter key")
            filters[key] = value
        emit(dashboard.ui("filter", page=page, filters=filters))

    @ui_group.command("highlight")
    @click.argument("target")
    def highlight(target):
        emit(dashboard.ui("highlight", target=target))

    @ui_group.command("clear")
    def clear():
        emit(dashboard.ui("clear"))
