"""BIRD / Spider 基准数据转换器：官方 dev 集 → 本项目 case jsonl。

    python -m insight_agent.evalkit.prepare bird /path/to/bird_dev \
        --out eval/cases/bird-dev.jsonl --limit 150 --seed 42
    python -m insight_agent.evalkit.prepare spider /path/to/spider \
        --out eval/cases/spider-dev.jsonl --limit 150

之后跑分（db 路径存的是相对基准根目录的路径，跑分时用 --db-root 指回去）：

    python -m insight_agent.evalkit.runner --cases eval/cases/bird-dev.jsonl \
        --db-root /path/to/bird_dev --repeats 3 --label baseline

数据下载见 docs/benchmarks.md。抽样固定 seed，保证子集可复现——
评测数字必须可复现，否则面试一问就穿。
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from pathlib import Path


def _find(root: Path, name: str) -> Path:
    """在 root 及其一级子目录里找文件/目录（官方 zip 解压层级不固定）。"""
    direct = root / name
    if direct.exists():
        return direct
    matches = sorted(root.glob(f"*/{name}"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"在 {root} 下找不到 {name}，请确认基准数据已解压")


def convert_bird(root: Path) -> tuple[list[dict], Path]:
    """BIRD dev：dev.json + dev_databases/<db_id>/<db_id>.sqlite。"""
    dev_json = _find(root, "dev.json")
    db_dir = _find(root, "dev_databases")
    items = json.loads(dev_json.read_text(encoding="utf-8"))
    cases = []
    for item in items:
        question = item["question"].strip()
        evidence = (item.get("evidence") or "").strip()
        if evidence:
            # BIRD 官方评测就是把 evidence 一并提供给模型的
            question = f"{question}\n（背景知识：{evidence}）"
        db_id = item["db_id"]
        cases.append(
            {
                "id": f"bird-{item['question_id']}",
                "question": question,
                "gold_sql": item["SQL"].strip(),
                "db": str((db_dir / db_id / f"{db_id}.sqlite").relative_to(root)),
                "tags": ["bird", item.get("difficulty") or "unknown"],
            }
        )
    return cases, root


def convert_spider(root: Path) -> tuple[list[dict], Path]:
    """Spider：dev.json + database/<db_id>/<db_id>.sqlite。"""
    dev_json = _find(root, "dev.json")
    db_dir = _find(root, "database")
    items = json.loads(dev_json.read_text(encoding="utf-8"))
    cases = []
    for i, item in enumerate(items):
        db_id = item["db_id"]
        cases.append(
            {
                "id": f"spider-{i:04d}",
                "question": item["question"].strip(),
                "gold_sql": item["query"].strip(),
                "db": str((db_dir / db_id / f"{db_id}.sqlite").relative_to(root)),
                "tags": ["spider"],
            }
        )
    return cases, root


def sample_cases(cases: list[dict], limit: int | None, seed: int) -> list[dict]:
    if limit is None or limit >= len(cases):
        return cases
    rng = random.Random(seed)
    picked = sorted(rng.sample(range(len(cases)), limit))
    return [cases[i] for i in picked]


def validate_cases(cases: list[dict], root: Path) -> tuple[list[dict], list[str]]:
    """gold 必须能在对应库上执行——坏 gold 是评测集的 bug，在转换期就剔除并报告。"""
    good, problems = [], []
    for case in cases:
        db_path = root / case["db"]
        if not db_path.exists():
            problems.append(f"{case['id']}: 数据库缺失 {db_path}")
            continue
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute(case["gold_sql"]).fetchmany(1)
            good.append(case)
        except sqlite3.Error as e:
            problems.append(f"{case['id']}: gold 执行失败: {e}")
        finally:
            conn.close()
    return good, problems


def prepare(
    bench: str,
    root: str | Path,
    out: str | Path,
    limit: int | None = None,
    seed: int = 42,
) -> dict:
    root = Path(root)
    if bench == "bird":
        cases, root = convert_bird(root)
    elif bench == "spider":
        cases, root = convert_spider(root)
    else:
        raise ValueError(f"未知基准: {bench}（支持 bird / spider）")

    total = len(cases)
    cases = sample_cases(cases, limit, seed)
    cases, problems = validate_cases(cases, root)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# {bench} 子集：{len(cases)}/{total} 条（seed={seed}），gold 已逐条执行校验\n"
        f"# 跑分：python -m insight_agent.evalkit.runner --cases {out} --db-root {root}\n"
    )
    lines = [json.dumps(c, ensure_ascii=False) for c in cases]
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return {"bench": bench, "total": total, "written": len(cases), "problems": problems, "out": str(out)}


def main() -> None:
    parser = argparse.ArgumentParser(description="BIRD/Spider → case jsonl 转换器")
    parser.add_argument("bench", choices=["bird", "spider"])
    parser.add_argument("root", help="基准数据根目录（解压后的目录）")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=None, help="固定 seed 抽样条数")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    info = prepare(args.bench, args.root, args.out, limit=args.limit, seed=args.seed)
    print(f"已写入 {info['written']}/{info['total']} 条到 {info['out']}")
    for p in info["problems"]:
        print(f"  [剔除] {p}")


if __name__ == "__main__":
    main()
