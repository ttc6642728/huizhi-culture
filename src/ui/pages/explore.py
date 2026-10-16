"""文化百科页：关键词检索、分类筛选、结果浏览与详情入口。

交互全部由真实控件驱动（文本框 / 下拉框 / 按钮），
结果直接来自 :class:`~src.data.repository.Repository` 的实时查询，
不预置任何写死的列表或数量。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import streamlit as st

from src.data.loader import DataError
from src.data.repository import Repository, SearchHit
from src.ui import components as ui
from src.ui import datastore, nav
from src.ui.theme import category_color

#: 每页展示的实体数量（3 列 × 4 行）
PAGE_SIZE = 12
GRID_COLUMNS = 3

SORT_DEFAULT = "默认（有配图优先）"
SORT_NAME = "按名称"
SORT_RELATIONS = "按关联关系数"
SORT_OPTIONS = (SORT_DEFAULT, SORT_NAME, SORT_RELATIONS)

ALL_CATEGORIES = "全部分类"


# --------------------------------------------------------------------------
# 数据选择
# --------------------------------------------------------------------------


def _select(
    repo: Repository, query: str, category: Optional[str], sort: str
) -> Tuple[List[SearchHit], str]:
    """按当前条件取出结果集。

    Returns:
        ``(命中列表, 说明文案)``；命中列表里的 ``score`` 与 ``matched_field``
        在未检索时为空值（不虚构匹配信息）。

    默认顺序下**已有配图的实体排在前面**：图片丰富的条目可读性更好，
    适合作为浏览入口。排序用 ``list.sort`` 的稳定性 + 0/1 键实现，
    因此有图实体内部、无图实体内部都保持数据原本的顺序。
    检索时不做这种重排——相关性必须优先于「有没有图」。
    """
    if query.strip():
        hits = repo.search(query, category=category)
        note = f"关键词「{query.strip()}」"
    else:
        entities = repo.by_category(category) if category else list(repo.entities)
        hits = [
            SearchHit(entity=e, score=0, matched_field="", matched_terms=(), matched_all=False)
            for e in entities
        ]
        note = ""

    if sort == SORT_NAME:
        hits.sort(key=lambda h: h.entity.name)
    elif sort == SORT_RELATIONS:
        hits.sort(key=lambda h: (-repo.degree(h.entity.id), h.entity.name))
    elif not query.strip():
        library = datastore.images()
        hits.sort(key=lambda h: 0 if library.has(h.entity.id) else 1)

    return hits, note


def _relation_count(repo: Repository, entity_id: str) -> int:
    out, inc = repo.relations_of(entity_id)
    return len(out) + len(inc)


# --------------------------------------------------------------------------
# 区块
# --------------------------------------------------------------------------


def _render_filters(repo: Repository) -> Tuple[str, Optional[str], str]:
    """渲染筛选控件并返回 (关键词, 分类 id 或 None, 排序)。"""
    cols = st.columns([3, 2, 2], gap="medium")
    with cols[0]:
        query = st.text_input(
            "关键词",
            key="ex_search",
            placeholder="输入实体名称、别名或关键词，例如「宏村」「三雕」「程大位」",
            help="支持多关键词，用空格或顿号分隔；全部命中的结果排在前面。",
        )
    with cols[1]:
        category_names = [ALL_CATEGORIES] + [
            f"{c.name}" for c in repo.categories() if repo.by_category(c.id)
        ]
        chosen = st.selectbox("分类", category_names, key="ex_category")
    with cols[2]:
        sort = st.selectbox("排序", list(SORT_OPTIONS), key="ex_sort")

    category_id: Optional[str] = None
    if chosen != ALL_CATEGORIES:
        for c in repo.categories():
            if c.name == chosen:
                category_id = c.id
                break
    return query, category_id, sort


def _render_category_buttons(repo: Repository) -> None:
    """分类快捷切换：每个按钮都真实改变筛选条件，并显示该分类的真实实体数。"""
    counts = {c.id: n for c, n in ((cc.category, cc.count) for cc in repo.category_counts())}
    options: List[Tuple[str, Optional[str]]] = [(ALL_CATEGORIES, None)]
    options += [(c.name, c.id) for c in repo.categories() if counts.get(c.id, 0) > 0]

    current = st.session_state.get("ex_category", ALL_CATEGORIES)
    per_row = 6
    for start in range(0, len(options), per_row):
        chunk = options[start : start + per_row]
        cols = st.columns(len(chunk), gap="small")
        for col, (label, cid) in zip(cols, chunk):
            count = len(repo.entities) if cid is None else counts.get(cid, 0)
            with col:
                if st.button(
                    f"{label} {count}",
                    key=f"ex_cat_{cid or 'all'}",
                    use_container_width=True,
                    type="primary" if label == current else "secondary",
                ):
                    st.session_state["ex_category"] = label
                    st.session_state["ex_page"] = 1
                    st.rerun()


def _render_results(repo: Repository, hits: Sequence[SearchHit], note: str) -> None:
    """结果网格：卡片 + 真实跳转按钮。"""
    total = len(hits)
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = int(st.session_state.get("ex_page", 1) or 1)
    page = min(max(page, 1), page_count)
    st.session_state["ex_page"] = page

    start = (page - 1) * PAGE_SIZE
    window = hits[start : start + PAGE_SIZE]

    pieces = [f"共 {total} 个实体"]
    if note:
        pieces.append(note)
    if page_count > 1:
        pieces.append(f"第 {page}/{page_count} 页")
    ui.render(ui.count_line("　·　".join(pieces)))

    numbered = list(enumerate(window, start=start + 1))
    for row_start in range(0, len(numbered), GRID_COLUMNS):
        chunk = numbered[row_start : row_start + GRID_COLUMNS]
        cols = st.columns(GRID_COLUMNS, gap="medium")
        for col, (_pos, hit) in zip(cols, chunk):
            entity = hit.entity
            category = repo.category(entity.category)
            with col:
                ui.render(
                    ui.entity_card(
                        name=entity.name,
                        summary=entity.summary,
                        category_name=category.name if category else entity.category,
                        category_color=category_color(entity.category),
                        degree=repo.degree(entity.id),
                        relation_count=_relation_count(repo, entity.id),
                        source_count=len(entity.source_ids),
                        has_image=datastore.images().has(entity.id),
                    )
                )
                if hit.matched_field:
                    st.caption(f"命中字段：{hit.matched_field}")
                nav.nav_button(
                    "查看详情 →",
                    "detail",
                    key=f"ex_open_{entity.id}",
                    entity_id=entity.id,
                )


def _render_pager(total: int) -> None:
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page_count <= 1:
        return
    page = int(st.session_state.get("ex_page", 1) or 1)
    cols = st.columns([1, 3, 1], gap="small")
    with cols[0]:
        if st.button("← 上一页", key="ex_prev", use_container_width=True, disabled=page <= 1):
            st.session_state["ex_page"] = page - 1
            st.rerun()
    with cols[1]:
        st.caption(f"第 {page} / {page_count} 页")
    with cols[2]:
        if st.button(
            "下一页 →",
            key="ex_next",
            use_container_width=True,
            disabled=page >= page_count,
        ):
            st.session_state["ex_page"] = page + 1
            st.rerun()


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def render() -> None:
    """文化百科页入口。"""
    ui.render(ui.crumb(["徽州文化", "文化百科"]))
    ui.render(
        ui.hero(
            "ENCYCLOPEDIA",
            "文化百科",
            "按名称、别名、摘要与属性检索徽州文化实体，或按分类逐类浏览。"
            "每个实体都可打开详情，查看结构化属性、真实关联关系与可核查来源。",
        )
    )

    try:
        repo = datastore.repository()
    except DataError as exc:
        ui.render_error("数据加载失败", str(exc))
        return

    _render_category_buttons(repo)
    st.markdown("<div style='height:.7rem;'></div>", unsafe_allow_html=True)
    query, category_id, sort = _render_filters(repo)

    hits, note = _select(repo, query, category_id, sort)

    if not hits:
        criteria = "、".join(
            [p for p in [f"关键词「{query.strip()}」" if query.strip() else "",
                         f"分类「{st.session_state.get('ex_category', '')}」"
                         if category_id else ""] if p]
        )
        ui.render_empty(
            f"没有匹配的实体{f'（{criteria}）' if criteria else ''}",
            "请更换关键词或放宽分类。检索覆盖名称、别名、摘要、正文与结构化属性，"
            "如果确实没有结果，说明数据集中暂无该条目——本项目不会用虚构条目填充结果。",
        )
        return

    _render_results(repo, hits, note)
    _render_pager(len(hits))
