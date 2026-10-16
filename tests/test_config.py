"""配置层单元测试：路径常量、后端探测与自动降级。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import config


def test_paths_are_absolute_and_rooted_in_project() -> None:
    assert config.BASE_DIR.is_absolute()
    assert config.DATA_DIR == config.BASE_DIR / "data"
    assert config.ENTITIES_FILE.parent == config.DATA_DIR
    assert config.RELATIONS_FILE.parent == config.DATA_DIR
    assert config.SOURCES_FILE.parent == config.DATA_DIR
    for p in (config.ENTITIES_FILE, config.RELATIONS_FILE, config.SOURCES_FILE):
        assert isinstance(p, Path)


def test_dify_config_requires_both_url_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFY_BASE_URL", "http://localhost/v1")
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    assert config.get_dify_config().configured is False

    monkeypatch.setenv("DIFY_API_KEY", "app-xxx")
    assert config.get_dify_config().configured is True


def test_llm_config_requires_url_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-xxx")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert config.get_llm_config().configured is False

    monkeypatch.setenv("LLM_MODEL", "some-model")
    assert config.get_llm_config().configured is True


def test_resolve_backend_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("DIFY_BASE_URL", "DIFY_API_KEY", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("QA_FORCE_LOCAL", "false")
    assert config.resolve_qa_backend() == config.BACKEND_LOCAL


def test_resolve_backend_prefers_dify_over_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_FORCE_LOCAL", "false")
    monkeypatch.setenv("DIFY_BASE_URL", "http://localhost/v1")
    monkeypatch.setenv("DIFY_API_KEY", "app-xxx")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-xxx")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    assert config.resolve_qa_backend() == config.BACKEND_DIFY


def test_resolve_backend_uses_llm_when_dify_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_FORCE_LOCAL", "false")
    monkeypatch.delenv("DIFY_BASE_URL", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-xxx")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    assert config.resolve_qa_backend() == config.BACKEND_LLM


def test_force_local_overrides_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_FORCE_LOCAL", "true")
    monkeypatch.setenv("DIFY_BASE_URL", "http://localhost/v1")
    monkeypatch.setenv("DIFY_API_KEY", "app-xxx")
    assert config.resolve_qa_backend() == config.BACKEND_LOCAL


def test_top_k_is_clamped_to_at_least_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QA_TOP_K", "0")
    assert config.qa_top_k() == 1
    monkeypatch.setenv("QA_TOP_K", "abc")
    assert config.qa_top_k() == 5  # 非法值回退到默认值
