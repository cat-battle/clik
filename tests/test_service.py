import pytest

from clio.models import NotFound, Priority, ValidationError
from clio.service import KanbanService


def titles(svc, column, **kw):
    view = svc.board_view(**kw)
    return [c.title for cv in view.columns if cv.column.name == column for c in cv.cards]


def positions(svc, column):
    view = svc.board_view()
    return [c.position for cv in view.columns if cv.column.name == column for c in cv.cards]


# -- boards ----------------------------------------------------------------


def test_first_use_creates_default_board(svc):
    board = svc.current_board()
    assert board.name == "Main"
    cols = svc.list_columns()
    assert [c.name for c in cols] == ["Backlog", "Todo", "Doing", "Done"]
    assert [c.is_done for c in cols] == [False, False, False, True]


def test_current_board_persists_across_connections(db_path):
    a = KanbanService(db_path)
    a.create_board("Main")
    a.create_board("Side")
    a.use_board("side")
    a.close()
    b = KanbanService(db_path)
    assert b.current_board().name == "Side"
    b.close()


def test_board_matching_prefers_exact_then_unique_prefix(svc):
    svc.create_board("Work")
    svc.create_board("Workshop")
    assert svc.get_board("work").name == "Work"
    assert svc.get_board("works").name == "Workshop"
    svc.create_board("Home")
    svc.create_board("Hobby")
    with pytest.raises(ValidationError, match="ambiguous"):
        svc.get_board("ho")
    with pytest.raises(NotFound):
        svc.get_board("zzz")


def test_duplicate_board_name_rejected(svc):
    svc.create_board("Work")
    with pytest.raises(ValidationError):
        svc.create_board("work")
    svc.create_board("Other")
    with pytest.raises(ValidationError):
        svc.rename_board("Other", "WORK")


def test_delete_board_cascades_and_current_falls_back(svc):
    svc.create_board("A")
    svc.create_board("B")
    svc.use_board("B")
    card = svc.add_card("x", tags=["t"])
    svc.add_check(card.id, "step")
    svc.delete_board("B")
    assert svc.current_board().name == "A"
    with pytest.raises(NotFound):
        svc.get_card(card.id)


# -- columns ---------------------------------------------------------------


def test_add_column_at_end_and_after(svc):
    svc.add_column("Review", after="doing")
    svc.add_column("Icebox")
    names = [c.name for c in svc.list_columns()]
    assert names == ["Backlog", "Todo", "Doing", "Review", "Done", "Icebox"]
    assert [c.position for c in svc.list_columns()] == list(range(6))
    with pytest.raises(ValidationError):
        svc.add_column("review")


def test_move_and_rename_column(svc):
    svc.move_column("done", 0)
    assert [c.name for c in svc.list_columns()] == ["Done", "Backlog", "Todo", "Doing"]
    svc.move_column("done", 99)
    assert [c.name for c in svc.list_columns()][-1] == "Done"
    assert svc.rename_column("todo", "Next").name == "Next"
    with pytest.raises(ValidationError):
        svc.rename_column("next", "Doing")


def test_delete_column_requires_target_for_cards(svc):
    keep = svc.add_card("keep", column="doing")
    a = svc.add_card("a", column="todo")
    b = svc.add_card("b", column="todo")
    archived = svc.add_card("old", column="todo")
    svc.archive_card(archived.id)
    with pytest.raises(ValidationError, match="say where"):
        svc.delete_column("todo")
    svc.delete_column("todo", move_to="doing")
    assert [c.name for c in svc.list_columns()] == ["Backlog", "Doing", "Done"]
    assert titles(svc, "Doing") == ["keep", "a", "b"]
    assert positions(svc, "Doing") == [0, 1, 2]
    assert svc.get_card(archived.id).column_id == keep.column_id
    assert {a.id, b.id} <= {c.id for cv in svc.board_view().columns for c in cv.cards}


def test_cannot_delete_last_column(svc):
    svc.create_board("Solo", columns=["Only"])
    with pytest.raises(ValidationError, match="at least one"):
        svc.delete_column("only", board="Solo")


