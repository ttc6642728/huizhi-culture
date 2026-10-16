"""评估层测试：指标计算、标注集校验、运行器行为与命令行入口。

三条原则贯穿本文件：

1. **指标用可手算的例子验证**——期望值直接在断言里写成算式或说明，
   不做「再算一遍同样的代码」这种同义反复。
2. **标注集出问题必须报错**——缺文件、字段类型错、id 重复、引用不存在的实体，
   一条都不能被静默跳过。
3. **全程不联网**——回答评估用注入的假后端；命令行入口只跑离线模式。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.data.loader import load_dataset
from src.data.repository import Repository
from src.eval import metrics as m
from src.eval import dataset as ev
from src.eval.runner import evaluate_answers, evaluate_retrieval
from src.qa.engine import BackendAnswer, QAEngine
from src.qa.retriever import Retriever

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def repo() -> Repository:
    return Repository(load_dataset())


@pytest.fixture(scope="module")
def retriever(repo: Repository) -> Retriever:
    return Retriever(repo, top_k=5)


# --------------------------------------------------------------------------
# 指标：可手算的例子
# --------------------------------------------------------------------------

#: 三名/五名的通用样例：a 强相关（3 级）、c 弱相关（1 级）、其余不相关
RANKED = ["a", "b", "c", "d", "e"]
GRADED = {"a": 3.0, "c": 1.0}


def test_as_grades_accepts_both_annotation_styles() -> None:
    assert m.as_grades(["a", "b"]) == {"a": 1.0, "b": 1.0}
    assert m.as_grades({"a": 3, "b": 0}) == {"a": 3.0}, "0 级应被剔除"


def test_dedup_keeps_first_position() -> None:
    assert m.dedup(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_mean_of_empty_is_zero() -> None:
    assert m.mean([]) == 0.0, "没有样本时返回 0，而不是抛异常"


def test_hit_at_k_uses_only_top_k() -> None:
    # 相关项 a 在第 1 名、c 在第 3 名
    assert m.hit_at_k(RANKED, GRADED, 1) == 1.0
    assert m.hit_at_k(RANKED, GRADED, 3) == 1.0
    assert m.hit_at_k(["b", "d", "e", "a"], GRADED, 3) == 0.0
    assert m.hit_at_k(RANKED, [], 5) == 0.0, "无相关项的查询不计命中"


def test_precision_at_k_divides_by_k_not_by_returned_count() -> None:
    # 只返回 1 条且命中：P@1 = 1/1，P@5 = 1/5（不足的名次算未命中）
    assert m.precision_at_k(["a"], {"a": 1}, 1) == 1.0
    assert m.precision_at_k(["a"], {"a": 1}, 5) == pytest.approx(0.2)


def test_recall_at_k_covers_two_of_two() -> None:
    assert m.recall_at_k(RANKED, GRADED, 1) == pytest.approx(0.5)  # 只召回 a
    assert m.recall_at_k(RANKED, GRADED, 3) == pytest.approx(1.0)  # a 与 c 都召回
    assert m.recall_at_k(RANKED, GRADED, 5) == pytest.approx(1.0)


def test_reciprocal_rank_is_inverse_of_first_hit_position() -> None:
    assert m.reciprocal_rank(["a", "b"], {"a": 1}) == 1.0
    assert m.reciprocal_rank(["b", "a"], {"a": 1}) == pytest.approx(0.5)
    assert m.reciprocal_rank(["b", "c"], {"a": 1}) == 0.0


def test_average_precision_matches_hand_computation() -> None:
    # 命中在第 1 与第 3 名：AP = (1/1 + 2/3) / 2
    assert m.average_precision(RANKED, GRADED) == pytest.approx((1.0 + 2 / 3) / 2)


def test_dcg_uses_exponential_gain() -> None:
    # DCG@2 = (2^3-1)/log2(2) + (2^1-1)/log2(3) = 7 + 1/log2(3)
    assert m.dcg_at_k([3, 1], 2) == pytest.approx(7 + 1 / 1.5849625007211562)


def test_ndcg_is_one_when_ideal_order_is_matched() -> None:
    # 名次 1、3 上分别是 3 级与 1 级，正好等于理想排序
    assert m.ndcg_at_k(RANKED, GRADED, 5) == pytest.approx(1.0)


def test_ndcg_penalises_putting_the_weak_item_first() -> None:
    # 把 1 级排在 1 位、3 级排在 2 位：
    #   DCG  = (2^1-1)/log2(2) + (2^3-1)/log2(3) = 1 + 7/log2(3)
    #   IDCG = (2^3-1)/log2(2) + (2^1-1)/log2(3) = 7 + 1/log2(3)
    value = m.ndcg_at_k(["c", "a"], GRADED, 2)
    assert value == pytest.approx((1 + 7 / 1.5849625007211562) / (7 + 1 / 1.5849625007211562))
    assert value < 1.0, "顺序错了就该扣分"


def test_ndcg_returns_zero_without_relevant_items() -> None:
    assert m.ndcg_at_k(RANKED, [], 5) == 0.0


# --------------------------------------------------------------------------
# 标注集：加载与严格校验
# --------------------------------------------------------------------------


def test_real_sets_load_and_validate(repo: Repository) -> None:
    rs, qs = ev.load_all(repo)
    assert len(rs.cases) >= 30, "检索标注集规模过小，指标没有统计意义"
    assert rs.negatives, "必须有负样本"
    assert qs.abstain and qs.answerable, "问答标注集必须同时包含可答与应拒答两类"
    assert rs.tags(), "标注应带标签，便于分组复盘"


def test_qa_labels_only_reference_real_entities(repo: Repository) -> None:
    _, qs = ev.load_all(repo)
    known = {e.id for e in repo.entities}
    for case in qs.cases:
        for entity_id in case.expect_citations:
            assert entity_id in known, f"{case.id} 引用了不存在的实体 {entity_id}"


def _write(tmp_path: Path, payload: dict, name: str = ev.RETRIEVAL_FILE) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ev.EvalDataError, match="不存在"):
        ev.load_retrieval_set(tmp_path / "nope.json")


def test_missing_id_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"cases": [{"query": "宏村", "relevant": {"hongcun": 3}}]})
    with pytest.raises(ev.EvalDataError, match="缺少 id"):
        ev.load_retrieval_set(path)


def test_duplicate_id_raises(tmp_path: Path) -> None:
    case = {"id": "r1", "query": "宏村", "relevant": {"hongcun": 3}}
    with pytest.raises(ev.EvalDataError, match="id 重复"):
        ev.load_retrieval_set(_write(tmp_path, {"cases": [case, dict(case)]}))


def test_bad_grade_raises(tmp_path: Path) -> None:
    case = {"id": "r1", "query": "宏村", "relevant": {"hongcun": 9}}
    with pytest.raises(ev.EvalDataError, match="等级应在"):
        ev.load_retrieval_set(_write(tmp_path, {"cases": [case]}))


def test_non_numeric_grade_raises(tmp_path: Path) -> None:
    case = {"id": "r1", "query": "宏村", "relevant": {"hongcun": "高"}}
    with pytest.raises(ev.EvalDataError, match="应为数字"):
        ev.load_retrieval_set(_write(tmp_path, {"cases": [case]}))


def test_all_negative_set_is_rejected(tmp_path: Path) -> None:
    cases = [{"id": "r1", "query": "量子纠缠", "relevant": []}]
    with pytest.raises(ev.EvalDataError, match="没有任何有答案的样本"):
        ev.load_retrieval_set(_write(tmp_path, {"cases": cases}))


def test_missing_negatives_is_reported(tmp_path: Path, repo: Repository) -> None:
    path = _write(tmp_path, {"cases": [{"id": "r1", "query": "宏村", "relevant": {"hongcun": 3}}]})
    problems = ev.validate_retrieval_set(ev.load_retrieval_set(path), repo)
    assert any("负样本" in p for p in problems)


def test_unknown_entity_is_reported(tmp_path: Path, repo: Repository) -> None:
    path = _write(tmp_path, {"cases": [{"id": "r1", "query": "不存在", "relevant": {"nope": 3}}]})
    problems = ev.validate_retrieval_set(ev.load_retrieval_set(path), repo)
    assert any("nope" in p for p in problems)


def test_abstain_case_may_not_carry_expectations(tmp_path: Path) -> None:
    case = {
        "id": "q1",
        "question": "量子纠缠是什么？",
        "must_abstain": True,
        "expect_citations": ["hongcun"],
    }
    with pytest.raises(ev.EvalDataError, match="互斥"):
        ev.load_qa_set(_write(tmp_path, {"cases": [case]}, ev.QA_FILE))


def test_answerable_case_needs_expectations(tmp_path: Path) -> None:
    case = {"id": "q1", "question": "宏村在哪？"}
    with pytest.raises(ev.EvalDataError, match="期望引用/要点"):
        ev.load_qa_set(_write(tmp_path, {"cases": [case]}, ev.QA_FILE))


# --------------------------------------------------------------------------
# 运行器：检索评估
# --------------------------------------------------------------------------


def test_retrieval_report_is_deterministic(retriever: Retriever, repo: Repository) -> None:
    rs, _ = ev.load_all(repo)
    first = evaluate_retrieval(retriever, rs, top_k=5)
    second = evaluate_retrieval(retriever, rs, top_k=5)
    assert first.aggregates == second.aggregates
    assert [(r.case_id, r.ranked) for r in first.rows] == [
        (r.case_id, r.ranked) for r in second.rows
    ]


def test_retrieval_report_shape_and_ranges(retriever: Retriever, repo: Repository) -> None:
    rs, _ = ev.load_all(repo)
    report = evaluate_retrieval(retriever, rs, top_k=5, ks=(1, 3, 5))
    assert report.ks == (1, 3, 5)
    assert len(report.rows) == len(rs.cases)
    for key in ("hit@1", "precision@3", "recall@5", "ndcg@5", "mrr", "map"):
        assert key in report.aggregates, f"缺少指标 {key}"
    for key, value in report.aggregates.items():
        assert 0.0 <= value <= 1.0, f"{key} 越界：{value}"
    assert 0.0 <= report.negative_empty_rate <= 1.0


def test_recall_is_monotonic_in_k(retriever: Retriever, repo: Repository) -> None:
    """召回率随 K 增大不应下降——否则说明名次处理有问题。"""
    rs, _ = ev.load_all(repo)
    report = evaluate_retrieval(retriever, rs, top_k=5, ks=(1, 3, 5))
    recalls = [report.aggregates[f"recall@{k}"] for k in report.ks]
    assert recalls == sorted(recalls), f"召回率未随 K 单调不减：{recalls}"


def test_known_negative_returns_nothing(retriever: Retriever) -> None:
    """语料外的查询必须空手而归，不能凑数。"""
    assert retriever.retrieve("量子纠缠与超导体") == []


def test_word_overlap_negatives_are_recorded_as_failures(
    retriever: Retriever, repo: Repository
) -> None:
    """词面重叠的负样本会被误召回——这是词袋检索的固有局限，指标必须如实计入。

    这里同时钉住两件事：一是这类样本确实被标了对应标签，二是报告没有把它们悄悄排除。
    """
    rs, _ = ev.load_all(repo)
    tagged = [c for c in rs.cases if "词面重叠" in c.tags]
    assert tagged, "标注集应包含「词面重叠」这一类困难负样本"

    report = evaluate_retrieval(retriever, rs, top_k=5)
    breakdown = report.tag_breakdown["词面重叠"]
    assert breakdown["negative_empty"] == 0.0, "若将来检索器能拦住它们，本断言需要随事实更新"
    assert report.negative_empty_rate < 1.0, "整体留空率必须把这类失败算进去"


def test_tag_breakdown_covers_every_tag(retriever: Retriever, repo: Repository) -> None:
    rs, _ = ev.load_all(repo)
    report = evaluate_retrieval(retriever, rs, top_k=5)
    assert set(report.tag_breakdown) == set(rs.tags())
    total = sum(int(v["cases"]) for v in report.tag_breakdown.values())
    assert total >= len(rs.cases), "同一查询可属多个标签，故合计不小于样本数"


def test_retrieval_json_is_serialisable(retriever: Retriever, repo: Repository) -> None:
    rs, _ = ev.load_all(repo)
    payload = evaluate_retrieval(retriever, rs, top_k=5).to_dict()
    text = json.dumps(payload, ensure_ascii=False)
    assert json.loads(text)["kind"] == "retrieval"


# --------------------------------------------------------------------------
# 运行器：回答评估（注入假后端，不联网）
# --------------------------------------------------------------------------


class _ScriptedBackend:
    """按问题返回预置回答的假后端。"""

    id = "scripted"
    label = "预置回答后端"

    def __init__(self, answers):
        self._answers = answers
        self.calls: list = []

    def available(self):
        return True, ""

    def answer(self, question, passages, *, directive=""):
        self.calls.append(question)
        return BackendAnswer(text=self._answers.get(question, ""), model="scripted")


def _qa_set_from(rows) -> ev.QASet:
    return ev.QASet(version="test", cases=tuple(rows))


def test_answer_metrics_on_controlled_backend(repo: Repository) -> None:
    legit = "宏村位于黟县。[1]"
    cases = [
        ev.QACase(id="q1", question="宏村在哪？", expect_citations=("hongcun",), required_terms=("黟县",)),
        ev.QACase(id="q2", question="徽墨属于哪类非遗？", expect_citations=("huimo",), required_terms=("传统技艺",)),
    ]
    backend = _ScriptedBackend({"宏村在哪？": legit, "徽墨属于哪类非遗？": "徽墨属于传统技艺。[1]"})
    engine = QAEngine(repo, backends=[backend])

    report = evaluate_answers(engine, _qa_set_from(cases))
    agg = report.aggregates
    assert agg["citation_coverage"] == 1.0
    assert agg["term_recall"] == 1.0
    assert agg["grounded_rate"] == 1.0
    assert agg["errors"] == 0
    assert backend.calls == ["宏村在哪？", "徽墨属于哪类非遗？"]


def test_answer_without_facts_lowers_term_recall(repo: Repository) -> None:
    cases = [ev.QACase(id="q1", question="宏村在哪？", expect_citations=("hongcun",), required_terms=("黟县", "黄山"))]
    engine = QAEngine(repo, backends=[_ScriptedBackend({"宏村在哪？": "宏村是一个村子。[1]"})])
    report = evaluate_answers(engine, _qa_set_from(cases))
    assert report.aggregates["term_recall"] == pytest.approx(0.0)
    assert report.rows[0].hit_terms == ()


def test_no_citation_counts_as_abstention(repo: Repository) -> None:
    """不产生任何引用即视为拒答——正确与否取决于这条样本是否本就该拒答。"""
    abstain = ev.QACase(id="q1", question="量子纠缠是什么？", must_abstain=True)
    answerable = ev.QACase(id="q2", question="宏村在哪？", expect_citations=("hongcun",))
    backend = _ScriptedBackend({"量子纠缠是什么？": "资料中没有相关内容。", "宏村在哪？": "资料中没有相关内容。"})
    report = evaluate_answers(QAEngine(repo, backends=[backend]), _qa_set_from([abstain, answerable]))

    by_id = {r.case_id: r for r in report.rows}
    assert by_id["q1"].abstention_correct is True
    assert by_id["q2"].abstention_correct is False, "该作答却拒答，应判为不正确"
    assert report.aggregates["abstention_accuracy"] == pytest.approx(0.5)


def test_invalid_citation_is_flagged(repo: Repository) -> None:
    cases = [ev.QACase(id="q1", question="宏村在哪？", expect_citations=("hongcun",), required_terms=("黟县",))]
    engine = QAEngine(repo, backends=[_ScriptedBackend({"宏村在哪？": "宏村位于黟县。[9]"})])
    report = evaluate_answers(engine, _qa_set_from(cases))
    row = report.rows[0]
    assert row.invalid_citations == (9,), "越界编号必须被记录"
    assert row.grounded is False
    assert report.aggregates["clean_citation_rate"] == 0.0


def test_all_backends_failed_is_recorded_not_swallowed(repo: Repository) -> None:
    cases = [ev.QACase(id="q1", question="宏村在哪？", expect_citations=("hongcun",))]
    engine = QAEngine(repo, backends=[_ScriptedBackend({})])  # 返回空回答 → 降级链耗尽
    report = evaluate_answers(engine, _qa_set_from(cases))
    assert report.rows[0].error, "后端全挂必须留下错误说明"
    assert report.aggregates["errors"] == 1.0


def test_answer_report_json_roundtrip(repo: Repository) -> None:
    cases = [ev.QACase(id="q1", question="宏村在哪？", expect_citations=("hongcun",), required_terms=("黟县",))]
    engine = QAEngine(repo, backends=[_ScriptedBackend({"宏村在哪？": "宏村位于黟县。[1]"})])
    payload = evaluate_answers(engine, _qa_set_from(cases)).to_dict()
    loaded = json.loads(json.dumps(payload, ensure_ascii=False))
    assert loaded["kind"] == "answer"
    assert loaded["backend"] == "scripted"


# --------------------------------------------------------------------------
# 命令行入口
# --------------------------------------------------------------------------


def test_cli_runs_offline_and_reports(tmp_path: Path) -> None:
    out = tmp_path / "eval.json"
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate.py"), "--retrieval-only", "--json", str(out)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, f"退出码 {done.returncode}：{done.stderr[-400:]}"
    assert "检索评估" in done.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["settings"]["live"] is False
    assert payload["retrieval"]["cases"] >= 30


def test_cli_rejects_malformed_ks() -> None:
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "evaluate.py"), "--ks", "a,b"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 2
    assert "--ks" in done.stdout
