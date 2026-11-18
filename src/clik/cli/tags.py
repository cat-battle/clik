from typing import Annotated

import typer
from rich.table import Table

from clik.cli import render
from clik.cli.context import svc
from clik.theme import DIM, tag_chips

app = typer.Typer(help="Manage tags.", no_args_is_help=True)


@app.command("ls")
def ls() -> None:
    """List tags and how many cards use each."""
    table = Table.grid(padding=(0, 2))
    for tag, count in svc().list_tags():
        table.add_row(tag_chips((tag,)), f"[{DIM}]{count} card(s)[/]")
    render.console.print(table)


@app.command("color")
def color(
    name: str,
    color: Annotated[
        str, typer.Argument(help="#rrggbb, a name like red/blue/green, or `auto` to reset.")
    ],
) -> None:
    """Pin a tag's color."""
    tag = svc().set_tag_color(name, None if color.lower() == "auto" else color)
    render.console.print(tag_chips((tag,)))


@app.command("rm")
def rm(name: str) -> None:
    """Delete a tag, removing it from every card."""
    render.ok(f"Deleted tag [bold]{svc().delete_tag(name).name}[/]")
