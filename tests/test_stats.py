import pytest

from insight_agent.evalkit.stats import mcnemar_exact, wilson_interval


class TestWilson:
    def test_known_value(self):
        # 15/20 = 75%，Wilson 95% 区间约 (0.531, 0.888)
        low, high = wilson_interval(15, 20)
        assert low == pytest.approx(0.531, abs=0.01)
        assert high == pytest.approx(0.888, abs=0.01)

    def test_bounds(self):
        low, high = wilson_interval(0, 10)
        assert low == 0.0 and 0 < high < 0.35
        low, high = wilson_interval(10, 10)
        assert 0.65 < low < 1 and high == 1.0

    def test_empty(self):
        assert wilson_interval(0, 0) == (0.0, 0.0)

    def test_narrower_with_more_samples(self):
        w20 = wilson_interval(15, 20)
        w200 = wilson_interval(150, 200)
        assert (w200[1] - w200[0]) < (w20[1] - w20[0])

    def test_invalid(self):
        with pytest.raises(ValueError):
            wilson_interval(11, 10)


class TestMcNemar:
    def test_no_disagreement(self):
        result = mcnemar_exact([True, False], [True, False])
        assert result.p_value == 1.0 and not result.significant_05

    def test_symmetric_disagreement_not_significant(self):
        a = [True, False] * 5
        b = [False, True] * 5
        result = mcnemar_exact(a, b)
        assert result.b == 5 and result.c == 5
        assert result.p_value > 0.05

    def test_onesided_improvement_significant(self):
        # B 在 8 道题上翻对、0 道翻错：p = 2 * (1/2^8) = 0.0078
        a = [False] * 8 + [True] * 12
        b = [True] * 20
        result = mcnemar_exact(a, b)
        assert result.b == 0 and result.c == 8
        assert result.p_value == pytest.approx(2 / 256)
        assert result.significant_05

    def test_length_mismatch(self):
        with pytest.raises(ValueError):
            mcnemar_exact([True], [True, False])
