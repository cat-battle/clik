from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from clio.models import ColumnView
from clio.theme import DIM, WARN
from clio.tui.widgets.card import CardWidget


class ColumnWidget(Vertical):
    def __init__(self, view: ColumnView) -> None:
        super().__init__(classes="column")
        self.view = view

    def compose(self) -> ComposeResult:
        col = self.view.column
        count = self.view.active_count
        shown = f"{count}/{col.wip_limit}" if col.wip_limit else str(count)
        header = Text(col.name, style="bold")
        header.append(f"  {shown}", style=f"bold {WARN}" if self.view.over_wip else DIM)
        if col.is_done:
            header.append("  ✓", style=DIM)
        yield Static(header, classes="column-header")

        body = VerticalScroll(classes="column-body")
        # Navigation is the board screen's job; a focusable scroller would steal the arrow keys.
        body.can_focus = False
        with body:
            if not self.view.cards:
                yield Static(Text("—", style=DIM), classes="empty")
            for card in self.view.cards:
                yield CardWidget(card, done=col.is_done)
