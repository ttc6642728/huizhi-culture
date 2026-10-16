"""Dify 后端的**真实 HTTP 路径**集成测试。

为什么单独一个文件
------------------

Dify 后端此前只用「注入假 ``post`` 函数」做过单元验证——那验证的是**解析逻辑**，
但 ``url`` 怎么拼、``Authorization`` 头长什么样、请求体字段、真实网络异常的类型，
一个都没被真正执行过。

这里在本地起一个最小的 HTTP 服务器充当假 Dify 实例，让 ``DifyBackend`` 走真实的
``requests`` 调用链路（真实 socket、真实序列化、真实异常），因此：

- 不依赖外网、不依赖真实 Dify 实例，可离线复现；
- 服务器会把收到的**请求原文**记下来，测试据此核对 URL 路径、请求头与请求体；
- 覆盖 chat / workflow 两类响应、非 200、非法 JSON、超时四类分支。

这样「Dify 后端未做真实联调」这条遗留就只剩「没有真实 Dify 实例可言」——
协议层已经由本文件实测钉住。
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Iterator, List, Optional, Tuple

import pytest

from src import config
from src.data.loader import load_dataset
from src.data.repository import Repository
from src.qa.engine import DifyBackend, QAEngine, _translate_http_error
from src.qa.errors import (
    BackendError,
    BackendResponseError,
    BackendTimeoutError,
    BackendUnavailableError,
)
from src.qa.retriever import Retriever


class _Handler(BaseHTTPRequestHandler):
    """按服务器上挂的 ``reply`` 应答，并把请求原文记录下来。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args, **kwargs) -> None:  # noqa: ARG002 - 静默，避免污染测试输出
        return

    def do_POST(self) -> None:  # noqa: N802 - 框架要求的名字
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            body = {"__raw__": raw.decode("utf-8", errors="replace")}

        self.server.calls.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization") or "",
                "content_type": self.headers.get("Content-Type") or "",
                "body": body,
            }
        )

        status = self.server.status
        delay = self.server.delay
        payload = self.server.payload
        if delay:
            time.sleep(delay)

        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # 客户端可能已经超时断开（超时用例），这里静默即可
            pass


class _StubServer(ThreadingHTTPServer):
    """线程化的假 Dify 实例。

    必须线程化：单线程的 ``HTTPServer`` 在 HTTP/1.1 keep-alive 下会停在
    同一个连接上等下一个请求，``shutdown()`` 便会一直阻塞（测试会挂死）。
    把处理线程设成守护线程，超时用例里那个「还没醒过来」的处理线程就不会拖住收尾。
    """

    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True

    payload: object = {}
    status: int = 200
    delay: float = 0.0
    calls: List[Dict] = []


@contextmanager
def dify_stub(
    payload,
    *,
    status: int = 200,
    delay: float = 0.0,
) -> Iterator[_StubServer]:
    """起一个本地假 Dify 实例，返回可通过 ``server.calls`` 查看请求的服务器对象。"""
    server = _StubServer(("127.0.0.1", 0), _Handler)
    server.payload = payload
    server.status = status
    server.delay = delay
    server.calls = []

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _cfg(server: _StubServer, app_type: str, timeout: int = 10) -> config.DifyConfig:
    host, port = server.server_address[:2]
    return config.DifyConfig(
        base_url=f"http://{host}:{port}",
        api_key="test-key",
        app_type=app_type,
        timeout=timeout,
    )


@pytest.fixture(scope="module")
def repo() -> Repository:
    return Repository(load_dataset())


@pytest.fixture(scope="module")
def passages(repo: Repository):
    return tuple(Retriever(repo, top_k=3).retrieve("宏村"))


# --------------------------------------------------------------------------
# 配置探测
# --------------------------------------------------------------------------


def test_unconfigured_backend_reports_missing_key() -> None:
    ok, reason = DifyBackend(config.DifyConfig()).available()
    assert ok is False and "DIFY_BASE_URL" in reason


