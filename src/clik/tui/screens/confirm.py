from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label


class ConfirmScreen(ModalScreen[bool]):
    """A yes/no question. Deliberately not answerable with Enter."""

    BINDINGS = [
        ("y", "answer(True)", "Yes"),
        ("n,escape", "answer(False)", "No"),
    ]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog small"):
            yield Label(self.question, markup=False)
            yield Label("[b]y[/] yes   [b]n[/] no", classes="hint")

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)
