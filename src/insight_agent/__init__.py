"""insight-agent：企业数据分析 Agent。

最小用法：
    from insight_agent import build_agent
    agent = build_agent()
    outcome = agent.ask("上海的客户一共有多少个？")
"""

from .agent import InsightAgent, RunOutcome
from .config import Settings, get_settings


def build_agent(settings: Settings | None = None) -> InsightAgent:
    """按 .env 配置组装 agent 实例（含可选的 Langfuse 追踪）。

    LLM_MOCK=1 时使用循环 MockLLM（演示/压测服务链路用，不调真实模型）——
    绝不能在评测里使用。
    """
    from .llm import LLMClient, MockLLM
    from .memory import MemoryStore
    from .tools.database import ReadOnlyDatabase
    from .tracing import build_tracer

    settings = settings or get_settings()
    db = ReadOnlyDatabase(
        settings.db_path,
        timeout_seconds=settings.sql_timeout_seconds,
        max_rows=settings.sql_max_rows,
    )
    if settings.llm_mock:
        llm = MockLLM(
            [
                "mock 演示。\n```sql\nSELECT status, COUNT(*) AS cnt FROM orders GROUP BY status\n```",
                "（mock 模式）各状态订单数量见结果表。",
            ],
            cycle=True,
        )
    else:
        llm = LLMClient(settings)
    return InsightAgent(
        settings,
        db,
        llm,
        tracer=build_tracer(settings),
        memory=MemoryStore(settings.memory_db_path),
    )


__all__ = ["InsightAgent", "RunOutcome", "Settings", "get_settings", "build_agent"]
