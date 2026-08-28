"""评测集自身的质量门禁：gold SQL 必须过守卫、可执行、结果非空、自评满分。"""

from pathlib import Path

import pytest

from deepquery.evalkit.runner import load_cases
from deepquery.evalkit.scorer import execution_match
from deepquery.guard import validate

CASES = load_cases(Path(__file__).parent.parent / "eval" / "cases" / "smoke.jsonl")


def test_case_count_and_ids_unique():
    assert len(CASES) == 20
    assert len({c["id"] for c in CASES}) == 20


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_gold_passes_guard(case, db):
    verdict = validate(case["gold_sql"], allowed_tables=set(db.table_names()), max_rows=10_000)
    assert verdict.allowed, f"gold 未过守卫: {verdict.reason}"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_gold_executes_nonempty(case, db):
    result = db.run_query(case["gold_sql"])
    assert result.ok, f"gold 执行失败或为空: [{result.error_kind}] {result.error_message}"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_gold_scores_itself(case, demo_db_path):
    assert execution_match(demo_db_path, case["gold_sql"], case["gold_sql"]).match


def test_demo_db_deterministic(tmp_path):
    """演示库必须可复现：两次构建的行数与金额校验和一致。"""
    import sqlite3

    from deepquery.demo_data import build

    def checksum(path):
        conn = sqlite3.connect(path)
        try:
            out = {}
            for table in ("customers", "products", "orders", "order_items", "payments"):
                out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            out["amount_sum"] = conn.execute("SELECT ROUND(SUM(amount), 2) FROM payments").fetchone()[0]
            return out
        finally:
            conn.close()

    a = build(tmp_path / "a.sqlite")
    b = build(tmp_path / "b.sqlite")
    assert checksum(a) == checksum(b)
