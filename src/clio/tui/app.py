from textual.app import App

from clio.service import KanbanService
from clio.tui.screens.board import BoardScreen


class ClioApp(App[None]):
    CSS_PATH = "clio.tcss"
    TITLE = "clio"

    def __init__(self, service: KanbanService) -> None:
        super().__init__()
        self.service = service

    def get_default_screen(self) -> BoardScreen:
        return BoardScreen(self.service)