def test_unsupported_app_type_is_reported() -> None:
    cfg = config.DifyConfig(base_url="http://x", api_key="k", app_type="unknown")
    ok, reason = DifyBackend(cfg).available()
    assert ok is False and "不受支持" in reason


# --------------------------------------------------------------------------
# 对话型应用（chat）：走真实的 requests
# --------------------------------------------------------------------------


def test_chat_request_reaches_real_endpoint(passages) -> None:
    payload = {
        "answer": "宏村位于黟县。[1]",
        "metadata": {"usage": {"total_tokens": 42}},
    }
    with dify_stub(payload) as server:
        backend = DifyBackend(_cfg(server, "chat"))
        assert backend.available() == (True, "")
        answer = backend.answer("宏村在哪里？", passages)

        assert answer.text == "宏村位于黟县。[1]"
        assert answer.usage == {"total_tokens": 42}, "token 用量应被解析出来"
        assert answer.model == "dify:chat"

        assert len(server.calls) == 1, "应当恰好发起一次 HTTP 请求"
        call = server.calls[0]
        assert call["path"] == "/chat-messages", f"路径应为 /chat-messages，实际 {call['path']}"
        assert call["authorization"] == "Bearer test-key", "鉴权头格式必须是 Bearer"
        assert call["content_type"] == "application/json"
        assert call["body"]["response_mode"] == "blocking"
        assert call["body"]["user"] == "huizhi-explorer"
        assert call["body"]["inputs"] == {}
        # 问题与检索到的资料都要进 query，否则 Dify 无从依据资料作答
        assert "宏村在哪里？" in call["body"]["query"]
        assert passages[0].title in call["body"]["query"]
        assert "[1]" in call["body"]["query"]


def test_agent_app_type_uses_chat_endpoint(passages) -> None:
    with dify_stub({"answer": "答。[1]"}) as server:
        DifyBackend(_cfg(server, "agent")).answer("宏村", passages)
        assert server.calls[0]["path"] == "/chat-messages"


def test_workflow_app_type_uses_workflow_endpoint_and_extracts_output(passages) -> None:
    payload = {"data": {"status": "succeeded", "outputs": {"answer": "工作流回答。[1]"}}}
    with dify_stub(payload) as server:
        answer = DifyBackend(_cfg(server, "workflow")).answer("宏村", passages)

        assert answer.text == "工作流回答。[1]"
        assert answer.model == "dify:workflow"
        call = server.calls[0]
        assert call["path"] == "/workflows/run", f"路径应为 /workflows/run，实际 {call['path']}"
        # 工作流的输入走 inputs.query，而不是顶层 query
        assert "宏村" in call["body"]["inputs"]["query"]
        assert "query" not in call["body"]


def test_workflow_outputs_fall_back_to_concatenation(passages) -> None:
    """outputs 里没有常见字段名时，把所有字符串值按顺序拼起来，而不是直接报错。"""
    payload = {"data": {"outputs": {"answer_text": "第一段", "extra": "第二段"}}}
    with dify_stub(payload) as server:
        answer = DifyBackend(_cfg(server, "workflow")).answer("宏村", passages)
    assert "第一段" in answer.text and "第二段" in answer.text


def test_completion_app_type_uses_completion_endpoint(passages) -> None:
    with dify_stub({"answer": "补全回答。[1]"}) as server:
        answer = DifyBackend(_cfg(server, "completion")).answer("宏村", passages)
    assert server.calls[0]["path"] == "/completion-messages"
    assert answer.text == "补全回答。[1]"


# --------------------------------------------------------------------------
# 失败分支：真实网络异常与响应异常
# --------------------------------------------------------------------------


def test_http_error_status_is_translated(passages) -> None:
    with dify_stub({"error": "bad"}, status=500) as server:
        backend = DifyBackend(_cfg(server, "chat"))
        with pytest.raises(BackendResponseError) as excinfo:
            backend.answer("宏村", passages)
    assert "HTTP 500" in str(excinfo.value)


def test_non_json_body_is_translated(passages) -> None:
    with dify_stub(b"<html>oops</html>") as server:
        backend = DifyBackend(_cfg(server, "chat"))
        with pytest.raises(BackendResponseError) as excinfo:
            backend.answer("宏村", passages)
    assert "JSON" in str(excinfo.value)


