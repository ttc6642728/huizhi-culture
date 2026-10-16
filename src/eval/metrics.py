"""评估指标（纯函数，零第三方依赖）。

相关性标注有两种写法，本模块都支持：

- **二元**：``["hongcun", "yixian"]``——列出的即相关；
- **分级**：``{"hongcun": 3, "yixian": 2}``——3 = 直接答案，2 = 高度相关，1 = 弱相关。

约定
----
- 排名列表 ``ranked`` 由检索器按相关度降序给出，**按位置计分**（第 1 名位置为 1）。
- 重复项会被去掉后计算，避免同一个实体占两个名次把指标刷高。
- ``K`` 超过列表长度时按列表长度处理（不足的名次不贡献收益，也不额外扣分）。

每个函数的公式都写在文档字符串里，可直接手算核对。
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, Sequence, Union

#: 相关性标注：实体 id 列表（二元）或 实体 id → 相关性等级 的映射（分级）
Relevance = Union[Sequence[str], Mapping[str, float]]

#: 默认评估的截断位置
DEFAULT_KS: tuple = (1, 3, 5)


def as_grades(relevant: Relevance) -> Dict[str, float]:
    """把两种标注写法统一成 ``{实体 id: 等级}``，并丢弃等级 ≤ 0 的项。"""
    if isinstance(relevant, Mapping):
        return {str(k): float(v) for k, v in relevant.items() if float(v) > 0}
    return {str(item): 1.0 for item in relevant}


def dedup(ranked: Iterable[str]) -> List[str]:
    """按名次去重，保留首次出现的位置。"""
    seen: set = set()
    out: List[str] = []
    for item in ranked:
        key = str(item)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def mean(values: Sequence[float]) -> float:
    """算术平均；空序列返回 0.0（而不是抛异常——没有样本就是无从评估）。"""
    return float(sum(values) / len(values)) if values else 0.0


# --------------------------------------------------------------------------
# 检索指标
# --------------------------------------------------------------------------


def hit_at_k(ranked: Sequence[str], relevant: Relevance, k: int) -> float:
    """前 K 名里是否至少命中一个相关项。命中 1.0，否则 0.0。"""
    grades = as_grades(relevant)
    if not grades:
        return 0.0
    return 1.0 if any(item in grades for item in dedup(ranked)[: max(0, k)]) else 0.0


def precision_at_k(ranked: Sequence[str], relevant: Relevance, k: int) -> float:
    """``P@K = 前 K 名中相关项数 / K``。

    分母固定为 ``K``（而不是实际返回条数），这样「返回不足 K 条」不会被算成满分；
    检索器返回空列表时结果自然为 0。
    """
    if k <= 0:
        return 0.0
    grades = as_grades(relevant)
    if not grades:
        return 0.0
    hits = sum(1 for item in dedup(ranked)[:k] if item in grades)
    return hits / k


def recall_at_k(ranked: Sequence[str], relevant: Relevance, k: int) -> float:
    """``R@K = 前 K 名命中的相关项数 / 全部相关项数``。"""
    grades = as_grades(relevant)
    if not grades:
        return 0.0
    hits = sum(1 for item in dedup(ranked)[: max(0, k)] if item in grades)
    return hits / len(grades)


def reciprocal_rank(ranked: Sequence[str], relevant: Relevance) -> float:
    """``RR = 1 / 第一个相关项的名次``；一个都没命中时为 0。"""
    grades = as_grades(relevant)
    if not grades:
        return 0.0
    for index, item in enumerate(dedup(ranked), start=1):
        if item in grades:
            return 1.0 / index
    return 0.0


def average_precision(ranked: Sequence[str], relevant: Relevance) -> float:
    """``AP = (Σ_{命中位置} P@位置) / 相关项总数``。

    用在「只关心前几名」的检索场景里，比单一 P@K 更能反映「相关项是否排在前排」。
    """
    grades = as_grades(relevant)
    if not grades:
        return 0.0
    hits = 0
    total = 0.0
    for index, item in enumerate(dedup(ranked), start=1):
        if item in grades:
            hits += 1
            total += hits / index
    return total / len(grades)


def dcg_at_k(gains: Sequence[float], k: int) -> float:
    """折损累计增益 ``DCG@K = Σ (2^g - 1) / log2(i + 1)``（i 从 1 起）。

    用 ``2^g - 1`` 而非 ``g``，让高等级相关项获得明显更大的收益：
    「3 级对了」比「三个 1 级对了」更值钱。
    """
    return sum(
        (2 ** gain - 1) / math.log2(index + 1)
        for index, gain in enumerate(gains[: max(0, k)], start=1)
    )


def ndcg_at_k(ranked: Sequence[str], relevant: Relevance, k: int) -> float:
    """``nDCG@K = DCG@K / IDCG@K``；IDCG 为「按等级降序排列时的理想 DCG」。

    标注全是二元（等级都为 1）时，nDCG 退化为一个受名次影响的召回度量。
    无相关项时返回 0.0——本函数只用于「应当有答案」的查询，
    负样本（无相关知识）由 :func:`src.eval.runner.evaluate_retrieval` 单独按
    「是否返回空列表」评估，不混进 nDCG。
    """
    grades = as_grades(relevant)
    if not grades:
        return 0.0
    gains = [grades[item] for item in dedup(ranked)[: max(0, k)] if item in grades]
    ideal = sorted(grades.values(), reverse=True)[: max(0, k)]
    denominator = dcg_at_k(ideal, k)
    if denominator <= 0:
        return 0.0
    return dcg_at_k(gains, k) / denominator
