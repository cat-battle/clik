from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from clio.models import ClioError, ColumnView
from clio.service import KanbanService
from clio.theme import DIM, OK
from clio.tui.screens.prompt import PromptScreen


class ColumnsScreen(ModalScreen[None]):
    """Add, rename, reorder and delete the columns of one board."""

    BINDINGS = [
        ("a", "add", "Add"),
        ("r", "rename", "Rename"),
        ("K", "shift(-1)", "Move up"),
        ("J", "shift(1)", "Move down"),
        ("w", "wip", "WIP limit"),
        ("m", "mark_done", "Mark as done column"),
        ("d", "delete", "Delete"),
        ("escape", "close", "Close"),
    ]

    def __init__(self, service: KanbanService, board_id: int) -> None:
        super().__init__()
        self.service = service
        self.board_id = board_id
        self.views: tuple[ColumnView, ...] = ()

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog small"):
            yield Label("Columns", classes="dialog-title")
            yield OptionList()
            yield Label(
                "[b]a[/] add   [b]r[/] rename   [b]J/K[/] move   [b]w[/] WIP limit\n"
                "[b]m[/] mark as done column   [b]d[/] delete   [b]esc[/] close",
                classes="hint",
            )

    def on_mount(self) -> None:
        self._refresh(0)

    def _refresh(self, highlight: int) -> None:
        self.views = self.service.board_view(self.board_id).columns
        options = self.query_one(OptionList)
        options.clear_options()
        for cv in self.views:
            col = cv.column
            line = Text(col.name, style="bold")
            line.append(f"  {cv.active_count} card(s)", style=DIM)
            if col.wip_limit:
                line.append(f"  WIP {col.wip_limit}", style=DIM)
            if col.is_done:
                line.append("  ✓ done column", style=OK)
            options.add_option(Option(line))
        options.highlighted = max(0, min(highlight, len(self.views) - 1))

    @property
    def _index(self) -> int:
        return self.query_one(OptionList).highlighted or 0

    def _run(self, change: Callable[[], object], highlight: int | None = None) -> None:
        try:
            change()
        except ClioError as exc:
            self.notify(str(exc), severity="error")
        self._refresh(self._index if highlight is None else highlight)

    def _ask(self, question: str, then: Callable[[str], None], value: str = "") -> None:
        def answered(answer: str | None) -> None:
            if answer is not None:
                then(answer)

        self.app.push_screen(PromptScreen(question, value), answered)

    def action_add(self) -> None:
        index, col = self._index, self.views[self._index].column
        self._ask(
            f"Name of the new column (goes after {col.name})",
            lambda name: self._run(
                lambda: self.service.add_column(name, board=self.board_id, after=col.id),
                index + 1,
            ),
        )

    def action_rename(self) -> None:
        col = self.views[self._index].column
        self._ask(
            f"New name for {col.name}",
            lambda name: self._run(
                lambda: self.service.rename_column(col.id, name, board=self.board_id)
            ),
            col.name,
        )

    def action_shift(self, delta: int) -> None:
        index = self._index
        target = index + delta
        if 0 <= target < len(self.views):
            col = self.views[index].column
            self._run(lambda: self.service.move_column(col.id, target, board=self.board_id), target)

    def action_wip(self) -> None:
        col = self.views[self._index].column

        def apply(answer: str) -> None:
            if not answer.strip().isdigit():
                self.notify("Enter a number (0 for no limit)", severity="error")
                return
            self._run(lambda: self.service.set_wip_limit(col.id, int(answer), board=self.board_id))

        self._ask(f"WIP limit for {col.name} (0 for none)", apply, str(col.wip_limit or ""))

    def action_mark_done(self) -> None:
        col = self.views[self._index].column
        self._run(lambda: self.service.set_done_column(col.id, board=self.board_id))

    def action_delete(self) -> None:
        cv = self.views[self._index]
        col = cv.column
        total = len(
            self.service.board_view(self.board_id, include_archived=True).columns[self._index].cards
        )
        if not total:
            self._run(lambda: self.service.delete_column(col.id, board=self.board_id))
            return
        self._ask(
            f"{col.name} holds {total} card(s). Move them to which column?",
            lambda target: self._run(
                lambda: self.service.delete_column(col.id, board=self.board_id, move_to=target)
            ),
        )

    def action_close(self) -> None:
        self.dismiss(None)
