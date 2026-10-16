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
    pending = {"explore": "P3", "ask": "P4", "about": "P5"}
    for page_key, phase in pending.items():
        app.run()
        app.session_state["page"] = page_key
        app.run()
        assert not app.exception, f"{page_key} 页抛出异常：{app.exception}"
        body = " ".join(m.value for m in app.markdown)
        assert phase in body, f"{page_key} 页未标注交付阶段 {phase}"
        assert "尚未实现" in body or "计划在" in body, f"{page_key} 页未说明尚未实现"


def test_graph_page_renders_real_content(app: AppTest) -> None:
    """已交付的图谱页必须渲染真实数据，而不是「未实现」占位。"""
    app.run()
    app.session_state["page"] = "graph"
    app.run()
    assert not app.exception, f"图谱页抛出异常：{app.exception}"
    body = " ".join(m.value for m in app.markdown)
    assert "知识图谱" in body
    assert "尚未实现" not in body
    # 概览指标必须存在，且数值来自真实图谱（90 个实体 / 150 条关系）
    metrics = {m.label: m.value for m in app.metric}
    assert metrics.get("实体节点") == "90"
    assert metrics.get("关系连线") == "150"


def test_unknown_page_falls_back_to_default(app: AppTest) -> None:
    app.run()
    app.session_state["page"] = "not-a-real-page"
    app.run()
    assert not app.exception
    assert app.session_state["page"] == "home"
