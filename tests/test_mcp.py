"""MCP server 工具测试：直接调用被注册的普通函数（不起 stdio 传输）。"""

import pytest

from deepquery import mcp_server
from deepquery.agent import DeepQuery
from deepquery.llm import MockLLM
from deepquery.memory import MemoryStore

pytest.importorskip("mcp", reason="需要可选依赖：uv sync --extra mcp")


@pytest.fixture(autouse=True)
def inject_agent(settings, db, tmp_path):
    cnt = db.run_query("SELECT COUNT(*) FROM customers WHERE city = '上海'").rows[0][0]
    llm = MockLLM(
        [
            "思路。\n```sql\nSELECT COUNT(*) FROM customers WHERE city = '上海'\n```",
            f"上海共有 {cnt} 位客户。",
        ],
        cycle=True,
    )
    agent = DeepQuery(settings, db, llm, memory=MemoryStore(tmp_path / "mem.sqlite"))
    mcp_server.set_agent(agent)
    yield
    mcp_server.set_agent(None)


class TestTools:
    def test_ask_data(self):
        out = mcp_server.ask_data("上海的客户一共有多少个？")
        assert out["status"] == "ok" and "customers" in out["sql"]
        assert "位客户" in out["answer"]

    def test_run_sql_readonly_ok(self):
        out = mcp_server.run_sql("SELECT COUNT(*) FROM customers")
        assert out["ok"] and out["row_count"] == 1

    def test_run_sql_write_rejected(self):
        out = mcp_server.run_sql("DELETE FROM customers")
        assert not out["ok"] and out["error_kind"] == "guard_rejected"

    def test_get_schema(self):
        assert "CREATE TABLE customers" in mcp_server.get_schema()

    def test_remember(self):
        assert "已记住" in mcp_server.remember_preference("只看华东区", user="u1")


class TestServerRegistration:
    def test_tools_registered(self):
        server = mcp_server.create_mcp_server()
        import anyio

        tools = anyio.run(server.list_tools)
        names = {t.name for t in tools}
        assert {"ask_data", "run_sql", "get_schema", "remember_preference"} <= names
