"""关于项目：平台说明、架构与模块职责，以及**可真实运行**的智能体工作流演示。

这一页承担两件事：

1. 把项目的定位、技术栈、模块划分与开发原则讲清楚（答辩与交接时最常被问到的部分）；
2. 让「可追踪智能体工作流」变成可以当场点、当场看的东西——输入一个问题，
   页面会把六个步骤的**输入、输出、耗时与状态**逐步列出来，包括在哪一步中止、
   核查为什么没通过。所有数字都来自真实运行，不是示意文案。
"""

from __future__ import annotations

import importlib.util
from typing import List, Tuple

import streamlit as st

from src import __version__, config
from src.agent import workflow as wf
from src.agent.workflow import AgentWorkflow, WorkflowResult
from src.data.loader import DataError, dataset_summary, load_dataset
from src.qa.errors import QAError
from src.ui import components as ui
from src.ui import datastore, nav

#: session_state 键
STATE_INPUT = "wf_input"
#: 待执行的问题（示例按钮通过 on_click 回调写入，避免渲染后回填控件报错）
STATE_PENDING = "wf_pending"
STATE_RESULT = "wf_result"

#: 架构说明：模块 → 职责。``模块`` 是否就绪由 importlib 实时探测。
_MODULES: List[Tuple[str, str]] = [
    ("src.config", "路径、环境变量与问答后端探测"),
    ("src.data.loader", "文化数据的模型、加载与 11 类校验"),
    ("src.data.repository", "检索、筛选、详情、邻居、子图、路径与统计"),
    ("src.data.images", "图片库与署名，清单缺失时安全降级"),
    ("src.graph.builder", "MultiDiGraph 建模、筛选与 ego 子图"),
    ("src.graph.analysis", "结构统计、中心性、最短路径与文化聚类"),
    ("src.graph.visualize", "离线自洽的交互式图谱 HTML"),
    ("src.qa.retriever", "jieba 分词 + BM25 资料检索（结果必带来源）"),
    ("src.qa.prompt", "编号引用提示词、引用解析与纠正指令"),
    ("src.qa.engine", "三层后端降级链、引用溯源与越界编号识别"),
    ("src.agent.workflow", "六步可追踪工作流与结构化引用核查"),
]

_PRINCIPLES = [
    "先检查现有文件与环境，再动手修改。",
    "模块化开发，每完成一个模块即运行并测试。",
    "不虚构 API、依赖或测试结果。",
    "所有按钮必须具备真实功能，不出现纯装饰按钮。",
    "文化事实必须标注可核查来源。",
    "AI 回答严格基于检索到的资料；资料不足时明确说明，不编造。",
    "敏感配置只存于环境变量，绝不写入代码或版本库。",
    "所有模块均处理异常、空结果与加载状态。",
]


def _module_ready(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError):
        return False


# --------------------------------------------------------------------------
# 区块：项目概览
# --------------------------------------------------------------------------


def _render_overview() -> None:
    ui.render_section("项目概览", "徽州文化知识图谱与 AI 智能问答平台，课程设计项目。")

    try:
        summary = dataset_summary(load_dataset())
        scale = (
            f"{summary['entities']} 个实体 / {summary['relations']} 条关系 / "
            f"{summary['sources']} 条来源 / {summary['categories']} 个分类"
        )
    except DataError as exc:
        scale = f"文化数据加载失败：{str(exc).splitlines()[0]}"

    rows = [
        ui.kv_row("项目定位", "把徽州文化整理成结构化、可核查、可交互的知识"),
        ui.kv_row("数据规模", ui.esc(scale)),
        ui.kv_row("技术栈", "Python · Streamlit · NetworkX · PyVis · jieba · pytest · Git"),
        ui.kv_row("问答后端", ui.esc(config.qa_backend_label()) + "（按 Dify → 大模型 → 本地检索式 自动降级）"),
        ui.kv_row("应用版本", f"v{ui.esc(__version__)}"),
    ]
    ui.render(ui.card_html("平台一览", "".join(rows)))

    ui.render(
        ui.note_line(
            "本页的智能体工作流演示会真实调用问答后端。"
            "未配置任何模型凭证时自动使用本地检索式后端（纯离线、可复现，不做生成式改写）。",
            "info",
        )
    )


