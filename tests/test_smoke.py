"""应用冒烟测试：确认 Streamlit 脚本可以完整执行且不抛异常。

使用 Streamlit 官方 ``AppTest``（``streamlit.testing.v1``）在无浏览器环境下
真实执行 ``app.py``，比「端口返回 200」更能反映脚本层面的正确性。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config
from src.agent import workflow
from src.data.loader import load_dataset
from src.data.repository import Repository
from src.ui import datastore
from src.ui.pages import explore, home

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


def _body(app: AppTest) -> str:
    """把一次运行产生的所有 markdown 文本拼起来，便于断言。"""
    return " ".join(m.value for m in app.markdown)


# --------------------------------------------------------------------------
# 首页：徽州主视觉，以及「环境自检」的归属
# --------------------------------------------------------------------------


def test_home_shows_a_credited_hero_image(app: AppTest) -> None:
    """首页要有徽州代表图片作主视觉，并且图注与作者署名必须一起出现。"""
    app.run()
    assert not app.exception, f"首页抛出异常：{app.exception}"
    assert len(app.image) == 1, "首页应恰好展示一张主视觉图片"

    image = datastore.images().get(home.HERO_IMAGE_ENTITY)
    assert image is not None, f"图片库缺少 {home.HERO_IMAGE_ENTITY}"
    body = _body(app)
    assert image.caption in body, "首页主视觉必须带图注"
    assert image.artist in body, "首页主视觉必须带作者署名（授权要求）"


def test_home_hero_image_entity_is_a_real_credited_image() -> None:
    """主视觉引用的实体必须真在图片库中、文件存在且有可核查来源。

    配错实体名时首页会**静默**少了主视觉（页面照常、不报错），
    只有这样的断言才拦得住。
    """
    image = datastore.images().get(home.HERO_IMAGE_ENTITY)
    assert image is not None, f"图片库中没有 {home.HERO_IMAGE_ENTITY}，首页将无主视觉"
    assert image.exists, f"{home.HERO_IMAGE_ENTITY} 的图片文件缺失：{image.path}"
    assert image.artist.strip(), "首页主视觉缺作者，按本项目规则不予收录"
    assert image.source_url.startswith("https://commons.wikimedia.org/"), (
        f"首页主视觉的来源页面不是 Commons：{image.source_url}"
    )


def test_environment_check_lives_on_about_page_not_home(app: AppTest) -> None:
    """环境自检属开发者信息：必须出现在「关于项目」页，且不再占用首页。"""
    app.run()
    home_body = _body(app)
    for text in ("环境自检", "模块交付进度", "运行依赖"):
        assert text not in home_body, f"首页不应再出现「{text}」"

    app.session_state["page"] = "about"
    app.run()
    about_body = _body(app)
    for text in ("环境自检", "模块交付进度", "运行依赖", "文化数据"):
        assert text in about_body, f"「关于项目」页缺少「{text}」区块"


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
    """百科页的「查看详情」按钮必须真的跳转（不允许只有外观的假按钮）。

    不假设某个具体实体排在第一页：默认顺序随「有配图优先」规则与图片收录情况变化，
    因此取当前列表里第一张卡片的按钮，并从按钮 key 反推它应跳到哪个实体。
    """
    app.run()
    app.session_state["page"] = "explore"
    app.run()
    button = next(
        b
        for b in app.button
        if str(getattr(b, "key", "") or "").startswith("ex_open_")
    )
    entity_id = str(button.key).removeprefix("ex_open_")
    button.click()
    app.run()
    assert not app.exception, f"点击后抛出异常：{app.exception}"
    assert app.session_state["page"] == "detail"
    assert app.session_state["entity_id"] == entity_id
    assert "结构化属性" in _body(app)


def test_explore_default_order_puts_illustrated_entities_first() -> None:
    """百科页**默认顺序**必须把已有配图的实体排在前面，且不打乱其余顺序。

    直接调用 ``explore._select`` 验证排序规则本身：比在渲染结果里猜卡片顺序
    更稳定、更快，也更能说清「为什么是这个顺序」。
    """
    repo = Repository(load_dataset())
    library = datastore.images()

    hits, _ = explore._select(repo, "", None, explore.SORT_DEFAULT)
    flags = [library.has(h.entity.id) for h in hits]

    illustrated = flags.count(True)
    assert illustrated > 0, "数据集中至少应有一张配图，否则这条规则无从验证"
    boundary = flags.index(False) if False in flags else len(flags)
    assert boundary == illustrated, (
        f"有图实体应全部排在无图实体之前：有图 {illustrated} 个，"
        f"但第一个无图实体出现在第 {boundary + 1} 位"
    )

    # 稳定排序：无图部分保持数据原本的顺序，不被这次重排打乱
    expected_plain = [e.id for e in repo.entities if not library.has(e.id)]
    assert [h.entity.id for h in hits[boundary:]] == expected_plain


def test_explore_search_and_explicit_sorts_ignore_image_priority() -> None:
    """「有配图优先」只作用于默认浏览顺序，不得污染检索与显式排序。"""
    repo = Repository(load_dataset())

    # 检索时必须保持相关性顺序（与 repository.search 完全一致）
    searched, _ = explore._select(repo, "宏村", None, explore.SORT_DEFAULT)
    assert [h.entity.id for h in searched] == [
        h.entity.id for h in repo.search("宏村")
    ]

    # 显式排序仍然只按各自的键排序
    by_name, _ = explore._select(repo, "", None, explore.SORT_NAME)
    assert [h.entity.name for h in by_name] == sorted(e.name for e in repo.entities)

    by_degree, _ = explore._select(repo, "", None, explore.SORT_RELATIONS)
    keys = [(-repo.degree(h.entity.id), h.entity.name) for h in by_degree]
    assert keys == sorted(keys)


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


def test_about_workflow_timeline_shows_every_step(local_app: AppTest) -> None:
    """运行工作流后必须逐步展示输入、输出与耗时（不得只给一个结论）。"""
    _open_about(local_app)
    local_app.text_area(key="wf_input").set_value("宏村是什么？")
    local_app.button(key="wf_run").click()
    local_app.run()
    assert not local_app.exception, f"运行工作流抛出异常：{local_app.exception}"

    result = local_app.session_state.get("wf_result")
    assert result is not None, "运行后应把工作流结果写入会话"
    assert len(result.steps) == len(workflow.STEP_ORDER)

    body = _body(local_app)
    for i, step in enumerate(result.steps, start=1):
        assert f"STEP {i}" in body, f"时间线缺少第 {i} 步"
        assert step.title in body
        assert step.status_label in body
    assert "步骤执行日志" in body
    assert "引用核查结论" in body
    assert "最终回答" in body
    assert "ms" in body, "每步耗时必须如实显示"


def test_about_workflow_records_input_and_output_per_step(local_app: AppTest) -> None:
    """每一步都要有输入与输出说明——「可追踪」的具体含义。"""
    _open_about(local_app)
    local_app.text_area(key="wf_input").set_value("徽商是什么？")
    local_app.button(key="wf_run").click()
    local_app.run()
    result = local_app.session_state.get("wf_result")
    for step in result.steps:
        assert step.output_summary
        assert step.elapsed_ms >= 0
    stored = workflow.StepRecord  # 便于阅读：断言的是真实的数据结构
    assert all(isinstance(s, stored) for s in result.steps)
    assert result.trace_text().count("输入：") == len(result.steps)


def test_about_workflow_aborts_honestly_on_unknown_topic(local_app: AppTest) -> None:
    """资料库里没有的主题必须中途中止并说明在哪一步停下，而不是硬凑答案。"""
    _open_about(local_app)
    local_app.text_area(key="wf_input").set_value("量子纠缠与超导体")
    local_app.button(key="wf_run").click()
    local_app.run()
    assert not local_app.exception
    result = local_app.session_state.get("wf_result")
    assert result.status == "aborted"
    assert result.aborted_at == workflow.STEP_RETRIEVE
    assert result.step(workflow.STEP_ANSWER).status == "skipped"
    body = _body(local_app)
    assert "工作流已中止" in body
    assert "第 2 步中止" in body, "中止信息要指明发生在哪一步"


def test_about_workflow_example_button_actually_runs(local_app: AppTest) -> None:
    """示例问题按钮必须真的运行工作流（不允许只有外观的假按钮）。"""
    _open_about(local_app)
    assert not local_app.session_state.get("wf_result")
    local_app.button(key="wf_ex_0").click()
    local_app.run()
    assert not local_app.exception
    result = local_app.session_state.get("wf_result")
    assert result is not None, "点击示例后应产生一次真实运行"
    assert result.question
    assert result.steps


def test_about_workflow_clear_button_resets(local_app: AppTest) -> None:
    """清空按钮必须真的清掉运行结果与输入。"""
    _open_about(local_app)
    local_app.text_area(key="wf_input").set_value("宏村是什么？")
    local_app.button(key="wf_run").click()
    local_app.run()
    assert local_app.session_state.get("wf_result") is not None

    local_app.button(key="wf_clear").click()
    local_app.run()
    assert not local_app.exception
    assert local_app.session_state.get("wf_result") is None
    assert not local_app.session_state.get("wf_input")


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


# --------------------------------------------------------------------------
# 关于项目页与智能体工作流（P5）—— 工作流同样走本地检索式后端，不联网
# --------------------------------------------------------------------------


def _open_about(app: AppTest) -> AppTest:
    app.run()
    app.session_state["page"] = "about"
    app.run()
    assert not app.exception, f"关于项目页抛出异常：{app.exception}"
    return app


def test_about_page_renders_real_content(app: AppTest) -> None:
    """「关于项目」页必须渲染真实内容与可运行的工作流，而不是「未实现」占位。"""
    _open_about(app)
    body = _body(app)
    assert "关于项目" in body
    assert "尚未实现" not in body, "已交付的页面不应再显示占位文案"
    # 工作流的六个步骤必须如实展示（步骤名来自代码常量，而不是页面里手写的文案）
    for key in workflow.STEP_ORDER:
        assert workflow.STEP_TITLES[key] in body, f"流程说明缺少步骤：{key}"
    # 模块职责表与开发原则都要有，且数据规模来自真实数据集
    assert "架构与模块职责" in body
    assert "开发原则" in body
    dataset = load_dataset()
    assert f"{len(dataset.entities)} 个实体" in body
