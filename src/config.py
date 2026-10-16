"""全局配置：项目路径、环境变量加载、问答后端探测。

设计原则：
- 所有路径以本文件位置为基准推导，保证在任意工作目录下都能正确定位数据文件。
- 敏感配置（API Key）只从环境变量 / 本地 .env 读取，绝不写入代码或版本库。
- 问答后端按 Dify -> OpenAI 兼容大模型 -> 本地检索式 的顺序自动降级，
  可通过 ``resolve_qa_backend()`` 获取当前实际生效的后端。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------

#: 项目根目录（src/ 的上一级）
BASE_DIR: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = BASE_DIR / "data"
ASSETS_DIR: Path = BASE_DIR / "assets"
IMAGES_DIR: Path = ASSETS_DIR / "images"
DOCS_DIR: Path = BASE_DIR / "docs"
OUTPUTS_DIR: Path = BASE_DIR / "outputs"

ENTITIES_FILE: Path = DATA_DIR / "entities.json"
RELATIONS_FILE: Path = DATA_DIR / "relations.json"
SOURCES_FILE: Path = DATA_DIR / "sources.json"

ENV_FILE: Path = BASE_DIR / ".env"


# --------------------------------------------------------------------------
# 环境变量
# --------------------------------------------------------------------------

_env_loaded = False


def load_env(force: bool = False) -> None:
    """加载项目根目录下的 ``.env``（幂等，重复调用只生效一次）。

    ``.env`` 不存在或不含任何配置时静默跳过，不影响程序启动。
    """
    global _env_loaded
    if _env_loaded and not force:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv 未安装时退化为只读系统环境变量
        _env_loaded = True
        return
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=False)
    _env_loaded = True


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def _env_int(key: str, default: int) -> int:
    raw = _env(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


# --------------------------------------------------------------------------
# 后端配置
# --------------------------------------------------------------------------

#: 支持的问答后端标识
BACKEND_DIFY = "dify"
BACKEND_LLM = "llm"
BACKEND_LOCAL = "local"

BACKEND_LABELS = {
    BACKEND_DIFY: "Dify 知识库 / 工作流",
    BACKEND_LLM: "OpenAI 兼容大模型",
    BACKEND_LOCAL: "本地检索式（离线可用）",
}


@dataclass(frozen=True)
class DifyConfig:
    """自建 Dify 实例配置。"""

    base_url: str = ""
    api_key: str = ""
    app_type: str = "chat"
    timeout: int = 60

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)


@dataclass(frozen=True)
class LLMConfig:
    """OpenAI 兼容大模型配置（DeepSeek / 通义千问 / 智谱 / OpenAI ...）。"""

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: int = 60

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


def get_dify_config() -> DifyConfig:
    load_env()
    return DifyConfig(
        base_url=_env("DIFY_BASE_URL").rstrip("/"),
        api_key=_env("DIFY_API_KEY"),
        app_type=_env("DIFY_APP_TYPE", "chat").lower() or "chat",
        timeout=_env_int("DIFY_TIMEOUT", 60),
    )


def get_llm_config() -> LLMConfig:
    load_env()
    return LLMConfig(
        base_url=_env("LLM_BASE_URL").rstrip("/"),
        api_key=_env("LLM_API_KEY"),
        model=_env("LLM_MODEL"),
        timeout=_env_int("LLM_TIMEOUT", 60),
    )


def qa_force_local() -> bool:
    """是否强制使用本地检索式后端（便于离线演示与测试对比）。"""
    load_env()
    return _env_bool("QA_FORCE_LOCAL", False)


def qa_top_k() -> int:
    """检索返回的资料片段数量。"""
    load_env()
    return max(1, _env_int("QA_TOP_K", 5))


def app_title() -> str:
    load_env()
    return _env("APP_TITLE", "徽知 · Huizhou Culture Explorer")


def resolve_qa_backend() -> str:
    """探测当前实际生效的问答后端。

    Returns:
        ``"dify"`` / ``"llm"`` / ``"local"`` 之一。
    """
    if qa_force_local():
        return BACKEND_LOCAL
    if get_dify_config().configured:
        return BACKEND_DIFY
    if get_llm_config().configured:
        return BACKEND_LLM
    return BACKEND_LOCAL


def qa_backend_label() -> str:
    """当前后端的中文可读名称（用于界面展示）。"""
    return BACKEND_LABELS.get(resolve_qa_backend(), "未知后端")


__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "ASSETS_DIR",
    "IMAGES_DIR",
    "DOCS_DIR",
    "OUTPUTS_DIR",
    "ENTITIES_FILE",
    "RELATIONS_FILE",
    "SOURCES_FILE",
    "ENV_FILE",
    "BACKEND_DIFY",
    "BACKEND_LLM",
    "BACKEND_LOCAL",
    "BACKEND_LABELS",
    "DifyConfig",
    "LLMConfig",
    "load_env",
    "get_dify_config",
    "get_llm_config",
    "qa_force_local",
    "qa_top_k",
    "app_title",
    "resolve_qa_backend",
    "qa_backend_label",
]
