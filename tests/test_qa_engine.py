"""问答引擎测试：三层后端的解析、降级链与引用溯源。

全部使用**注入的假后端 / 假 HTTP 响应**，因此不联网、不消耗任何 API 额度，
并且能稳定覆盖超时、返回体异常、引用越界等真实环境里偶发难复现的分支。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import pytest

from src import config
from src.data.loader import Source, load_dataset
from src.data.repository import Repository
from src.qa.engine import (
    BackendAnswer,
    DifyBackend,
    LocalRetrievalBackend,
    OpenAICompatBackend,
    QAEngine,
    default_backends,
    requests_post,
)
from src.qa.errors import (
    AllBackendsFailedError,
    BackendResponseError,
    BackendTimeoutError,
    BackendUnavailableError,
    QuestionError,
)
from src.qa.retriever import Passage, Retriever


# --------------------------------------------------------------------------
# 测试替身
# --------------------------------------------------------------------------


class FakeResponse:
    """模仿 requests.Response 的最小接口。"""

    def __init__(self, status_code: int = 200, payload: Optional[dict] = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ("{}" if payload is None else str(payload))

    def json(self) -> dict:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeTimeout(Exception):
    """类名含 timeout，用于验证异常翻译逻辑。"""


class FakeBackend:
    """可控的假后端：可配置可用性、回答文本与抛出的异常。"""

    def __init__(
        self,
        backend_id: str,
        label: str,
        available: bool = True,
        reason: str = "",
        answer: str = "这是回答 [1]。",
        raises: Optional[BaseException] = None,
        model: str = "fake",
    ):
        self.id = backend_id
        self.label = label
        self._available = available
        self._reason = reason
        self._answer = answer
        self._raises = raises
        self._model = model
        self.calls: List[Tuple[str, Sequence[Passage]]] = []

    def available(self) -> Tuple[bool, str]:
        return self._available, self._reason

    def answer(self, question: str, passages: Sequence[Passage]) -> BackendAnswer:
        self.calls.append((question, passages))
        if self._raises is not None:
            raise self._raises
        return BackendAnswer(text=self._answer, model=self._model, usage={"total_tokens": 7})


@pytest.fixture(scope="module")
def repo() -> Repository:
    return Repository(load_dataset())


@pytest.fixture(scope="module")
def retriever(repo: Repository) -> Retriever:
    return Retriever(repo, top_k=3)


def _passage(entity_id: str = "hongcun", title: str = "宏村", with_source: bool = True) -> Passage:
    sources = (
        (Source(id="s1", type="web", title="皖南古村落", publisher="UNESCO", url="https://e.org"),)
        if with_source
        else ()
    )
    return Passage(
        entity_id=entity_id,
        title=title,
        category_name="古村落",
        text="正文",
        score=1.0,
        matched_terms=(title,),
        sources=sources,
        relation_count=1,
    )


def _engine(repo: Repository, retriever: Retriever, backends: Sequence) -> QAEngine:
    return QAEngine(repo, retriever=retriever, backends=backends)


# --------------------------------------------------------------------------
# 降级链
# --------------------------------------------------------------------------


def test_first_available_backend_is_used(repo: Repository, retriever: Retriever) -> None:
    first = FakeBackend("a", "后端A", answer="A 的回答 [1]。")
    second = FakeBackend("b", "后端B")
    result = _engine(repo, retriever, [first, second]).ask("宏村是什么？")
    assert result.backend == "a"
    assert len(first.calls) == 1 and not second.calls, "可用后端应被使用，且不应继续尝试后续后端"
    assert result.degradations == ()


def test_unavailable_backend_is_skipped_with_reason(repo: Repository, retriever: Retriever) -> None:
    first = FakeBackend("dify", "Dify", available=False, reason="未配置 DIFY_BASE_URL")
    second = FakeBackend("llm", "大模型", answer="回答 [1]。")
    result = _engine(repo, retriever, [first, second]).ask("宏村是什么？")
    assert result.backend == "llm"
    assert not first.calls, "不可用的后端不应被调用"
    assert any("未配置 DIFY_BASE_URL" in d for d in result.degradations)
    assert result.degraded is True


def test_failing_backend_falls_through(repo: Repository, retriever: Retriever) -> None:
    broken = FakeBackend("llm", "大模型", raises=BackendResponseError("HTTP 500", backend="llm"))
    fallback = FakeBackend("local", "本地检索式", answer="本地回答 [1]。")
    result = _engine(repo, retriever, [broken, fallback]).ask("宏村是什么？")
    assert result.backend == "local"
    assert any("HTTP 500" in d for d in result.degradations)


def test_unexpected_exception_also_triggers_fallback(repo: Repository, retriever: Retriever) -> None:
    broken = FakeBackend("llm", "大模型", raises=RuntimeError("意料之外"))
    fallback = FakeBackend("local", "本地检索式", answer="本地回答 [1]。")
    result = _engine(repo, retriever, [broken, fallback]).ask("宏村是什么？")
    assert result.backend == "local"
    assert any("RuntimeError" in d for d in result.degradations)


def test_empty_answer_is_treated_as_failure(repo: Repository, retriever: Retriever) -> None:
    empty = FakeBackend("llm", "大模型", answer="   ")
    fallback = FakeBackend("local", "本地检索式", answer="兜底 [1]。")
    result = _engine(repo, retriever, [empty, fallback]).ask("宏村是什么？")
    assert result.backend == "local"
    assert any("空回答" in d for d in result.degradations)


def test_all_backends_failed_raises_with_attempts(repo: Repository, retriever: Retriever) -> None:
    a = FakeBackend("a", "后端A", available=False, reason="没配 key")
    b = FakeBackend("b", "后端B", raises=BackendUnavailableError("连不上", backend="b"))
    with pytest.raises(AllBackendsFailedError) as excinfo:
        _engine(repo, retriever, [a, b]).ask("宏村是什么？")
    assert len(excinfo.value.attempts) == 2
    assert any("没配 key" in a for a in excinfo.value.attempts)


def test_degradation_reasons_are_deduplicated(repo: Repository, retriever: Retriever) -> None:
    a = FakeBackend("a", "后端A", available=False, reason="同样的原因")
    b = FakeBackend("b", "后端B", available=False, reason="同样的原因")
    c = FakeBackend("c", "后端C", answer="好 [1]。")
    result = _engine(repo, retriever, [a, b, c]).ask("宏村是什么？")
    # 两个后端的原因文本不同（前缀是后端名），因此都保留；这里验证顺序稳定
    assert len(result.degradations) == 2
    assert result.degradations[0].startswith("后端A")


def test_availability_reports_every_backend(repo: Repository, retriever: Retriever) -> None:
    a = FakeBackend("a", "后端A", available=False, reason="x")
    b = FakeBackend("b", "后端B")
    rows = _engine(repo, retriever, [a, b]).availability()
    assert len(rows) == 2
    assert rows[0][0] == "a" and rows[0][2] is False
    assert rows[1][0] == "b" and rows[1][2] is True


def test_active_backend_returns_first_usable(repo: Repository, retriever: Retriever) -> None:
    a = FakeBackend("a", "后端A", available=False, reason="x")
    b = FakeBackend("b", "后端B")
    active = _engine(repo, retriever, [a, b]).active_backend()
    assert active is not None and active.id == "b"


def test_availability_never_raises(repo: Repository, retriever: Retriever) -> None:
    class Exploding:
        id, label = "boom", "会炸的后端"

        def available(self) -> Tuple[bool, str]:
            raise RuntimeError("探测失败")

        def answer(self, question: str, passages: Sequence[Passage]) -> BackendAnswer:
            raise AssertionError("不应被调用")

    healthy = FakeBackend("ok", "正常后端", answer="回答 [1]。")
    result = _engine(repo, retriever, [Exploding(), healthy]).ask("宏村是什么？")
    assert result.backend == "ok"
    assert any("探测失败" in d for d in result.degradations)


# --------------------------------------------------------------------------
# 引用溯源
# --------------------------------------------------------------------------


def test_citations_map_to_numbered_passages(repo: Repository, retriever: Retriever) -> None:
    backend = FakeBackend("a", "A", answer="结论 [1][2]。")
    result = _engine(repo, retriever, [backend]).ask("宏村是什么？")
    assert len(result.passages) >= 2, "该问题应检索到至少两条资料"
    assert [c.index for c in result.citations] == [1, 2]
    assert result.citations[0].passage is result.passages[0]
    assert result.citations[1].passage is result.passages[1]
    assert result.grounded is True


def test_invalid_citations_are_recorded_not_hidden(repo: Repository, retriever: Retriever) -> None:
    backend = FakeBackend("a", "A", answer="结论 [1]，另外 [99] 也支持。")
    result = _engine(repo, retriever, [backend]).ask("宏村是什么？")
    assert [c.index for c in result.citations] == [1]
    assert result.invalid_citations == (99,), "越界编号必须被记录并暴露给界面"


def test_unused_passages_are_separated(repo: Repository, retriever: Retriever) -> None:
    backend = FakeBackend("a", "A", answer="只用第一条 [1]。")
    result = _engine(repo, retriever, [backend]).ask("宏村是什么？")
    used_ids = {c.passage.entity_id for c in result.citations}
    unused_ids = {p.entity_id for p in result.unused_passages}
    assert used_ids.isdisjoint(unused_ids)
    assert len(result.citations) + len(result.unused_passages) == len(result.passages)


def test_answer_without_citations_is_not_grounded(repo: Repository, retriever: Retriever) -> None:
    backend = FakeBackend("a", "A", answer="我从记忆里回答，没有引用。")
    result = _engine(repo, retriever, [backend]).ask("宏村是什么？")
    assert result.citations == ()
    assert result.grounded is False, "没有引用的回答不应被判定为可溯源"


def test_backend_receives_retrieved_passages(repo: Repository, retriever: Retriever) -> None:
    backend = FakeBackend("a", "A", answer="[1]")
    _engine(repo, retriever, [backend]).ask("宏村是什么？")
    question, passages = backend.calls[0]
    assert question == "宏村是什么？"
    assert passages and passages[0].entity_id == "hongcun"
    assert all(p.sources for p in passages), "交给后端的资料必须自带来源"


def test_question_validation_happens_before_backend_call(repo: Repository, retriever: Retriever) -> None:
    backend = FakeBackend("a", "A")
    with pytest.raises(QuestionError):
        _engine(repo, retriever, [backend]).ask("   ")
    assert not backend.calls, "问题不合法时不应调用任何后端"


def test_elapsed_time_is_recorded(repo: Repository, retriever: Retriever) -> None:
    ticks = iter([1.0, 1.25])
    engine = QAEngine(
        repo,
        retriever=retriever,
        backends=[FakeBackend("a", "A", answer="[1]")],
        clock=lambda: next(ticks),
    )
    result = engine.ask("宏村是什么？")
    assert result.elapsed_ms == 250


def test_engine_stats_describe_index(repo: Repository, retriever: Retriever) -> None:
    stats = _engine(repo, retriever, [FakeBackend("a", "A")]).stats()
    assert stats["documents"] == retriever.document_count
    assert stats["backends"] == ["A"]


def test_retrieve_does_not_call_backends(repo: Repository, retriever: Retriever) -> None:
    backend = FakeBackend("a", "A")
    passages = _engine(repo, retriever, [backend]).retrieve("宏村")
    assert passages
    assert not backend.calls, "只检索不应触发任何后端调用"


# --------------------------------------------------------------------------
# 本地检索式后端
# --------------------------------------------------------------------------


def test_local_backend_is_always_available() -> None:
    ok, reason = LocalRetrievalBackend().available()
    assert ok is True and reason == ""


def test_local_backend_presents_passages_verbatim(retriever: Retriever) -> None:
    passages = retriever.retrieve("宏村")
    answer = LocalRetrievalBackend().answer("宏村是什么？", passages)
    assert "未经" in answer.text or "原文" in answer.text, "必须说明这是资料原文而非生成"
    for index, passage in enumerate(passages, start=1):
        assert f"[{index}] {passage.title}" in answer.text, "每条资料都要带编号与标题"
    assert "来源：" in answer.text


def test_local_backend_explains_missing_material() -> None:
    answer = LocalRetrievalBackend().answer("量子纠缠", [])
    assert "没有检索到" in answer.text
    assert "不会虚构" in answer.text


def test_local_backend_answers_with_engine(repo: Repository, retriever: Retriever) -> None:
    engine = QAEngine(repo, retriever=retriever, backends=[LocalRetrievalBackend()], top_k=3)
    result = engine.ask("徽墨是什么？")
    assert result.backend == config.BACKEND_LOCAL
    assert result.used_local_fallback is True
    assert result.citations, "本地后端也必须产出可解析的引用编号"
    assert result.grounded


# --------------------------------------------------------------------------
# OpenAI 兼容后端
# --------------------------------------------------------------------------


def _llm_backend(post) -> OpenAICompatBackend:
    cfg = config.LLMConfig(base_url="https://llm.invalid/v1", api_key="secret", model="test-model")
    return OpenAICompatBackend(cfg, post=post)


def test_openai_backend_available_requires_full_config() -> None:
    assert OpenAICompatBackend(config.LLMConfig()).available()[0] is False
    ok, reason = OpenAICompatBackend(config.LLMConfig(base_url="u", api_key="k")).available()
    assert ok is False and "LLM_MODEL" in reason
    assert OpenAICompatBackend(
        config.LLMConfig(base_url="u", api_key="k", model="m")
    ).available()[0] is True


def test_openai_backend_parses_answer_and_usage() -> None:
    captured: Dict = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, body=json, timeout=timeout)
        return FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "宏村位于黟县 [1]。"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    answer = _llm_backend(fake_post).answer("宏村在哪里？", [_passage()])
    assert answer.text == "宏村位于黟县 [1]。"
    assert answer.usage["total_tokens"] == 15
    assert answer.model == "test-model"

    assert captured["url"] == "https://llm.invalid/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    messages = captured["body"]["messages"]
    assert messages[0]["role"] == "system"
    assert "宏村在哪里？" in messages[1]["content"]
    assert captured["body"]["stream"] is False


def test_openai_backend_raises_on_http_error() -> None:
    backend = _llm_backend(lambda *a, **k: FakeResponse(401, None, "unauthorized"))
    with pytest.raises(BackendResponseError) as excinfo:
        backend.answer("问", [_passage()])
    assert "401" in str(excinfo.value)


def test_openai_backend_raises_on_empty_choices() -> None:
    backend = _llm_backend(lambda *a, **k: FakeResponse(200, {"choices": []}))
    with pytest.raises(BackendResponseError):
        backend.answer("问", [_passage()])


def test_openai_backend_raises_on_blank_content() -> None:
    backend = _llm_backend(
        lambda *a, **k: FakeResponse(
            200, {"choices": [{"message": {"content": "", "reasoning_content": "思考中"}}]}
        )
    )
    with pytest.raises(BackendResponseError) as excinfo:
        backend.answer("问", [_passage()])
    assert "推理" in str(excinfo.value), "只返回推理过程时应如实说明"


def test_openai_backend_translates_timeout() -> None:
    def boom(*a, **k):
        raise FakeTimeout("read timed out")

    with pytest.raises(BackendTimeoutError) as excinfo:
        _llm_backend(boom).answer("问", [_passage()])
    assert excinfo.value.backend == config.BACKEND_LLM


def test_openai_backend_translates_connection_error() -> None:
    def boom(*a, **k):
        raise OSError("connection refused")

    with pytest.raises(BackendUnavailableError):
        _llm_backend(boom).answer("问", [_passage()])


def test_openai_backend_raises_on_non_json() -> None:
    backend = _llm_backend(lambda *a, **k: FakeResponse(200, None))
    with pytest.raises(BackendResponseError):
        backend.answer("问", [_passage()])


# --------------------------------------------------------------------------
# Dify 后端
# --------------------------------------------------------------------------


def test_dify_available_requires_config() -> None:
    assert DifyBackend(config.DifyConfig()).available()[0] is False
    ok, reason = DifyBackend(config.DifyConfig(base_url="u")).available()
    assert ok is False and "DIFY_API_KEY" in reason
    bad = DifyBackend(config.DifyConfig(base_url="u", api_key="k", app_type="unknown"))
    assert bad.available()[0] is False
    assert DifyBackend(config.DifyConfig(base_url="u", api_key="k")).available()[0] is True


def test_dify_chat_backend_parses_answer() -> None:
    captured: Dict = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, body=json)
        return FakeResponse(200, {"answer": "宏村是世界文化遗产 [1]。", "metadata": {}})

    cfg = config.DifyConfig(base_url="https://dify.invalid/v1", api_key="app-key", app_type="chat")
    answer = DifyBackend(cfg, post=fake_post).answer("宏村是什么？", [_passage()])
    assert answer.text == "宏村是世界文化遗产 [1]。"
    assert captured["url"].endswith("/chat-messages")
    assert captured["body"]["response_mode"] == "blocking"
    assert "宏村是什么？" in captured["body"]["query"]
    assert "[1]" in captured["body"]["query"], "资料必须随 query 一起传给 Dify"


def test_dify_workflow_backend_extracts_outputs() -> None:
    captured: Dict = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, body=json)
        return FakeResponse(200, {"data": {"outputs": {"answer": "工作流回答 [1]。"}}})

    cfg = config.DifyConfig(base_url="https://dify.invalid/v1", api_key="k", app_type="workflow")
    answer = DifyBackend(cfg, post=fake_post).answer("宏村是什么？", [_passage()])
    assert answer.text == "工作流回答 [1]。"
    assert captured["url"].endswith("/workflows/run")
    assert "query" in captured["body"]["inputs"]


def test_dify_workflow_outputs_fallback_to_any_text() -> None:
    def fake_post(url, *, headers, json, timeout):
        return FakeResponse(200, {"data": {"outputs": {"custom_field": "自定义输出"}}})

    cfg = config.DifyConfig(base_url="https://dify.invalid/v1", api_key="k", app_type="workflow")
    assert DifyBackend(cfg, post=fake_post).answer("问", [_passage()]).text == "自定义输出"


def test_dify_raises_when_answer_missing() -> None:
    backend = DifyBackend(
        config.DifyConfig(base_url="https://dify.invalid", api_key="k"),
        post=lambda *a, **k: FakeResponse(200, {"event": "message"}),
    )
    with pytest.raises(BackendResponseError):
        backend.answer("问", [_passage()])


# --------------------------------------------------------------------------
# 后端链构造与 HTTP 层
# --------------------------------------------------------------------------


def test_default_backends_follow_degrade_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QA_FORCE_LOCAL", raising=False)
    ids = [b.id for b in default_backends()]
    assert ids == [config.BACKEND_DIFY, config.BACKEND_LLM, config.BACKEND_LOCAL]


def test_force_local_env_keeps_only_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_FORCE_LOCAL", "1")
    ids = [b.id for b in default_backends()]
    assert ids == [config.BACKEND_LOCAL], "强制本地时不应保留任何外部后端"


def test_requests_post_raises_when_requests_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.qa.engine as engine_module

    monkeypatch.setattr(engine_module, "requests", None)
    with pytest.raises(BackendUnavailableError):
        requests_post("https://x.invalid", headers={}, json={}, timeout=1)
