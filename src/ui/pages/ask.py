"""AI 问答页：先检索本地文化资料，再由后端基于资料作答，回答强制标注来源。

交互链路全部真实可用：
- 提问 → BM25 检索 → 后端作答 → 展示回答 + 引用来源 + 检索到的全部资料；
- 示例问题由当前数据实时生成（取连接度最高的实体），点击即真实提问；
- 引用来源只列出**回答里真正引用到**的资料，未被引用的资料单独标注，便于核查；
- 后端降级原因、模型引用了不存在的编号等情况都会如实展示，不做粉饰。
"""

from __future__ import annotations

from typing import List, Sequence

import streamlit as st

from src import config
from src.data.loader import DataError
from src.data.repository import Repository
from src.qa.engine import QAEngine, QAResult
from src.qa.errors import AllBackendsFailedError, QAError, QuestionError
from src.ui import components as ui
from src.ui import datastore, nav
from src.ui.theme import category_color

#: session_state 键
STATE_HISTORY = "qa_history"
STATE_VIEW = "qa_view"
STATE_INPUT = "qa_input"
#: 待执行的问题。示例按钮通过 on_click 回调写入（回调在控件实例化之前运行，
#: 因此可以安全地回填输入框；若在渲染后再写 qa_input，Streamlit 会直接报错）。
STATE_PENDING = "qa_pending"

#: 会话中保留的问答轮数
MAX_HISTORY = 6


# --------------------------------------------------------------------------
# 示例问题（从当前数据实时生成）
# --------------------------------------------------------------------------


def _build_examples(repo: Repository, limit: int = 6) -> List[str]:
    """生成示例问题。

    取自连接度最高的实体，因此这些问题**一定检索得到资料**，
    点击后能看到真实回答——不做「点了没反应」的装饰性示例。
    """
    examples: List[str] = []
    ranked = sorted(repo.entities, key=lambda e: (-repo.degree(e.id), e.name))

    for entity in ranked[:3]:
        examples.append(f"{entity.name}是什么？")
        neighbors = repo.neighbors(entity.id)
        if neighbors:
            examples.append(f"{entity.name}与{neighbors[0].entity.name}有什么关系？")
        if len(examples) >= limit:
            break

    if len(examples) < limit:
        villages = repo.by_category("village")
        if villages:
            examples.append(f"{villages[0].name}有什么特点？")
    if len(examples) < limit:
        heritage = repo.by_category("heritage")
        if heritage:
            examples.append(f"{heritage[0].name}是哪一级非物质文化遗产？")

    seen: set = set()
    unique: List[str] = []
    for question in examples:
        if question not in seen:
            seen.add(question)
            unique.append(question)
    return unique[:limit]


# --------------------------------------------------------------------------
# 区块
# --------------------------------------------------------------------------


def _render_backend_bar(engine: QAEngine) -> None:
    """后端状态条：当前生效的后端高亮，不可用的说明原因。"""
    rows = engine.availability()
    active = engine.active_backend()

    badges = "".join(
        ui.backend_badge(label, active=(active is not None and bid == active.id), available=ok)
        for bid, label, ok, _reason in rows
    )
    ui.render(f'<div style="margin-bottom:.4rem;">{badges}</div>')

    if config.qa_force_local():
        ui.render(
            ui.note_line(
                "已通过环境变量 QA_FORCE_LOCAL 强制使用本地检索式后端，"
                "本次会话不会调用任何外部接口。",
                "info",
            )
        )

    unavailable = [(label, reason) for _bid, label, ok, reason in rows if not ok]
    if unavailable:
        detail = "；".join(f"{label}：{reason}" for label, reason in unavailable)
        ui.render(
            ui.note_line(
                f"以下后端在当前环境中不可用，已自动跳过：{detail}",
                "warn",
            )
        )