def test_empty_answer_is_translated(passages) -> None:
    with dify_stub({"answer": "   "}) as server:
        with pytest.raises(BackendResponseError) as excinfo:
            DifyBackend(_cfg(server, "chat")).answer("宏村", passages)
    assert "没有可用文本" in str(excinfo.value)


def test_timeout_becomes_backend_timeout(passages) -> None:
    """真实 socket 读超时 → 本层的 BackendTimeoutError（降级链据此继续往下走）。"""
    with dify_stub({"answer": "太慢了"}, delay=1.5) as server:
        backend = DifyBackend(_cfg(server, "chat", timeout=1))
        with pytest.raises(BackendTimeoutError):
            backend.answer("宏村", passages)


def test_connection_failure_is_translated_not_leaked() -> None:
    """连不上时抛出的必须是本项目自己的异常，而不是 requests 的原始异常。

    不断言具体子类：本机若设有 HTTP 代理，连接失败可能被代理回成 502，
    于是表现为 ``BackendResponseError`` 而非 ``BackendUnavailableError``——
    两者都能被降级链正确处理，这才是真正要钉住的不变量。
    """
    cfg = config.DifyConfig(base_url="http://127.0.0.1:9", api_key="k", app_type="chat", timeout=3)
    with pytest.raises(BackendError) as excinfo:
        DifyBackend(cfg).answer("宏村", ())
    assert str(excinfo.value).strip(), "异常必须带可读信息，供降级说明展示"


def test_translate_http_error_maps_exception_types() -> None:
    """真实的 requests 异常 → 本层语义化异常（不依赖网络，直接验证映射规则）。"""

    class ReadTimeout(Exception):
        pass

    class ConnectTimeout(Exception):
        pass

    class ConnectionError_(Exception):
        pass

    mapped_timeout = _translate_http_error(ReadTimeout("read timed out"), config.BACKEND_DIFY)
    assert isinstance(mapped_timeout, BackendTimeoutError)

    mapped_connect_timeout = _translate_http_error(ConnectTimeout("connect timeout"), config.BACKEND_DIFY)
    assert isinstance(mapped_connect_timeout, BackendTimeoutError)

    mapped_refused = _translate_http_error(ConnectionError_("refused"), config.BACKEND_DIFY)
    assert isinstance(mapped_refused, BackendUnavailableError)

    # 已经是本层异常时原样返回，避免二次包装把原因盖掉
    original = BackendResponseError("已经翻译过", backend=config.BACKEND_DIFY)
    assert _translate_http_error(original, config.BACKEND_DIFY) is original


# --------------------------------------------------------------------------
# 与降级链的联动
# --------------------------------------------------------------------------


def test_engine_uses_dify_when_reachable_and_cites_answer(repo: Repository) -> None:
    """端到端：引擎 → Dify（真实 HTTP）→ 引用溯源。"""
    payload = {"answer": "宏村位于黟县。[1][2]"}
    with dify_stub(payload) as server:
        engine = QAEngine(repo, backends=[DifyBackend(_cfg(server, "chat"))])
        result = engine.ask("宏村位于哪个县？")

    assert result.backend == config.BACKEND_DIFY
    assert result.grounded is True
    assert [c.index for c in result.citations] == [1, 2]
    assert result.degradations == ()


def test_engine_degrades_to_local_when_dify_fails(repo: Repository) -> None:
    """Dify 挂掉时降级到本地后端，并把降级原因原样记录下来。"""
    from src.qa.engine import LocalRetrievalBackend

    with dify_stub({"error": "boom"}, status=503) as server:
        engine = QAEngine(
            repo, backends=[DifyBackend(_cfg(server, "chat")), LocalRetrievalBackend()]
        )
        result = engine.ask("宏村位于哪个县？")

    assert result.backend == config.BACKEND_LOCAL
    assert result.used_local_fallback is True
    assert any("HTTP 503" in d for d in result.degradations), f"降级原因应可读：{result.degradations}"