def test_wip_limit_flags_overloaded_column(svc):
    svc.set_wip_limit("doing", 1)
    svc.add_card("a", column="doing")
    view = {cv.column.name: cv for cv in svc.board_view().columns}
    assert not view["Doing"].over_wip
    svc.add_card("b", column="doing")
    view = {cv.column.name: cv for cv in svc.board_view().columns}
    assert view["Doing"].over_wip
    assert svc.set_wip_limit("doing", 0).wip_limit is None


# -- cards -----------------------------------------------------------------


def test_add_card_defaults_and_top(svc):
    svc.add_card("first")
    svc.add_card("second")
    svc.add_card("urgent", top=True, priority=Priority.URGENT)
    assert titles(svc, "Backlog") == ["urgent", "first", "second"]
    assert positions(svc, "Backlog") == [0, 1, 2]
    with pytest.raises(ValidationError):
        svc.add_card("   ")


def test_move_between_columns_keeps_both_dense(svc):
    a, b, c = (svc.add_card(t, column="todo") for t in "abc")
    svc.add_card("x", column="doing")
    svc.add_card("y", column="doing")
    svc.move_card(b.id, "doing", 1)
    assert titles(svc, "Todo") == ["a", "c"]
    assert positions(svc, "Todo") == [0, 1]
    assert titles(svc, "Doing") == ["x", "b", "y"]
    assert positions(svc, "Doing") == [0, 1, 2]
    svc.move_card(a.id, "doing")
    assert titles(svc, "Doing") == ["x", "b", "y", "a"]
    assert c.id == svc.board_view().columns[1].cards[0].id


def test_reorder_within_column(svc):
    a, b, c = (svc.add_card(t) for t in "abc")
    svc.move_card(c.id, "backlog", 0)
    assert titles(svc, "Backlog") == ["c", "a", "b"]
    svc.move_card(c.id, "backlog", 99)
    assert titles(svc, "Backlog") == ["a", "b", "c"]
    svc.move_card(a.id, "backlog", 1)
    assert titles(svc, "Backlog") == ["b", "a", "c"]
    assert positions(svc, "Backlog") == [0, 1, 2]


def test_move_targets_columns_of_the_cards_own_board(svc):
    svc.create_board("One")
    svc.create_board("Two", columns=["Inbox", "Shipped"])
    card = svc.add_card("x", board="Two")
    svc.use_board("One")
    assert svc.column_of(svc.move_card(card.id, "ship")).name == "Shipped"
    with pytest.raises(NotFound):
        svc.move_card(card.id, "backlog")


def test_completion_tracks_the_done_column(svc):
    card = svc.add_card("x")
    assert card.completed_at is None
    done = svc.complete_card(card.id)
    assert svc.column_of(done).name == "Done" and done.completed_at
    assert svc.move_card(card.id, "todo").completed_at is None
    svc.set_done_column("doing")
    assert svc.column_of(svc.complete_card(card.id)).name == "Doing"
    assert [c.name for c in svc.list_columns() if c.is_done] == ["Doing"]


def test_update_card_changes_only_given_fields(svc):
    card = svc.add_card("x", description="d", priority=Priority.LOW, tags=["a"])
    updated = svc.update_card(card.id, title="y")
    assert (updated.title, updated.description, updated.priority) == ("y", "d", Priority.LOW)
    assert [t.name for t in updated.tags] == ["a"]
    assert svc.update_card(card.id, tags=[]).tags == ()
    with pytest.raises(NotFound):
        svc.update_card(999, title="z")


def test_archive_hides_card_and_unarchive_restores(svc):
    a, b, c = (svc.add_card(t) for t in "abc")
    svc.archive_card(a.id)
    assert titles(svc, "Backlog") == ["b", "c"]
    assert positions(svc, "Backlog") == [0, 1]
    assert titles(svc, "Backlog", include_archived=True) == ["b", "c", "a"]
    with pytest.raises(ValidationError, match="archived"):
        svc.move_card(a.id, "todo")
    svc.unarchive_card(a.id)
    assert titles(svc, "Backlog") == ["b", "c", "a"]
    with pytest.raises(ValidationError):
        svc.unarchive_card(a.id)