def _render_retrieval_hint(engine: QAEngine) -> None:
    """检索索引概况：让「回答基于资料」这件事可验证。"""
    stats = engine.retriever.stats()
    st.caption(
        f"检索范围：{int(stats['documents'])} 份文化资料"
        f"（词表 {int(stats['vocabulary'])} 词，平均长度 {stats['avg_length']} 词，"
        f"返回前 {int(stats['top_k'])} 条）。每份资料都对应一个实体并带可核查来源。"
    )


def _queue_question(question: str) -> None:
    """示例按钮的点击回调：回填输入框并把问题挂起，等本轮渲染到主流程时执行。"""
    st.session_state[STATE_INPUT] = question
    st.session_state[STATE_PENDING] = question


def _clear_session() -> None:
    """清空按钮的点击回调。

    必须走 on_click：回调在控件实例化**之前**执行，
    因此可以安全地重置 ``qa_input``；在渲染之后直接赋值会被 Streamlit 拒绝。
    """
    st.session_state[STATE_HISTORY] = []
    st.session_state[STATE_VIEW] = 0
    st.session_state[STATE_INPUT] = ""
    st.session_state.pop(STATE_PENDING, None)


def _render_examples(examples: Sequence[str]) -> None:
    """示例问题按钮。点击即真实提问（通过 on_click 回调，避免回填输入框报错）。"""
    if not examples:
        return
    ui.render_section("示例问题", "由当前数据集实时生成，点击即提问。")
    per_row = 2
    for start in range(0, len(examples), per_row):
        chunk = examples[start : start + per_row]
        cols = st.columns(len(chunk), gap="small")
        for offset, (col, question) in enumerate(zip(cols, chunk)):
            with col:
                st.button(
                    question,
                    key=f"qa_ex_{start + offset}",
                    width="stretch",
                    on_click=_queue_question,
                    args=(question,),
                )


def _render_citations(res: QAResult) -> None:
    """引用来源：回答里真正引用到的资料，逐条给出可核查链接。"""
    ui.render_section(
        "引用来源",
        f"回答中共出现 {len(res.citations)} 处引用，对应下列资料；点击链接可核查原文出处。",
    )

    if not res.citations:
        ui.render(
            ui.note_line(
                "本次回答没有引用任何资料。这可能意味着资料不足以回答问题，"
                "请核对回答内容或换一种问法。",
                "warn",
            )
        )
        return

    for citation in res.citations:
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

    per_row = 4
    for start in range(0, len(res.citations), per_row):
        chunk = res.citations[start : start + per_row]
        cols = st.columns(len(chunk), gap="small")
        for col, citation in zip(cols, chunk):
            with col:
                nav.nav_button(
                    f"查看「{citation.title}」",
                    "detail",
                    key=f"qa_cite_{citation.index}_{citation.entity_id}",
                    entity_id=citation.entity_id,
                )


def _render_passages(res: QAResult, repo: Repository) -> None:
    """检索到的全部资料：被引用与未被引用都列出，便于核查检索质量。"""
    if not res.passages:
        ui.render(
            ui.note_line(
                "本次提问没有检索到任何相关资料。本地资料库中可能没有覆盖该主题；"
                "本项目不会用无关资料凑数，也不允许模型凭记忆作答。",
                "warn",
            )
        )
        return

    used = {c.index for c in res.citations}
    cited_count = len(used)
    # 这行放在 expander 之外：检索条数是一眼可见的信息，不该藏在折叠区里
    ui.render(
        ui.count_line(
            f"检索到 {len(res.passages)} 条资料，其中 {cited_count} 条被回答引用；"
            "未被引用的资料同样列出，便于核查检索质量。"
        )
    )
    label = (
        f"查看检索到的全部 {len(res.passages)} 条资料"
        f"（其中 {cited_count} 条被回答引用）"
    )
    with st.expander(label, expanded=False):
        for index, passage in enumerate(res.passages, start=1):
            category_id = _category_of(repo, passage.entity_id)
            ui.render(
                ui.passage_block(
                    index=index,
                    title=passage.title,
                    category_name=passage.category_name,
                    category_color=category_color(category_id),
                    text=passage.text,
                    source_titles=[s.citation for s in passage.sources],
                    score=passage.score,
                    hits=passage.matched_terms,
                    used=index in used,
                )
            )
            nav.nav_button(
                "打开实体详情",
                "detail",
                key=f"qa_passage_{index}_{passage.entity_id}",
                entity_id=passage.entity_id,
                width="content",
            )


