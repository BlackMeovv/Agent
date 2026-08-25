import pytest

from insight_agent.config import Settings
from insight_agent.demo_data import build
from insight_agent.tools.database import ReadOnlyDatabase


@pytest.fixture(scope="session")
def demo_db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "ecommerce.sqlite"
    build(path)
    return path


@pytest.fixture(scope="session")
def db(demo_db_path):
    return ReadOnlyDatabase(demo_db_path, timeout_seconds=5, max_rows=200)


@pytest.fixture()
def settings(demo_db_path):
    # _env_file=None：测试不读 .env，行为与 CI 一致
    return Settings(_env_file=None, db_path=str(demo_db_path))