# --------------------------------------------------------------------------
# 区块：架构与模块职责
# --------------------------------------------------------------------------


def _render_architecture() -> None:
    ui.render_section("架构与模块职责", "分层设计：界面只做展示，业务逻辑下沉到可单测的模块。")

    rows = []
    for dotted, duty in _MODULES:
        ready = _module_ready(dotted)
        mark = (
            f'<span class="hz-tag hz-tag--accent">已交付</span>'
            if ready
            else f'<span class="hz-tag">缺失</span>'
        )
        rows.append([f"<code>{ui.esc(dotted)}</code>", ui.esc(duty), mark])
    ui.render(
        ui.card_html(
            "模块划分（就绪状态由程序实时探测）",
            ui.table_html(["模块", "职责", "状态"], rows, aligns=["left", "left", "right"]),
        )
    )

    ui.render_section("开发原则")
    st.markdown("\n".join(f"{i}. {p}" for i, p in enumerate(_PRINCIPLES, start=1)))


# --------------------------------------------------------------------------
# 区块：可追踪智能体工作流
# --------------------------------------------------------------------------


def _queue_question(question: str) -> None:
    """示例按钮回调：回填输入框并挂起问题，等主流程执行。"""
    st.session_state[STATE_INPUT] = question
    st.session_state[STATE_PENDING] = question


def _clear() -> None:
    st.session_state[STATE_RESULT] = None
    st.session_state[STATE_INPUT] = ""
    st.session_state.pop(STATE_PENDING, None)


def _run(workflow: AgentWorkflow, question: str) -> None:
    """真实执行一次工作流并把结果写入会话。"""
    try:
        with st.spinner("正在执行工作流…"):
            result = workflow.run(question)
    except QAError as exc:
        ui.render(ui.note_line(f"工作流执行失败：{exc}", "error"))
        return
    except Exception as exc:  # noqa: BLE001 - 兜底，避免整页崩溃
        ui.render(ui.note_line(f"未预期的异常：{type(exc).__name__}：{exc}", "error"))
        return

    st.session_state[STATE_RESULT] = result
    st.rerun()


def _render_flow() -> None:
    """流程说明：步骤与职责直接取自代码常量，避免图与实现脱节。"""
    chain = [
        (i, wf.STEP_TITLES[key], wf.STEP_DUTIES[key])
        for i, key in enumerate(wf.STEP_ORDER, start=1)
    ]
    ui.render(ui.flow_chain(chain))
    st.caption(
        f"共 {len(wf.STEP_ORDER)} 步。任何一步判定为致命失败（问题不合法 / 检索不到资料 / "
        "后端全部不可用）都会立刻中止，余下步骤记为「跳过」并写明原因——不做静默兜底。"
    )


def _render_checks(result: WorkflowResult) -> None:
    if not result.checks:
        return
    ui.render_section(
        "引用核查结论",
        "核查项全部由程序判定，不使用模型自评，因此结论可复现、可测试。",
    )
    rows = []
    for item in result.checks:
        label = {"pass": "通过", "warn": "警告", "fail": "未通过"}.get(item.level, item.level)
        rows.append([ui.esc(item.label), ui.level_tag(item.level, label), ui.esc(item.detail)])
    ui.render(
        ui.card_html(
            f"核查 {result.passed_checks}/{len(result.checks)} 项通过",
            ui.table_html(["核查项", "结论", "说明"], rows, aligns=["left", "center", "left"]),
            flat=True,
        )
    )


