"""FastAPI 服务测试：SSE 流、缓存、指标、图表文件安全。全离线（MockLLM）。"""

import json

import pytest
from fastapi.testclient import TestClient

from insight_agent.agent import InsightAgent
from insight_agent.llm import MockLLM
from insight_agent.server import create_app


def sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[len("event: "):] for line in lines if line.startswith("event: "))
        data = next(line[len("data: "):] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


@pytest.fixture()
def client(settings, db):
    cnt = db.run_query("SELECT COUNT(*) FROM customers WHERE city = '上海'").rows[0][0]
    llm = MockLLM(
        [
            "思路。\n```sql\nSELECT COUNT(*) FROM customers WHERE city = '上海'\n```",
            f"上海共有 {cnt} 位客户。",
        ],
        cycle=True,
    )
    agent = InsightAgent(settings, db, llm)
    app = create_app(agent=agent, settings=settings)
    with TestClient(app) as c:
        c.agent_llm = llm
        yield c


class TestBasics:
    def test_healthz(self, client):
        body = client.get("/healthz").json()
        assert body["ok"] is True and body["cache"] == "memory"

    def test_index_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200 and "InsightAgent" in resp.text
        assert "执行日志" in resp.text  # 生产控制台式布局的关键区块

    def test_metrics(self, client):
        client.get("/api/ask", params={"question": "上海的客户一共有多少个？"})
        text = client.get("/metrics").text
        assert "insight_requests_total" in text and "insight_request_seconds" in text


class TestAskStream:
    def test_sse_events_and_final(self, client):
        resp = client.get("/api/ask", params={"question": "上海的客户一共有多少个？"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = sse_events(resp.text)
        node_names = [d["node"] for e, d in events if e == "node"]
        assert node_names[:2] == ["generate_sql", "execute"]
        assert "summarize" in node_names
        final = [d for e, d in events if e == "final"][0]
        assert final["status"] == "ok"
        assert "customers" in final["sql"]
        assert final["rows"] and final["usage"]["llm_calls"] >= 1
        assert "位客户" in final["answer"]

    def test_cache_hit_on_second_request(self, client):
        params = {"question": "上海的客户一共有多少个？"}
        client.get("/api/ask", params=params)
        calls_before = len(client.agent_llm.calls)
        resp = client.get("/api/ask", params=params)
        final = [d for e, d in sse_events(resp.text) if e == "final"][0]
        assert final["cached"] is True
        assert len(client.agent_llm.calls) == calls_before  # 没有新的 LLM 调用

    def test_question_validation(self, client):
        assert client.get("/api/ask", params={"question": ""}).status_code == 422


class TestChartFiles:
    def test_path_traversal_rejected(self, client):
        assert client.get("/charts/..%2f..%2fetc%2fpasswd").status_code == 404
        assert client.get("/charts/evil.png").status_code == 404

    def test_missing_chart_404(self, client):
        assert client.get("/charts/chart-000000000000.png").status_code == 404