def test_delete_card_closes_gap(svc):
    a, b, c = (svc.add_card(t) for t in "abc")
    svc.delete_card(b.id)
    assert titles(svc, "Backlog") == ["a", "c"]
    assert positions(svc, "Backlog") == [0, 1]


# -- tags, filters, checklists ----------------------------------------------


def test_tags_are_normalized_shared_and_counted(svc):
    a = svc.add_card("a", tags=["#Bug", "bug", "ui"])
    assert [t.name for t in a.tags] == ["bug", "ui"]
    b = svc.add_card("b")
    svc.add_tags(b.id, ["BUG"])
    assert {t.name: n for t, n in svc.list_tags()} == {"bug": 2, "ui": 1}
    assert [t.name for t in svc.remove_tags(a.id, ["ui"]).tags] == ["bug"]
    with pytest.raises(ValidationError):
        svc.add_tags(a.id, ["two words"])


def test_tag_color_and_delete(svc):
    card = svc.add_card("a", tags=["bug"])
    assert svc.set_tag_color("bug", "red").color == "#f38ba8"
    assert svc.set_tag_color("bug", "#ABCDEF").color == "#abcdef"
    assert svc.set_tag_color("bug", None).color is None
    with pytest.raises(ValidationError):
        svc.set_tag_color("bug", "sparkly")
    svc.delete_tag("bug")
    assert svc.get_card(card.id).tags == ()
    with pytest.raises(NotFound):
        svc.delete_tag("bug")


def test_board_view_filters(svc):
    svc.add_card("fix login", tags=["bug"], priority=Priority.HIGH)
    svc.add_card("write docs", description="for the LOGIN flow")
    svc.add_card("refactor", tags=["bug"])
    assert titles(svc, "Backlog", tags=["#bug"]) == ["fix login", "refactor"]
    assert titles(svc, "Backlog", priority=Priority.HIGH) == ["fix login"]
    assert titles(svc, "Backlog", text="login") == ["fix login", "write docs"]
    assert titles(svc, "Backlog", text="login", tags=["bug"]) == ["fix login"]
    assert svc.board_view(tags=["bug"]).columns[0].active_count == 3


def test_filtering_by_several_tags_requires_all_of_them(svc):
    svc.add_card("both", tags=["a", "b"])
    svc.add_card("only a", tags=["a"])
    svc.add_card("only b", tags=["b"])
    assert titles(svc, "Backlog", tags=["a", "b"]) == ["both"]
    assert titles(svc, "Backlog", tags=["B", "#a", "a"]) == ["both"]
    assert titles(svc, "Backlog", tags=["a", "missing"]) == []
    assert titles(svc, "Backlog", tags=[]) == ["both", "only a", "only b"]


def test_checklist_operations(svc):
    card = svc.add_card("x")
    svc.add_check(card.id, "one")
    svc.add_check(card.id, "two")
    card = svc.toggle_check(card.id, 2)
    assert [(i.text, i.done) for i in card.checklist] == [("one", False), ("two", True)]
    assert card.checks_done == 1
    card = svc.remove_check(card.id, 1)
    assert [(i.text, i.done) for i in card.checklist] == [("two", True)]
    with pytest.raises(NotFound):
        svc.toggle_check(card.id, 5)
    with pytest.raises(ValidationError):
        svc.add_check(card.id, "  ")
    assert svc.set_checklist(card.id, [("a", True), ("b", False)]).checks_done == 1


def test_failed_operation_leaves_no_partial_write(svc):
    with pytest.raises(ValidationError):
        svc.add_card("x", tags=["ok", "not ok"])
    assert titles(svc, "Backlog") == []
    assert svc.list_tags() == []


def test_priority_parse():
    assert Priority.parse("h") is Priority.HIGH
    assert Priority.parse("3") is Priority.HIGH
    assert Priority.parse("Urgent") is Priority.URGENT
    for bad in ("", "x", "9"):
        with pytest.raises(ValidationError):
            Priority.parse(bad)
