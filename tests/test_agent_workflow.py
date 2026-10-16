"""智能体工作流测试：步骤顺序、失败中止、日志完整性、自我核查与纠正、实体锚定。

全部用例**离线运行**：后端由 ``FakeBackend`` 注入，时钟由 ``FakeClock`` 注入，
既不联网也不消耗任何 API 额度。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from src.agent import workflow as wf
from src.agent.workflow import AgentWorkflow
from src.data.loader import load_dataset
from src.data.repository import Repository
from src.qa import prompt as qa_prompt
from src.qa.engine import BackendAnswer, LocalRetrievalBackend, QAEngine
from src.qa.retriever import Passage, Retriever

# --------------------------------------------------------------------------
# 测试替身
# --------------------------------------------------------------------------


class FakeClock:
    """每次读取都前进固定秒数，便于断言「耗时被记录且大于 0」。"""

    def __init__(self, step: float = 0.01):
        self._step = step
        self._now = 0.0

    def __call__(self) -> float:
        self._now += self._step
        return self._now


class FakeBackend:
    """按脚本依次返回回答的后端，并记录每次调用收到的参数。"""

    id = "fake"
    label = "假后端"

    def __init__(
        self,
        answers: Optional[Sequence[str]] = None,
        *,
        available: bool = True,
        reason: str = "",
        model: str = "fake-model",
    ):
        self._answers: List[str] = list(answers or [])
        self._available = available
        self._reason = reason
        self._model = model
        self.calls: List[Dict[str, object]] = []

    def available(self) -> Tuple[bool, str]:
        return self._available, self._reason

    def answer(
        self,
        question: str,
        passages: Sequence[Passage],
        *,
        directive: str = "",
    ) -> BackendAnswer:
        self.calls.append(
            {"question": question, "passages": tuple(passages), "directive": directive}
        )
        text = self._answers.pop(0) if self._answers else ""
        return BackendAnswer(text=text, model=self._model)


@pytest.fixture(scope="module")
def repo() -> Repository:
    return Repository(load_dataset())


def make_workflow(
    repository: Repository,
    backends: Sequence[object],
    *,
    top_k: int = 5,
) -> AgentWorkflow:
    engine = QAEngine(repository, backends=list(backends), top_k=top_k)
    return AgentWorkflow(repository, engine=engine, clock=FakeClock())


# --------------------------------------------------------------------------
# 步骤顺序与日志完整性
# --------------------------------------------------------------------------


def test_steps_follow_the_declared_order(repo: Repository) -> None:
    """步骤必须严格按 STEP_ORDER 执行，不允许跳步或改序。"""
    result = make_workflow(repo, [LocalRetrievalBackend()]).run("宏村是什么？")
    assert [s.key for s in result.steps] == list(wf.STEP_ORDER)


def test_every_step_records_input_output_and_elapsed(repo: Repository) -> None:
    """每一步都要有标题、状态、输入、输出与耗时——这是「可追踪」的最低要求。"""
    result = make_workflow(repo, [LocalRetrievalBackend()]).run("宏村是什么？")
    assert len(result.steps) == len(wf.STEP_ORDER)
    for step in result.steps:
        assert step.title == wf.STEP_TITLES[step.key]
        assert step.status in wf.STATUS_LABELS
        assert step.output_summary, f"{step.key} 缺少输出说明"
        assert step.elapsed_ms >= 0
        if step.executed:
            assert step.input_summary, f"{step.key} 缺少输入说明"
            assert "—" != step.input_summary
    executed = [s for s in result.steps if s.executed and s.key != wf.STEP_REVISE]
    assert all(s.elapsed_ms > 0 for s in executed), "真实执行的步骤必须记录到耗时"


def test_trace_covers_every_step(repo: Repository) -> None:
    """追踪日志必须覆盖全部步骤，且带状态与输入输出。"""
    result = make_workflow(repo, [LocalRetrievalBackend()]).run("徽商是什么？")
    lines = result.trace()
    assert len(lines) == len(wf.STEP_ORDER)
    text = result.trace_text()
    for step in result.steps:
        assert step.title in text
        assert step.status_label in text
    assert text.count("输入：") == len(wf.STEP_ORDER)
    assert text.count("输出：") == len(wf.STEP_ORDER)


def test_result_helpers_are_consistent(repo: Repository) -> None:
    result = make_workflow(repo, [LocalRetrievalBackend()]).run("宏村是什么？")
    assert result.step(wf.STEP_VERIFY) is not None
    assert result.step("不存在的步骤") is None
    # 核查一次通过，纠正重试被跳过，因此实际执行的是 5 步
    assert result.steps_executed == len(wf.STEP_ORDER) - 1
    assert result.aborted is False
    assert result.answer
    assert result.citations


# --------------------------------------------------------------------------
# 失败中止
# --------------------------------------------------------------------------


def test_invalid_question_aborts_at_first_step(repo: Repository) -> None:
    """问题不合法时在第 1 步中止，且后续步骤全部记为「跳过」。"""
    result = make_workflow(repo, [LocalRetrievalBackend()]).run("")
    assert result.status == "aborted"
    assert result.aborted_at == wf.STEP_INTENT
    assert result.abort_reason
    assert result.step(wf.STEP_INTENT).status == "failed"
    for key in wf.STEP_ORDER[1:]:
        skipped = result.step(key)
        assert skipped.status == "skipped", f"{key} 应为跳过"
        assert result.abort_reason in skipped.detail, "跳过的步骤必须写明中止原因"
    assert result.answer == ""
    assert result.answer_result is None


def test_aborts_when_nothing_retrieved(repo: Repository) -> None:
    """检索不到资料就地中止，不会让模型凭记忆作答。"""
    backend = FakeBackend(["这段回答不应该被用到。"])
    result = make_workflow(repo, [backend]).run("量子纠缠与超导体")

    assert result.status == "aborted"
    assert result.aborted_at == wf.STEP_RETRIEVE
    assert result.step(wf.STEP_RETRIEVE).status == "failed"
    assert result.step(wf.STEP_RETRIEVE).output_summary == "没有检索到任何相关资料"
    assert result.step(wf.STEP_ANSWER).status == "skipped"
    assert "检索" in result.abort_reason
    assert backend.calls == [], "检索不到资料时不应调用任何后端"
    assert result.answer == ""


def test_aborts_when_all_backends_fail(repo: Repository) -> None:
    """后端全部不可用时在第 3 步中止，并保留逐条失败原因。"""
    backend = FakeBackend([], available=False, reason="未配置 FAKE_KEY")
    result = make_workflow(repo, [backend]).run("宏村是什么？")

    assert result.status == "aborted"
    assert result.aborted_at == wf.STEP_ANSWER
    assert result.step(wf.STEP_RETRIEVE).status != "failed", "检索本身是成功的"
    answer_step = result.step(wf.STEP_ANSWER)
    assert answer_step.status == "failed"
    assert "未配置 FAKE_KEY" in answer_step.detail
    assert "未配置 FAKE_KEY" in result.abort_reason
    for key in (wf.STEP_VERIFY, wf.STEP_REVISE, wf.STEP_FINALIZE):
        assert result.step(key).status == "skipped"


# --------------------------------------------------------------------------
# 自我核查
# --------------------------------------------------------------------------


def test_verify_fails_without_citations(repo: Repository) -> None:
    """回答里没有编号 = 核查不通过（本项目要求每个事实都可溯源）。"""
    backend = FakeBackend(["宏村位于黟县，是一座有代表性的徽州村落。"])
    result = make_workflow(repo, [backend]).run("宏村是什么？")

    item = next(c for c in result.checks if c.label == "标注了来源编号")
    assert item.level == wf.LEVEL_FAIL
    assert result.verdict == wf.LEVEL_FAIL
    assert result.step(wf.STEP_VERIFY).status == "warn"
    assert result.status == "degraded"


def test_verify_fails_on_invalid_citation_numbers(repo: Repository) -> None:
    """引用了不存在的编号同样是不通过，且会被明确指出。"""
    backend = FakeBackend(["宏村位于黟县[9]。", "宏村位于黟县[9]。"])
    result = make_workflow(repo, [backend]).run("宏村是什么？")

    item = next(c for c in result.checks if c.label == "引用编号均指向真实资料")
    assert item.level == wf.LEVEL_FAIL
    assert "[9]" in item.detail
    assert {c.label for c in result.failed_checks} >= {
        "标注了来源编号",
        "引用编号均指向真实资料",
    }


def test_verify_warns_when_passages_underused(repo: Repository) -> None:
    """只用了少量资料属于警告（不致命），不会被夸大成失败。"""
    backend = FakeBackend(["宏村位于黟县[1]。"])
    result = make_workflow(repo, [backend]).run("宏村是什么？")

    item = next(c for c in result.checks if c.label == "检索资料被有效利用")
    assert item.level == wf.LEVEL_WARN
    assert result.verdict == wf.LEVEL_WARN
    assert result.status == "degraded"
    # 只出现警告时不触发纠正
    assert result.step(wf.STEP_REVISE).status == "skipped"


def test_degradation_is_visible_in_checks_and_steps(repo: Repository) -> None:
    """后端降级必须同时出现在核查表与作答步骤明细里，不能悄悄发生。"""
    dead = FakeBackend([], available=False, reason="未配置 FAKE_KEY")
    result = make_workflow(repo, [dead, LocalRetrievalBackend()]).run("宏村是什么？")

    assert result.answer_result.degraded is True
    item = next(c for c in result.checks if c.label == "未发生后端降级")
    assert item.level == wf.LEVEL_WARN
    assert "未配置 FAKE_KEY" in item.detail
    assert "未配置 FAKE_KEY" in result.step(wf.STEP_ANSWER).detail
    assert result.status == "degraded"


def test_grounded_run_passes_every_check(repo: Repository) -> None:
    """本地检索式后端的回答逐条标编号，应当全部核查通过。"""
    result = make_workflow(repo, [LocalRetrievalBackend()]).run("宏村是什么？")
    assert result.verdict == wf.LEVEL_PASS
    assert result.passed_checks == len(result.checks)
    assert result.status == "completed"


# --------------------------------------------------------------------------
# 纠正重试（至多一次）
# --------------------------------------------------------------------------


CITED_ANSWER = "宏村位于黟县[1]，西递同属黟县[2]，二者都是徽州古村落的代表[3]。"


def test_revise_retries_once_with_directive(repo: Repository) -> None:
    """核查未通过时带着具体原因重试一次；重试成功后结论随之更新。"""
    backend = FakeBackend(["宏村位于黟县，是徽州古村落的代表。", CITED_ANSWER])
    result = make_workflow(repo, [backend]).run("宏村是什么？")

    assert len(backend.calls) == 2, "纠正只应重试一次"
    assert backend.calls[0]["directive"] == ""
    assert backend.calls[1]["directive"] == qa_prompt.STRICT_RETRY_DIRECTIVE

    revise = result.step(wf.STEP_REVISE)
    assert revise.status == "ok"
    assert result.verdict == wf.LEVEL_PASS
    assert result.status == "corrected", "纠正后通过：整体结论应区别于一次就通过的运行"
    assert result.answer == CITED_ANSWER, "归档的应当是纠正后的回答"
    assert sum(1 for s in result.steps if s.key == wf.STEP_REVISE) == 1


def test_revise_failure_keeps_original_answer_and_reports_honestly(repo: Repository) -> None:
    """纠正失败时保留第一次的回答，并如实报告核查未通过。"""
    # 脚本用尽后 FakeBackend 返回空回答 → 引擎判定该后端失败 → 纠正整体失败
    backend = FakeBackend(["宏村位于黟县。", ""])
    result = make_workflow(repo, [backend]).run("宏村是什么？")

    revise = result.step(wf.STEP_REVISE)
    assert revise.status == "failed"
    assert "纠正未成功" in revise.output_summary
    assert result.verdict == wf.LEVEL_FAIL
    assert result.status == "degraded"
    assert result.answer == "宏村位于黟县。", "纠正失败不应丢掉原有回答"


# --------------------------------------------------------------------------
# 问题解析与实体锚定
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,kind",
    [
        ("宏村是什么？", wf.KIND_DEFINITION),
        ("宏村和西递有什么关系", wf.KIND_RELATION),
        ("胡适是哪里人", wf.KIND_ATTRIBUTE),
        ("马头墙有什么特点", wf.KIND_ATTRIBUTE),
        ("随便聊聊", wf.KIND_GENERAL),
    ],
)
def test_intent_kind_is_classified(repo: Repository, question: str, kind: str) -> None:
    assert wf.analyse_question(repo, question).kind == kind


def test_anchors_prefer_longer_names(repo: Repository) -> None:
    """长词优先：否则「徽州三雕」会被更短的「徽州」抢先锚定。"""
    assert wf.detect_anchors(repo, "徽州三雕是什么") == ("huizhou_sandiao",)
    assert wf.detect_anchors(repo, "宏村和西递有什么关系") == ("hongcun", "xidi")
    assert wf.detect_anchors(repo, "量子纠缠是什么") == ()


def test_intent_reports_anchor_names(repo: Repository) -> None:
    intent = wf.analyse_question(repo, "宏村和西递有什么关系")
    assert intent.kind == wf.KIND_RELATION
    assert intent.anchor_names == ("宏村", "西递")
    assert "关系类" in intent.summary
    assert "宏村" in intent.detail


def test_anchored_entity_is_put_first(repo: Repository) -> None:
    """锚定到的实体必须排进检索结果首位，而不是依赖 BM25 的自然排序。"""
    result = make_workflow(repo, [LocalRetrievalBackend()]).run("徽州三雕是什么")
    assert result.passages, "应当检索到资料"
    assert result.passages[0].entity_id == "huizhou_sandiao"
    assert "锚定实体" in result.step(wf.STEP_RETRIEVE).input_summary
    assert "来自锚定实体" in result.step(wf.STEP_RETRIEVE).output_summary


def test_run_records_warning_when_no_anchor_found(repo: Repository) -> None:
    """锚不到实体时如实给出警告，但不影响流程继续。"""
    result = make_workflow(repo, [LocalRetrievalBackend()]).run("徽州的村落有什么特点")
    intent_step = result.step(wf.STEP_INTENT)
    if not result.intent.anchor_ids:
        assert intent_step.status == "warn"
        assert "未识别到已知实体" in intent_step.detail


def test_suggest_questions_reference_real_entities(repo: Repository) -> None:
    questions = wf.suggest_questions(repo, limit=4)
    assert len(questions) == 4
    names = {e.name for e in repo.entities}
    for question in questions:
        assert any(name in question for name in names), f"示例问题引用了不存在的实体：{question}"


# --------------------------------------------------------------------------
# 引擎侧配合改动
# --------------------------------------------------------------------------


class CountingRetriever:
    """包一层用于统计 ``retrieve`` 调用次数。"""

    def __init__(self, inner: Retriever):
        self._inner = inner
        self.calls = 0

    @property
    def top_k(self) -> int:
        return self._inner.top_k

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Passage]:
        self.calls += 1
        return self._inner.retrieve(query, top_k=top_k)


def test_answer_from_reuses_given_passages_without_retrieving(repo: Repository) -> None:
    """工作流把检索与作答拆成两步，``answer_from`` 不应再自行检索一次。"""
    counting = CountingRetriever(Retriever(repo, top_k=5))
    engine = QAEngine(repo, retriever=counting, backends=[LocalRetrievalBackend()], top_k=5)

    passages = counting.retrieve("宏村是什么？")
    assert counting.calls == 1

    result = engine.answer_from("宏村是什么？", passages)
    assert counting.calls == 1, "answer_from 不应重复检索"
    assert result.passages == tuple(passages)
    assert result.citations


def test_backend_protocol_without_directive_still_works(repo: Repository) -> None:
    """旧式后端（不接受 directive 参数）在常规问答路径上必须照常工作。"""

    class LegacyBackend:
        id = "legacy"
        label = "旧式后端"

        def available(self) -> Tuple[bool, str]:
            return True, ""

        def answer(self, question: str, passages: Sequence[Passage]) -> BackendAnswer:
            return BackendAnswer(text="宏村位于黟县[1]。", model="legacy")

    engine = QAEngine(repo, backends=[LegacyBackend()], top_k=5)
    result = engine.ask("宏村是什么？")
    assert result.citations, "旧式后端应正常返回带引用的回答"
