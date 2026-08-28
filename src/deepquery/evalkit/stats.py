"""评测统计：Wilson 置信区间 + McNemar 配对检验。

为什么需要：单次跑分的"提升了 7 个点"可能只是抖动。
- Wilson 区间回答"这个准确率的不确定度有多大"（小样本下比正态近似稳健）；
- McNemar 检验回答"两个配置在同一批题上的差异是否显著"（配对设计，
  只看两边结论不一致的题，比比较两个独立比例更有功效）。
纯标准库实现，不引入 scipy。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb, sqrt


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """成功率的 Wilson score 置信区间（默认 95%）。返回 (low, high)。"""
    if total <= 0:
        return (0.0, 0.0)
    if successes < 0 or successes > total:
        raise ValueError(f"successes 必须在 [0, {total}] 内，实际 {successes}")
    p = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denom
    margin = (z / denom) * sqrt(p * (1 - p) / total + z2 / (4 * total * total))
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass
class McNemarResult:
    b: int  # A 对、B 错的题数
    c: int  # A 错、B 对的题数
    p_value: float  # 精确二项检验（双侧）
    significant_05: bool

    def describe(self) -> str:
        return (
            f"不一致题数 b(A对B错)={self.b}, c(A错B对)={self.c}, "
            f"精确双侧 p={self.p_value:.4f}"
            f"（{'显著' if self.significant_05 else '不显著'} @0.05）"
        )


def mcnemar_exact(a_correct: list[bool], b_correct: list[bool]) -> McNemarResult:
    """精确 McNemar 检验（二项版本，适合不一致题数较少的场景）。

    输入为同一批题上两个配置的逐题对错（顺序必须对应同一题）。
    """
    if len(a_correct) != len(b_correct):
        raise ValueError(f"两组长度不一致: {len(a_correct)} vs {len(b_correct)}")
    b = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)
    c = sum(1 for x, y in zip(a_correct, b_correct) if not x and y)
    n = b + c
    if n == 0:
        return McNemarResult(b=b, c=c, p_value=1.0, significant_05=False)
    k = min(b, c)
    # 双侧精确 p：P(X <= k) * 2，X ~ Binomial(n, 0.5)，封顶 1
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2**n)
    p = min(1.0, 2 * tail)
    return McNemarResult(b=b, c=c, p_value=p, significant_05=p < 0.05)
