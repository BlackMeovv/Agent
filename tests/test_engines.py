"""多引擎支持测试：工厂路由、伪连接注入的 MySQL/PG 行为、方言全链路、演示库导出。"""

import pytest

from insight_agent.agent import InsightAgent
from insight_agent.guard import validate
from insight_agent.llm import MockLLM
from insight_agent.tools.database import ReadOnlyDatabase
from insight_agent.tools.engines import (
    MySQLDatabase,
    PostgresDatabase,
    is_server_dsn,
    open_database,
)

TABLES = {"customers"}


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql):
        self._conn.executed.append(sql)
        behavior = self._conn.behavior
        if isinstance(behavior, Exception):
            if sql.strip().upper().startswith("SET"):
                return  # 会话初始化语句成功，只有真实查询抛错
            raise behavior
        self.description = [(c,) for c in behavior["columns"]]
        self._rows = list(behavior["rows"])

    def fetchmany(self, n):
        out, self._rows = self._rows[:n], self._rows[n:]
        return out

    def fetchall(self):
        out, self._rows = self._rows, []
        return out

    def close(self):
        pass


class FakeConn:
    def __init__(self, behavior):
        self.behavior = behavior
        self.executed: list[str] = []

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass


def mysql_db(behavior, **kw):
    conn = FakeConn(behavior)
    db = MySQLDatabase("mysql://readonly:pwd@localhost:3306/insight", connect_fn=lambda: conn, **kw)
    return db, conn


class TestFactory:
    def test_sqlite_path(self, demo_db_path):
        assert isinstance(open_database(demo_db_path), ReadOnlyDatabase)

    def test_mysql_url(self):
        db = open_database("mysql://u:p@h:3306/d")
        assert isinstance(db, MySQLDatabase) and db.dialect == "mysql"
        assert (db.host, db.port, db.database) == ("h", 3306, "d")

    def test_postgres_url(self):
        db = open_database("postgresql://u:p@h/d")
        assert isinstance(db, PostgresDatabase) and db.port == 5432

    def test_missing_dbname_rejected(self):
        with pytest.raises(ValueError):
            open_database("mysql://u:p@h:3306/")

    def test_is_server_dsn(self):
        assert is_server_dsn("mysql://x/y") and is_server_dsn("postgres://x/y")
        assert not is_server_dsn("data/demo/ecommerce.sqlite")


class TestMySQLBehavior:
    def test_readonly_session_and_query(self):
        db, conn = mysql_db({"columns": ["cnt"], "rows": [(21,)]})
        result = db.run_query("SELECT COUNT(*) FROM customers")
        assert result.ok and result.rows == [(21,)]
        assert any("TRANSACTION READ ONLY" in s for s in conn.executed)
        assert any("max_execution_time" in s for s in conn.executed)

    def test_truncation(self):
        db, _ = mysql_db({"columns": ["id"], "rows": [(i,) for i in range(300)]}, max_rows=100)
        result = db.run_query("SELECT id FROM customers")
        assert result.ok and result.row_count == 100 and result.truncated

    def test_empty_result_classified(self):
        db, _ = mysql_db({"columns": ["id"], "rows": []})
        assert db.run_query("SELECT 1").error_kind == "empty_result"

    @pytest.mark.parametrize(
        "message,kind",
        [
            ("(3024, 'Query execution was interrupted, maximum statement execution time exceeded')", "timeout"),
            ("(1146, \"Table 'insight.ghosts' doesn't exist\")", "no_such_table"),
            ("(1054, \"Unknown column 'nope' in 'field list'\")", "no_such_column"),
            ("(1064, 'You have an error in your SQL syntax')", "syntax_error"),
            ("(1792, 'Cannot execute statement in a READ ONLY transaction.')", "guard_rejected"),
        ],
    )
    def test_error_classification(self, message, kind):
        db, _ = mysql_db(RuntimeError(message))
        assert db.run_query("SELECT 1").error_kind == kind


class TestPostgresBehavior:
    def test_readonly_session(self):
        conn = FakeConn({"columns": ["cnt"], "rows": [(1,)]})
        db = PostgresDatabase("postgres://u:p@h/d", connect_fn=lambda: conn)
        assert db.run_query("SELECT 1").ok
        assert any("default_transaction_read_only" in s for s in conn.executed)
        assert any("statement_timeout" in s for s in conn.executed)

    @pytest.mark.parametrize(
        "message,kind",
        [
            ("canceling statement due to statement timeout", "timeout"),
            ('relation "ghosts" does not exist', "no_such_table"),
            ('column "nope" does not exist', "no_such_column"),
            ('syntax error at or near "SELEC"', "syntax_error"),
            ("cannot execute INSERT in a read-only transaction", "guard_rejected"),
        ],
    )
    def test_error_classification(self, message, kind):
        db = PostgresDatabase("postgres://u:p@h/d", connect_fn=lambda: FakeConn(RuntimeError(message)))
        assert db.run_query("SELECT 1").error_kind == kind


class TestDialectThreading:
    def test_guard_parses_mysql_backticks(self):
        verdict = validate("SELECT `name` FROM `customers`", allowed_tables=TABLES, dialect="mysql")
        assert verdict.allowed

    def test_guard_rejects_write_in_all_dialects(self):
        for dialect in ("sqlite", "mysql", "postgres"):
            assert not validate("DELETE FROM customers", allowed_tables=TABLES, dialect=dialect).allowed

    def test_prompt_carries_dialect(self, settings):
        class FakeMySQLLike:
            dialect = "mysql"

            def table_names(self):
                return ["customers"]

            def schema_by_table(self, sample_rows=3):
                return {"customers": "CREATE TABLE customers (id INT, name VARCHAR(64), city VARCHAR(32)) COMMENT='客户表';"}

            def run_query(self, sql):
                from insight_agent.tools.contract import QueryResult

                return QueryResult(ok=True, columns=["cnt"], rows=[(5,)], row_count=1)

        llm = MockLLM(["思路。\n```sql\nSELECT COUNT(*) FROM customers\n```"])
        agent = InsightAgent(settings, FakeMySQLLike(), llm)
        outcome = agent.ask("客户数？", generate_answer=False)
        assert outcome.status == "ok"
        assert "MySQL" in llm.calls[0][0]["content"]  # system prompt 按方言渲染
        assert "DATE_FORMAT" in llm.calls[0][0]["content"]


class TestDumps:
    def test_mysql_dump(self):
        from insight_agent.demo_data import dump_sql

        dump = dump_sql("mysql")
        assert "CREATE TABLE customers" in dump and "COMMENT" in dump
        assert dump.count("INSERT INTO") >= 6
        assert "用户0001" in dump

    def test_postgres_dump(self):
        from insight_agent.demo_data import dump_sql

        dump = dump_sql("postgres")
        assert "COMMENT ON TABLE customers" in dump
        assert "INSERT INTO payments" in dump

    def test_unknown_dialect(self):
        from insight_agent.demo_data import dump_sql

        with pytest.raises(ValueError):
            dump_sql("oracle")
