from deepquery.tools.contract import QueryResult
from deepquery.verify import check_answer, extract_numbers


def result_with(rows, columns=None):
    return QueryResult(ok=True, columns=columns or ["v"], rows=rows, row_count=len(rows))


class TestExtractNumbers:
    def test_plain_and_thousands(self):
        nums = extract_numbers("总额 1,234.56 元，共 42 笔")
        assert nums[0].raw == "1,234.56" and nums[0].matches(1234.56)
        assert nums[1].matches(42)

    def test_wan_unit(self):
        (num,) = extract_numbers("约 1.2万 元")
        assert num.matches(12000) and num.matches(12345)  # 1.2万 是 12345 的舍入形式
        assert not num.matches(13000)

    def test_percent(self):
        (num,) = extract_numbers("占比 37.5%")
        assert num.matches(37.5) and num.matches(0.375)

    def test_rounding_tolerance(self):
        (num,) = extract_numbers("平均 14774.78 元")
        assert num.matches(14774.779393939392)  # 展示精度下的舍入形式
        assert not num.matches(14775.9)


class TestCheckAnswer:
    def test_clean_answer_passes(self):
        result = result_with([("上海", 20)], ["city", "cnt"])
        assert check_answer("上海共有 20 位客户。", result) == []

    def test_fabricated_number_flagged(self):
        result = result_with([(20,)])
        violations = check_answer("共有 20 位客户，占全部客户的 8.3%。", result)
        assert violations == ["8.3%"]

    def test_question_numbers_allowed(self):
        result = result_with([("用户0001", 18)])
        assert check_answer("下单最多的前5名中第一位下了 18 单。", result, question="前5名客户") == []

    def test_sql_numbers_allowed(self):
        result = result_with([(10,)])
        assert (
            check_answer(
                "vip_level 为 3 的客户有 10 人。", result, sql="SELECT COUNT(*) FROM c WHERE vip_level = 3"
            )
            == []
        )

    def test_numbers_inside_string_cells_allowed(self):
        result = result_with([("2025-01", 1305227.48)], ["month", "amount"])
        assert check_answer("2025年1月支付总额为 1,305,227.48 元。", result) == []

    def test_row_count_allowed(self):
        result = result_with([(f"row{i}",) for i in range(30)])
        assert check_answer("共返回 30 条记录。", result) == []

    def test_small_ordinals_allowed(self):
        result = result_with([("a", 100)])
        assert check_answer("第1名是 a，金额 100。", result) == []

    def test_empty_result(self):
        assert check_answer("没有符合条件的数据。", None) == []
