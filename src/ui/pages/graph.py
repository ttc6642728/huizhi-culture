"""知识图谱页：可交互图谱、筛选聚焦、关联路径查询、核心枢纽排名与文化聚类。

页面上的每一个数字都来自 ``data/*.json`` 实时建图后的计算结果，
不存在写死的示意图或假的交互控件。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import networkx as nx
import streamlit as st

from src.data.loader import DataError
from src.graph import analysis as ga
from src.graph import builder as gb
from src.graph import runtime
from src.graph import visualize as gv
from src.ui import components as ui

def _embed(html: str, height: int) -> None:
    """把自包含的图谱 HTML 嵌入页面。

    使用 ``st.iframe``（而非已废弃的 ``streamlit.components.v1.html``）：
    传入的字符串既不是 URL 也不是本地文件路径，Streamlit 会走 ``srcdoc`` 分支
    直接内嵌，不产生任何网络请求，因此断网也能正常显示。
    """
    st.iframe(html, height=height)

#: 图谱画布高度（像素）
CANVAS_HEIGHT = 700


# --------------------------------------------------------------------------
# 数据与缓存
# --------------------------------------------------------------------------


@st.cache_data(show_spinner=False, max_entries=16)
def _graph_shards(
    signature: Tuple[int, int, str],
    categories: Tuple[str, ...],
    relation_types: Tuple[str, ...],
    focus: str,
    radius: int,
    physics: bool,
    edge_labels: bool,
) -> List[gv.GraphShard]:
    """按筛选条件生成图谱 HTML（节点过多时自动分片）。

    ``signature`` 只是缓存键的一部分（节点数、边数、数据版本），
    真正的图来自 :func:`~src.graph.runtime.get_graph`；
    数据文件变化时键随之改变，缓存自动失效。

    返回**列表**：规模不大时只有一项（与不分片时的行为完全一致），
    节点数超过 :data:`~src.graph.visualize.DEFAULT_NODE_BUDGET` 时按分类拆成多份，
    避免一次性渲染上千节点把页面拖垮。
    """
    graph = runtime.get_graph()
    view = gb.filter_graph(
        graph,
        categories=categories or None,
        relation_types=relation_types or None,
    )
    active_focus = focus if (focus and view.has_node(focus)) else ""
    if active_focus:
        view = gb.ego_graph(view, active_focus, radius)
    return gv.build_sharded_html(
        view,
        focus=active_focus or None,
        height=CANVAS_HEIGHT,
        physics=physics,
        show_edge_labels=edge_labels,
    )


def _options(graph: nx.MultiDiGraph) -> Tuple[Dict[str, str], List[str]]:
    """返回 ``(node_id → 展示标签, 按分类顺序的 node_id 列表)``。"""
    pairs = gb.sorted_node_options(graph)
    return dict(pairs), [node_id for node_id, _ in pairs]


# --------------------------------------------------------------------------
# 区块渲染
# --------------------------------------------------------------------------


def _render_metrics(stats: ga.GraphStats) -> None:
    cols = st.columns(5, gap="medium")
    cols[0].metric("实体节点", stats.node_count)
    cols[1].metric("关系连线", stats.edge_count)
    cols[2].metric("连通分量", stats.component_count)
    cols[3].metric("图密度", f"{stats.density:.4f}")
    cols[4].metric(
        "平均最短关联",
        f"{stats.avg_shortest_path:.2f}" if stats.avg_shortest_path is not None else "—",
    )

    detail = [
        ("平均度数", f"{stats.avg_degree:.2f}"),
        ("最大度数", str(stats.max_degree)),
        ("网络直径", str(stats.diameter) if stats.diameter is not None else "—"),
        ("最大连通子图", f"{stats.largest_component_size} 个实体（{stats.largest_component_ratio:.0%}）"),
        ("环形结构（独立回路数）", str(stats.cycle_count)),
        ("孤立实体", str(stats.isolated_count)),
    ]
    rows = [ui.kv_row(k, ui.esc(v)) for k, v in detail]
    ui.render(ui.card_html("结构指标", "".join(rows), flat=True))


def _render_controls(
    graph: nx.MultiDiGraph, labels: Dict[str, str], node_ids: List[str]
) -> Tuple[Tuple[str, ...], Tuple[str, ...], str, int, bool, bool]:
    """渲染筛选控件并返回选择结果。"""
    # 分类名 → id（保持数据文件中的分类顺序）
    ordered_cats: List[Tuple[str, str]] = []
    for node_id in node_ids:
        data = graph.nodes[node_id]
        pair = (data.get("category_name", ""), data.get("category", ""))
        if pair not in ordered_cats:
            ordered_cats.append(pair)

    rel_types: List[Tuple[str, str]] = []
    for *_, data in graph.edges(keys=True, data=True):
        pair = (data.get("type_name", ""), data.get("type", ""))
        if pair not in rel_types:
            rel_types.append(pair)
    rel_types.sort(key=lambda p: p[0])

    with st.expander("图谱筛选与布局", expanded=True):
        c1, c2 = st.columns(2, gap="large")
        with c1:
            picked_cats = st.multiselect(
                "按分类筛选（不选 = 全部）",
                options=[cid for _, cid in ordered_cats],
                default=[],
                format_func=lambda cid: next(n for n, i in ordered_cats if i == cid),
                help="只保留所选分类的实体；关系会在两端都被保留时才呈现。",
            )
        with c2:
            picked_types = st.multiselect(
                "按关系类型筛选（不选 = 全部）",
                options=[tid for _, tid in rel_types],
                default=[],
                format_func=lambda tid: next(n for n, i in rel_types if i == tid),
                help="只保留所选类型的关系。",
            )

        c3, c4, c5, c6 = st.columns([2, 2, 1, 1], gap="medium")
        with c3:
            focus = st.selectbox(
                "聚焦实体",
                options=[""] + node_ids,
                key="graph_focus_select",
                format_func=lambda nid: "（不聚焦，显示全图）" if not nid else labels.get(nid, nid),
                help="以该实体为中心，仅显示半径内的关联子图。",
            )
        with c4:
            radius = st.slider("聚焦半径", min_value=1, max_value=3, value=1, disabled=not focus)
        with c5:
            physics = st.toggle("力导布局", value=True, help="关闭后为静态布局，大图更流畅。")
        with c6:
            edge_labels = st.toggle("关系标签", value=False, help="关系较多时常开会显得拥挤。")

    return (
        tuple(picked_cats),
        tuple(picked_types),
        focus,
        int(radius),
        bool(physics),
        bool(edge_labels),
    )


def _render_canvas(
    graph: nx.MultiDiGraph,
    picked_cats: Tuple[str, ...],
    picked_types: Tuple[str, ...],
    focus: str,
    radius: int,
    physics: bool,
    edge_labels: bool,
) -> None:
    """渲染交互式图谱画布。

    展示范围与画布内容严格一致：先按分类/关系类型筛选，再按需取聚焦子图，
    图例与统计都基于同一个 ``display`` 视图，避免出现「数字和画面不符」。
    """
    filtered = gb.filter_graph(
        graph, categories=picked_cats or None, relation_types=picked_types or None
    )

    if filtered.number_of_nodes() == 0:
        ui.render_empty(
            "当前筛选条件下没有任何实体",
            "请放宽分类或关系类型的筛选范围。图谱只展示真实存在的数据，不会用占位节点填充。",
        )
        return

    if filtered.number_of_edges() == 0:
        ui.render_empty(
            f"当前筛选下有 {filtered.number_of_nodes()} 个实体，但它们之间没有任何关系",
            "分类之间往往通过少数枢纽实体（如「徽州」「徽派建筑」）相连，"
            "单独筛选某个分类时可能没有内部关系。建议同时选入枢纽所在的分类，或清空关系类型筛选。",
        )
        return

    active_focus = focus if (focus and filtered.has_node(focus)) else ""
    if focus and not active_focus:
        st.info(
            f"所选实体「{gb.node_option_label(focus, graph)}」不在当前筛选结果中，"
            "本次已忽略「聚焦」，改为展示筛选后的完整子图。"
        )

    display = gb.ego_graph(filtered, active_focus, radius) if active_focus else filtered

    with st.spinner("正在生成交互式图谱…"):
        shards = _graph_shards(
            runtime.signature(graph), picked_cats, picked_types, focus, radius, physics, edge_labels
        )

    ui.render(gv.graph_legend_html(display))

    scope = (
        f"已聚焦「{gb.node_option_label(active_focus, graph)}」，半径 {radius}"
        if active_focus
        else "全图范围"
    )
    st.caption(
        f"{scope}：展示 {display.number_of_nodes()} 个实体、{display.number_of_edges()} 条关系。"
        "可拖拽平移、滚轮缩放、点击节点高亮其直接邻居并淡化其余节点"
        "（把鼠标停在节点上不会弹出浮层；关系的说明可在下方关系明细中查看）。"
    )

    if len(shards) == 1:
        _embed(shards[0].html, CANVAS_HEIGHT + 20)
        return

    # 节点数超过规模阈值：按分类分片展示，每片一张独立图谱
    st.info(
        f"当前视图有 {display.number_of_nodes()} 个实体，已超过单张图谱的规模阈值"
        f"（{gv.DEFAULT_NODE_BUDGET} 个），因此按分类拆成 {len(shards)} 片展示。"
        "每片只画片内的关系，跨片关联请用上方的「聚焦实体」或清空筛选查看全图。"
    )
    labels = [f"{shard.label}（{shard.node_count} 实体 / {shard.edge_count} 关系）" for shard in shards]
    for tab, shard in zip(st.tabs(labels), shards):
        with tab:
            st.caption(f"本片大小约 {shard.size_kb:.0f} KB。")
            _embed(shard.html, CANVAS_HEIGHT + 20)


def _render_focus_panel(graph: nx.MultiDiGraph, labels: Dict[str, str], node_ids: List[str]) -> None:
    st.caption("选择一个实体，查看它在图谱中的真实关联关系（含方向、类型与来源数量）。")

    selected = st.selectbox(
        "实体",
        options=node_ids,
        index=node_ids.index("huizhou_region") if "huizhou_region" in node_ids else 0,
        format_func=lambda nid: labels.get(nid, nid),
        key="graph_focus_panel_select",
    )
    data = graph.nodes[selected]
    view = gb.ego_graph(graph, selected, 1)

    rows: List[List[str]] = []

    for u, v, key, edata in graph.edges(keys=True, data=True):
        if u == selected:
            rows.append([
                '<span class="hz-tag hz-tag--accent">出</span>',
                ui.esc(edata.get("type_name", "")),
                ui.esc(graph.nodes[v].get("name", v)),
                ui.esc(edata.get("description", "") or "—"),
                str(edata.get("source_count", 0)),
            ])
        elif v == selected:
            rows.append([
                '<span class="hz-tag">入</span>',
                ui.esc(edata.get("type_name", "")),
                ui.esc(graph.nodes[u].get("name", u)),
                ui.esc(edata.get("description", "") or "—"),
                str(edata.get("source_count", 0)),
            ])

    cols = st.columns([2, 3], gap="large")
    with cols[0]:
        info = [
            ui.kv_row("名称", ui.esc(data.get("name", ""))),
            ui.kv_row("分类", ui.esc(data.get("category_name", ""))),
            ui.kv_row("别名", ui.esc("、".join(data.get("aliases") or ()) or "—")),
            ui.kv_row("关系条数", f"<strong>{graph.degree(selected)}</strong>"
                                  f"（出 {graph.out_degree(selected)} / 入 {graph.in_degree(selected)}）"),
            ui.kv_row("一度关联实体", str(view.number_of_nodes() - 1)),
            ui.kv_row("来源条数", str(data.get("source_count", 0))),
        ]
        ui.render(ui.card_html("实体信息", "".join(info), accent=True))
        ui.render(f'<p style="font-size:.9rem;">{ui.esc(data.get("summary", ""))}</p>')
    with cols[1]:
        ui.render(ui.table_html(["方向", "关系类型", "关联实体", "关系说明", "来源"], rows))
        if not rows:
            ui.render_empty("该实体暂无关联关系")

    if view.number_of_edges():
        with st.expander("只看这个实体的关联子图", expanded=False):
            html = gv.build_network_html(view, focus=selected, height=460, physics=True)
            _embed(html, 470)


def _render_path_panel(graph: nx.MultiDiGraph, labels: Dict[str, str], node_ids: List[str]) -> None:
    st.caption(
        "查询两个实体之间的最短关联线路。关系方向不构成阻碍（视为「相关」网络），"
        "但呈现时会如实标注某一段的真实方向与行进方向是否一致。"
    )

    c1, c2 = st.columns(2, gap="large")
    default_a = "xidi" if "xidi" in node_ids else node_ids[0]
    default_b = "huishang" if "huishang" in node_ids else node_ids[-1]
    with c1:
        src = st.selectbox("起点", options=node_ids, index=node_ids.index(default_a),
                           format_func=lambda n: labels.get(n, n), key="path_src")
    with c2:
        dst = st.selectbox("终点", options=node_ids, index=node_ids.index(default_b),
                           format_func=lambda n: labels.get(n, n), key="path_dst")

    if src == dst:
        ui.render_empty("起点与终点相同", "请选择两个不同的实体以查询关联路径。")
        return

    path = ga.shortest_path(graph, src, dst)
    if path is None:
        ui.render_empty(
            f"「{labels.get(src, src)}」与「{labels.get(dst, dst)}」之间没有关联路径",
            "两者分属不同的连通分量。这不是错误，而是真实的数据结构——"
            "可以考虑补充关系，或在图谱页查看两者的各自聚类。",
        )
        return

    st.markdown(
        ui.card(
            f'<div style="font-size:.78rem;letter-spacing:.12em;color:#B23A2F;">'
            f"最短关联路径 · 经过 {path.length} 条关系</div>"
            + gv.path_chain_html(graph, path),
            accent=True,
        ),
        unsafe_allow_html=True,
    )

    rows = [
        [
            str(i + 1),
            ui.esc(e.from_name),
            ui.esc(e.label),
            f'<span class="hz-path__arrow">{"→" if e.is_forward else "←"}</span>',
            ui.esc(e.to_name),
            ui.esc(e.type_name),
            ui.esc(e.description or "—"),
            str(e.source_count),
        ]
        for i, e in enumerate(path.edges)
    ]
    ui.render(ui.table_html(
        ["#", "起点", "关系", "方向", "终点", "类型", "说明", "来源"], rows
    ))

    alternatives = ga.shortest_path_all(graph, src, dst, limit=4)
    if len(alternatives) > 1:
        with st.expander(f"另有 {len(alternatives) - 1} 条等长线路", expanded=False):
            for idx, alt in enumerate(alternatives[1:], 2):
                st.markdown(
                    f'<div style="font-size:.78rem;color:#8C867A;">线路 {idx}</div>'
                    + gv.path_chain_html(graph, alt),
                    unsafe_allow_html=True,
                )

    if path.edges:
        with st.expander("只看这条线路", expanded=False):
            html = gv.build_path_html(graph, list(path.nodes), height=360)
            _embed(html, 370)


def _render_hubs_panel(graph: nx.MultiDiGraph) -> None:
    st.caption(
        "度数排名表示「关系最多」的实体；介数排名表示「跨越不同文化领域、充当桥梁」的实体。"
        "两者互补，均由图谱实时计算。"
    )

    deg = ga.degree_ranking(graph, top_n=12)
    btw = ga.betweenness_ranking(graph, top_n=12)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        rows = [
            [str(i + 1), f"<strong>{ui.esc(r.name)}</strong>", ui.esc(r.category_name),
             str(r.degree), str(r.in_degree), str(r.out_degree)]
            for i, r in enumerate(deg)
        ]
        ui.render(ui.card_html(
            "度数排名（连接最多）",
            ui.table_html(["#", "实体", "分类", "度数", "入度", "出度"], rows),
        ))
    with c2:
        rows = [
            [str(i + 1), f"<strong>{ui.esc(r.name)}</strong>", ui.esc(r.category_name),
             f"{r.betweenness:.3f}", str(r.degree)]
            for i, r in enumerate(btw)
        ]
        ui.render(ui.card_html(
            "介数排名（桥梁作用）",
            ui.table_html(["#", "实体", "分类", "介数中心性", "度数"], rows),
        ))

    stats = ga.graph_stats(graph)
    rows = [[ui.esc(k), str(v)] for k, v in stats.relation_type_counts.items()]
    ui.render(ui.card_html(
        f"关系类型分布（共 {len(stats.relation_type_counts)} 类、{stats.edge_count} 条）",
        ui.table_html(["关系类型", "条数"], rows),
    ))


def _render_community_panel(graph: nx.MultiDiGraph) -> None:
    st.caption(
        "基于模块度优化的社区发现（贪心算法，在无向关联视图上计算）。"
        "结果用于观察「徽州文化在结构上聚成哪几块」，属探索性分析，不作为定论。"
    )

    comms = ga.communities(graph)
    if not comms:
        ui.render_empty("图谱关系不足以形成聚类")
        return

    sizes = "、".join(f"{c.size}" for c in comms)
    st.markdown(
        f"共识别出 **{len(comms)}** 个聚类，规模依次为 {sizes} 个实体。"
        f"（模块度 Q = {_modularity(graph):.3f}）"
    )

    for comm in comms:
        names = [graph.nodes[n].get("name", n) for n in comm.node_ids]
        rows = [[ui.esc(k), str(v)] for k, v in
                sorted(_category_breakdown(graph, comm.node_ids).items(), key=lambda kv: -kv[1])]
        body = (
            f'<div style="font-size:.8rem;color:#8C867A;margin-bottom:.5rem;">'
            f"规模 {comm.size} · 内部密度 {comm.cohesion:.3f} · 涉及 {len(comm.category_names)} 个分类</div>"
            + ui.tags(names, kind="stone")
        )
        with st.expander(f"聚类 {comm.index + 1}　·　{names[0]} 等 {comm.size} 个实体", expanded=comm.index < 2):
            ui.render(ui.card(body, flat=True))
            ui.render(ui.table_html(["分类", "实体数"], rows))


def _modularity(graph: nx.MultiDiGraph) -> float:
    """全网模块度 Q：衡量聚类结构的显著程度（>0.3 视为结构明显）。"""
    communities = ga.communities(graph)
    if not communities:
        return 0.0
    partition = [set(c.node_ids) for c in communities]
    try:
        return float(nx.community.modularity(ga.to_undirected_simple(graph), partition))
    except Exception:  # 理论上不会发生；保守返回 0 而不是编造数值
        return 0.0


def _category_breakdown(graph: nx.MultiDiGraph, node_ids: Tuple[str, ...]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for node_id in node_ids:
        name = str(graph.nodes[node_id].get("category_name", ""))
        counts[name] = counts.get(name, 0) + 1
    return counts


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def render() -> None:
    """图谱页入口。"""
    try:
        graph = runtime.get_graph()
    except DataError as exc:
        ui.render_error("文化数据加载失败，无法建图", str(exc).splitlines()[0])
        with st.expander("查看详细错误"):
            st.code(str(exc))
        return
    except gb.GraphError as exc:
        ui.render_error("知识图谱构建失败", str(exc))
        return

    stats = ga.graph_stats(graph)

    ui.render(
        ui.hero(
            "KNOWLEDGE GRAPH",
            "知识图谱",
            f"以 {stats.node_count} 个文化实体为节点、{stats.edge_count} 条实体关系为连线构建的多重有向图。"
            "可筛选分类与关系类型、聚焦单个实体的关联网络、查询任意两者之间的最短关联线路，"
            "并查看由算法计算出的核心枢纽与文化聚类。",
        )
    )

    _render_metrics(stats)

    if stats.isolated_count:
        ui.render_error(
            f"存在 {stats.isolated_count} 个孤立实体",
            "这些实体没有任何关系，会在图谱中显示为游离节点，建议补充关系数据。",
        )

    labels, node_ids = _options(graph)

    # 支持从详情页「在图谱中查看」跳转过来：把请求的实体预置为当前聚焦对象。
    # 该请求只消费一次（弹栈），避免用户手动改成「不聚焦」后又被拽回去。
    requested = str(st.session_state.pop("graph_focus", "") or "")
    if requested and requested in node_ids:
        st.session_state["graph_focus_select"] = requested
        st.session_state["graph_focus_panel_select"] = requested

    picked_cats, picked_types, focus, radius, physics, edge_labels = _render_controls(
        graph, labels, node_ids
    )

    _render_canvas(graph, picked_cats, picked_types, focus, radius, physics, edge_labels)

    st.markdown("<hr/>", unsafe_allow_html=True)
    tab_focus, tab_path, tab_hubs, tab_comm = st.tabs(
        ["聚焦实体", "关联路径", "核心枢纽", "文化聚类"]
    )
    with tab_focus:
        _render_focus_panel(graph, labels, node_ids)
    with tab_path:
        _render_path_panel(graph, labels, node_ids)
    with tab_hubs:
        _render_hubs_panel(graph)
    with tab_comm:
        _render_community_panel(graph)


__all__ = ["render"]
