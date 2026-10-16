"""实体详情页：结构化属性、正文、真实关联关系、参考资料与图片。

页面读取 ``session_state['entity_id']`` 决定展示哪个实体；
实体不存在（例如数据被改动或链接过期）时显示明确的错误状态并提供返回入口，
不做静默回退到别的实体。
"""

from __future__ import annotations

from typing import Dict, List, Optional

import streamlit as st

from src.data.images import EntityImage
from src.data.loader import DataError, Entity, Relation
from src.data.repository import Repository
from src.ui import components as ui
from src.ui import datastore, nav
from src.ui.theme import category_color

#: 「快速前往」区块最多展示的关联实体数量
MAX_QUICK_LINKS = 12


# --------------------------------------------------------------------------
# 各区块
# --------------------------------------------------------------------------


def _render_not_found(entity_id: str) -> None:
    ui.render(ui.crumb(["徽州文化", "文化百科", "实体详情"]))
    ui.render_error(
        "未找到该实体",
        f"数据集中不存在 id 为「{entity_id}」的实体。它可能已在数据更新中调整或移除，"
        "本项目不会用其它实体顶替。",
    )
    cols = st.columns([1, 1, 3])
    with cols[0]:
        nav.nav_button("← 返回文化百科", "explore", key="dt_back_missing")


def _render_head(repo: Repository, entity: Entity) -> None:
    category = repo.category(entity.category)
    ui.render(ui.crumb(["徽州文化", "文化百科", category.name if category else entity.category]))
    ui.render(
        ui.detail_head(
            name=entity.name,
            category_name=category.name if category else entity.category,
            category_color=category_color(entity.category),
            summary=entity.summary,
            aliases=entity.aliases,
            eyebrow=f"{entity.id}",
        )
    )


def _render_image(image: Optional[EntityImage]) -> None:
    """渲染图片与署名。没有图片时**什么都不显示**（不以占位图充数）。"""
    if image is None or not image.exists:
        return
    try:
        st.image(str(image.path), use_container_width=True)
    except Exception as exc:  # noqa: BLE001 - 图片损坏时不应让整页崩溃
        ui.render_error("图片无法显示", f"本地图片读取失败：{exc}")
        return
    ui.render(
        ui.figure_caption(
            caption=image.caption,
            credit=image.credit,
            source_url=image.source_url,
            license_url=image.license_url,
        )
    )
    st.caption("图片为自由授权作品，署名与许可见上图；完整清单见 assets/images/CREDITS.md。")


def _render_attributes(entity: Entity) -> None:
    ui.render_section("结构化属性", f"{len(entity.attributes)} 项，均来自数据文件")
    if not entity.attributes:
        ui.render_empty("该实体暂无结构化属性")
        return
    rows = [[ui.esc(k), ui.esc(v)] for k, v in entity.attributes.items()]
    ui.render(ui.table_html(["属性", "内容"], rows, aligns=["left", "left"]))


def _render_description(entity: Entity) -> None:
    ui.render_section("正文")
    ui.render(ui.card(f'<div class="hz-body">{ui.esc(entity.description)}</div>'))


def _relation_label(repo: Repository, relation: Relation, direction: str) -> str:
    """以当前实体为主语给出关系标签。

    正向（本实体为起点）用关系名，反向用 ``inverse_name``，
    这样每条关系都以「当前实体」为核心读得通，且不会把方向说反。
    """
    if direction == "out":
        return relation.label or repo.relation_type_name(relation.type)
    for rt in repo.relation_types():
        if rt.id == relation.type:
            return rt.inverse_name or rt.name
    return repo.relation_type_name(relation.type)


def _render_relations(repo: Repository, entity: Entity) -> None:
    out_rels, in_rels = repo.relations_of(entity.id)
    total = len(out_rels) + len(in_rels)
    ui.render_section("关联关系", f"共 {total} 条：以本实体为起点 {len(out_rels)} 条、为终点 {len(in_rels)} 条")

    if total == 0:
        ui.render_empty(
            "该实体暂无关联关系",
            "数据集中尚未建立与其它实体的关系，因此这里没有内容可显示。",
        )
        return

    neighbors = repo.neighbors(entity.id)
    # 分组展示：出向在前、入向在后，组内按关系类型与名称排序
    for direction, title in (("out", "从本实体出发"), ("in", "指向本实体")):
        rows = [n for n in neighbors if n.direction == direction]
        if not rows:
            continue
        ui.render(ui.group_title(f"{title}（{len(rows)} 条）"))
        html = "".join(
            ui.relation_row(
                direction=n.direction,
                relation_label=_relation_label(repo, n.relation, n.direction),
                other_name=n.entity.name,
                description=n.relation.description,
                source_count=len(n.relation.source_ids),
            )
            for n in rows
        )
        ui.render(ui.card(html))

    quick = neighbors[:MAX_QUICK_LINKS]
    if quick:
        ui.render(ui.group_title(f"快速查看关联实体（前 {len(quick)} 个）"))
        per_row = 4
        for start in range(0, len(quick), per_row):
            chunk = quick[start : start + per_row]
            cols = st.columns(len(chunk), gap="small")
            for col, nb in zip(cols, chunk):
                with col:
                    nav.nav_button(
                        f"{nb.entity.name}",
                        "detail",
                        key=f"dt_nb_{entity.id}_{nb.entity.id}_{nb.relation.id}",
                        entity_id=nb.entity.id,
                    )


