"""问答层异常。

分层设计的目的：**让「失败原因」可以被程序分辨、被人读懂**。
前端界面据此决定是「提示用户换个问法」还是「如实说明某个后端挂了并已降级」，
而不是把一切异常都压成一句「出错了」。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple


class QAError(Exception):
    """问答层基础异常。"""


class QuestionError(QAError):
    """问题本身不合法（空、过短或过长）。

    ``reason`` 是给用户看的一句话说明，界面可直接展示。
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class RetrievalError(QAError):
    """资料检索阶段的失败（索引构建异常、分词失败等）。"""


# --------------------------------------------------------------------------
# 后端相关
# --------------------------------------------------------------------------


class BackendError(QAError):
    """后端调用失败的基类。

    ``backend`` 是后端标识（``dify`` / ``llm`` / ``local``），
    降级链会把它写进「为什么跳过了这个后端」的说明里。
    """

    def __init__(self, message: str, backend: str = ""):
        self.backend = backend
        super().__init__(message)


class BackendUnavailableError(BackendError):
    """后端未配置、依赖缺失或连接不可建立。"""


class BackendTimeoutError(BackendError):
    """后端在超时时间内没有响应。"""


class BackendResponseError(BackendError):
    """后端有响应，但状态码异常或返回体无法解析。"""


class AllBackendsFailedError(QAError):
    """整条降级链上的后端全部失败。

    携带 ``attempts``：逐条记录「哪个后端、因为什么被跳过」，
    界面会原样展示，便于定位是配置问题还是网络问题。
    """

    def __init__(self, attempts: Sequence[str]):
        self.attempts: Tuple[str, ...] = tuple(attempts)
        detail = "\n".join(f"  - {a}" for a in self.attempts) or "  (没有任何可用后端)"
        super().__init__(f"所有问答后端均不可用：\n{detail}")


def describe_exception(exc: BaseException) -> str:
    """把异常压成一行可读文案（用于降级说明，避免多行堆叠）。"""
    text = str(exc).strip().replace("\n", " ")
    if len(text) > 200:
        text = text[:197] + "…"
    return f"{type(exc).__name__}：{text}" if text else type(exc).__name__


def collect_reasons(attempts: Sequence[str]) -> List[str]:
    """降级原因去重（保留顺序），避免同一句重复展示。"""
    seen: set = set()
    out: List[str] = []
    for item in attempts:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


__all__ = [
    "QAError",
    "QuestionError",
    "RetrievalError",
    "BackendError",
    "BackendUnavailableError",
    "BackendTimeoutError",
    "BackendResponseError",
    "AllBackendsFailedError",
    "describe_exception",
    "collect_reasons",
]
