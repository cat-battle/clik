from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from clio.models import ClioError
from clio.service import KanbanService
from clio.tui.screens.prompt import PromptScreen


class BoardPickerScreen(ModalScreen[int | None]):
    """Pick a board, or create one. Dismisses with the chosen board's id."""

    BINDINGS = [
        ("n", "new", "New board"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, service: KanbanService, current_id: int) -> None:
        super().__init__()
        self.service = service
        self.current_id = current_id

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog small"):
            yield Label("Boards", classes="dialog-title")
            yield OptionList()
            yield Label("[b]enter[/] open   [b]n[/] new   [b]esc[/] cancel", classes="hint")

    def on_mount(self) -> None:
        boards = self.service.list_boards()
        options = self.query_one(OptionList)
        for board in boards:
            mark = "● " if board.id == self.current_id else "  "
            options.add_option(Option(Text(mark + board.name), id=str(board.id)))
        options.highlighted = next((i for i, b in enumerate(boards) if b.id == self.current_id), 0)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(int(event.option.id))

    def action_new(self) -> None:
        def create(name: str | None) -> None:
            if name is None:
                return
            try:
                self.dismiss(self.service.create_board(name).id)
            except ClioError as exc:
                self.notify(str(exc), severity="error")

        self.app.push_screen(PromptScreen("Name of the new board"), create)

    def action_cancel(self) -> None:
        self.dismiss(None)
