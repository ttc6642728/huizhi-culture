"""问答层：基于文化资料的检索、提示词构造与多后端问答引擎。

对外入口：
    :class:`~src.qa.retriever.Retriever`    jieba + BM25 资料检索
    :class:`~src.qa.engine.QAEngine`        三层后端问答引擎（自动降级）
    :class:`~src.qa.engine.QAResult`        一次问答的完整结果（含溯源信息）

异常层级见 :mod:`src.qa.errors`，提示词构造见 :mod:`src.qa.prompt`。
"""

from src.qa.engine import (
    Backend,
    BackendAnswer,
    Citation,
    DifyBackend,
    LocalRetrievalBackend,
    OpenAICompatBackend,
    QAEngine,
    QAResult,
    default_backends,
)
from src.qa.errors import (
    AllBackendsFailedError,
    BackendError,
    BackendResponseError,
    BackendTimeoutError,
    BackendUnavailableError,
    QAError,
    QuestionError,
    RetrievalError,
)
from src.qa.retriever import Passage, Retriever

__all__ = [
    "Retriever",
    "Passage",
    "QAEngine",
    "QAResult",
    "Citation",
    "Backend",
    "BackendAnswer",
    "DifyBackend",
    "OpenAICompatBackend",
    "LocalRetrievalBackend",
    "default_backends",
    "QAError",
    "QuestionError",
    "RetrievalError",
    "BackendError",
    "BackendUnavailableError",
    "BackendTimeoutError",
    "BackendResponseError",
    "AllBackendsFailedError",
]
