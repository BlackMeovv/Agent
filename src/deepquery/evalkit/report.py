"""消融对比报告：把多个带 label 的评测结果汇成一张表。

    python -m deepquery.evalkit.report eval/results/a.json eval/results/b.json \
        --out eval/results/report.md
    python -m deepquery.evalkit.report a.json b.json --mcnemar   # 对前两个做配对检验

这张表就是消融实验结论的原始材料：每行一个配置，
EX 带 95% 置信区间，成本与延迟并列——优化是否值得一目了然。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .stats import mcnemar_exact

console = Console()


def load_report(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _case_success(result: dict) -> bool:
    """多次重复时按多数票折算成单个布尔（repeats=1 时即原值）。"""
    votes = result.get("ex_by_repeat") or [result.get("ex", False)]
    return sum(votes) * 2 >= len(votes)


def compare(reports: list[dict]) -> list[dict]:
    rows = []
    for report in reports:
        s = report["summary"]
        rows.append(
            {
                "label": s.get("label", "?"),
                "model": s.get("model") or "-",
                "ex": f"{s['ex_accuracy']:.1%} [{s.get('wilson_low', 0):.1%}, {s.get('wilson_high', 0):.1%}]",
                "trials": f"{s.get('repeats', 1)}×{s['cases']}",
                "cost": f"{s.get('total_cost', 0):.4f}",
                "latency": f"{s.get('avg_latency_ms', 0)} ms",
            }
        )
    return rows


def mcnemar_between(a: dict, b: dict):
    a_map = {r["id"]: _case_success(r) for r in a["results"]}
    b_map = {r["id"]: _case_success(r) for r in b["results"]}
    common = sorted(a_map.keys() & b_map.keys())
    if not common:
        raise ValueError("两个报告没有共同的 case id，无法做配对检验")
    skipped = (len(a_map) - len(common)) + (len(b_map) - len(common))
    result = mcnemar_exact([a_map[i] for i in common], [b_map[i] for i in common])
    return result, len(common), skipped


def render_markdown(rows: list[dict], mcnemar_note: str = "") -> str:
    lines = [
        "# 评测对比报告",
        "",
        "| 配置 | 模型 | EX（95% CI） | 重复×题数 | 总成本 | 平均延迟 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['model']} | {r['ex']} | {r['trials']} | {r['cost']} | {r['latency']} |"
        )
    if mcnemar_note:
        lines += ["", f"**配对检验（前两个配置）**：{mcnemar_note}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="评测对比报告生成器")
    parser.add_argument("reports", nargs="+", help="runner 产出的结果 JSON 文件")
    parser.add_argument("--out", default=None, help="markdown 输出路径")
    parser.add_argument("--mcnemar", action="store_true", help="对前两个报告做 McNemar 配对检验")
    args = parser.parse_args()

    reports = [load_report(p) for p in args.reports]
    rows = compare(reports)

    table = Table(title="评测对比")
    for col in ("配置", "模型", "EX（95% CI）", "重复×题数", "总成本", "平均延迟"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["label"], r["model"], r["ex"], r["trials"], r["cost"], r["latency"])
    console.print(table)

    note = ""
    if args.mcnemar:
        if len(reports) < 2:
            raise SystemExit("--mcnemar 需要至少两个报告")
        result, n, skipped = mcnemar_between(reports[0], reports[1])
        note = f"{result.describe()}，共同题数 {n}" + (f"（{skipped} 条不重叠已跳过）" if skipped else "")
        console.print(note)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(render_markdown(rows, note), encoding="utf-8")
        console.print(f"已写入 {args.out}")


if __name__ == "__main__":
    main()
