"""问答引擎：Dify → OpenAI 兼容大模型 → 本地检索式，三层自动降级。

设计要点
--------
1. **回答必须基于检索资料**。无论用哪个后端，流程都是「先检索、再让后端基于资料作答」；
   本地后端则直接呈现资料原文，不做任何生成式改写。
2. **降级必须可见**。后端不可用或被跳过时，原因会逐条记进结果里
   （``QAResult.degradations``），界面上能看到「实际用了哪个后端、为什么没用上一个」。
   不静默失败，也不假装一切正常。
3. **三级兜底保证可用性**：Dify 需要知识库/工作流；大模型需要 API Key；
   本地检索式后端零依赖、可离线运行，是最后一道防线。
4. **HTTP 调用可注入**（``post`` 参数），因此单元测试用假响应即可覆盖
   降级链、超时、返回体异常等分支，不需要联网。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from src import config
from src.data.loader import Source
from src.data.repository import Repository
from src.qa import prompt as qa_prompt
from src.qa.errors import (
    AllBackendsFailedError,
    BackendResponseError,
    BackendTimeoutError,
    BackendUnavailableError,
    collect_reasons,
    describe_exception,
)
from src.qa.retriever import Passage, Retriever

try:  # 允许在未安装 requests 的环境里导入本模块（本地后端仍可用）
    import requests
except ImportError:  # pragma: no cover - 依赖缺失时的兜底
    requests = None  # type: ignore[assignment]


# --------------------------------------------------------------------------
# HTTP 调用
# --------------------------------------------------------------------------

#: 统一的 POST 签名：``(url, headers=..., json=..., timeout=...) -> 响应对象``
PostFn = Callable[..., object]


def requests_post(url: str, *, headers: Dict[str, str], json: Dict, timeout: int) -> object:
    """默认的 POST 实现（requests）。"""
    if requests is None:
        raise BackendUnavailableError(
            "未安装 requests，无法调用远程问答后端；已改用本地检索式。"
        )
    return requests.post(url, headers=headers, json=json, timeout=timeout)


def _translate_http_error(exc: BaseException, backend: str) -> Exception:
    """把网络层异常翻译成本层的语义化异常。"""
    if isinstance(exc, (BackendUnavailableError, BackendTimeoutError, BackendResponseError)):
        return exc
    name = type(exc).__name__.lower()
    message = str(exc)[:160]
    if "timeout" in name:
        return BackendTimeoutError(f"请求超时：{message}", backend=backend)
    return BackendUnavailableError(f"无法连接后端：{message}", backend=backend)


# --------------------------------------------------------------------------
# 后端
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendAnswer:
    """后端返回的原始回答。"""

    text: str
    usage: Mapping[str, int] = field(default_factory=dict)
    model: str = ""


class Backend(Protocol):
    """问答后端协议。实现类需提供标识、可用性探测与作答方法。"""

    id: str
    label: str

    def available(self) -> Tuple[bool, str]:
        """返回 ``(是否可用, 不可用原因)``。不发起网络请求，只做配置检查。"""

    def answer(
        self,
        question: str,
        passages: Sequence[Passage],
        *,
        directive: str = "",
    ) -> BackendAnswer:
        """基于给定资料回答问题。失败时抛 :class:`~src.qa.errors.BackendError`。

        ``directive`` 是可选的补充要求（目前只有智能体工作流的纠正重试会用到）：
        引擎在 ``directive`` 为空时只用两个位置参数调用本方法，
        因此旧式实现即使不接受该参数也照常工作；不支持它的后端在纠正重试时会失败，
        该失败会被如实记入降级说明，而不是被静默吞掉。
        """


class DifyBackend:
    """自建 Dify 实例（对话型应用 / 工作流）。"""

    id = config.BACKEND_DIFY
    label = config.BACKEND_LABELS[config.BACKEND_DIFY]

    #: app_type → 接口路径
    _ENDPOINTS = {
        "chat": "chat-messages",
        "agent": "chat-messages",
        "workflow": "workflows/run",
        "completion": "completion-messages",
    }

    def __init__(
        self,
        cfg: Optional[config.DifyConfig] = None,
        post: Optional[PostFn] = None,
        timeout: Optional[int] = None,
    ):
        self._cfg = cfg or config.get_dify_config()
        self._post: PostFn = post or requests_post
        self._timeout = timeout or self._cfg.timeout

    def available(self) -> Tuple[bool, str]:
        if not self._cfg.base_url:
            return False, "未配置 DIFY_BASE_URL"
        if not self._cfg.api_key:
            return False, "未配置 DIFY_API_KEY"
        if self._cfg.app_type not in self._ENDPOINTS:
            return False, f"DIFY_APP_TYPE「{self._cfg.app_type}」不受支持"
        return True, ""

    def answer(
        self,
        question: str,
        passages: Sequence[Passage],
        *,
        directive: str = "",
    ) -> BackendAnswer:
        endpoint = self._ENDPOINTS[self._cfg.app_type]
        url = f"{self._cfg.base_url}/{endpoint}"
        text = qa_prompt.build_dify_query(question, passages, directive)

        if self._cfg.app_type == "workflow":
            payload: Dict = {
                "inputs": {"query": text},
                "response_mode": "blocking",
                "user": "huizhi-explorer",
            }
        else:
            payload = {
                "inputs": {},
                "query": text,
                "response_mode": "blocking",
                "user": "huizhi-explorer",
            }

        try:
            response = self._post(
                url,
                headers={
                    "Authorization": f"Bearer {self._cfg.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001 - 统一翻译成后端异常以便降级
            raise _translate_http_error(exc, self.id) from exc

        data = _json_body(response, self.id)

        if self._cfg.app_type == "workflow":
            outputs = (data.get("data") or {}).get("outputs") or {}
            answer = _extract_outputs(outputs)
        else:
            answer = str(data.get("answer") or "").strip()

        if not answer:
            raise BackendResponseError("Dify 返回体中没有可用文本", backend=self.id)

        metadata = data.get("metadata")
        raw_usage = (metadata or {}).get("usage") if isinstance(metadata, Mapping) else None
        total = (raw_usage or {}).get("total_tokens") if isinstance(raw_usage, Mapping) else 0
        usage = {"total_tokens": int(total)} if isinstance(total, (int, float)) else {}
        return BackendAnswer(text=answer, usage=usage, model=f"dify:{self._cfg.app_type}")


class OpenAICompatBackend:
    """OpenAI 兼容接口（DeepSeek / 通义千问 / 智谱 / OpenAI 等）。"""

    id = config.BACKEND_LLM
    label = config.BACKEND_LABELS[config.BACKEND_LLM]

    def __init__(
        self,
        cfg: Optional[config.LLMConfig] = None,
        post: Optional[PostFn] = None,
        timeout: Optional[int] = None,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ):
        self._cfg = cfg or config.get_llm_config()
        self._post: PostFn = post or requests_post
        self._timeout = timeout or self._cfg.timeout
        self._temperature = temperature
        self._max_tokens = max_tokens

    def available(self) -> Tuple[bool, str]:
        if not self._cfg.base_url:
            return False, "未配置 LLM_BASE_URL"
        if not self._cfg.api_key:
            return False, "未配置 LLM_API_KEY"
        if not self._cfg.model:
            return False, "未配置 LLM_MODEL"
        return True, ""

    def answer(
        self,
        question: str,
        passages: Sequence[Passage],
        *,
        directive: str = "",
    ) -> BackendAnswer:
        url = f"{self._cfg.base_url}/chat/completions"
        payload = {
            "model": self._cfg.model,
            "messages": qa_prompt.build_messages(question, passages, directive),
            # 温度调低：本项目要的是「照着资料说」，不是创作
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }

        try:
            response = self._post(
                url,
                headers={
                    "Authorization": f"Bearer {self._cfg.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )
        except Exception as exc:  # noqa: BLE001
            raise _translate_http_error(exc, self.id) from exc

        data = _json_body(response, self.id)
        choices = data.get("choices") or []
        if not choices:
            raise BackendResponseError("模型返回体中没有 choices", backend=self.id)

        message = choices[0].get("message") or {}
        text = str(message.get("content") or "").strip()
        if not text:
            # 推理型模型可能只给了 reasoning_content，这里如实说明而不是硬凑
            reasoning = str(message.get("reasoning_content") or "").strip()
            hint = "（模型只返回了推理过程，没有给出最终回答）" if reasoning else ""
            raise BackendResponseError(f"模型返回了空回答{hint}", backend=self.id)

        raw_usage = data.get("usage") or {}
        usage = {
            k: int(v)
            for k, v in raw_usage.items()
            if isinstance(v, (int, float)) and k in {"prompt_tokens", "completion_tokens", "total_tokens"}
        }
        return BackendAnswer(text=text, usage=usage, model=self._cfg.model)


class LocalRetrievalBackend:
    """本地检索式后端：把检索到的资料原文整理呈现，**不做生成**。

    这是零依赖、可离线的兜底路径。因为不生成，所以不存在「幻觉」，
    但也不会做跨资料的归纳——这一点会在回答开头如实说明。
    """

    id = config.BACKEND_LOCAL
    label = config.BACKEND_LABELS[config.BACKEND_LOCAL]

    def __init__(self, max_sources_per_passage: int = 3):
        self._max_sources = max(1, max_sources_per_passage)

    def available(self) -> Tuple[bool, str]:
        return True, ""

    def answer(
        self,
        question: str,
        passages: Sequence[Passage],
        *,
        directive: str = "",
    ) -> BackendAnswer:
        # 本后端不做生成，纠正指令无从生效——它本来就逐条标注编号，
        # 因此这里接受参数是为了满足后端协议，而不是假装执行了纠正。
        if not passages:
            return BackendAnswer(
                text=(
                    "本地资料库中没有检索到与该问题相关的内容，因此无法作答。\n\n"
                    "本地检索式后端不进行生成式改写，检索不到时如实说明，不会虚构答案。\n"
                    "可以尝试换用更具体的实体名称（例如「宏村」「徽墨」「马头墙」）重新提问。"
                ),
                model="local-retrieval",
            )

        lines: List[str] = [
            "以下是依据你的问题，从本地徽州文化资料库中检索到的内容"
            "（按相关度排序，直接呈现资料原文，未经过生成式改写）。",
            "",
        ]
        for index, passage in enumerate(passages, start=1):
            lines.append(f"[{index}] {passage.title}（{passage.category_name}）")
            if passage.text:
                lines.append(passage.text)
            if passage.sources:
                cited = "；".join(
                    s.citation for s in passage.sources[: self._max_sources]
                )
                lines.append(f"来源：{cited}")
            lines.append("")

        lines.append(
            "以上为检索结果原文。如需基于这些资料的归纳性回答，"
            "请配置 LLM_API_KEY（或 DIFY_BASE_URL / DIFY_API_KEY）后重启应用。"
        )
        return BackendAnswer(text="\n".join(lines), model="local-retrieval")


# --------------------------------------------------------------------------
# 响应解析助手
# --------------------------------------------------------------------------


def _json_body(response: object, backend: str) -> Dict:
    """校验状态码并解析 JSON 响应体。"""
    status = int(getattr(response, "status_code", 0) or 0)
    if status != 200:
        detail = str(getattr(response, "text", "") or "")[:200].replace("\n", " ")
        raise BackendResponseError(f"HTTP {status}：{detail}", backend=backend)
    try:
        data = response.json()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        raise BackendResponseError(f"响应不是合法 JSON：{exc}", backend=backend) from exc
    if not isinstance(data, dict):
        raise BackendResponseError("响应 JSON 的顶层结构不是对象", backend=backend)
    return data


def _extract_outputs(outputs: Mapping) -> str:
    """从 Dify 工作流的 outputs 中取出文本。

    优先常见字段名；都没有时，把所有字符串值按顺序拼起来——
    总比「返回体里明明有内容却报错」要好。
    """
    if not isinstance(outputs, Mapping):
        return ""
    for key in ("answer", "text", "output", "result", "content"):
        value = outputs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    chunks = [str(v).strip() for v in outputs.values() if isinstance(v, str) and str(v).strip()]
    return "\n".join(chunks)


# --------------------------------------------------------------------------
# 结果模型
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Citation:
    """答案实际引用到的一条资料。``index`` 与答案里的 ``[index]`` 对应。"""

    index: int
    passage: Passage

    @property
    def entity_id(self) -> str:
        return self.passage.entity_id

    @property
    def title(self) -> str:
        return self.passage.title

    @property
    def sources(self) -> Tuple[Source, ...]:
        return self.passage.sources


@dataclass(frozen=True)
class QAResult:
    """一次问答的完整结果（含溯源信息与降级说明）。"""

    question: str
    answer: str
    backend: str
    backend_label: str
    model: str
    passages: Tuple[Passage, ...]
    citations: Tuple[Citation, ...]
    unused_passages: Tuple[Passage, ...]
    invalid_citations: Tuple[int, ...]
    degradations: Tuple[str, ...]
    elapsed_ms: int
    usage: Mapping[str, int] = field(default_factory=dict)
    used_local_fallback: bool = False

    @property
    def degraded(self) -> bool:
        """是否发生过降级（有后端被跳过或失败）。"""
        return bool(self.degradations)

    @property
    def has_passages(self) -> bool:
        return bool(self.passages)

    @property
    def grounded(self) -> bool:
        """回答是否带上了可核查的引用。"""
        return bool(self.citations) and all(c.sources for c in self.citations)


# --------------------------------------------------------------------------
# 引擎
# --------------------------------------------------------------------------


class QAEngine:
    """问答引擎：检索 → 依次尝试各后端 → 返回带溯源的结果。"""

    def __init__(
        self,
        repository: Repository,
        *,
        retriever: Optional[Retriever] = None,
        backends: Optional[Sequence[Backend]] = None,
        top_k: Optional[int] = None,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self._repo = repository
        self._top_k = max(1, int(top_k)) if top_k else max(1, config.qa_top_k())
        self._retriever = retriever or Retriever(repository, top_k=self._top_k)
        self._backends: List[Backend] = list(backends) if backends is not None else default_backends()
        self._clock = clock

    # ------------------------------------------------------------------
    # 组成信息
    # ------------------------------------------------------------------

    @property
    def retriever(self) -> Retriever:
        return self._retriever

    @property
    def backends(self) -> Tuple[Backend, ...]:
        return tuple(self._backends)

    def availability(self) -> Tuple[Tuple[str, str, bool, str], ...]:
        """逐个后端报告可用性，供界面展示（不发起网络请求）。"""
        rows = []
        for backend in self._backends:
            ok, reason = self._probe(backend)
            rows.append((backend.id, backend.label, ok, reason))
        return tuple(rows)

    @staticmethod
    def _probe(backend: Backend) -> Tuple[bool, str]:
        """探测后端可用性。

        探测本身出错（例如实现有 bug、依赖缺失）一律视为不可用，
        并带上原因——绝不让一个探测异常把整条问答链路打断。
        """
        try:
            ok, reason = backend.available()
        except Exception as exc:  # noqa: BLE001 - 探测失败即不可用
            return False, f"可用性探测失败：{describe_exception(exc)}"
        return bool(ok), str(reason or "")

    def active_backend(self) -> Optional[Backend]:
        """当前首个可用的后端（界面用于显示「将会使用哪个」）。"""
        for backend in self._backends:
            ok, _ = self._probe(backend)
            if ok:
                return backend
        return None

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def retrieve(self, question: str) -> List[Passage]:
        """只做检索，不调用后端（供界面「先看检索到什么」使用）。"""
        return self._retriever.retrieve(question)

    def ask(self, question: str) -> QAResult:
        """回答问题（检索 + 作答）。

        Raises:
            QuestionError: 问题不合法。
            AllBackendsFailedError: 降级链上的后端全部失败。
        """
        text = qa_prompt.validate_question(question)
        started = self._clock()
        passages = tuple(self._retriever.retrieve(text, top_k=self._top_k))
        return self.answer_from(text, passages, started=started)

    def answer_from(
        self,
        question: str,
        passages: Sequence[Passage],
        *,
        directive: str = "",
        backends: Optional[Sequence[Backend]] = None,
        started: Optional[float] = None,
    ) -> QAResult:
        """在**已经检索好的资料**上运行后端降级链。

        ``ask()`` 就是「检索 + 本方法」的组合；把两步拆开是为了让智能体工作流
        能把「检索」与「作答」当成两个可分别追踪的步骤（见 :mod:`src.agent.workflow`）。

        Args:
            question: 已经通过校验的问题文本。
            passages: 本次要交给后端的资料（编号即答案里的引用编号）。
            directive: 附加给后端的补充要求，空字符串表示无额外要求。
            backends: 覆盖引擎自带的降级链（工作流做纠正重试时可能只想用其中一个后端）。
            started: 起始计时点；不传则以当前时刻为起点。

        Raises:
            AllBackendsFailedError: 降级链上的后端全部失败。
        """
        started = self._clock() if started is None else started
        chain: Sequence[Backend] = self._backends if backends is None else list(backends)
        passages = tuple(passages)

        degradations: List[str] = []
        for backend in chain:
            ok, reason = self._probe(backend)
            if not ok:
                degradations.append(f"{backend.label}：{reason}")
                continue
            try:
                # 无补充要求时只用两个位置参数调用，保证旧式后端实现（不接受
                # directive）在常规问答路径上不受影响。
                if directive:
                    backend_answer = backend.answer(question, passages, directive=directive)
                else:
                    backend_answer = backend.answer(question, passages)
            except Exception as exc:  # noqa: BLE001 - 任何一个后端的失败都不应终止流程
                degradations.append(f"{backend.label}：{describe_exception(exc)}")
                continue

            answer_text = qa_prompt.strip_wrapping(backend_answer.text)
            if not answer_text:
                degradations.append(f"{backend.label}：返回了空回答")
                continue

            elapsed_ms = int((self._clock() - started) * 1000)
            return self._build_result(
                question=question,
                answer=answer_text,
                backend=backend,
                model=backend_answer.model,
                passages=passages,
                degradations=degradations,
                elapsed_ms=elapsed_ms,
                usage=backend_answer.usage,
            )

        raise AllBackendsFailedError(collect_reasons(degradations))

    def _build_result(
        self,
        *,
        question: str,
        answer: str,
        backend: Backend,
        model: str,
        passages: Tuple[Passage, ...],
        degradations: Sequence[str],
        elapsed_ms: int,
        usage: Mapping[str, int],
    ) -> QAResult:
        """把回答与资料编号对应起来，并剔除模型编造的编号。"""
        numbers = qa_prompt.citation_numbers(answer)

        citations: List[Citation] = []
        invalid: List[int] = []
        used: set = set()
        for number in numbers:
            if 1 <= number <= len(passages):
                citations.append(Citation(index=number, passage=passages[number - 1]))
                used.add(number)
            else:
                # 模型引用了不存在的编号：如实记录，界面会提示，而不是假装没发生
                invalid.append(number)

        unused = tuple(p for i, p in enumerate(passages, start=1) if i not in used)

        return QAResult(
            question=question,
            answer=answer,
            backend=backend.id,
            backend_label=backend.label,
            model=model,
            passages=passages,
            citations=tuple(citations),
            unused_passages=unused,
            invalid_citations=tuple(invalid),
            degradations=tuple(collect_reasons(degradations)),
            elapsed_ms=elapsed_ms,
            usage=usage,
            used_local_fallback=backend.id == config.BACKEND_LOCAL,
        )

    def stats(self) -> Dict[str, object]:
        """引擎概况，供界面与文档展示。"""
        return {
            "documents": self._retriever.document_count,
            "vocabulary": self._retriever.vocabulary_size,
            "top_k": self._top_k,
            "backends": [b.label for b in self._backends],
            "active": self.active_backend().label if self.active_backend() else "无",
        }


def default_backends() -> List[Backend]:
    """按既定顺序构造默认后端链。

    ``QA_FORCE_LOCAL=1`` 时只保留本地检索式后端，
    便于离线演示与「同一问题在不同后端下的对比」。
    """
    if config.qa_force_local():
        return [LocalRetrievalBackend()]
    return [DifyBackend(), OpenAICompatBackend(), LocalRetrievalBackend()]


__all__ = [
    "BackendAnswer",
    "Backend",
    "DifyBackend",
    "OpenAICompatBackend",
    "LocalRetrievalBackend",
    "Citation",
    "QAResult",
    "QAEngine",
    "default_backends",
    "requests_post",
]
