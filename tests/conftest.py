import pytest

from clik.service import KanbanService


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "clik.db"


@pytest.fixture
def svc(db_path):
    service = KanbanService(db_path)
    yield service
    service.close()
