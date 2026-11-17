import pytest

from clio.models import Priority
from clio.tui.app import ClioApp
from clio.tui.screens.board import BoardScreen
from clio.tui.widgets.card import CardWidget
from clio.tui.widgets.column import ColumnWidget


def keys(text):
    return ["space" if ch == " " else ch for ch in text]


def column(svc, name, board=None):
    view = svc.board_view(board)
    return [c.title for cv in view.columns if cv.column.name == name for c in cv.cards]


def selected(app):
    card = app.screen.current_card
    return card.title if card else None


def shown(app):
    return sorted(w.card.title for w in app.screen.query(CardWidget))


@pytest.fixture
def seeded(svc):
    for title in ("a", "b", "c"):
        svc.add_card(title)
    svc.add_card("t1", column="todo")
    return svc


async def test_navigation_follows_keys(seeded):
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        assert isinstance(app.screen, BoardScreen)
        assert selected(app) == "a"
        await pilot.press("j", "j", "j")
        assert selected(app) == "c"
        await pilot.press("g")
        assert selected(app) == "a"
        await pilot.press("G")
        assert selected(app) == "c"
        await pilot.press("l")
        assert selected(app) == "t1"
        await pilot.press("l", "l", "l", "l")
        assert app.screen.current_column.column.name == "Done" and selected(app) is None
        await pilot.press("left", "left", "left")
        assert selected(app) == "c", "each column remembers its row"
        highlighted = [
            w.card.title for w in app.screen.query(CardWidget) if w.has_class("selected")
        ]
        assert highlighted == ["c"]
        active = [
            w.view.column.name for w in app.screen.query(ColumnWidget) if w.has_class("active")
        ]
        assert active == ["Backlog"]


async def test_move_card_between_and_within_columns(seeded):
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("j", "L")
        assert column(seeded, "Backlog") == ["a", "c"]
        assert column(seeded, "Todo") == ["b", "t1"]
        assert selected(app) == "b", "selection follows the moved card"
        await pilot.press("J")
        assert column(seeded, "Todo") == ["t1", "b"]
        await pilot.press("J", "K", "K")
        assert column(seeded, "Todo") == ["b", "t1"]
        await pilot.press("H", "H")
        assert column(seeded, "Backlog") == ["b", "a", "c"]
        await pilot.press("L", "L", "L")
        card = seeded.board_view().columns[3].cards[0]
        assert card.title == "b" and card.completed_at


async def test_add_card_with_enter(seeded):
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("l", "a", *keys("new one"), "enter")
        await pilot.pause()
        assert column(seeded, "Todo") == ["t1", "new one"]
        assert selected(app) == "new one"
        await pilot.press("a", "enter")
        await pilot.pause()
        assert not isinstance(app.screen, BoardScreen), "an empty title keeps the dialog open"
        await pilot.press("escape")
        assert column(seeded, "Todo") == ["t1", "new one"]


async def test_edit_card_fields_and_checklist(seeded):
    card = seeded.board_view().columns[0].cards[0]
    seeded.set_checklist(card.id, [("old", False), ("gone", False)])
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 50)) as pilot:
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("end", *keys("bc"))
        await pilot.click("#tags")
        await pilot.press(*keys("Bug, ui"))
        await pilot.click("#new-item")
        await pilot.press(*keys("fresh"), "enter")
        await pilot.click("#checklist")
        await pilot.press("home", "space", "down", "delete")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, BoardScreen)
    card = seeded.get_card(card.id)
    assert card.title == "abc"
    assert [t.name for t in card.tags] == ["bug", "ui"]
    assert [(i.text, i.done) for i in card.checklist] == [("old", True), ("fresh", False)]


async def test_cancelled_edit_changes_nothing(seeded):
    before = seeded.board_view()
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("e")
        await pilot.pause()
        await pilot.press(*keys("zzz"), "escape")
        await pilot.pause()
    assert seeded.board_view() == before


async def test_delete_needs_confirmation(seeded):
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("d", "n")
        await pilot.pause()
        assert column(seeded, "Backlog") == ["a", "b", "c"]
        await pilot.press("d", "enter")
        await pilot.pause()
        assert column(seeded, "Backlog") == ["a", "b", "c"], "enter must not confirm a delete"
        await pilot.press("y")
        await pilot.pause()
        assert column(seeded, "Backlog") == ["b", "c"]
        assert selected(app) == "b"


