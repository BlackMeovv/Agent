"""执行准确率（Execution Accuracy, EX）打分。

约定与 BIRD/Spider 的 EX 一致：比较两条 SQL 在同一库上的执行结果集，
不比较 SQL 文本本身。gold 无 ORDER BY 时按多重集合比较（行序无关），
有 ORDER BY 时按序比较。浮点按 4 位小数取整后比较。
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp

_SCORER_MAX_ROWS = 10_000  # 打分不受 agent 行数限额影响，用更高的安全上限


@dataclass
class ExecutionScore:
    match: bool
    reason: str = ""
    pred_rows: int | None = None
    gold_rows: int | None = None


def _normalize_cell(value):
    if isinstance(value, float):
        return round(value, 4)
    return value


def _run(db_path: str | Path, sql: str) -> tuple[int, list[tuple]]:
    """返回 (列数, 行)。列数取自 cursor.description——空结果集也有列信息。"""
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        cur = conn.execute(sql)
        ncols = len(cur.description) if cur.description else 0
        rows = cur.fetchmany(_SCORER_MAX_ROWS)
        return ncols, [tuple(_normalize_cell(v) for v in row) for row in rows]
    finally:
        conn.close()


def tables_in_sql(sql: str) -> set[str]:
    """提取 SQL 引用的真实表名（排除 CTE 别名，小写）。选表召回率用。"""
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return set()
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    return {
        t.name.lower()
        for t in tree.find_all(exp.Table)
        if isinstance(t.this, exp.Identifier) and t.name.lower() not in cte_names
    }


def gold_order_matters(gold_sql: str) -> bool:
    try:
        tree = sqlglot.parse_one(gold_sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return False
    return tree.args.get("order") is not None if isinstance(tree, exp.Expression) else False


def execution_match(db_path: str | Path, pred_sql: str | None, gold_sql: str) -> ExecutionScore:
    if not pred_sql:
        return ExecutionScore(match=False, reason="无预测 SQL")
    try:
        gold_ncols, gold_rows = _run(db_path, gold_sql)
    except sqlite3.Error as e:
        # gold 本身跑不通是评测集的 bug，必须显式暴露而不是判 agent 错
        raise ValueError(f"gold SQL 执行失败（评测集数据问题）: {e}\n{gold_sql}") from e
    try:
        pred_ncols, pred_rows = _run(db_path, pred_sql)
    except sqlite3.Error as e:
        return ExecutionScore(match=False, reason=f"预测 SQL 执行失败: {e}", gold_rows=len(gold_rows))

    score = ExecutionScore(match=False, pred_rows=len(pred_rows), gold_rows=len(gold_rows))
    if pred_ncols != gold_ncols:
        score.reason = f"列数不一致: pred={pred_ncols}, gold={gold_ncols}"
        return score
    if gold_order_matters(gold_sql):
        score.match = pred_rows == gold_rows
        score.reason = "" if score.match else "行内容或顺序不一致"
    else:
        score.match = Counter(pred_rows) == Counter(gold_rows)
        score.reason = "" if score.match else "结果多重集不一致"
    return score
