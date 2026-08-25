"""追踪接线测试：用 FakeTracer 验证 agent 在正确的位置上报了正确的内容。"""

from insight_agent.agent import InsightAgent
from insight_agent.llm import MockLLM
from insight_agent.tracing import NOOP_TRACER, RunTrace, Tracer, build_tracer


class FakeRunTrace(RunTrace):
    def __init__(self):
        self.spans: list[tuple[str, dict]] = []
        self.generations: list[dict] = []
        self.ended: dict | None = None

    def span(self, name, metadata=None):
        self.spans.append((name, metadata or {}))

    def generation(self, tag, messages, output, model, prompt_tokens=0, completion_tokens=0):
        self.generations.append(
            {"tag": tag, "model": model, "output": output, "tokens": prompt_tokens + completion_tokens}
        )

    def end(self, status="", output="", usage=None):
        self.ended = {"status": status, "usage": usage}


class FakeTracer(Tracer):
    enabled = True

    def __init__(self):
        self.runs: list[FakeRunTrace] = []

    def start_run(self, question):
        trace = FakeRunTrace()
        self.runs.append(trace)
        return trace


def sql_reply(sql):
    return f"思路。\n```sql\n{sql}\n```"


class TestTracingWiring:
    def test_full_run_traced(self, settings, db):
        tracer = FakeTracer()
        agent = InsightAgent(
            settings,
            db,
            MockLLM([sql_reply("SELECT nope FROM customers"), sql_reply("SELECT COUNT(*) FROM customers"), "答案"]),
            tracer=tracer,
        )
        outcome = agent.ask("客户数？")
        assert outcome.status == "ok"

        trace = tracer.runs[0]
        tags = [g["tag"] for g in trace.generations]
        assert tags == ["generate_sql", "repair", "answer"]
        assert all(g["model"] == "mock" for g in trace.generations)
        assert all(g["tokens"] > 0 for g in trace.generations)

        execute_spans = [m for name, m in trace.spans if name == "execute"]
        assert len(execute_spans) == 2  # 失败一次 + 成功一次
        assert execute_spans[0]["error_kind"] == "no_such_column"
        assert execute_spans[1]["ok"] is True

        assert trace.ended is not None and trace.ended["status"] == "ok"
        assert trace.ended["usage"]["llm_calls"] == 3

    def test_default_tracer_is_noop(self, settings, db):
        agent = InsightAgent(settings, db, MockLLM([sql_reply("SELECT COUNT(*) FROM customers")]))
        assert agent.tracer is NOOP_TRACER
        outcome = agent.ask("客户数？", generate_answer=False)  # 不抛异常即可
        assert outcome.status == "ok"


class TestBuildTracer:
    def test_disabled_without_keys(self, settings):
        assert build_tracer(settings) is NOOP_TRACER

    def test_missing_package_degrades_gracefully(self, settings, capsys):
        configured = settings.model_copy(
            update={"langfuse_public_key": "pk-lf-x", "langfuse_secret_key": "sk-lf-x"}
        )
        tracer = build_tracer(configured)  # 本环境未安装 langfuse：应降级为 no-op 并提示
        assert tracer is NOOP_TRACER
        assert "langfuse" in capsys.readouterr().err.lower()
