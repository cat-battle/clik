"""Rich output for the one-shot commands."""

import json
from dataclasses import asdict
from typing import Any

from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from clik.models import BoardView, Card, Column
from clik.theme import DIM, OK, PRIORITY_COLORS, WARN, checklist_progress, priority_text, tag_chips

console = Console()


def error(message: str) -> None:
    Console(stderr=True).print(Text("Error: ", style=f"bold {WARN}") + Text(message))


def ok(message: str) -> None:
    console.print(Text("✓ ", style=OK) + Text.from_markup(message))


def card_ref(card: Card) -> str:
    return f"[bold]#{card.id}[/] {card.title!r}"


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2))


def _card_dict(card: Card) -> dict:
    return asdict(card) | {"priority": card.priority.label}


def card_json(card: Card, column: Column) -> dict:
    return _card_dict(card) | {"column": column.name}


def board_json(view: BoardView) -> dict:
    return {
        "board": asdict(view.board),
        "columns": [
            asdict(cv.column) | {"cards": [_card_dict(c) for c in cv.cards]} for cv in view.columns
        ],
    }


def _card_panel(card: Card, dim: bool) -> Panel:
    title = Text(f"#{card.id} ", style=DIM)
    title.append(card.title, style="dim" if dim else "bold")
    lines: list[Text] = [title]
    if card.tags:
        lines.append(tag_chips(card.tags))
    if card.checklist:
        lines.append(checklist_progress(card))
    if card.archived:
        lines.append(Text("archived", style=f"italic {DIM}"))
    return Panel(
        Group(*lines),
        border_style=DIM if dim else PRIORITY_COLORS[card.priority],
        padding=(0, 1),
    )


def print_board(view: BoardView) -> None:
    table = Table(
        title=Text(view.board.name, style="bold"),
        expand=True,
        box=None,
        padding=(0, 1),
        show_header=True,
    )
    cells = []
    for cv in view.columns:
        col = cv.column
        count = f"{cv.active_count}/{col.wip_limit}" if col.wip_limit else str(cv.active_count)
        header = Text(col.name, style="bold " + (OK if col.is_done else "#89b4fa"))
        header.append(f"  {count}", style=f"bold {WARN}" if cv.over_wip else DIM)
        table.add_column(header, ratio=1, overflow="fold")
        dim = col.is_done
        cells.append(
            Group(*(_card_panel(c, dim or c.archived) for c in cv.cards))
            if cv.cards
            else Padding(Text("—", style=DIM), (0, 2))
        )
    table.add_row(*cells)
    console.print(table)


def print_card(card: Card, column: Column, board_name: str) -> None:
    meta = Table.grid(padding=(0, 2))
    meta.add_row(Text("board", style=DIM), board_name)
    meta.add_row(Text("column", style=DIM), column.name)
    meta.add_row(Text("priority", style=DIM), priority_text(card.priority))
    if card.tags:
        meta.add_row(Text("tags", style=DIM), tag_chips(card.tags))
    meta.add_row(Text("created", style=DIM), card.created_at)
    meta.add_row(Text("updated", style=DIM), card.updated_at)
    if card.completed_at:
        meta.add_row(Text("completed", style=DIM), card.completed_at)
    if card.archived_at:
        meta.add_row(Text("archived", style=DIM), card.archived_at)

    parts: list[Any] = [meta]
    if card.description:
        parts += [Text(), Text(card.description)]
    if card.checklist:
        parts += [Text(), checklist_progress(card, width=12)]
        for number, item in enumerate(card.checklist, 1):
            line = Text(f"{number:>2}. ", style=DIM)
            line.append("☑ " if item.done else "☐ ", style=OK if item.done else "")
            line.append(item.text, style=f"strike {DIM}" if item.done else "")
            parts.append(line)

    title = Text(f"#{card.id} ", style=DIM)
    title.append(card.title, style="bold")
    console.print(
        Panel(
            Group(*parts),
            title=title,
            title_align="left",
            border_style=PRIORITY_COLORS[card.priority],
            padding=(1, 2),
        )
    )
