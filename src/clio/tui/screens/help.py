from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

KEYS = [
    ("Move around", ""),
    ("h j k l / arrows", "select column / card"),
    ("g / G", "first / last card in the column"),
    ("Move cards", ""),
    ("H / L", "move card to the column on the left / right"),
    ("J / K", "move card down / up within its column"),
    ("Cards", ""),
    ("a", "add a card to the selected column"),
    ("enter / e", "open the card: title, description, priority, tags, checklist"),
    ("p", "cycle priority"),
    ("t", "edit tags"),
    ("x", "archive (hide; `clio unarchive ID` brings it back)"),
    ("d", "delete"),
    ("Board", ""),
    ("/", "filter by text and/or #tag  (esc clears)"),
    ("b", "switch or create boards"),
    ("c", "manage columns"),
    ("r", "reload from disk"),
    ("?", "this help"),
    ("q", "quit"),
]


class HelpScreen(ModalScreen[None]):
    def compose(self) -> ComposeResult:
        table = Table.grid(padding=(0, 3))
        for keys, what in KEYS:
            if what:
                table.add_row(Text(keys, style="bold"), what)
            else:
                table.add_row(Text(f"\n{keys}", style="bold underline"), "")
        with Vertical(classes="dialog"):
            yield Label("clio keys", classes="dialog-title")
            yield Static(table)
            yield Label("press any key to close", classes="hint")

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self.dismiss(None)

    def on_click(self) -> None:
        self.dismiss(None)
