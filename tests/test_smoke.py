"""应用冒烟测试：确认 Streamlit 脚本可以完整执行且不抛异常。

使用 Streamlit 官方 ``AppTest``（``streamlit.testing.v1``）在无浏览器环境下
真实执行 ``app.py``，比「端口返回 200」更能反映脚本层面的正确性。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_FILE = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture()
def app() -> AppTest:
    return AppTest.from_file(str(APP_FILE), default_timeout=60)


def test_app_file_exists() -> None:
    assert APP_FILE.is_file(), f"未找到应用入口：{APP_FILE}"


def test_app_runs_without_exception(app: AppTest) -> None:
    app.run()
    assert not app.exception, f"应用执行抛出异常：{app.exception}"


def test_default_page_renders_navigation(app: AppTest) -> None:
    app.run()
    # 侧边栏导航按钮应包含全部规划中的页面
    labels = [b.label for b in app.sidebar.button]
    for expected in ["文化探索", "文化百科", "知识图谱", "AI 问答", "关于项目"]:
        assert expected in labels, f"侧边栏缺少导航项：{expected}"


def test_pending_page_explains_its_phase(app: AppTest) -> None:
    """未实现页面必须如实说明所处阶段，而不是显示空壳内容。"""
    app.run()
    app.session_state["page"] = "graph"
    app.run()
    assert not app.exception
    body = " ".join(m.value for m in app.markdown)
    assert "P2" in body, "未实现页面未标注交付阶段"


def test_unknown_page_falls_back_to_default(app: AppTest) -> None:
    app.run()
    app.session_state["page"] = "not-a-real-page"
    app.run()
    assert not app.exception
    assert app.session_state["page"] == "home"
