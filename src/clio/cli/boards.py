from typing import Annotated

import typer
from rich.table import Table

from clio.cli import render
from clio.cli.context import svc
from clio.theme import DIM, OK

app = typer.Typer(help="Manage boards.", no_args_is_help=True)


@app.command("ls")
def ls() -> None:
    """List boards; the current one is marked."""
    current = svc().current_board()
    table = Table.grid(padding=(0, 2))
    for board in svc().list_boards():
        cards = sum(cv.active_count for cv in svc().board_view(board.id).columns)
        mark = f"[{OK}]●[/]" if board.id == current.id else " "
        table.add_row(mark, f"[bold]{board.name}[/]", f"[{DIM}]{cards} card(s)[/]")
    render.console.print(table)


@app.command("new")
def new(
    name: str,
    column: Annotated[
        list[str] | None,
        typer.Option("-c", "--column", help="Repeatable; default Backlog/Todo/Doing/Done."),
    ] = None,
    use: Annotated[bool, typer.Option("--use", help="Switch to it.")] = False,
) -> None:
    """Create a board."""
    board = svc().create_board(name, column) if column else svc().create_board(name)
    if use:
        svc().use_board(board.id)
    render.ok(f"Created board [bold]{board.name}[/]" + (" and switched to it" if use else ""))


@app.command("use")
def use(name: str) -> None:
    """Make a board the current one."""
    render.ok(f"Now on board [bold]{svc().use_board(name).name}[/]")


@app.command("rename")
def rename(name: str, new_name: str) -> None:
    """Rename a board."""
    render.ok(f"Renamed board to [bold]{svc().rename_board(name, new_name).name}[/]")


@app.command("rm")
def rm(
    name: str,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Don't ask.")] = False,
) -> None:
    """Delete a board and every card on it."""
    board = svc().get_board(name)
    if not yes:
        typer.confirm(f"Delete board {board.name!r} and all its cards?", abort=True)
    svc().delete_board(board.id)
    render.ok(f"Deleted board [bold]{board.name}[/]")
