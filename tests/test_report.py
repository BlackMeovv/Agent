from deepquery.evalkit.report import _case_success, compare, mcnemar_between, render_markdown


def fake_report(label, ids_success: dict[str, bool]):
    return {
        "summary": {
            "label": label,
            "model": "m",
            "cases": len(ids_success),
            "repeats": 1,
            "ex_accuracy": sum(ids_success.values()) / len(ids_success),
            "wilson_low": 0.1,
            "wilson_high": 0.9,
            "total_cost": 0.01,
            "avg_latency_ms": 100,
        },
        "results": [
            {"id": i, "ex": ok, "ex_by_repeat": [ok]} for i, ok in ids_success.items()
        ],
    }


class TestReport:
    def test_compare_rows(self):
        rows = compare([fake_report("a", {"1": True, "2": False})])
        assert rows[0]["label"] == "a" and "50.0%" in rows[0]["ex"]

    def test_case_success_majority(self):
        assert _case_success({"ex_by_repeat": [True, True, False]})
        assert not _case_success({"ex_by_repeat": [True, False, False]})
        assert _case_success({"ex": True})  # 无 repeats 字段的兼容路径

    def test_mcnemar_between(self):
        a = fake_report("a", {"1": True, "2": False, "3": False})
        b = fake_report("b", {"1": True, "2": True, "3": True, "4": True})  # 4 不重叠
        result, n, skipped = mcnemar_between(a, b)
        assert n == 3 and skipped == 1
        assert result.c == 2 and result.b == 0

    def test_markdown_output(self):
        md = render_markdown(compare([fake_report("baseline", {"1": True})]), "p=1.0")
        assert "| baseline |" in md and "配对检验" in md