def _render_answer(result: WorkflowResult) -> None:
    if result.aborted:
        ui.render(
            ui.note_line(
                f"工作流在第 {wf.STEP_ORDER.index(result.aborted_at) + 1} 步中止："
                f"{result.abort_reason}。因此没有生成回答——"
                "本项目不允许在没有资料支撑的情况下让模型自由发挥。",
                "warn",
            )
        )
        return

    ui.render_section("最终回答", "与「AI 问答」页同一套作答链路，此处展示的是工作流归档的结果。")
    answer = result.answer_result
    if answer is None:
        ui.render(ui.note_line("本次运行没有产生作答结果。", "warn"))
        return
    meta = [
        f"后端：{answer.backend_label}",
        f"模型：{answer.model or '—'}",
        f"耗时：{answer.elapsed_ms} ms",
        f"引用：{len(answer.citations)} 处",
    ]
    ui.render(
        f'<div class="hz-answer__meta">{"".join(f"<span>{ui.esc(b)}</span>" for b in meta)}</div>'
    )
    ui.render(ui.answer_block(answer.answer, valid_numbers=[c.index for c in answer.citations]))

    used = {c.index for c in answer.citations}
    ui.render(
        ui.count_line(
            f"引用来源 {len(answer.citations)} 条，检索资料 {len(answer.passages)} 条"
            f"（其中 {len(answer.unused_passages)} 条未被引用，同样列出便于核查）。"
        )
    )
    for citation in answer.citations:
        blocks = [
            f'<div class="hz-passage__title">[{citation.index}] {ui.esc(citation.title)}'
            f'<span class="hz-src__meta" style="display:inline;">　·　'
            f"{ui.esc(citation.passage.category_name)}</span></div>"
        ]
        for order, source in enumerate(citation.sources, start=1):
            blocks.append(
                ui.source_row(
                    index=order,
                    title=source.title,
                    publisher=source.publisher,
                    url=source.url,
                    note=source.note,
                )
            )
        ui.render(ui.card("".join(blocks)))

    if used and len(used) < len(answer.passages):
        with st.expander(f"查看未被引用的 {len(answer.passages) - len(used)} 条资料"):
            for index, passage in enumerate(answer.passages, start=1):
                if index in used:
                    continue
                st.markdown(f"**[{index}] {passage.title}**　相关度 {passage.score:.2f}　{passage.text[:200]}…")


def _render_timeline(result: WorkflowResult) -> None:
    ui.render_section(
        "步骤执行日志",
        "每一步的输入、输出与耗时均来自本次真实运行；跳过的步骤不会被隐藏。",
    )
    html = "".join(
        ui.workflow_step(
            index=i,
            title=step.title,
            status=step.status,
            status_label=step.status_label,
            elapsed_ms=step.elapsed_ms,
            input_summary=step.input_summary,
            output_summary=step.output_summary,
        )
        for i, step in enumerate(result.steps, start=1)
    )
    ui.render(html)

    for i, step in enumerate(result.steps, start=1):
        if not step.detail:
            continue
        with st.expander(f"STEP {i} · {step.title} 明细"):
            st.code(step.detail, language="text")

    with st.expander("查看完整追踪日志（纯文本，可直接用于答辩演示或写进报告）"):
        st.code(result.trace_text(), language="text")


def _render_result(result: WorkflowResult) -> None:
    """一次工作流运行的完整呈现：结论 → 步骤 → 核查 → 回答。"""
    verdict_label = {
        wf.LEVEL_PASS: "全部通过",
        wf.LEVEL_WARN: "通过但有警告",
        wf.LEVEL_FAIL: "未通过",
    }.get(result.verdict, result.verdict)

    meta_bits = [
        f"整体状态：{result.status_label}",
        f"总耗时：{result.elapsed_ms} ms",
        f"步骤：{result.steps_executed}/{len(result.steps)} 步已执行",
    ]
    if not result.aborted:
        meta_bits.append(f"引用核查：{verdict_label}")
    ui.render(
        f'<div class="hz-answer__meta">{"".join(f"<span>{ui.esc(b)}</span>" for b in meta_bits)}</div>'
    )

    if result.aborted:
        ui.render(ui.note_line(f"工作流已中止：{result.abort_reason}", "error"))
    elif result.verdict == wf.LEVEL_FAIL:
        failed = "、".join(c.label for c in result.failed_checks)
        ui.render(
            ui.note_line(
                f"自我核查未通过（{failed}）。纠正重试已经执行过一次，仍未通过——"
                "这里如实报告，而不是把有问题的回答包装成「已完成」。",
                "error",
            )
        )
    elif result.verdict == wf.LEVEL_WARN:
        ui.render(
            ui.note_line(
                "核查未发现致命问题，但存在警告项（详见下方核查表）。",
                "warn",
            )
        )

    _render_timeline(result)
    _render_checks(result)
    _render_answer(result)


