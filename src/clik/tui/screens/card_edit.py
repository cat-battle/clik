import re
from dataclasses import dataclass, field

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Select, SelectionList, TextArea
from textual.widgets.selection_list import Selection

from clik.models import Card, ClikError, Priority
from clik.service import normalize_tag


def split_tags(text: str) -> list[str]:
    return [t for t in re.split(r"[\s,]+", text) if t]


@dataclass
class CardDraft:
    title: str = ""
    description: str = ""
    priority: Priority = Priority.NONE
    tags: list[str] = field(default_factory=list)
    checklist: list[tuple[str, bool]] = field(default_factory=list)

    @classmethod
    def of(cls, card: Card) -> "CardDraft":
        return cls(
            card.title,
            card.description,
            card.priority,
            [t.name for t in card.tags],
            [(i.text, i.done) for i in card.checklist],
        )


class CardEditScreen(ModalScreen[CardDraft | None]):
    """Edit a draft of a card. Nothing is saved here: the caller gets the draft back."""

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("escape", "cancel", "Cancel"),
        ("delete", "remove_item", "Remove checklist item"),
    ]

    def __init__(self, heading: str, draft: CardDraft | None = None) -> None:
        super().__init__()
        self.heading = heading
        self.draft = draft or CardDraft()
        # SelectionList values must be unique, and two items may share a text.
        self._item_text: dict[int, str] = {}

    def compose(self) -> ComposeResult:
        d = self.draft
        with Vertical(classes="dialog"):
            yield Label(self.heading, classes="dialog-title", markup=False)
            yield Input(d.title, placeholder="Title", id="title")
            yield TextArea(d.description, id="description")
            with Horizontal(id="fields"):
                yield Select(
                    [(p.label, p) for p in Priority],
                    value=d.priority,
                    allow_blank=False,
                    id="priority",
                )
                yield Input(" ".join(d.tags), placeholder="tags, space separated", id="tags")
            yield Label("Checklist", classes="section")
            yield SelectionList(id="checklist")
            yield Input(placeholder="Add a checklist item and press enter", id="new-item")
            yield Label(
                "[b]ctrl+s[/] save   [b]esc[/] cancel   "
                "checklist: [b]space[/] toggle, [b]delete[/] remove",
                classes="hint",
            )

    def on_mount(self) -> None:
        self.query_one("#description", TextArea).border_title = "Description"
        self.query_one("#checklist", SelectionList).border_title = "space toggles"
        for text, done in self.draft.checklist:
            self._add_item(text, done)

    def _add_item(self, text: str, done: bool = False) -> None:
        key = len(self._item_text)
        self._item_text[key] = text
        self.query_one("#checklist", SelectionList).add_option(Selection(Text(text), key, done))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "new-item":
            self.action_save()
        elif event.value.strip():
            self._add_item(event.value.strip())
            event.input.value = ""

    def action_remove_item(self) -> None:
        items = self.query_one("#checklist", SelectionList)
        if items.has_focus and items.highlighted is not None:
            items.remove_option_at_index(items.highlighted)

    def action_save(self) -> None:
        title = self.query_one("#title", Input).value.strip()
        if not title:
            self.notify("A card needs a title", severity="error")
            self.query_one("#title", Input).focus()
            return
        try:
            tags = [normalize_tag(t) for t in split_tags(self.query_one("#tags", Input).value)]
        except ClikError as exc:
            self.notify(str(exc), severity="error")
            return
        items = self.query_one("#checklist", SelectionList)
        checked = set(items.selected)
        keys = [items.get_option_at_index(i).value for i in range(items.option_count)]
        self.dismiss(
            CardDraft(
                title=title,
                description=self.query_one("#description", TextArea).text,
                priority=self.query_one("#priority", Select).value,
                tags=tags,
                checklist=[(self._item_text[k], k in checked) for k in keys],
            )
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
