"""应用冒烟测试：确认 Streamlit 脚本可以完整执行且不抛异常。

使用 Streamlit 官方 ``AppTest``（``streamlit.testing.v1``）在无浏览器环境下
真实执行 ``app.py``，比「端口返回 200」更能反映脚本层面的正确性。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config
from src.data.loader import load_dataset

APP_FILE = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture()
def app() -> AppTest:
    return AppTest.from_file(str(APP_FILE), default_timeout=60)


@pytest.fixture()
def local_app(monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """强制本地检索式后端的应用实例。

    问答页的测试**不依赖任何外部 API**：把 QA_FORCE_LOCAL 置 1 后，
    引擎只会走本地检索式路径，测试因此可离线、可复现。
    """
    monkeypatch.setenv("QA_FORCE_LOCAL", "1")
    return AppTest.from_file(str(APP_FILE), default_timeout=120)


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
    app.session_state["page"] = "about"
    app.run()
    assert not app.exception, f"about 页抛出异常：{app.exception}"
    body = " ".join(m.value for m in app.markdown)
    assert "P5" in body, "about 页未标注交付阶段 P5"


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
    app.run()
    app.session_state["page"] = "about"
    app.run()
    assert not app.exception, f"about 页抛出异常：{app.exception}"
    body = _body(app)
    assert "P5" in body, "about 页未标注交付阶段 P5"
    assert "尚未实现" in body or "计划在" in body, "about 页未说明尚未实现"


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


# --------------------------------------------------------------------------
# AI 问答页（P4）—— 全部走本地检索式后端，不联网
# --------------------------------------------------------------------------


def _open_ask(app: AppTest) -> AppTest:
    app.run()
    app.session_state["page"] = "ask"
    app.run()
    assert not app.exception, f"问答页抛出异常：{app.exception}"
    return app


def _ask(app: AppTest, question: str) -> AppTest:
    app.text_area(key="qa_input").set_value(question)
    app.button(key="qa_submit").click()
    app.run()
    assert not app.exception, f"提问后抛出异常：{app.exception}"
    return app


def test_ask_page_renders_real_content(local_app: AppTest) -> None:
    """问答页必须渲染真实内容与后端状态，而不是「未实现」占位。"""
    _open_ask(local_app)
    body = _body(local_app)
    assert "AI 智能问答" in body
    assert "尚未实现" not in body
    # 后端状态必须真实展示（强制本地时只会有本地后端）
    assert config.BACKEND_LABELS[config.BACKEND_LOCAL] in body
    assert "QA_FORCE_LOCAL" in body, "强制本地模式必须如实告知用户"


def test_ask_examples_come_from_real_data(local_app: AppTest) -> None:
    """示例问题必须由当前数据集生成，且引用的实体真实存在。"""
    _open_ask(local_app)
    labels = [b.label for b in local_app.button]
    examples = [label for label in labels if label.endswith("？")]
    assert len(examples) >= 3, "示例问题应由数据动态生成"

    names = {e.name for e in load_dataset().entities}
    for question in examples:
        assert any(name in question for name in names), f"示例问题未引用真实实体：{question}"


def test_ask_returns_answer_with_verifiable_citations(local_app: AppTest) -> None:
    """真实提问必须返回带引用的回答，且每条引用都能落到来源。"""
    _open_ask(local_app)
    _ask(local_app, "徽墨是什么？")

    history = local_app.session_state.get("qa_history") or []
    assert len(history) == 1, "提问后应记录一轮结果"
    result = history[0]
    assert result.question == "徽墨是什么？"
    assert result.backend == config.BACKEND_LOCAL
    assert result.passages, "应当检索到资料"
    assert result.citations, "回答必须引用资料"
    assert result.grounded, "每条引用都必须能对应到可核查来源"
    for citation in result.citations:
        assert citation.sources, f"引用 [{citation.index}] 没有来源"
        assert all(source.url for source in citation.sources), "来源必须带可点击地址"


def test_ask_example_button_actually_asks(local_app: AppTest) -> None:
    """示例问题按钮必须真的提问（不允许只有外观的假按钮）。"""
    _open_ask(local_app)
    assert not local_app.session_state.get("qa_history")
    local_app.button(key="qa_ex_0").click()
    local_app.run()
    assert not local_app.exception
    history = local_app.session_state.get("qa_history") or []
    assert len(history) == 1, "点击示例后应产生一轮真实问答"
    assert history[0].question, "记录的问题不应为空"
    assert history[0].answer, "记录的回答不应为空"


def test_ask_empty_question_prompts_instead_of_failing(local_app: AppTest) -> None:
    """空提问必须给出提示，而不是报错或产生空记录。"""
    _open_ask(local_app)
    local_app.button(key="qa_submit").click()
    local_app.run()
    assert not local_app.exception
    assert "请先输入问题" in _body(local_app)
    assert not local_app.session_state.get("qa_history")


def test_ask_empty_question_from_example_flow_is_handled(local_app: AppTest) -> None:
    """先输入再清空的情形：清空按钮必须真的清掉会话与输入。"""
    _open_ask(local_app)
    _ask(local_app, "宏村是什么？")
    assert local_app.session_state.get("qa_history")

    local_app.button(key="qa_clear").click()
    local_app.run()
    assert not local_app.exception
    assert not local_app.session_state.get("qa_history"), "清空后不应残留历史"
    assert not local_app.session_state.get("qa_input"), "清空后输入框应被重置"


def test_ask_renders_citation_badges_and_links(local_app: AppTest) -> None:
    """回答里的 [n] 必须渲染成徽标，并给出可点击的来源链接。"""
    _open_ask(local_app)
    _ask(local_app, "宏村是什么？")
    body = _body(local_app)
    assert 'class="hz-cite"' in body, "引用编号应渲染为徽标"
    assert 'class="hz-answer"' in body, "回答应使用统一的回答区块样式"
    assert "引用来源" in body
    assert "href=" in body, "引用来源必须带可点击链接"


def test_ask_reports_retrieved_passages(local_app: AppTest) -> None:
    """检索到的资料必须如实列出，并标注哪些未被回答引用。"""
    _open_ask(local_app)
    _ask(local_app, "宏村是什么？")
    result = (local_app.session_state.get("qa_history") or [])[0]
    body = _body(local_app)
    assert f"检索到 {len(result.passages)} 条资料" in body, "检索条数应如实显示"
    # 未引用的资料要标注出来，便于核查检索质量
    if result.unused_passages:
        assert "未被回答引用" in body
    assert 'class="hz-passage"' in body


def test_ask_has_no_degradation_when_local_forced(local_app: AppTest) -> None:
    """强制本地模式不应出现「跳过后端」的说明（因为链上只有本地后端）。"""
    _open_ask(local_app)
    _ask(local_app, "宏村是什么？")
    result = (local_app.session_state.get("qa_history") or [])[0]
    assert result.degradations == (), f"本地后端不应产生降级说明：{result.degradations}"
    assert result.used_local_fallback is True
    assert "本地检索式后端" in _body(local_app)