def _category_of(repo: Repository, entity_id: str) -> str:
    entity = repo.get(entity_id)
    return entity.category if entity else ""


def _render_result(res: QAResult, repo: Repository, expanded: bool = True) -> None:
    """渲染一轮完整问答。"""
    ui.render(ui.question_box(res.question))

    meta_bits = [
        f"后端：{res.backend_label}",
        f"模型：{res.model or '—'}",
        f"耗时：{res.elapsed_ms} ms",
    ]
    if res.usage.get("total_tokens"):
        meta_bits.append(f"tokens：{res.usage['total_tokens']}")
    meta_bits.append(f"检索：{len(res.passages)} 条")
    ui.render(f'<div class="hz-answer__meta">{"".join(f"<span>{ui.esc(b)}</span>" for b in meta_bits)}</div>')

    ui.render(ui.answer_block(res.answer, valid_numbers=[c.index for c in res.citations]))

    if res.degradations:
        ui.render(
            ui.note_line(
                "本次回答跳过了部分后端：" + "；".join(res.degradations),
                "info",
            )
        )
    if res.invalid_citations:
        bad = "、".join(f"[{n}]" for n in res.invalid_citations)
        ui.render(
            ui.note_line(
                f"模型引用了不存在的资料编号 {bad}（已在上方用红字标出）。"
                "这类引用无法核查，请以实际列出的来源为准。",
                "error",
            )
        )
    if res.used_local_fallback:
        ui.render(
            ui.note_line(
                "当前使用本地检索式后端：回答为资料原文，未经过生成式改写。"
                "配置 LLM_API_KEY 或 DIFY_BASE_URL / DIFY_API_KEY 后可获得归纳式回答。",
                "info",
            )
        )

    _render_citations(res)
    _render_passages(res, repo)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def _run_ask(engine: QAEngine, question: str) -> None:
    """执行一次提问并把结果写入会话历史。"""
    try:
        with st.spinner("正在检索资料并生成回答…"):
            res = engine.ask(question)
    except QuestionError as exc:
        ui.render(ui.note_line(exc.reason, "warn"))
        return
    except AllBackendsFailedError as exc:
        ui.render(ui.note_line("所有问答后端均不可用，本次提问未能完成。", "error"))
        with st.expander("查看各后端的失败原因"):
            for attempt in exc.attempts:
                st.markdown(f"- {attempt}")
        return
    except QAError as exc:
        ui.render(ui.note_line(f"问答过程出现异常：{exc}", "error"))
        return
    except Exception as exc:  # noqa: BLE001 - 兜底，避免整页崩溃
        ui.render(ui.note_line(f"未预期的异常：{type(exc).__name__}：{exc}", "error"))
        return

    history: List[QAResult] = list(st.session_state.get(STATE_HISTORY, []))
    history.append(res)
    st.session_state[STATE_HISTORY] = history[-MAX_HISTORY:]
    st.session_state[STATE_VIEW] = len(st.session_state[STATE_HISTORY]) - 1
    st.rerun()


