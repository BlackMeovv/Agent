"""命令行入口。

    insight-agent ask "上海的客户一共有多少个？" [--trace] [--no-answer]
    insight-agent schema        # 查看喂给模型的 schema 上下文
    insight-agent demo-db       # 生成演示库
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def _cmd_ask(args: argparse.Namespace) -> int:
    from . import build_agent

    agent = build_agent()
    outcome = agent.ask(args.question, generate_answer=not args.no_answer)

    # 模型/数据库产出的文本都是不受信内容，必须 escape/Text 后再交给 rich 渲染
    if args.trace:
        for i, attempt in enumerate(outcome.attempts, 1):
            status = "[green]成功[/green]" if attempt.ok else (
                f"[red]{escape(attempt.error_kind or '')}[/red] {escape(attempt.error_message or '')}"
            )
            console.print(Panel(Text(attempt.sql_raw), title=f"尝试 {i} · {status}"))

    if outcome.final_sql:
        console.print(Panel(Text(outcome.final_sql), title="最终 SQL", border_style="cyan"))
    if outcome.result and outcome.result.ok:
        table = Table(*[Text(c) for c in outcome.result.columns])
        for row in outcome.result.rows[:20]:
            table.add_row(*[Text("NULL" if v is None else str(v)) for v in row])
        console.print(table)
        if outcome.result.row_count > 20:
            console.print(f"（共 {outcome.result.row_count} 行，仅展示前 20 行）")
    if outcome.answer:
        console.print(Panel(Text(outcome.answer), title="回答", border_style="green"))

    usage = outcome.usage
    console.print(
        f"[dim]状态 {outcome.status} · LLM 调用 {usage.get('llm_calls', 0)} 次 · "
        f"tokens {usage.get('total_tokens', 0)} · 成本 {usage.get('cost', 0):.6f} · "
        f"耗时 {outcome.latency_ms} ms[/dim]"
    )
    return 0 if outcome.succeeded else 1


def _cmd_schema(_args: argparse.Namespace) -> int:
    from .config import get_settings
    from .tools.database import ReadOnlyDatabase

    settings = get_settings()
    db = ReadOnlyDatabase(settings.db_path)
    console.print(db.schema_text())
    return 0


def _cmd_demo_db(_args: argparse.Namespace) -> int:
    from .demo_data import build

    path = build()
    console.print(f"演示库已生成: {path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="insight-agent", description="企业数据分析 Agent")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="用自然语言提问")
    ask.add_argument("question")
    ask.add_argument("--trace", action="store_true", help="展示每一次尝试的 SQL 与错误")
    ask.add_argument("--no-answer", action="store_true", help="跳过总结节点（只要 SQL 和数据）")
    ask.set_defaults(func=_cmd_ask)

    schema = sub.add_parser("schema", help="查看喂给模型的 schema 上下文")
    schema.set_defaults(func=_cmd_schema)

    demo = sub.add_parser("demo-db", help="生成演示数据库")
    demo.set_defaults(func=_cmd_demo_db)

    args = parser.parse_args()
    try:
        sys.exit(args.func(args))
    except FileNotFoundError as e:
        console.print(f"[red]错误：[/red]{escape(str(e))}")
        sys.exit(2)
    except Exception as e:
        from .llm import LLMError

        if isinstance(e, LLMError):
            console.print(f"[red]错误：[/red]{escape(str(e))}")
            sys.exit(2)
        raise


if __name__ == "__main__":
    main()
