import pytest

from insight_agent.evalkit.scorer import execution_match, gold_order_matters


class TestOrderSensitivity:
    def test_unordered_gold_ignores_row_order(self, demo_db_path):
        gold = "SELECT city, COUNT(*) FROM customers GROUP BY city"
        pred = "SELECT city, COUNT(*) FROM customers GROUP BY city ORDER BY city DESC"
        assert execution_match(demo_db_path, pred, gold).match

    def test_ordered_gold_requires_order(self, demo_db_path):
        gold = "SELECT id FROM customers ORDER BY id LIMIT 5"
        pred = "SELECT id FROM customers ORDER BY id DESC LIMIT 5"
        assert not execution_match(demo_db_path, pred, gold).match

    def test_gold_order_matters_detection(self):
        assert gold_order_matters("SELECT id FROM t ORDER BY id")
        assert not gold_order_matters("SELECT id FROM t")
        # 子查询里的 ORDER BY 不算顶层排序要求
        assert not gold_order_matters(
            "SELECT * FROM (SELECT id FROM t ORDER BY id LIMIT 3)"
        )


class TestComparison:
    def test_identical(self, demo_db_path):
        sql = "SELECT COUNT(*) FROM customers"
        assert execution_match(demo_db_path, sql, sql).match

    def test_equivalent_different_text(self, demo_db_path):
        gold = "SELECT COUNT(*) FROM customers WHERE city = '上海'"
        pred = "SELECT COUNT(id) FROM customers WHERE city LIKE '上海'"
        assert execution_match(demo_db_path, pred, gold).match

    def test_wrong_value(self, demo_db_path):
        gold = "SELECT COUNT(*) FROM customers"
        pred = "SELECT COUNT(*) FROM customers WHERE vip_level = 3"
        assert not execution_match(demo_db_path, pred, gold).match

    def test_column_count_mismatch(self, demo_db_path):
        gold = "SELECT id, name FROM customers ORDER BY id LIMIT 1"
        pred = "SELECT id FROM customers ORDER BY id LIMIT 1"
        score = execution_match(demo_db_path, pred, gold)
        assert not score.match and "列数" in score.reason

    def test_float_tolerance(self, demo_db_path):
        gold = "SELECT SUM(amount) FROM payments"
        pred = "SELECT ROUND(SUM(amount), 4) FROM payments"
        assert execution_match(demo_db_path, pred, gold).match

    def test_missing_pred(self, demo_db_path):
        assert not execution_match(demo_db_path, None, "SELECT 1").match

    def test_pred_error(self, demo_db_path):
        score = execution_match(demo_db_path, "SELECT * FROM ghosts", "SELECT 1")
        assert not score.match and "执行失败" in score.reason

    def test_broken_gold_raises(self, demo_db_path):
        with pytest.raises(ValueError):
            execution_match(demo_db_path, "SELECT 1", "SELECT * FROM ghosts")
