import sys
from pathlib import Path
from typing import Annotated

import typer

from clio import __version__
from clio.cli import boards, cards, columns, context, render, tags
from clio.models import ClioError

app = typer.Typer(
    help="clio: a terminal kanban. Run with no command to open the board.",
    context_settings={"help_option_names": ["-h", "--help"]},
    pretty_exceptions_show_locals=False,
)
cards.register(app)
app.add_typer(boards.app, name="board")
app.add_typer(columns.app, name="column")
app.add_typer(tags.app, name="tag")


def _version(value: bool) -> None:
    if value:
        print(f"clio {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Database file (default: $CLIO_DB, else your user data dir)."),
    ] = None,
    version: Annotated[
        bool, typer.Option("--version", callback=_version, is_eager=True, help="Show version.")
    ] = False,
) -> None:
    context.set_db(db)
    if ctx.invoked_subcommand is None:
        from clio.tui.app import ClioApp

        ClioApp(context.svc()).run()


def main(argv: list[str] | None = None) -> None:
    try:
        app(args=argv)
    except ClioError as exc:
        render.error(str(exc))
        sys.exit(1)
    finally:
        context.close()
