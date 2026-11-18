from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from clik.models import Card
from clik.theme import DIM, checklist_progress, tag_chips


class CardWidget(Static):
    """One card on the board. Priority shows as the left border color (see clik.tcss)."""

    class Clicked(Message):
        def __init__(self, card_id: int) -> None:
            super().__init__()
            self.card_id = card_id

    def __init__(self, card: Card, done: bool) -> None:
        self.card = card
        lines = [Text(f"#{card.id} ", style=DIM).append(card.title, style="" if done else "bold")]
        if card.tags:
            lines.append(tag_chips(card.tags))
        if card.checklist:
            lines.append(checklist_progress(card))
        classes = f"card prio-{int(card.priority)}" + (" done" if done else "")
        super().__init__(Text("\n").join(lines), classes=classes)

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.card.id))
