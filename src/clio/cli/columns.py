from typing import Annotated

import typer
from rich.table import Table

from clio.cli import render
from clio.cli.context import svc
from clio.theme import DIM, OK

app = typer.Typer(help="Manage a board's columns.", no_args_is_help=True)

BoardOpt = Annotated[
    str | None, typer.Option("-b", "--board", help="Board name or prefix (default: current).")
]


@app.command("ls")
def ls(board: BoardOpt = None) -> None:
    """List columns in order."""
    table = Table.grid(padding=(0, 2))
    for number, cv in enumerate(svc().board_view(board).columns, 1):
        col = cv.column
        notes = [f"{cv.active_count} card(s)"]
        if col.wip_limit:
            notes.append(f"WIP limit {col.wip_limit}")
        table.add_row(
            f"[{DIM}]{number}[/]",
            f"[bold]{col.name}[/]",
            f"[{DIM}]{', '.join(notes)}[/]",
            f"[{OK}]done column[/]" if col.is_done else "",
        )
    render.console.print(table)


@app.command("add")
def add(
    name: str,
    board: BoardOpt = None,
    after: Annotated[
        str | None, typer.Option("--after", help="Insert after this column (default: at the end).")
    ] = None,
) -> None:
    """Add a column."""
    render.ok(f"Added column [bold]{svc().add_column(name, board=board, after=after).name}[/]")


@app.command("rename")
def rename(name: str, new_name: str, board: BoardOpt = None) -> None:
    """Rename a column."""
    col = svc().rename_column(name, new_name, board=board)
    render.ok(f"Renamed column to [bold]{col.name}[/]")


@app.command("mv")
def mv(
    name: str,
    position: Annotated[int, typer.Argument(min=1, help="New position, counting from 1.")],
    board: BoardOpt = None,
) -> None:
    """Move a column to a new position."""
    col = svc().move_column(name, position - 1, board=board)
    render.ok(f"Moved column [bold]{col.name}[/] to position {col.position + 1}")


@app.command("rm")
def rm(
    name: str,
    board: BoardOpt = None,
    move_to: Annotated[
        str | None, typer.Option("--move-to", help="Column that takes over this one's cards.")
    ] = None,
) -> None:
    """Delete a column. A column holding cards needs --move-to."""
    col = svc().delete_column(name, board=board, move_to=move_to)
    render.ok(f"Deleted column [bold]{col.name}[/]")


@app.command("wip")
def wip(
    name: str,
    limit: Annotated[int, typer.Argument(min=0, help="Max cards; 0 removes the limit.")],
    board: BoardOpt = None,
) -> None:
    """Set a column's work-in-progress limit (advisory: it is highlighted, not enforced)."""
    col = svc().set_wip_limit(name, limit, board=board)
    if col.wip_limit:
        render.ok(f"WIP limit for [bold]{col.name}[/] is {col.wip_limit}")
    else:
        render.ok(f"Removed the WIP limit from [bold]{col.name}[/]")


@app.command("done")
def done(name: str, board: BoardOpt = None) -> None:
    """Mark a column as the one finished cards go to."""
    col = svc().set_done_column(name, board=board)
    render.ok(f"[bold]{col.name}[/] is now the done column")
