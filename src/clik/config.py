"""Where the database lives: explicit path > CLIK_DB > per-user data dir."""

import os
from pathlib import Path

from platformdirs import user_data_dir


def db_path(override: str | Path | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("CLIK_DB")
    if env:
        return Path(env).expanduser()
    return Path(user_data_dir("clik", appauthor=False)) / "clik.db"
