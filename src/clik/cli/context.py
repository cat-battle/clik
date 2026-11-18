"""Per-invocation state shared by the command modules."""

from pathlib import Path

from clik import config
from clik.service import KanbanService

_db_override: Path | None = None
_service: KanbanService | None = None


def set_db(path: Path | None) -> None:
    global _db_override
    _db_override = path


def svc() -> KanbanService:
    global _service
    if _service is None:
        _service = KanbanService(config.db_path(_db_override))
    return _service


def close() -> None:
    global _service
    if _service is not None:
        _service.close()
        _service = None
