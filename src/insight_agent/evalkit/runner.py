"""评测运行器。

    python -m insight_agent.evalkit.runner --cases eval/cases/smoke.jsonl            # 真实 LLM
    python -m insight_agent.evalkit.runner --cases eval/cases/smoke.jsonl --gold-replay  # 离线自检

--gold-replay 用 MockLLM 把每题的 gold SQL 原样喂给 agent，全链路（守卫→执行→打分）
不经过任何真实模型。它验证的是评测基建本身：跑不到 100% 说明 harness 有 bug。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..agent import InsightAgent
from ..config import get_settings
from ..llm import LLMClient, MockLLM
from ..tools.database import ReadOnlyDatabase
from .scorer import execution_match

console = Console()


def load_cases(path: str | Path) -> list[dict]:
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            cases.append(json.loads(line))
    return cases


def run_eval(
    cases_path: str | Path,
    gold_replay: bool = False,
    limit: int | None = None,
    out_path: str | Path | None = None,
) -> dict:
    settings = get_settings()
    cases = load_cases(cases_path)
    if limit:
        cases = cases[:limit]

    db = ReadOnlyDatabase(
        settings.db_path,
        timeout_seconds=settings.sql_timeout_seconds,
        max_rows=settings.sql_max_rows,
    )
    real_llm = None if gold_replay else LLMClient(settings)

    results = []
    started = time.monotonic()
    for case in cases:
        if gold_replay:
            llm = MockLLM([f"直接回放 gold SQL。\n```sql\n{case['gold_sql']}\n```"])
            agent = InsightAgent(settings, db, llm)
        else:
            agent = InsightAgent(settings, db, real_llm)
        outcome = agent.ask(case["question"], generate_answer=False)
        # 打分用模型原始 SQL：守卫注入的 LIMIT 是生产安全措施，不参与 EX 判定
        score = execution_match(settings.db_path, outcome.predicted_sql, case["gold_sql"])
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "ex": score.match,
                "reason": score.reason,
                "status": outcome.status,
                "pred_sql": outcome.predicted_sql,
                "executed_sql": outcome.final_sql,
                "gold_sql": case["gold_sql"],
                "attempts": len(outcome.attempts),
                "error_kinds": [a.error_kind for a in outcome.attempts if not a.ok],
                "tokens": outcome.usage.get("total_tokens", 0),
                "cost": outcome.usage.get("cost", 0.0),
                "latency_ms": outcome.latency_ms,
            }
        )
        mark = "✓" if score.match else "✗"
        console.print(f"[{'green' if score.match else 'red'}]{mark}[/] {case['id']} {case['question']}")

    total = len(results)
    matched = sum(1 for r in results if r["ex"])
    summary = {
        "mode": "gold-replay" if gold_replay else "llm",
        "model": None if gold_replay else settings.llm_model,
        "cases": total,
        "ex_match": matched,
        "ex_accuracy": round(matched / total, 4) if total else 0.0,
        "total_cost": round(sum(r["cost"] for r in results), 6),
        "total_tokens": sum(r["tokens"] for r in results),
        "avg_latency_ms": int(sum(r["latency_ms"] for r in results) / total) if total else 0,
        "wall_seconds": round(time.monotonic() - started, 1),
    }

    report = {"summary": summary, "results": results}
    if out_path is None:
        out_dir = Path("eval/results")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_path = out_dir / f"smoke-{summary['mode']}-{stamp}.json"
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    table = Table(title=f"EX 结果（{summary['mode']}）")
    table.add_column("指标")
    table.add_column("值", justify="right")
    table.add_row("执行准确率 EX", f"{matched}/{total} = {summary['ex_accuracy']:.1%}")
    table.add_row("总成本", f"{summary['total_cost']:.6f}")
    table.add_row("总 tokens", str(summary["total_tokens"]))
    table.add_row("平均单题延迟", f"{summary['avg_latency_ms']} ms")
    table.add_row("报告文件", str(out_path))
    console.print(table)
    for r in results:
        if not r["ex"]:
            console.print(f"[red]未通过[/red] {r['id']}: {r['reason']}\n  pred: {r['pred_sql']}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="insight-agent 评测运行器")
    parser.add_argument("--cases", default="eval/cases/smoke.jsonl")
    parser.add_argument("--gold-replay", action="store_true", help="离线回放 gold SQL 自检评测基建")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    report = run_eval(args.cases, gold_replay=args.gold_replay, limit=args.limit, out_path=args.out)
    if args.gold_replay and report["summary"]["ex_accuracy"] < 1.0:
        raise SystemExit("gold-replay 未达 100%：评测基建存在 bug，请先修复")


if __name__ == "__main__":
    main()