def _render_sources(repo: Repository, entity: Entity) -> None:
    relation_sources: Dict[str, int] = {}
    out_rels, in_rels = repo.relations_of(entity.id)
    for rel in [*out_rels, *in_rels]:
        for sid in rel.source_ids:
            relation_sources[sid] = relation_sources.get(sid, 0) + 1

    sources = repo.sources_of(entity)
    ui.render_section(
        "参考资料",
        f"实体本身登记 {len(entity.source_ids)} 条，另有 "
        f"{len({s for s in relation_sources if s not in entity.source_ids})} 条来自关联关系的来源",
    )
    if not sources and not relation_sources:
        ui.render_empty("该实体暂无参考资料", "缺少可核查来源的内容不会被收录，请反馈以便补充。")
        return

    rows: List[str] = []
    seen = set()
    for sid in entity.source_ids:
        source = repo.dataset.get_source(sid)
        if source is None or sid in seen:
            continue
        seen.add(sid)
        rows.append(
            ui.source_row(
                index=len(rows) + 1,
                title=source.title,
                publisher=source.publisher,
                url=source.url,
                note=source.note,
            )
        )

    extra = [sid for sid in relation_sources if sid not in seen]
    if extra:
        rows.append(ui.group_title("关联关系引用的来源"))
        for sid in extra:
            source = repo.dataset.get_source(sid)
            if source is None:
                continue
            rows.append(
                ui.source_row(
                    index=len(rows) + 1,
                    title=source.title,
                    publisher=source.publisher,
                    url=source.url,
                    note=source.note,
                )
            )
    ui.render(ui.card("".join(rows)))


def _render_actions(repo: Repository, entity: Entity) -> None:
    """页脚操作区：返回列表、去图谱看该实体、复制 id。"""
    ui.render(ui.group_title("继续探索"))
    cols = st.columns([1, 1, 1, 2], gap="small")
    with cols[0]:
        nav.nav_button("← 返回文化百科", "explore", key=f"dt_back_{entity.id}")
    with cols[1]:
        nav.nav_button(
            "在图谱中查看",
            "graph",
            key=f"dt_graph_{entity.id}",
            graph_focus=entity.id,
        )
    with cols[2]:
        with st.popover("实体标识", use_container_width=True):
            st.code(entity.id, language=None)
            st.caption("该 id 用于数据文件与关系引用，可在图谱页或命令行工具中使用。")


def _render_path_hint(repo: Repository, entity: Entity) -> None:
    """给出一条真实存在的关联路径示例，帮助理解该实体在图谱中的位置。"""
    out_rels, in_rels = repo.relations_of(entity.id)
    candidates = [n.entity for n in repo.neighbors(entity.id)]
    if not candidates:
        return
    target = candidates[0]
    path = repo.shortest_path(entity.id, target.id)
    if not path or len(path) < 2:
        return
    names = [repo.require(pid).name for pid in path]
    chain = " → ".join(names)
    st.caption(f"示例关联线路（{len(path) - 1} 步）：{chain}")


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def render() -> None:
    """实体详情页入口。"""
    entity_id = str(st.session_state.get(nav.STATE_ENTITY, "") or "").strip()

    try:
        repo = datastore.repository()
    except DataError as exc:
        ui.render_error("数据加载失败", str(exc))
        return

    if not entity_id:
        ui.render(ui.crumb(["徽州文化", "文化百科", "实体详情"]))
        ui.render_empty(
            "尚未选择实体",
            "请先到「文化百科」检索并打开一个实体。",
        )
        cols = st.columns([1, 3])
        with cols[0]:
            nav.nav_button("前往文化百科", "explore", key="dt_goto_explore")
        return

    entity = repo.get(entity_id)
    if entity is None:
        _render_not_found(entity_id)
        return

    _render_head(repo, entity)

    left, right = st.columns([3, 2], gap="large")
    with right:
        _render_image(datastore.images().get(entity.id))
    with left:
        _render_attributes(entity)

    _render_description(entity)
    _render_relations(repo, entity)
    _render_sources(repo, entity)
    _render_path_hint(repo, entity)
    _render_actions(repo, entity)
