"""把检索器与问答引擎跑在标注集上，产出结构化报告。

两条评估线
----------

**检索评估**（:func:`evaluate_retrieval`）——只看「该被检索到的资料有没有被检索到」，
不涉及任何后端，因此完全离线且确定。

- 有答案的查询：Hit@K、Precision@K、Recall@K、nDCG@K、RR、AP；
- 无答案的负样本：只统计「是否正确返回了空列表」。
  负样本不进 nDCG——它们没有可排名的相关项，混进去只会让数字失去意义。

**回答评估**（:func:`evaluate_answers`）——看端到端行为，四项互相独立：

- **引用覆盖**：期望被引用的实体里，实际被引用到的比例；
- **要点命中**：金标准要点词在答案文本里的出现比例；
- **拒答表现**：该拒答的是否拒答、不该拒答的是否给了答案；
- **可溯源**：回答是否带可核查引用、有没有编造不存在的编号。

默认用本地检索式后端（离线、确定）；要评估真实大模型时传入别的引擎，
报告里会如实写明用的是哪个后端，不会张冠李戴。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from src.eval import metrics
from src.eval.dataset import QACase, QASet, RetrievalCase, RetrievalSet
from src.qa.engine import QAEngine
from src.qa.errors import AllBackendsFailedError
from src.qa.retriever import Retriever

#: 默认的截断位置
DEFAULT_KS: Tuple[int, ...] = (1, 3, 5)


# --------------------------------------------------------------------------
# 检索评估
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalRow:
    """单条查询的检索结果。"""

    case_id: str
    query: str
    tags: Tuple[str, ...]
    relevant: Mapping[str, float]
    ranked: Tuple[str, ...]
    is_negative: bool

    @property
    def empty_result(self) -> bool:
        return not self.ranked

    @property
    def ranked_titles(self) -> Tuple[str, ...]:
        return self.ranked


@dataclass(frozen=True)
class RetrievalReport:
    """检索评估报告。"""

    rows: Tuple[RetrievalRow, ...]
    ks: Tuple[int, ...]
    top_k: int
    aggregates: Mapping[str, float]
    index_stats: Mapping[str, object] = field(default_factory=dict)

    @property
    def positives(self) -> Tuple[RetrievalRow, ...]:
        return tuple(r for r in self.rows if not r.is_negative)

    @property
    def negatives(self) -> Tuple[RetrievalRow, ...]:
        return tuple(r for r in self.rows if r.is_negative)

    @property
    def negative_empty_rate(self) -> float:
        """负样本中「正确返回空列表」的比例。"""
        negs = self.negatives
        if not negs:
            return 0.0
        return metrics.mean([1.0 if r.empty_result else 0.0 for r in negs])

    @property
    def misses(self) -> Tuple[RetrievalRow, ...]:
        """有答案但前 K 名一个相关项都没命中的查询（用于人工复盘）。"""
        top = max(self.ks) if self.ks else self.top_k
        return tuple(
            r
            for r in self.positives
            if metrics.hit_at_k(r.ranked, r.relevant, top) == 0.0
        )

    @property
    def tag_breakdown(self) -> Dict[str, Dict[str, float]]:
        """按标签分组统计（同一查询可属于多个标签）。

        分组的意义在于**不让平均分掩盖差异**：把「专名」「别名」「关系」
        「词面重叠的负样本」混在一起算一个总分，会看不出问题究竟出在哪一类查询上。
        """
        top = max(self.ks) if self.ks else self.top_k
        tags = sorted({t for r in self.rows for t in r.tags})
        out: Dict[str, Dict[str, float]] = {}
        for tag in tags:
            rows = [r for r in self.rows if tag in r.tags]
            positives = [r for r in rows if not r.is_negative]
            negatives = [r for r in rows if r.is_negative]
            item: Dict[str, float] = {"cases": float(len(rows))}
            if positives:
                item["hit"] = round(
                    metrics.mean([metrics.hit_at_k(r.ranked, r.relevant, top) for r in positives]), 4
                )
                item["recall"] = round(
                    metrics.mean([metrics.recall_at_k(r.ranked, r.relevant, top) for r in positives]), 4
                )
                item["ndcg"] = round(
                    metrics.mean([metrics.ndcg_at_k(r.ranked, r.relevant, top) for r in positives]), 4
                )
                item["mrr"] = round(
                    metrics.mean([metrics.reciprocal_rank(r.ranked, r.relevant) for r in positives]), 4
                )
            if negatives:
                item["negative_empty"] = round(
                    metrics.mean([1.0 if r.empty_result else 0.0 for r in negatives]), 4
                )
            out[tag] = item
        return out

    def summary_lines(self) -> List[str]:
        lines = [
            f"检索评估：{len(self.rows)} 条标注（有答案 {len(self.positives)} / 负样本 {len(self.negatives)}），"
            f"索引 {self.index_stats.get('documents', '?')} 份资料"
        ]
        for k in self.ks:
            lines.append(
                f"  @{k}: Hit {self.aggregates.get(f'hit@{k}', 0):.3f}　"
                f"P {self.aggregates.get(f'precision@{k}', 0):.3f}　"
                f"R {self.aggregates.get(f'recall@{k}', 0):.3f}　"
                f"nDCG {self.aggregates.get(f'ndcg@{k}', 0):.3f}"
            )
        lines.append(
            f"  MRR {self.aggregates.get('mrr', 0):.3f}　"
            f"MAP {self.aggregates.get('map', 0):.3f}　"
            f"负样本正确留空 {self.negative_empty_rate:.3f}"
        )
        return lines

    def to_dict(self) -> Dict[str, object]:
        return {
            "kind": "retrieval",
            "cases": len(self.rows),
            "positives": len(self.positives),
            "negatives": len(self.negatives),
            "top_k": self.top_k,
            "ks": list(self.ks),
            "aggregates": dict(self.aggregates),
            "negative_empty_rate": round(self.negative_empty_rate, 4),
            "tags": self.tag_breakdown,
            "index": dict(self.index_stats),
            "rows": [
                {
                    "id": r.case_id,
                    "query": r.query,
                    "tags": list(r.tags),
                    "relevant": dict(r.relevant),
                    "ranked": list(r.ranked),
                    "is_negative": r.is_negative,
                    "empty": r.empty_result,
                }
                for r in self.rows
            ],
        }


def evaluate_retrieval(
    retriever: Retriever,
    rs: RetrievalSet,
    *,
    top_k: Optional[int] = None,
    ks: Sequence[int] = DEFAULT_KS,
) -> RetrievalReport:
    """在标注集上评估检索。只看检索，不调用任何后端。"""
    limit = max(1, int(top_k)) if top_k else retriever.top_k
    ks = tuple(sorted({max(1, int(k)) for k in ks}))
    effective_ks = tuple(k for k in ks if k <= limit) or (limit,)

    rows: List[RetrievalRow] = []
    for case in rs.cases:
        hits = retriever.retrieve(case.query, top_k=limit)
        rows.append(
            RetrievalRow(
                case_id=case.id,
                query=case.query,
                tags=case.tags,
                relevant=dict(case.relevant),
                ranked=tuple(h.entity_id for h in hits),
                is_negative=case.is_negative,
            )
        )

    positives = [r for r in rows if not r.is_negative]
    aggregates: Dict[str, float] = {}
    for k in effective_ks:
        aggregates[f"hit@{k}"] = round(
            metrics.mean([metrics.hit_at_k(r.ranked, r.relevant, k) for r in positives]), 4
        )
        aggregates[f"precision@{k}"] = round(
            metrics.mean([metrics.precision_at_k(r.ranked, r.relevant, k) for r in positives]), 4
        )
        aggregates[f"recall@{k}"] = round(
            metrics.mean([metrics.recall_at_k(r.ranked, r.relevant, k) for r in positives]), 4
        )
        aggregates[f"ndcg@{k}"] = round(
            metrics.mean([metrics.ndcg_at_k(r.ranked, r.relevant, k) for r in positives]), 4
        )
    aggregates["mrr"] = round(
        metrics.mean([metrics.reciprocal_rank(r.ranked, r.relevant) for r in positives]), 4
    )
    aggregates["map"] = round(
        metrics.mean([metrics.average_precision(r.ranked, r.relevant) for r in positives]), 4
    )

    return RetrievalReport(
        rows=tuple(rows),
        ks=effective_ks,
        top_k=limit,
        aggregates=aggregates,
        index_stats=retriever.stats(),
    )


# --------------------------------------------------------------------------
# 回答评估
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AnswerRow:
    """单条问答的结果。"""

    case_id: str
    question: str
    tags: Tuple[str, ...]
    must_abstain: bool
    abstained: bool
    expected: Tuple[str, ...]
    cited: Tuple[str, ...]
    required_terms: Tuple[str, ...]
    hit_terms: Tuple[str, ...]
    grounded: bool
    invalid_citations: Tuple[int, ...]
    backend: str
    elapsed_ms: int
    error: str = ""

    @property
    def citation_coverage(self) -> float:
        if not self.expected:
            return 1.0
        hit = len(set(self.expected) & set(self.cited))
        return hit / len(set(self.expected))

    @property
    def term_recall(self) -> float:
        if not self.required_terms:
            return 1.0
        return len(self.hit_terms) / len(self.required_terms)

    @property
    def abstention_correct(self) -> bool:
        """该拒答的拒答了、该回答的回答了，才算正确。"""
        return self.abstained if self.must_abstain else not self.abstained


@dataclass(frozen=True)
class AnswerReport:
    """回答评估报告。"""

    rows: Tuple[AnswerRow, ...]
    backend: str = ""

    @property
    def answerable(self) -> Tuple[AnswerRow, ...]:
        return tuple(r for r in self.rows if not r.must_abstain)

    @property
    def abstain_cases(self) -> Tuple[AnswerRow, ...]:
        return tuple(r for r in self.rows if r.must_abstain)

    def _agg(self, rows: Sequence[AnswerRow], getter) -> float:
        rows = [r for r in rows if not r.error]
        return round(metrics.mean([getter(r) for r in rows]), 4)

    @property
    def aggregates(self) -> Dict[str, float]:
        answerable = self.answerable
        return {
            "citation_coverage": self._agg(answerable, lambda r: r.citation_coverage),
            "term_recall": self._agg(answerable, lambda r: r.term_recall),
            "grounded_rate": self._agg(answerable, lambda r: 1.0 if r.grounded else 0.0),
            "answer_rate": self._agg(answerable, lambda r: 0.0 if r.abstained else 1.0),
            "abstention_accuracy": self._agg(self.rows, lambda r: 1.0 if r.abstention_correct else 0.0),
            "clean_citation_rate": self._agg(
                self.rows, lambda r: 0.0 if r.invalid_citations else 1.0
            ),
            "errors": float(sum(1 for r in self.rows if r.error)),
        }

    def summary_lines(self) -> List[str]:
        agg = self.aggregates
        return [
            f"回答评估：{len(self.rows)} 条（可答 {len(self.answerable)} / 应拒答 {len(self.abstain_cases)}），"
            f"后端：{self.backend or '未记录'}",
            f"  引用覆盖 {agg['citation_coverage']:.3f}　要点命中 {agg['term_recall']:.3f}　"
            f"可溯源 {agg['grounded_rate']:.3f}",
            f"  作答率 {agg['answer_rate']:.3f}　拒答判断正确 {agg['abstention_accuracy']:.3f}　"
            f"无编造编号 {agg['clean_citation_rate']:.3f}",
        ]

    def to_dict(self) -> Dict[str, object]:
        return {
            "kind": "answer",
            "backend": self.backend,
            "cases": len(self.rows),
            "aggregates": self.aggregates,
            "rows": [
                {
                    "id": r.case_id,
                    "question": r.question,
                    "tags": list(r.tags),
                    "must_abstain": r.must_abstain,
                    "abstained": r.abstained,
                    "expected": list(r.expected),
                    "cited": list(r.cited),
                    "required_terms": list(r.required_terms),
                    "hit_terms": list(r.hit_terms),
                    "grounded": r.grounded,
                    "invalid_citations": list(r.invalid_citations),
                    "backend": r.backend,
                    "elapsed_ms": r.elapsed_ms,
                    "error": r.error,
                }
                for r in self.rows
            ],
        }


def _contains(text: str, term: str) -> bool:
    return term.strip() in text


def evaluate_answers(engine: QAEngine, qs: QASet) -> AnswerReport:
    """在标注集上评估端到端问答。

    一律通过 ``engine.ask()`` 走真实链路（检索 + 后端降级 + 引用溯源），
    不在评估里另写一套逻辑，否则评的就不是用户实际得到的东西了。
    """
    rows: List[AnswerRow] = []
    backends: set = set()

    for case in qs.cases:
        try:
            result = engine.ask(case.question)
        except AllBackendsFailedError as exc:
            rows.append(
                AnswerRow(
                    case_id=case.id,
                    question=case.question,
                    tags=case.tags,
                    must_abstain=case.must_abstain,
                    abstained=True,
                    expected=case.expect_citations,
                    cited=(),
                    required_terms=case.required_terms,
                    hit_terms=(),
                    grounded=False,
                    invalid_citations=(),
                    backend="",
                    elapsed_ms=0,
                    error=f"全部后端失败：{exc}",
                )
            )
            continue

        backends.add(result.backend)
        cited = tuple(c.entity_id for c in result.citations)
        hit_terms = tuple(t for t in case.required_terms if _contains(result.answer, t))
        rows.append(
            AnswerRow(
                case_id=case.id,
                question=case.question,
                tags=case.tags,
                must_abstain=case.must_abstain,
                # 没有引用任何资料即视为拒答：本地后端与模型后端都会在资料不足时
                # 明确说明「没有检索到相关内容」，此时不会产生引用。
                abstained=not result.citations,
                expected=case.expect_citations,
                cited=cited,
                required_terms=case.required_terms,
                hit_terms=hit_terms,
                grounded=result.grounded,
                invalid_citations=result.invalid_citations,
                backend=result.backend,
                elapsed_ms=result.elapsed_ms,
            )
        )

    return AnswerReport(
        rows=tuple(rows),
        backend=", ".join(sorted(b for b in backends if b)) or "无",
    )


# --------------------------------------------------------------------------
# 合并报告
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalReport:
    """一次完整评估的结果（检索 + 回答）。"""

    retrieval: Optional[RetrievalReport] = None
    answers: Optional[AnswerReport] = None

    def summary_lines(self) -> List[str]:
        lines: List[str] = []
        if self.retrieval:
            lines += self.retrieval.summary_lines()
        if self.answers:
            lines += self.answers.summary_lines()
        return lines

    def to_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {"version": 1}
        if self.retrieval:
            out["retrieval"] = self.retrieval.to_dict()
        if self.answers:
            out["answers"] = self.answers.to_dict()
        return out


__all__ = [
    "RetrievalRow",
    "RetrievalReport",
    "AnswerRow",
    "AnswerReport",
    "EvalReport",
    "evaluate_retrieval",
    "evaluate_answers",
    "DEFAULT_KS",
]
