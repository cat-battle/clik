from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


class PromptScreen(ModalScreen[str | None]):
    """Ask for one line of text. Dismisses with None when cancelled."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, question: str, value: str = "", placeholder: str = "") -> None:
        super().__init__()
        self.question = question
        self.value = value
        self.placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog small"):
            yield Label(self.question, markup=False)
            yield Input(self.value, placeholder=self.placeholder)
            yield Label("[b]enter[/] ok   [b]esc[/] cancel", classes="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)
