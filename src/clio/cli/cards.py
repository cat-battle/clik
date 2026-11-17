"""Card commands, registered directly on the root app."""

from typing import Annotated

import typer

from clio.cli import render
from clio.cli.context import svc
from clio.models import Priority

BoardOpt = Annotated[
    str | None, typer.Option("-b", "--board", help="Board name or prefix (default: current).")
]
PriorityOpt = Annotated[
    str | None,
    typer.Option("-p", "--priority", help="none, low, medium, high, urgent (or 0-4)."),
]
CardId = Annotated[int, typer.Argument(metavar="ID", help="Card number, as shown by `ls`.")]

check_app = typer.Typer(help="Manage a card's checklist.", no_args_is_help=True)


def _priority(value: str | None) -> Priority | None:
    return None if value is None else Priority.parse(value)


def register(app: typer.Typer) -> None:
    app.command()(add)
    app.command("ls")(ls)
    app.command()(show)
    app.command()(mv)
    app.command()(done)
    app.command()(edit)
    app.command()(rm)
    app.command()(archive)
    app.command()(unarchive)
    app.add_typer(check_app, name="check")


def add(
    title: str,
    board: BoardOpt = None,
    column: Annotated[
        str | None, typer.Option("-c", "--column", help="Column (default: the first).")
    ] = None,
    priority: PriorityOpt = None,
    tag: Annotated[list[str] | None, typer.Option("-t", "--tag", help="Repeatable.")] = None,
    desc: Annotated[str, typer.Option("-d", "--desc", help="Description.")] = "",
    top: Annotated[bool, typer.Option("--top", help="Put it at the top of the column.")] = False,
) -> None:
    """Add a card."""
    card = svc().add_card(
        title,
        board=board,
        column=column,
        description=desc,
        priority=_priority(priority) or Priority.NONE,
        tags=tag or [],
        top=top,
    )
    render.ok(f"Added {render.card_ref(card)} to [bold]{svc().column_of(card).name}[/]")


def ls(
    board: BoardOpt = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Only cards with this tag.")] = None,
    priority: PriorityOpt = None,
    search: Annotated[
        str | None, typer.Option("-s", "--search", help="Text in title or description.")
    ] = None,
    all_: Annotated[bool, typer.Option("--all", help="Include archived cards.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Show a board."""
    view = svc().board_view(
        board, include_archived=all_, tag=tag, priority=_priority(priority), text=search
    )
    if as_json:
        render.print_json(render.board_json(view))
    else:
        render.print_board(view)


def show(
    card_id: CardId,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Show one card in full."""
    card = svc().get_card(card_id)
    column = svc().column_of(card)
    if as_json:
        render.print_json(render.card_json(card, column))
    else:
        render.print_card(card, column, svc().get_board(column.board_id).name)


def mv(
    card_id: CardId,
    column: Annotated[str, typer.Argument(help="Target column name or prefix.")],
    top: Annotated[bool, typer.Option("--top/--bottom", help="Where in the column.")] = False,
) -> None:
    """Move a card to another column (or within its own)."""
    card = svc().move_card(card_id, column, 0 if top else None)
    render.ok(f"Moved {render.card_ref(card)} to [bold]{svc().column_of(card).name}[/]")


def done(card_id: CardId) -> None:
    """Move a card to the board's done column."""
    card = svc().complete_card(card_id)
    render.ok(f"Completed {render.card_ref(card)}")


def edit(
    card_id: CardId,
    title: Annotated[str | None, typer.Option("--title")] = None,
    desc: Annotated[str | None, typer.Option("-d", "--desc")] = None,
    priority: PriorityOpt = None,
    add_tag: Annotated[list[str] | None, typer.Option("--add-tag", help="Repeatable.")] = None,
    rm_tag: Annotated[list[str] | None, typer.Option("--rm-tag", help="Repeatable.")] = None,
) -> None:
    """Change a card's fields."""
    if all(v is None for v in (title, desc, priority, add_tag, rm_tag)):
        raise typer.BadParameter("nothing to change; pass at least one option")
    card = svc().update_card(card_id, title=title, description=desc, priority=_priority(priority))
    if add_tag:
        card = svc().add_tags(card_id, add_tag)
    if rm_tag:
        card = svc().remove_tags(card_id, rm_tag)
    render.ok(f"Updated {render.card_ref(card)}")


def rm(
    card_id: CardId,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Don't ask.")] = False,
) -> None:
    """Delete a card permanently."""
    card = svc().get_card(card_id)
    if not yes:
        typer.confirm(f"Delete #{card.id} {card.title!r}?", abort=True)
    svc().delete_card(card_id)
    render.ok(f"Deleted {render.card_ref(card)}")


def archive(card_id: CardId) -> None:
    """Hide a card from the board without deleting it."""
    render.ok(f"Archived {render.card_ref(svc().archive_card(card_id))}")


def unarchive(card_id: CardId) -> None:
    """Bring an archived card back."""
    render.ok(f"Restored {render.card_ref(svc().unarchive_card(card_id))}")


ItemNo = Annotated[int, typer.Argument(metavar="N", help="Item number, as shown by `show`.")]


@check_app.command("add")
def check_add(card_id: CardId, text: str) -> None:
    """Add a checklist item."""
    card = svc().add_check(card_id, text)
    render.ok(f"Added item {len(card.checklist)} to {render.card_ref(card)}")


@check_app.command("toggle")
def check_toggle(card_id: CardId, number: ItemNo) -> None:
    """Check or uncheck an item."""
    card = svc().toggle_check(card_id, number)
    item = card.checklist[number - 1]
    state = "done" if item.done else "not done"
    render.ok(f"{item.text!r} is {state} ({card.checks_done}/{len(card.checklist)})")


@check_app.command("rm")
def check_rm(card_id: CardId, number: ItemNo) -> None:
    """Remove an item."""
    card = svc().remove_check(card_id, number)
    render.ok(f"Removed item {number} from {render.card_ref(card)}")
