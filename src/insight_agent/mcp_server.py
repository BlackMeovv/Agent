"""MCP server：把 insight-agent 暴露给任何 MCP 客户端（Claude Desktop / Claude Code 等）。

    uv sync --extra mcp
    uv run insight-agent-mcp        # stdio transport

Claude Desktop 配置示例（claude_desktop_config.json）：
    {"mcpServers": {"insight-agent": {
        "command": "uv", "args": ["run", "--directory", "/path/to/Agent", "insight-agent-mcp"]}}}

工具设计原则与主链路一致：run_sql 也必须过守卫（只读、白名单、行数限额）——
MCP 客户端同样是不受信输入源。
"""

from __future__ import annotations

from typing import Any

from .config import get_settings
from .guard import validate

_agent = None


def set_agent(agent) -> None:
    """测试注入用。"""
    global _agent
    _agent = agent


def _get_agent():
    global _agent
    if _agent is None:
        from . import build_agent

        _agent = build_agent()
    return _agent


def ask_data(question: str, user: str = "default") -> dict[str, Any]:
    """用自然语言查询业务数据库。返回回答、SQL 与结果预览。"""
    outcome = _get_agent().ask(question, user_id=user)
    return {
        "status": outcome.status,
        "answer": outcome.answer,
        "sql": outcome.final_sql,
        "result_preview": outcome.result.preview(max_rows=20) if outcome.result else None,
        "usage": outcome.usage,
    }


def run_sql(sql: str) -> dict[str, Any]:
    """直接执行一条只读 SQL（经过与主链路相同的安全守卫）。"""
    agent = _get_agent()
    verdict = validate(
        sql,
        allowed_tables=set(agent.db.table_names()),
        max_rows=agent.settings.sql_max_rows,
    )
    if not verdict.allowed:
        return {"ok": False, "error_kind": verdict.error_kind, "error": verdict.reason}
    result = agent.db.run_query(verdict.sql)
    if not result.ok:
        return {"ok": False, "error_kind": result.error_kind, "error": result.error_message}
    return {
        "ok": True,
        "columns": result.columns,
        "rows": [list(r) for r in result.rows[:50]],
        "row_count": result.row_count,
        "truncated": result.truncated,
    }


def get_schema() -> str:
    """返回数据库 schema（建表语句 + 样例行）。"""
    return _get_agent().db.schema_text()


def remember_preference(note: str, user: str = "default") -> str:
    """为用户记住一条口径偏好（跨会话生效）。"""
    agent = _get_agent()
    if agent.memory is None:
        return "记忆功能未启用"
    note_id = agent.memory.remember(user, note)
    return f"已记住（#{note_id}）"


def create_mcp_server():
    """构建 MCP server（需要可选依赖：uv sync --extra mcp）。

    兼容 mcp SDK 2.x（MCPServer）与 1.x（FastMCP，同一套 API 的旧名字）。
    """
    try:
        try:
            from mcp.server.mcpserver import MCPServer as ServerClass  # mcp >= 2.0
        except ImportError:
            from mcp.server.fastmcp import FastMCP as ServerClass  # mcp 1.x
    except ImportError as e:
        raise SystemExit("未安装 MCP SDK。运行：uv sync --extra mcp") from e

    server = ServerClass("insight-agent")
    server.tool()(ask_data)
    server.tool()(run_sql)
    server.tool()(get_schema)
    server.tool()(remember_preference)
    return server


def main() -> None:
    get_settings()  # 提前暴露配置错误
    create_mcp_server().run()


if __name__ == "__main__":
    main()
