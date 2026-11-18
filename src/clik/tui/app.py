from textual.app import App

from clik.service import KanbanService
from clik.tui.screens.board import BoardScreen


class ClikApp(App[None]):
    CSS_PATH = "clik.tcss"
    TITLE = "clik"

    def __init__(self, service: KanbanService) -> None:
        super().__init__()
        self.service = service

    def get_default_screen(self) -> BoardScreen:
        return BoardScreen(self.service)
