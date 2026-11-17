from collections.abc import Callable
from typing import TypeVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Input, Static

from clio.models import BoardView, Card, ClioError, ColumnView, Priority
from clio.service import KanbanService
from clio.theme import DIM
from clio.tui.screens.board_picker import BoardPickerScreen
from clio.tui.screens.card_edit import CardDraft, CardEditScreen, split_tags
from clio.tui.screens.columns import ColumnsScreen
from clio.tui.screens.confirm import ConfirmScreen
from clio.tui.screens.help import HelpScreen
from clio.tui.screens.prompt import PromptScreen
from clio.tui.widgets.card import CardWidget
from clio.tui.widgets.column import ColumnWidget

T = TypeVar("T")


def _hidden(keys: str, action: str) -> Binding:
    return Binding(keys, action, show=False)


class BoardScreen(Screen[None]):
    """The board. Selection is our own state (a column and a row per column), not widget focus."""

    # Nothing on the board takes focus; the keys below drive it directly.
    AUTO_FOCUS = ""

    BINDINGS = [
        _hidden("h,left", "column(-1)"),
        _hidden("l,right", "column(1)"),
        _hidden("k,up", "row(-1)"),
        _hidden("j,down", "row(1)"),
        _hidden("g,home", "edge(0)"),
        _hidden("G,end", "edge(-1)"),
        _hidden("H,shift+left", "move_column(-1)"),
        _hidden("L,shift+right", "move_column(1)"),
        _hidden("K,shift+up", "move_row(-1)"),
        _hidden("J,shift+down", "move_row(1)"),
        Binding("a", "add", "Add"),
        Binding("enter,e", "edit", "Open"),
        _hidden("p", "priority"),
        _hidden("t", "tags"),
        _hidden("x", "archive"),
        Binding("d", "delete", "Delete"),
        Binding("slash", "filter", "Filter", key_display="/"),
        Binding("b", "boards", "Boards"),
        _hidden("c", "columns"),
        _hidden("r", "reload"),
        _hidden("escape", "clear_filter"),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, service: KanbanService) -> None:
        super().__init__()
        self.service = service
        self.board_id = service.current_board().id
        self.view: BoardView = service.board_view(self.board_id)
        self.col = 0
        self.rows: dict[int, int] = {}  # column id -> selected row
        self.filter = ""
        self._widgets: dict[int, CardWidget] = {}

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        yield Horizontal(id="board")
        yield Input(placeholder="filter: text and/or #tag", id="filter", disabled=True)
        yield Footer()

    async def on_mount(self) -> None:
        await self.reload()

    # -- state --------------------------------------------------------------

    @property
    def current_column(self) -> ColumnView:
        return self.view.columns[self.col]

    @property
    def current_card(self) -> Card | None:
        cv = self.current_column
        return cv.cards[self.rows.get(cv.column.id, 0)] if cv.cards else None

    def _try(self, call: Callable[[], T]) -> T | None:
        """Run a service call; show a failure instead of crashing."""
        try:
            return call()
        except ClioError as exc:
            self.notify(str(exc), severity="error")
            return None

    def _filter_args(self) -> dict:
        words = self.filter.split()
        tags = [w for w in words if w.startswith("#") and len(w) > 1]
        text = " ".join(w for w in words if w not in tags)
        return {"tags": tags, "text": text or None}

    async def reload(self, select: int | None = None) -> None:
        """Re-read the board and rebuild it; optionally select the card with id `select`."""
        view = self._try(lambda: self.service.board_view(self.board_id, **self._filter_args()))
        if view is None:
            return
        self.view = view
        self.col = max(0, min(self.col, len(view.columns) - 1))
        for index, cv in enumerate(view.columns):
            ids = [c.id for c in cv.cards]
            if select in ids:
                self.col, self.rows[cv.column.id] = index, ids.index(select)
            row = self.rows.get(cv.column.id, 0)
            self.rows[cv.column.id] = max(0, min(row, len(ids) - 1))

        board = self.query_one("#board", Horizontal)
        await board.remove_children()
        await board.mount(*(ColumnWidget(cv) for cv in view.columns))
        self._widgets = {w.card.id: w for w in self.query(CardWidget)}

        bar = Text(" clio ", style="bold reverse")
        bar.append(f"  {view.board.name}", style="bold")
        if self.filter:
            bar.append(f"   filter: {self.filter}", style=DIM)
        self.query_one("#topbar", Static).update(bar)
        self._show_selection()

    def _show_selection(self) -> None:
        for index, column in enumerate(self.query(ColumnWidget)):
            column.set_class(index == self.col, "active")
        card = self.current_card
        for widget in self._widgets.values():
            widget.set_class(card is not None and widget.card.id == card.id, "selected")
        columns = list(self.query(ColumnWidget))
        if columns:
            columns[self.col].scroll_visible(animate=False)
        if card is not None:
            self._widgets[card.id].scroll_visible(animate=False)

    # -- navigation ---------------------------------------------------------

    def action_column(self, delta: int) -> None:
        self.col = max(0, min(self.col + delta, len(self.view.columns) - 1))
        self._show_selection()

    def action_row(self, delta: int) -> None:
        cv = self.current_column
        if cv.cards:
            row = self.rows.get(cv.column.id, 0) + delta
            self.rows[cv.column.id] = max(0, min(row, len(cv.cards) - 1))
            self._show_selection()

    def action_edge(self, row: int) -> None:
        cv = self.current_column
        if cv.cards:
            self.rows[cv.column.id] = row % len(cv.cards)
            self._show_selection()

    def on_card_widget_clicked(self, event: CardWidget.Clicked) -> None:
        was_selected = self.current_card is not None and self.current_card.id == event.card_id
        for index, cv in enumerate(self.view.columns):
            ids = [c.id for c in cv.cards]
            if event.card_id in ids:
                self.col, self.rows[cv.column.id] = index, ids.index(event.card_id)
        self._show_selection()
        if was_selected:
            self.action_edit()

    # -- moving cards -------------------------------------------------------

    async def action_move_column(self, delta: int) -> None:
        card, target = self.current_card, self.col + delta
        if card is None or not 0 <= target < len(self.view.columns):
            return
        column = self.view.columns[target].column
        if self._try(lambda: self.service.move_card(card.id, column.id, 0)):
            await self.reload(select=card.id)

    async def action_move_row(self, delta: int) -> None:
        cv, card = self.current_column, self.current_card
        if card is None:
            return
        row = self.rows[cv.column.id] + delta
        if not 0 <= row < len(cv.cards):
            return
        # Swap with the visible neighbour, which under a filter may not be the adjacent card.
        position = cv.cards[row].position
        if self._try(lambda: self.service.move_card(card.id, cv.column.id, position)):
            await self.reload(select=card.id)

    # -- editing ------------------------------------------------------------

    def action_add(self) -> None:
        column = self.current_column.column

        async def save(draft: CardDraft | None) -> None:
            if draft is None:
                return

            def create() -> Card:
                card = self.service.add_card(
                    draft.title,
                    board=self.board_id,
                    column=column.id,
                    description=draft.description,
                    priority=draft.priority,
                    tags=draft.tags,
                )
                return self.service.set_checklist(card.id, draft.checklist)

            card = self._try(create)
            await self.reload(select=card.id if card else None)

        self.app.push_screen(CardEditScreen(f"New card in {column.name}"), save)

    def action_edit(self) -> None:
        card = self.current_card
        if card is None:
            return

        async def save(draft: CardDraft | None) -> None:
            if draft is None:
                return

            def update() -> Card:
                self.service.update_card(
                    card.id,
                    title=draft.title,
                    description=draft.description,
                    priority=draft.priority,
                    tags=draft.tags,
                )
                return self.service.set_checklist(card.id, draft.checklist)

            self._try(update)
            await self.reload(select=card.id)

        self.app.push_screen(CardEditScreen(f"Card #{card.id}", CardDraft.of(card)), save)

    async def action_priority(self) -> None:
        card = self.current_card
        if card is None:
            return
        following = Priority((card.priority + 1) % len(Priority))
        if self._try(lambda: self.service.update_card(card.id, priority=following)):
            await self.reload(select=card.id)

    def action_tags(self) -> None:
        card = self.current_card
        if card is None:
            return

        async def save(answer: str | None) -> None:
            if answer is None:
                return
            self._try(lambda: self.service.update_card(card.id, tags=split_tags(answer)))
            await self.reload(select=card.id)

        current = " ".join(t.name for t in card.tags)
        self.app.push_screen(
            PromptScreen(f"Tags for #{card.id}", current, "tags, space separated"), save
        )

    async def action_archive(self) -> None:
        card = self.current_card
        if card is not None and self._try(lambda: self.service.archive_card(card.id)):
            self.notify(f"Archived #{card.id}. Restore with: clio unarchive {card.id}")
            await self.reload()

    def action_delete(self) -> None:
        card = self.current_card
        if card is None:
            return

        async def confirmed(yes: bool | None) -> None:
            if yes and self._try(lambda: self.service.delete_card(card.id)):
                await self.reload()

        self.app.push_screen(ConfirmScreen(f"Delete #{card.id} {card.title!r}?"), confirmed)

    # -- board-level --------------------------------------------------------

    def action_boards(self) -> None:
        async def chosen(board_id: int | None) -> None:
            if board_id is None:
                return
            if self._try(lambda: self.service.use_board(board_id)):
                self.board_id, self.col = board_id, 0
            await self.reload()

        self.app.push_screen(BoardPickerScreen(self.service, self.board_id), chosen)

    def action_columns(self) -> None:
        async def closed(_: None) -> None:
            await self.reload()

        self.app.push_screen(ColumnsScreen(self.service, self.board_id), closed)

    async def action_reload(self) -> None:
        await self.reload()

    def action_filter(self) -> None:
        box = self.query_one("#filter", Input)
        box.disabled = False
        box.add_class("open")
        box.focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        self.filter = event.value.strip()
        await self.reload()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Keep the filter applied, hand the keyboard back to the board.
        self.set_focus(None)
        event.input.disabled = True
        event.input.set_class(bool(self.filter), "open")

    def action_clear_filter(self) -> None:
        box = self.query_one("#filter", Input)
        box.value = ""
        box.disabled = True
        box.remove_class("open")
        self.set_focus(None)

    def action_help(self) -> None:
        self.app.push_screen(HelpScreen())

    def action_quit(self) -> None:
        self.app.exit()