def _render_history(repo: Repository) -> None:
    """历史轮次：最新的完整展示，其余折叠。"""
    history: List[QAResult] = list(st.session_state.get(STATE_HISTORY, []))
    if not history:
        return

    current = int(st.session_state.get(STATE_VIEW, len(history) - 1) or 0)
    current = min(max(current, 0), len(history) - 1)
    st.session_state[STATE_VIEW] = current

    ui.render_section("本轮会话", f"共 {len(history)} 次提问（最多保留 {MAX_HISTORY} 次）。")

    if len(history) > 1:
        others = [i for i in range(len(history)) if i != current]
        cols = st.columns(min(len(others), 5), gap="small")
        for col, idx in zip(cols, others):
            with col:
                if st.button(
                    f"第 {idx + 1} 次：{history[idx].question[:10]}…",
                    key=f"qa_hist_{idx}",
                    width="stretch",
                ):
                    st.session_state[STATE_VIEW] = idx
                    st.rerun()

    _render_result(history[current], repo)


def render() -> None:
    """AI 问答页入口。"""
    ui.render(ui.crumb(["徽州文化", "AI 问答"]))
    ui.render(
        ui.hero(
            "GROUNDED QA",
            "AI 智能问答",
            "提问后，系统先在你的本地徽州文化资料中检索，再让模型严格依据这些资料作答，"
            "并在每个事实后标注来源编号。资料没写的内容不会被编造出来——"
            "检索不到时，回答会直接说明「无法回答」。",
        )
    )

    try:
        repo = datastore.repository()
        engine = datastore.qa_engine()
    except DataError as exc:
        ui.render(ui.error_state("文化数据加载失败", str(exc).splitlines()[0]))
        return
    except Exception as exc:  # noqa: BLE001 - 引擎构建失败也要给出可读状态
        ui.render(ui.error_state("问答引擎初始化失败", f"{type(exc).__name__}：{exc}"))
        return

    _render_backend_bar(engine)
    _render_retrieval_hint(engine)

    st.markdown("<div style='height:.6rem;'></div>", unsafe_allow_html=True)
    question = st.text_area(
        "你的问题",
        key=STATE_INPUT,
        height=90,
        placeholder="例如：宏村和西递有什么关系？徽墨是怎么制作的？马头墙有什么特点？",
        help=f"最多 {300} 字。问题会先在本地资料中检索，再基于检索结果作答。",
    )

    cols = st.columns([1, 1, 4], gap="small")
    submit = cols[0].button("提问", key="qa_submit", type="primary", width="stretch")
    cols[1].button(
        "清空会话",
        key="qa_clear",
        width="stretch",
        on_click=_clear_session,
    )

    examples = _build_examples(repo)
    _render_examples(examples)

    if submit:
        if question.strip():
            _run_ask(engine, question)
        else:
            ui.render(ui.note_line("请先输入问题，或点击上方示例问题。", "warn"))

    # 示例按钮挂起的问题（已 pop，保证只消费一次）
    pending = st.session_state.pop(STATE_PENDING, None)
    if pending and not submit:
        _run_ask(engine, pending)

    _render_history(repo)

    if not st.session_state.get(STATE_HISTORY):
        ui.render(
            ui.note_line(
                "还没有提问记录。上方示例问题由当前数据集实时生成，"
                "点击任意一个即可看到真实的检索结果与带来源的回答。",
                "info",
            )
        )
        with st.expander("问答是怎么工作的？"):
            st.markdown(
                "1. **检索**：用 jieba 分词 + BM25 在本地文化资料中找出最相关的若干条，"
                "每条都对应一个实体并带可核查来源。\n"
                "2. **作答**：把资料编号后交给后端（Dify → 大模型 → 本地检索式），"
                "提示词要求模型只能使用这些资料、且必须标注编号。\n"
                "3. **溯源**：解析回答里的 `[n]` 编号，与资料表比对；"
                "模型若引用了不存在的编号，会被标红提示，而不是被悄悄忽略。\n"
                "4. **降级**：任一层后端不可用时自动切到下一层，"
                "并且**把原因显示出来**，不会让用户误以为用的是最好的那条链路。"
            )
            st.caption(
                "当前后端："
                f"{config.qa_backend_label()}　·　"
                f"检索条数上限 {config.qa_top_k()}（通过 QA_TOP_K 调整）"
            )


__all__ = ["render"]