def _render_workflow(workflow: AgentWorkflow) -> None:
    try:
        repo = datastore.repository()
    except DataError:
        repo = None

    examples = wf.suggest_questions(repo) if repo is not None else []

    ui.render_section(
        "可追踪智能体工作流",
        "现场运行：输入问题后，页面会逐步展示每个步骤做了什么、花了多久、结果如何。",
    )
    _render_flow()

    question = st.text_area(
        "工作流输入",
        key=STATE_INPUT,
        height=80,
        placeholder="例如：宏村和西递有什么关系？胡适当年考取庚款留美是哪一年？",
        help="问题会经过解析 → 检索 → 作答 → 核查 → （必要时）纠正 → 归档六个步骤。",
    )
    cols = st.columns([1, 1, 4], gap="small")
    submit = cols[0].button("运行工作流", key="wf_run", type="primary", use_container_width=True)
    cols[1].button("清空", key="wf_clear", use_container_width=True, on_click=_clear)

    if examples:
        st.caption("示例问题（由当前数据集实时生成）：")
        per_row = 2
        for start in range(0, len(examples), per_row):
            chunk = examples[start : start + per_row]
            cols = st.columns(len(chunk), gap="small")
            for offset, item in enumerate(chunk):
                with cols[offset]:
                    st.button(
                        item,
                        key=f"wf_ex_{start + offset}",
                        use_container_width=True,
                        on_click=_queue_question,
                        args=(item,),
                    )

    if submit:
        if question.strip():
            _run(workflow, question)
        else:
            ui.render(ui.note_line("请先输入问题，或点击上方示例问题。", "warn"))

    pending = st.session_state.pop(STATE_PENDING, None)
    if pending and not submit:
        _run(workflow, pending)

    result = st.session_state.get(STATE_RESULT)
    if result is None:
        ui.render(
            ui.note_line(
                "还没有运行记录。上方示例问题由当前数据集实时生成，"
                "点任意一个即可看到完整的六步追踪日志。",
                "info",
            )
        )
        return
    _render_result(result)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def render() -> None:
    """关于项目页入口。"""
    ui.render(ui.crumb(["徽州文化", "关于项目"]))
    ui.render(
        ui.hero(
            "ABOUT · AGENT WORKFLOW",
            "关于项目",
            "徽知把徽州文化整理成可检索、可核查、可交互的知识。"
            "这一页说明项目的架构与开发原则，并提供一条**可现场运行**的智能体工作流："
            "从问题解析、资料检索、依据资料作答，到引用自我核查与输出归档，每一步都留痕。",
        )
    )

    _render_overview()

    try:
        workflow = datastore.agent_workflow()
    except DataError as exc:
        ui.render_error("工作流初始化失败", str(exc).splitlines()[0])
        return
    except Exception as exc:  # noqa: BLE001 - 初始化失败也要给出可读状态
        ui.render_error("工作流初始化失败", f"{type(exc).__name__}：{exc}")
        return

    st.markdown("<div style='height:.4rem;'></div>", unsafe_allow_html=True)
    _render_workflow(workflow)

    st.markdown("<div style='height:.6rem;'></div>", unsafe_allow_html=True)
    _render_architecture()

    cols = st.columns([1, 1, 1, 1, 3], gap="small")
    with cols[0]:
        nav.nav_button("打开 AI 问答", "ask", key="about_go_ask")
    with cols[1]:
        nav.nav_button("浏览文化百科", "explore", key="about_go_explore")
    with cols[2]:
        nav.nav_button("查看知识图谱", "graph", key="about_go_graph")


__all__ = ["render"]