async def test_priority_tags_and_archive_shortcuts(seeded):
    card = seeded.board_view().columns[0].cards[0]
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("p", "p")
        assert seeded.get_card(card.id).priority is Priority.MEDIUM
        await pilot.press("p", "p", "p")
        assert seeded.get_card(card.id).priority is Priority.NONE
        await pilot.press("t", *keys("x y"), "enter")
        await pilot.pause()
        assert [t.name for t in seeded.get_card(card.id).tags] == ["x", "y"]
        await pilot.press("x")
        assert seeded.get_card(card.id).archived
        assert column(seeded, "Backlog") == ["b", "c"]


async def test_filter_narrows_board_and_swallows_shortcut_keys(seeded):
    seeded.add_card("deploy", tags=["ops"])
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("slash", *keys("d"))
        await pilot.pause()
        assert shown(app) == ["deploy"], "typing 'd' filters; it does not delete"
        assert not any(not isinstance(s, BoardScreen) for s in app.screen_stack)
        await pilot.press("backspace", *keys("#ops"), "enter")
        await pilot.pause()
        assert shown(app) == ["deploy"]
        assert selected(app) == "deploy"
        await pilot.press("L")
        assert column(seeded, "Todo") == ["deploy", "t1"]
        await pilot.press("escape")
        await pilot.pause()
        assert shown(app) == ["a", "b", "c", "deploy", "t1"]
    assert len(column(seeded, "Backlog")) == 3


async def test_filter_with_several_tags_and_text(svc):
    svc.add_card("foo both", tags=["a", "b"])
    svc.add_card("foo a", tags=["a"])
    svc.add_card("bar both", tags=["a", "b"])
    app = ClioApp(svc)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("slash", *keys("foo #a #b"), "enter")
        await pilot.pause()
        assert shown(app) == ["foo both"]
        await pilot.press("slash", *(["backspace"] * 9), *keys("#b #a"), "enter")
        await pilot.pause()
        assert shown(app) == ["bar both", "foo both"]


async def test_reorder_under_filter_swaps_with_visible_neighbour(svc):
    for title in ("x1", "y", "x2", "x3"):
        svc.add_card(title)
    app = ClioApp(svc)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("slash", "x", "enter")
        await pilot.pause()
        await pilot.press("J")
        assert column(svc, "Backlog") == ["y", "x2", "x1", "x3"]


async def test_switch_and_create_boards(seeded):
    seeded.create_board("Other", columns=["Inbox"])
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        assert app.screen.view.board.name == "Other"
        assert seeded.current_board().name == "Other"
        await pilot.press("a", *keys("in other"), "enter")
        await pilot.pause()
        assert column(seeded, "Inbox", "Other") == ["in other"]
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("n", *keys("Third"), "enter")
        await pilot.pause()
        assert app.screen.view.board.name == "Third"
        assert seeded.current_board().name == "Third"


async def test_manage_columns(seeded):
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("c")
        await pilot.pause()
        await pilot.press("a", *keys("Next"), "enter")
        await pilot.pause()
        names = [c.name for c in seeded.list_columns()]
        assert names == ["Backlog", "Next", "Todo", "Doing", "Done"]
        await pilot.press("J")
        assert [c.name for c in seeded.list_columns()][2] == "Next"
        await pilot.press("r", "end", "2", "enter")
        await pilot.pause()
        await pilot.press("w", "3", "enter")
        await pilot.pause()
        col = seeded.get_column("Next2")
        assert col.wip_limit == 3
        await pilot.press("d")
        assert "Next2" not in [c.name for c in seeded.list_columns()]
        await pilot.press("home", "d")
        await pilot.pause()
        await pilot.press(*keys("todo"), "enter")
        await pilot.pause()
        assert column(seeded, "Todo") == ["t1", "a", "b", "c"]
        await pilot.press("escape")
        await pilot.pause()
        assert [w.view.column.name for w in app.screen.query(ColumnWidget)] == [
            "Todo",
            "Doing",
            "Done",
        ]


async def test_service_errors_are_shown_not_raised(seeded):
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("t", *keys("ok"), "enter")
        await pilot.pause()
        seeded.delete_card(app.screen.current_card.id)  # changed behind the TUI's back
        await pilot.press("p")
        await pilot.pause()
        assert isinstance(app.screen, BoardScreen)
        await pilot.press("r")
        assert shown(app) == ["b", "c", "t1"]


async def test_help_and_quit(seeded):
    app = ClioApp(seeded)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert not isinstance(app.screen, BoardScreen)
        await pilot.press("d")
        await pilot.pause()
        assert isinstance(app.screen, BoardScreen)
        assert column(seeded, "Backlog") == ["a", "b", "c"]
        await pilot.press("q")
    assert app.return_code == 0
