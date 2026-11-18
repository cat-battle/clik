# clik

CLI Kanban: a kanban board that lives in your terminal. A full-screen board for
working, and one-shot commands for quick capture and scripting. Both read and write the same
local SQLite file.

## Install

Needs Python 3.11 or newer. Works on Linux, macOS and Windows (use Windows Terminal).

```sh
pipx install .            # or: pip install .
```

For development:

```sh
python -m venv .venv
.venv/bin/pip install -e ".[dev]"      # Windows: .venv\Scripts\pip
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## The board

Run `clik` with no arguments.

| Keys | Action |
|---|---|
| `h` `j` `k` `l` / arrows | Select column / card |
| `g` / `G` | First / last card in the column |
| `H` / `L` | Move the card to the column on the left / right |
| `J` / `K` | Move the card down / up within its column |
| `a` | Add a card to the selected column |
| `enter` / `e` | Open the card: title, description, priority, tags, checklist |
| `p` | Cycle priority |
| `t` | Edit tags |
| `x` | Archive (hide without deleting) |
| `d` | Delete (asks first) |
| `/` | Filter by text and/or `#tags` (a card must have all of them); `esc` clears |
| `b` | Switch or create boards |
| `c` | Manage columns: add, rename, reorder, WIP limit, done column, delete |
| `r` | Reload from disk |
| `?` | Help |
| `q` | Quit |

A card's left edge shows its priority (grey none, green low, yellow medium, orange high, red
urgent). A column's count turns red when it is over its WIP limit. `ctrl+p` opens Textual's
command palette, where you can switch color themes.

## Commands

```sh
clik add "Fix login bug" -p high -t bug -t auth -d "Cookie expires early"
clik add "Write docs" -c todo --top
clik ls                         # the board; -t/--tag (repeatable), -p, -s/--search, --all, --json
clik show 1                     # one card in full; --json
clik mv 1 doing                 # --top to put it first
clik done 1                     # move to the board's done column
clik edit 1 --title "..." -p urgent --add-tag ui --rm-tag bug
clik archive 1 / clik unarchive 1
clik rm 1                       # asks; -y to skip

clik check add 1 "write a repro"
clik check toggle 1 1
clik check rm 1 1

clik board ls | new NAME [-c COL ...] [--use] | use NAME | rename OLD NEW | rm NAME
clik column ls | add NAME [--after COL] | rename OLD NEW | mv COL POSITION
clik column rm COL [--move-to COL] | wip COL N | done COL
clik tag ls | color NAME COLOR | rm NAME
```

Boards and columns can be named by any unambiguous prefix, ignoring case (`clik mv 3 doi`).
Cards are named by their number. Card commands act on the current board unless given
`-b BOARD`; moving a card always stays within the card's own board.

`clik -h` and `clik COMMAND -h` list every option.

## Where the data lives

One SQLite file, chosen in this order:

1. `--db PATH`
2. the `CLIK_DB` environment variable
3. `~/.local/share/clik/clik.db` on Linux, `%LOCALAPPDATA%\clik\clik.db` on Windows,
   `~/Library/Application Support/clik/clik.db` on macOS

Back it up by copying the file while clik is not running.

## Layout of the code

```
src/clik/
  models.py     plain data types and errors
  db/           SQLite: connection, migrations, and all SQL (repo.py)
  service.py    KanbanService, the only API the UIs call
  theme.py      colors shared by both UIs
  cli/          Typer commands and Rich rendering
  tui/          Textual app, screens and widgets
```

`cli/` and `tui/` only import `service`, `models` and `theme`, never `db/`. That boundary is
what would let a client/server split replace `KanbanService` with a remote implementation
without touching either UI.
