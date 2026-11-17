import json

import pytest

from clio.cli.app import main
from clio.service import KanbanService


@pytest.fixture
def run(db_path, monkeypatch, capsys):
    """Run the real entry point; returns (exit_code, stdout, stderr)."""
    monkeypatch.setenv("CLIO_DB", str(db_path))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "120")

    def _run(*argv, stdin=None):
        if stdin is not None:
            monkeypatch.setattr("sys.stdin", __import__("io").StringIO(stdin))
        code = 0
        try:
            main(list(argv))
        except SystemExit as exc:
            code = exc.code or 0
        out = capsys.readouterr()
        return code, out.out, out.err

    return _run


def board(run, *extra):
    code, out, _ = run("ls", "--json", *extra)
    assert code == 0
    data = json.loads(out)
    return {col["name"]: [c["title"] for c in col["cards"]] for col in data["columns"]}


def test_add_move_done_roundtrip(run):
    assert run("add", "first")[0] == 0
    code, out, _ = run("add", "second", "-c", "todo", "-p", "high", "-t", "bug", "-d", "why")
    assert code == 0 and "#2" in out and "Todo" in out
    assert board(run) == {"Backlog": ["first"], "Todo": ["second"], "Doing": [], "Done": []}
    assert run("mv", "1", "doi")[0] == 0
    assert run("done", "2")[0] == 0
    assert board(run) == {"Backlog": [], "Todo": [], "Doing": ["first"], "Done": ["second"]}


def test_mv_top_and_bottom(run):
    for title in "abc":
        run("add", title)
    run("mv", "3", "backlog", "--top")
    assert board(run)["Backlog"] == ["c", "a", "b"]
    run("mv", "3", "backlog", "--bottom")
    assert board(run)["Backlog"] == ["a", "b", "c"]


def test_show_json_and_text(run):
    run("add", "task", "-p", "urgent", "-t", "x", "-d", "details here")
    run("check", "add", "1", "step one")
    run("check", "toggle", "1", "1")
    code, out, _ = run("show", "1", "--json")
    data = json.loads(out)
    assert data["priority"] == "urgent" and data["column"] == "Backlog"
    assert [t["name"] for t in data["tags"]] == ["x"]
    assert data["checklist"][0]["done"] is True
    code, out, _ = run("show", "1")
    assert code == 0
    for expected in ("task", "urgent", "details here", "step one", "1/1"):
        assert expected in out


def test_ls_renders_board_and_filters(run):
    run("add", "alpha", "-t", "bug")
    run("add", "beta")
    code, out, _ = run("ls")
    assert code == 0
    for expected in ("Main", "Backlog", "Done", "alpha", "beta", "bug"):
        assert expected in out
    assert board(run, "--tag", "bug")["Backlog"] == ["alpha"]
    assert board(run, "-s", "BET")["Backlog"] == ["beta"]
    run("add", "gamma", "-t", "bug", "-t", "ui")
    assert board(run, "--tag", "bug", "-t", "ui")["Backlog"] == ["gamma"]


def test_edit_and_tags(run):
    run("add", "task", "-t", "a")
    assert run("edit", "1", "--title", "renamed", "--add-tag", "b", "--rm-tag", "a")[0] == 0
    data = json.loads(run("show", "1", "--json")[1])
    assert data["title"] == "renamed" and [t["name"] for t in data["tags"]] == ["b"]
    assert run("edit", "1")[0] == 2
    code, out, _ = run("tag", "ls")
    assert "b" in out and "1 card(s)" in out
    assert run("tag", "color", "b", "blue")[0] == 0
    assert run("tag", "rm", "b")[0] == 0
    assert json.loads(run("show", "1", "--json")[1])["tags"] == []


def test_rm_asks_unless_yes(run):
    run("add", "a")
    run("add", "b")
    assert run("rm", "1", stdin="n\n")[0] == 1
    assert board(run)["Backlog"] == ["a", "b"]
    assert run("rm", "1", stdin="y\n")[0] == 0
    assert run("rm", "2", "--yes")[0] == 0
    assert board(run)["Backlog"] == []


def test_archive_and_all(run):
    run("add", "a")
    run("archive", "1")
    assert board(run)["Backlog"] == []
    assert board(run, "--all")["Backlog"] == ["a"]
    run("unarchive", "1")
    assert board(run)["Backlog"] == ["a"]


def test_boards(run):
    run("ls")  # first use creates the default board
    assert run("board", "new", "Work", "-c", "Inbox", "-c", "Shipped", "--use")[0] == 0
    run("add", "w1")
    assert board(run) == {"Inbox": ["w1"], "Shipped": []}
    assert run("board", "use", "main")[0] == 0
    run("add", "m1")
    assert board(run)["Backlog"] == ["m1"]
    assert board(run, "-b", "work")["Inbox"] == ["w1"]
    out = run("board", "ls")[1]
    assert "Main" in out and "Work" in out
    assert run("board", "rename", "work", "Job")[0] == 0
    assert run("board", "rm", "job", "-y")[0] == 0
    assert "Job" not in run("board", "ls")[1]


def test_columns(run):
    assert run("column", "add", "Review", "--after", "doing")[0] == 0
    assert run("column", "mv", "review", "1")[0] == 0
    assert run("column", "rename", "review", "QA")[0] == 0
    assert list(board(run)) == ["QA", "Backlog", "Todo", "Doing", "Done"]
    run("add", "x", "-c", "qa")
    code, _, err = run("column", "rm", "qa")
    assert code == 1 and "say where" in err
    assert run("column", "rm", "qa", "--move-to", "todo")[0] == 0
    assert board(run)["Todo"] == ["x"]
    assert run("column", "wip", "todo", "1")[0] == 0
    assert "WIP limit 1" in run("column", "ls")[1]
    assert run("column", "done", "doing")[0] == 0
    run("done", "1")
    assert board(run)["Doing"] == ["x"]


def test_errors_are_one_line_and_exit_1(run):
    code, out, err = run("show", "99")
    assert (code, out) == (1, "") and err.strip() == "Error: no card #99"
    code, _, err = run("add", "x", "-p", "bogus")
    assert code == 1 and "unknown priority" in err
    assert board(run)["Backlog"] == []


def test_db_option_overrides_env(run, tmp_path):
    other = tmp_path / "other.db"
    assert run("--db", str(other), "add", "elsewhere")[0] == 0
    assert board(run)["Backlog"] == []
    svc = KanbanService(other)
    assert svc.board_view().columns[0].cards[0].title == "elsewhere"
    svc.close()
