"""评测运行器。

    python -m insight_agent.evalkit.runner --cases eval/cases/smoke.jsonl                  # 真实 LLM
    python -m insight_agent.evalkit.runner --cases eval/cases/smoke.jsonl --gold-replay    # 离线自检
    python -m insight_agent.evalkit.runner --cases eval/cases/bird-dev.jsonl \
        --repeats 3 --label "baseline"                                                     # 正式跑分

设计要点：
- --gold-replay 用 MockLLM 把每题 gold SQL 原样喂给 agent，验证评测基建本身，
  跑不到 100% 说明 harness 有 bug（离线、零成本）。
- --repeats N 重复整套评测 N 次，汇总为合并试验的 Wilson 95% 置信区间——
  报"58.0% [51.2, 64.5]"而不是一个孤立数字。
- 每条 case 可带 "db" 字段（相对 --db-root 或 cases 文件目录），支持 BIRD/Spider
  这类一题一库的基准；不带则用 .env 的 DB_PATH。
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
from .stats import wilson_interval

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
    repeats: int = 1,
    label: str | None = None,
    db_root: str | Path | None = None,
) -> dict:
    settings = get_settings()
    cases = load_cases(cases_path)
    if limit:
        cases = cases[:limit]
    if repeats < 1:
        raise ValueError("repeats 必须 >= 1")

    root = Path(db_root) if db_root else Path(cases_path).parent

    def resolve_db_path(case: dict) -> Path:
        if case.get("db"):
            p = Path(case["db"])
            return p if p.is_absolute() else root / p
        return Path(settings.db_path)

    dbs: dict[str, ReadOnlyDatabase] = {}
    agents: dict[str, InsightAgent] = {}
    real_llm = None if gold_replay else LLMClient(settings)

    def get_db(path: Path) -> ReadOnlyDatabase:
        key = str(path)
        if key not in dbs:
            dbs[key] = ReadOnlyDatabase(
                path,
                timeout_seconds=settings.sql_timeout_seconds,
                max_rows=settings.sql_max_rows,
            )
        return dbs[key]

    per_case: dict[str, dict] = {
        c["id"]: {"case": c, "ex_by_repeat": [], "tokens": 0, "cost": 0.0, "latency": []}
        for c in cases
    }
    per_repeat_accuracy: list[float] = []
    started = time.monotonic()

    for r in range(repeats):
        matched = 0
        for case in cases:
            db_path = resolve_db_path(case)
            db = get_db(db_path)
            if gold_replay:
                llm = MockLLM([f"直接回放 gold SQL。\n```sql\n{case['gold_sql']}\n```"])
                agent = InsightAgent(settings, db, llm)
            else:
                key = str(db_path)
                if key not in agents:
                    agents[key] = InsightAgent(settings, db, real_llm)
                agent = agents[key]

            outcome = agent.ask(case["question"], generate_answer=False)
            # 打分用模型原始 SQL：守卫注入的 LIMIT 是生产安全措施，不参与 EX 判定
            score = execution_match(db_path, outcome.predicted_sql, case["gold_sql"])

            entry = per_case[case["id"]]
            entry["ex_by_repeat"].append(score.match)
            entry["tokens"] += outcome.usage.get("total_tokens", 0)
            entry["cost"] += outcome.usage.get("cost", 0.0)
            entry["latency"].append(outcome.latency_ms)
            entry["last"] = {
                "ex": score.match,
                "reason": score.reason,
                "status": outcome.status,
                "pred_sql": outcome.predicted_sql,
                "executed_sql": outcome.final_sql,
                "attempts": len(outcome.attempts),
                "error_kinds": [a.error_kind for a in outcome.attempts if not a.ok],
            }
            if score.match:
                matched += 1
            mark, color = ("✓", "green") if score.match else ("✗", "red")
            prefix = f"[r{r + 1}] " if repeats > 1 else ""
            console.print(f"[{color}]{mark}[/] {prefix}{case['id']} {case['question'][:60]}")
        per_repeat_accuracy.append(round(matched / len(cases), 4) if cases else 0.0)

    total_trials = repeats * len(cases)
    pooled = sum(sum(e["ex_by_repeat"]) for e in per_case.values())
    low, high = wilson_interval(pooled, total_trials)

    results = []
    for case in cases:
        entry = per_case[case["id"]]
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "gold_sql": case["gold_sql"],
                "db": case.get("db"),
                "ex_by_repeat": entry["ex_by_repeat"],
                "success_rate": round(sum(entry["ex_by_repeat"]) / repeats, 4),
                "tokens": entry["tokens"],
                "cost": round(entry["cost"], 6),
                "avg_latency_ms": int(sum(entry["latency"]) / len(entry["latency"])),
                **entry["last"],
            }
        )

    mode = "gold-replay" if gold_replay else "llm"
    summary = {
        "label": label or f"{Path(cases_path).stem}-{mode}",
        "mode": mode,
        "model": None if gold_replay else settings.llm_model,
        "cases": len(cases),
        "repeats": repeats,
        "trials": total_trials,
        "ex_matched": pooled,
        "ex_accuracy": round(pooled / total_trials, 4) if total_trials else 0.0,
        "wilson_low": round(low, 4),
        "wilson_high": round(high, 4),
        "per_repeat_accuracy": per_repeat_accuracy,
        "total_cost": round(sum(e["cost"] for e in per_case.values()), 6),
        "total_tokens": sum(e["tokens"] for e in per_case.values()),
        "avg_latency_ms": (
            int(sum(r["avg_latency_ms"] for r in results) / len(results)) if results else 0
        ),
        "wall_seconds": round(time.monotonic() - started, 1),
    }

    report = {"summary": summary, "results": results}
    if out_path is None:
        out_dir = Path("eval/results")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_path = out_dir / f"{summary['label']}-{stamp}.json"
    Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    table = Table(title=f"EX 结果 · {summary['label']}")
    table.add_column("指标")
    table.add_column("值", justify="right")
    ci = f"{summary['ex_accuracy']:.1%} [{low:.1%}, {high:.1%}]"
    table.add_row("执行准确率 EX（95% CI）", f"{pooled}/{total_trials} = {ci}")
    if repeats > 1:
        table.add_row("各次重复", ", ".join(f"{a:.1%}" for a in per_repeat_accuracy))
    table.add_row("总成本", f"{summary['total_cost']:.6f}")
    table.add_row("总 tokens", str(summary["total_tokens"]))
    table.add_row("平均单题延迟", f"{summary['avg_latency_ms']} ms")
    table.add_row("报告文件", str(out_path))
    console.print(table)
    for r_ in results:
        if r_["success_rate"] < 1.0:
            console.print(
                f"[red]未通过[/red] {r_['id']} (成功率 {r_['success_rate']:.0%}): {r_['reason']}"
            )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="insight-agent 评测运行器")
    parser.add_argument("--cases", default="eval/cases/smoke.jsonl")
    parser.add_argument("--gold-replay", action="store_true", help="离线回放 gold SQL 自检评测基建")
    parser.add_argument("--repeats", type=int, default=1, help="重复次数（汇总为 Wilson 置信区间）")
    parser.add_argument("--label", default=None, help="本次配置名（消融表行名）")
    parser.add_argument("--db-root", default=None, help="case 内相对 db 路径的根目录")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    report = run_eval(
        args.cases,
        gold_replay=args.gold_replay,
        limit=args.limit,
        out_path=args.out,
        repeats=args.repeats,
        label=args.label,
        db_root=args.db_root,
    )
    if args.gold_replay and report["summary"]["ex_accuracy"] < 1.0:
        raise SystemExit("gold-replay 未达 100%：评测基建存在 bug，请先修复")


if __name__ == "__main__":
    main()
