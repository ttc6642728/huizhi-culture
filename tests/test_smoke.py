"""应用冒烟测试：确认 Streamlit 脚本可以完整执行且不抛异常。

使用 Streamlit 官方 ``AppTest``（``streamlit.testing.v1``）在无浏览器环境下
真实执行 ``app.py``，比「端口返回 200」更能反映脚本层面的正确性。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.data.loader import load_dataset

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
    pending = {"ask": "P4", "about": "P5"}
    for page_key, phase in pending.items():
        app.run()
        app.session_state["page"] = page_key
        app.run()
        assert not app.exception, f"{page_key} 页抛出异常：{app.exception}"
        body = " ".join(m.value for m in app.markdown)
        assert phase in body, f"{page_key} 页未标注交付阶段 {phase}"


def _body(app: AppTest) -> str:
    """把一次运行产生的所有 markdown 文本拼起来，便于断言。"""
    return " ".join(m.value for m in app.markdown)


def test_explore_page_lists_real_entities(app: AppTest) -> None:
    """百科页必须列出真实实体，并给出真实总数。"""
    app.run()
    app.session_state["page"] = "explore"
    app.run()
    assert not app.exception, f"百科页抛出异常：{app.exception}"
    body = _body(app)
    assert "文化百科" in body
    assert "尚未实现" not in body
    dataset = load_dataset()
    assert f"共 {len(dataset.entities)} 个实体" in body, "结果计数未反映真实数据量"
    # 首屏应当渲染出若干实体卡片与对应的真实跳转按钮
    # （注意用 class="hz-ecard" 计数，避免把注入的 CSS 也算进去）
    assert body.count('class="hz-ecard"') >= 3
    assert len(app.button) >= 3


def test_explore_search_narrows_results(app: AppTest) -> None:
    """关键词检索必须真实改变结果集，而不是摆设。"""
    app.run()
    app.session_state["page"] = "explore"
    app.run()

    app.text_input(key="ex_search").set_value("宏村")
    app.run()
    assert not app.exception
    body = _body(app)
    assert "关键词「宏村」" in body
    assert "宏村" in body
    # 命中的实体数量应远小于全库
    assert f"共 {len(load_dataset().entities)} 个实体" not in body


def test_explore_empty_state_on_no_match(app: AppTest) -> None:
    """检索不到时必须显示空状态，而不是空白或伪造结果。"""
    app.run()
    app.session_state["page"] = "explore"
    app.run()

    app.text_input(key="ex_search").set_value("这是一个不存在的关键词xyz")
    app.run()
    assert not app.exception
    body = _body(app)
    assert "没有匹配的实体" in body
    assert 'class="hz-ecard"' not in body


def test_explore_category_filter(app: AppTest) -> None:
    """分类筛选必须真实生效。"""
    app.run()
    app.session_state["page"] = "explore"
    app.session_state["ex_category"] = "古村落"
    app.run()
    assert not app.exception
    body = _body(app)
    villages = [e for e in load_dataset().entities if e.category == "village"]
    assert f"共 {len(villages)} 个实体" in body


def test_detail_page_renders_entity_with_sources(app: AppTest) -> None:
    """详情页必须渲染结构化属性、关联关系与可点击来源。"""
    app.run()
    app.session_state["page"] = "detail"
    app.session_state["entity_id"] = "hongcun"
    app.run()
    assert not app.exception, f"详情页抛出异常：{app.exception}"
    body = _body(app)
    assert "宏村" in body
    assert "结构化属性" in body
    assert "关联关系" in body
    assert "参考资料" in body
    # 来源必须是真实可点击的链接（来自 sources.json 的 url）
    assert "whc.unesco.org" in body
    assert "href=" in body


def test_detail_page_unknown_entity_shows_error(app: AppTest) -> None:
    """实体不存在时必须明确报错，不得静默回退到别的实体。"""
    app.run()
    app.session_state["page"] = "detail"
    app.session_state["entity_id"] = "__not_exist__"
    app.run()
    assert not app.exception
    body = _body(app)
    assert "未找到该实体" in body


def test_detail_page_without_selection_prompts(app: AppTest) -> None:
    """未选择实体时给出引导，而不是空白页。"""
    app.run()
    app.session_state["page"] = "detail"
    app.session_state["entity_id"] = ""
    app.run()
    assert not app.exception
    assert "尚未选择实体" in _body(app)


def test_detail_relation_direction_is_not_faked(app: AppTest) -> None:
    """详情页必须如实区分「从本实体出发」与「指向本实体」。"""
    app.run()
    app.session_state["page"] = "detail"
    app.session_state["entity_id"] = "huizhou_region"
    app.run()
    assert not app.exception
    body = _body(app)
    assert "从本实体出发" in body
    assert "指向本实体" in body
    # 徽州新增了 6 条出向关系（一府六县），页面上必须体现
    assert "包含组成" in body


def test_explore_button_actually_navigates_to_detail(app: AppTest) -> None:
    """百科页的「查看详情」按钮必须真的跳转（不允许只有外观的假按钮）。"""
    app.run()
    app.session_state["page"] = "explore"
    app.run()
    app.button(key="ex_open_hongcun").click()
    app.run()
    assert not app.exception, f"点击后抛出异常：{app.exception}"
    assert app.session_state["page"] == "detail"
    assert app.session_state["entity_id"] == "hongcun"
    assert "结构化属性" in _body(app)


def test_detail_graph_button_sets_real_focus(app: AppTest) -> None:
    """详情页「在图谱中查看」必须把图谱聚焦到该实体，而不是跳到空图。"""
    app.run()
    app.session_state["page"] = "detail"
    app.session_state["entity_id"] = "hongcun"
    app.run()
    app.button(key="dt_graph_hongcun").click()
    app.run()
    assert not app.exception, f"跳转图谱页抛出异常：{app.exception}"
    assert app.session_state["page"] == "graph"
    assert app.session_state["graph_focus_select"] == "hongcun"
    assert app.session_state.get("graph_focus", "") == "", "聚焦请求应只被消费一次"


def test_pending_pages_state_their_phase(app: AppTest) -> None:
    """仍未实现的页面必须说明所处阶段，不得出现只有外观的空壳。"""
    for page_key, phase in {"ask": "P4", "about": "P5"}.items():
        app.run()
        app.session_state["page"] = page_key
        app.run()
        assert not app.exception, f"{page_key} 页抛出异常：{app.exception}"
        body = _body(app)
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
    # 概览指标必须存在，且数值与数据集一致（而非写死的数字）
    dataset = load_dataset()
    metrics = {m.label: m.value for m in app.metric}
    assert metrics.get("实体节点") == str(len(dataset.entities))
    assert metrics.get("关系连线") == str(len(dataset.relations))


def test_unknown_page_falls_back_to_default(app: AppTest) -> None:
    app.run()
    app.session_state["page"] = "not-a-real-page"
    app.run()
    assert not app.exception
    assert app.session_state["page"] == "home"
