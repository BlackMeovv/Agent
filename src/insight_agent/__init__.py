"""insight-agent：企业数据分析 Agent。

最小用法：
    from insight_agent import build_agent
    agent = build_agent()
    outcome = agent.ask("上海的客户一共有多少个？")
"""

from .agent import InsightAgent, RunOutcome
from .config import Settings, get_settings


def build_agent(settings: Settings | None = None) -> InsightAgent:
    """按 .env 配置组装真实 LLM 的 agent 实例（含可选的 Langfuse 追踪）。"""
    from .llm import LLMClient
    from .tools.database import ReadOnlyDatabase
    from .tracing import build_tracer

    settings = settings or get_settings()
    db = ReadOnlyDatabase(
        settings.db_path,
        timeout_seconds=settings.sql_timeout_seconds,
        max_rows=settings.sql_max_rows,
    )
    return InsightAgent(settings, db, LLMClient(settings), tracer=build_tracer(settings))


__all__ = ["InsightAgent", "RunOutcome", "Settings", "get_settings", "build_agent"]
