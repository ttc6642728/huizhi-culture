"""知识图谱测试：建模保真、分析正确性、筛选聚焦、关联路径与离线可视化。

这些测试把「图谱必须忠实反映数据」这件事变成了可执行断言：
节点数必须等于实体数，边数必须等于关系数（平行边不能被合并），
渲染出来的 HTML 不允许包含任何外部资源引用。
"""

from __future__ import annotations

import json
import re
from typing import List

import networkx as nx
import pytest

from src.data.loader import load_dataset
from src.graph import analysis as ga
from src.graph import builder as gb
from src.graph import visualize as gv

EXTERNAL_REF = re.compile(r"<(?:script|link)\b[^>]*\b(?:src|href)\s*=\s*[\"']https?://", re.I)


@pytest.fixture(scope="module")
def dataset():
    return load_dataset()


@pytest.fixture(scope="module")
def graph(dataset) -> nx.MultiDiGraph:
    return gb.build_graph(dataset)


# --------------------------------------------------------------------------
# 建模保真
# --------------------------------------------------------------------------


def test_graph_is_multidigraph(graph: nx.MultiDiGraph) -> None:
    assert isinstance(graph, nx.MultiDiGraph), "必须使用 MultiDiGraph，否则同向平行边会被静默合并"


def test_node_and_edge_counts_match_data(graph: nx.MultiDiGraph, dataset) -> None:
    assert graph.number_of_nodes() == len(dataset.entities)
    assert graph.number_of_edges() == len(dataset.relations)


def test_parallel_edges_are_preserved(graph: nx.MultiDiGraph) -> None:
    """「渐江 → 新安画派」同时有 founder_of 与 representative_of，两条都必须存在。"""
    assert graph.has_edge("jianjiang", "xinan_huapai")
    types = {d["type"] for d in graph["jianjiang"]["xinan_huapai"].values()}
    assert types == {"founder_of", "representative_of"}


def test_node_attributes_complete(graph: nx.MultiDiGraph) -> None:
    for node_id, data in graph.nodes(data=True):
        for field in ("name", "category", "category_name", "summary", "degree", "source_count"):
            assert field in data, f"节点 {node_id} 缺少属性 {field}"
        assert data["name"]
        assert data["category_name"]


def test_edge_attributes_complete(graph: nx.MultiDiGraph) -> None:
    for u, v, key, data in graph.edges(keys=True, data=True):
        for field in ("type", "type_name", "label", "description", "source_ids", "source_count"):
            assert field in data, f"关系 {key} 缺少属性 {field}"
        assert data["type"]
        assert data["source_ids"], f"关系 {key} 没有来源"


def test_degree_attribute_matches_graph_degree(graph: nx.MultiDiGraph) -> None:
    for node_id, data in graph.nodes(data=True):
        assert data["degree"] == graph.degree(node_id)
        assert data["in_degree"] == graph.in_degree(node_id)
        assert data["out_degree"] == graph.out_degree(node_id)


def test_build_graph_raises_on_dangling_relation(dataset) -> None:
    """防御性检查：手工构造一条端点不存在的关�系，必须在建图时报错而不是静默丢弃。"""
    from dataclasses import replace

    bad = replace(dataset.relations[0], id="r_bad", target="__not_exist__")
    broken = replace(dataset, relations=tuple(dataset.relations) + (bad,))
    with pytest.raises(gb.GraphError):
        gb.build_graph(broken)


# --------------------------------------------------------------------------
# 筛选与聚焦
# --------------------------------------------------------------------------


def test_filter_by_category(graph: nx.MultiDiGraph) -> None:
    view = gb.filter_graph(graph, categories=["village"])
    assert view.number_of_nodes() == 10
    assert all(d["category"] == "village" for _, d in view.nodes(data=True))
    # 两条边都必须在保留集合内
    for u, v, *_ in view.edges(keys=True):
        assert view.nodes[u]["category"] == "village"
        assert view.nodes[v]["category"] == "village"


def test_filter_by_relation_type(graph: nx.MultiDiGraph) -> None:
    view = gb.filter_graph(graph, relation_types=["located_in"])
    assert view.number_of_edges() == 26
    assert {d["type"] for *_, d in view.edges(keys=True, data=True)} == {"located_in"}


def test_filter_empty_iterable_means_no_limit(graph: nx.MultiDiGraph) -> None:
    """显式传入空集合不应被解释为「清空图」。"""
    view = gb.filter_graph(graph, categories=[], relation_types=[])
    assert view.number_of_nodes() == graph.number_of_nodes()
    assert view.number_of_edges() == graph.number_of_edges()


def test_filter_recomputes_degree(graph: nx.MultiDiGraph) -> None:
    view = gb.filter_graph(graph, relation_types=["located_in"])
    for node_id, data in view.nodes(data=True):
        assert data["degree"] == view.degree(node_id)


def test_filter_does_not_mutate_input(graph: nx.MultiDiGraph) -> None:
    before = graph.number_of_nodes(), graph.number_of_edges()
    gb.filter_graph(graph, categories=["village"])
    assert (graph.number_of_nodes(), graph.number_of_edges()) == before


def test_ego_graph_radius_growth(graph: nx.MultiDiGraph) -> None:
    r1 = gb.ego_graph(graph, "huizhou_region", 1)
    r2 = gb.ego_graph(graph, "huizhou_region", 2)
    assert r1.number_of_nodes() < r2.number_of_nodes()
    assert r1.has_node("huizhou_region")
    # 半径 1 的节点集必须包含中心及其全部直接邻居
    assert r1.number_of_nodes() == graph.degree("huizhou_region") + 1


def test_ego_graph_unknown_node(graph: nx.MultiDiGraph) -> None:
    with pytest.raises(gb.NodeNotFoundError):
        gb.ego_graph(graph, "__not_exist__", 1)


def test_sorted_node_options_cover_all(graph: nx.MultiDiGraph) -> None:
    options = gb.sorted_node_options(graph)
    assert len(options) == graph.number_of_nodes()
    assert len({n for n, _ in options}) == graph.number_of_nodes()


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------


def test_stats_counts(graph: nx.MultiDiGraph) -> None:
    stats = ga.graph_stats(graph)
    assert stats.node_count == graph.number_of_nodes()
    assert stats.edge_count == graph.number_of_edges()
    assert stats.isolated_count == 0, "数据中不应存在孤立实体"
    assert stats.self_loop_count == 0
    assert stats.component_count == 1, "全部实体应处于同一连通分量"
    assert stats.largest_component_size == stats.node_count


def test_density_matches_definition(graph: nx.MultiDiGraph) -> None:
    stats = ga.graph_stats(graph)
    undirected = ga.to_undirected_simple(graph)
    n, m = undirected.number_of_nodes(), undirected.number_of_edges()
    assert stats.density == pytest.approx(m / (n * (n - 1) / 2), abs=1e-5)


def test_diameter_and_avg_path_defined(graph: nx.MultiDiGraph) -> None:
    stats = ga.graph_stats(graph)
    assert stats.diameter is not None and stats.diameter >= 2
    assert stats.avg_shortest_path is not None
    assert 1 < stats.avg_shortest_path <= stats.diameter


def test_relation_type_counts_sum_to_edges(graph: nx.MultiDiGraph) -> None:
    stats = ga.graph_stats(graph)
    assert sum(stats.relation_type_counts.values()) == graph.number_of_edges()


def test_category_counts_sum_to_nodes(graph: nx.MultiDiGraph) -> None:
    stats = ga.graph_stats(graph)
    assert sum(stats.category_counts.values()) == graph.number_of_nodes()
    assert len(stats.category_counts) == 11


def test_empty_graph_stats() -> None:
    stats = ga.graph_stats(nx.MultiDiGraph())
    assert stats.node_count == 0
    assert stats.diameter is None
    assert stats.component_count == 0


# --------------------------------------------------------------------------
# 排名
# --------------------------------------------------------------------------


def test_degree_ranking_descending(graph: nx.MultiDiGraph) -> None:
    rows = ga.degree_ranking(graph)
    assert len(rows) == graph.number_of_nodes()
    degrees = [r.degree for r in rows]
    assert degrees == sorted(degrees, reverse=True)
    assert rows[0].node_id == "huizhou_region", "「徽州」应为度数最高的枢纽"


def test_degree_ranking_top_n(graph: nx.MultiDiGraph) -> None:
    assert len(ga.degree_ranking(graph, top_n=5)) == 5


def test_degree_centrality_within_range(graph: nx.MultiDiGraph) -> None:
    for row in ga.degree_ranking(graph):
        assert 0.0 <= row.degree_centrality <= 1.0


def test_betweenness_ranking_descending(graph: nx.MultiDiGraph) -> None:
    rows = ga.betweenness_ranking(graph, top_n=10)
    assert len(rows) == 10
    values = [r.betweenness for r in rows]
    assert values == sorted(values, reverse=True)
    assert rows[0].node_id == "huizhou_region"
    assert rows[0].betweenness > 0


# --------------------------------------------------------------------------
# 连通性
# --------------------------------------------------------------------------


def test_components_partition_all_nodes(graph: nx.MultiDiGraph) -> None:
    comps = ga.connected_components(graph)
    flat: List[str] = [n for c in comps for n in c]
    assert sorted(flat) == sorted(graph.nodes())
    assert len(flat) == len(set(flat)), "分量之间不应重叠"
    assert len(comps) == 1


def test_isolated_nodes_empty(graph: nx.MultiDiGraph) -> None:
    assert ga.isolated_nodes(graph) == []


# --------------------------------------------------------------------------
# 关联路径
# --------------------------------------------------------------------------


def test_shortest_path_known_route(graph: nx.MultiDiGraph) -> None:
    """西递 → 承志堂 应经「徽州民居」中转，长度 2。"""
    path = ga.shortest_path(graph, "xidi", "chengzhitang")
    assert path is not None
    assert path.length == 2
    assert path.nodes[0] == "xidi"
    assert path.nodes[-1] == "chengzhitang"
    assert "huizhou_minju" in path.nodes


def test_shortest_path_edges_are_real_relations(graph: nx.MultiDiGraph) -> None:
    path = ga.shortest_path(graph, "xidi", "chengzhitang")
    assert path is not None
    for edge in path.edges:
        assert graph.has_edge(edge.from_id, edge.to_id) or graph.has_edge(edge.to_id, edge.from_id)
        assert edge.relation_id, "每一段都必须能追溯到具体关系 id"
        assert edge.source_count >= 1


def test_shortest_path_direction_flag_is_honest(graph: nx.MultiDiGraph) -> None:
    """西递→承志堂 的第二段由「承志堂 —属于→ 徽州民居」反向构成，必须标记为 reversed。"""
    path = ga.shortest_path(graph, "xidi", "chengzhitang")
    assert path is not None
    reversed_flags = [e.reversed for e in path.edges]
    assert True in reversed_flags, "反向经过的关系必须被标记，不能伪装成同向"
    for edge, is_rev in zip(path.edges, reversed_flags):
        assert edge.is_forward is (not is_rev)


def test_shortest_path_same_node(graph: nx.MultiDiGraph) -> None:
    path = ga.shortest_path(graph, "xidi", "xidi")
    assert path is not None and path.length == 0


def test_shortest_path_unknown_node(graph: nx.MultiDiGraph) -> None:
    with pytest.raises(gb.NodeNotFoundError):
        ga.shortest_path(graph, "xidi", "__not_exist__")


def test_shortest_path_unreachable_returns_none() -> None:
    """两个互不相连的孤立节点之间应返回 None，而不是抛异常或编造路径。"""
    g = nx.MultiDiGraph()
    g.add_node("a", name="甲", category="village", category_name="古村落",
               category_order=1, summary="", source_count=0, aliases=())
    g.add_node("b", name="乙", category="village", category_name="古村落",
               category_order=1, summary="", source_count=0, aliases=())
    assert ga.shortest_path(g, "a", "b") is None


def test_shortest_path_all_returns_equivalent_routes(graph: nx.MultiDiGraph) -> None:
    routes = ga.shortest_path_all(graph, "xidi", "chengzhitang", limit=5)
    assert routes, "应至少返回一条最短路径"
    lengths = {r.length for r in routes}
    assert lengths == {2}, "返回的必须都是等长最短路"


# --------------------------------------------------------------------------
# 聚类
# --------------------------------------------------------------------------


def test_communities_partition_all_nodes(graph: nx.MultiDiGraph) -> None:
    comms = ga.communities(graph)
    flat = [n for c in comms for n in c.node_ids]
    assert sorted(flat) == sorted(graph.nodes())
    assert len(flat) == len(set(flat))
    assert 2 <= len(comms) <= 8


def test_communities_are_ordered_by_size(graph: nx.MultiDiGraph) -> None:
    sizes = [c.size for c in ga.communities(graph)]
    assert sizes == sorted(sizes, reverse=True)


def test_communities_have_category_breakdown(graph: nx.MultiDiGraph) -> None:
    for comm in ga.communities(graph):
        assert comm.category_names, "每个聚类都应能列出涉及的文化分类"
        assert 0.0 <= comm.cohesion <= 1.0


def test_communities_of_membership(graph: nx.MultiDiGraph) -> None:
    comm = ga.communities_of(graph, "hongcun")
    assert comm is not None and "hongcun" in comm.node_ids
    assert "xidi" in comm.node_ids, "宏村与西递应落入同一聚类"


def test_communities_of_unknown_node(graph: nx.MultiDiGraph) -> None:
    with pytest.raises(gb.NodeNotFoundError):
        ga.communities_of(graph, "__not_exist__")


# --------------------------------------------------------------------------
# 可视化：离线自洽
# --------------------------------------------------------------------------


def test_network_html_has_no_external_resources(graph: nx.MultiDiGraph) -> None:
    """核心约束：断网也必须能渲染，因此不允许任何外部 script/link 引用。"""
    html = gv.build_network_html(graph, height=600)
    assert not EXTERNAL_REF.search(html), "图谱 HTML 仍引用外部资源"
    assert "cdn.jsdelivr.net" not in html
    assert "cdnjs.cloudflare.com" not in html


def test_network_html_has_no_external_css_urls(graph: nx.MultiDiGraph) -> None:
    """内联 CSS 中不能残留外部 url()（字体、图标等），否则断网仍会缺样式。"""
    html = gv.build_network_html(graph, height=600)
    assert not re.search(r"url\(\s*[\"']?(?:https?:)?//", html, re.I)
    assert "@import" not in html
    assert "@font-face" not in html


def test_network_html_is_not_mistaken_for_a_url(graph: nx.MultiDiGraph) -> None:
    """``st.iframe`` 会先判断入参像不像 URL；只有不像 URL 时才走 srcdoc 内嵌。

    这条断言把该假设钉死：若某天 HTML 里出现了会让 Streamlit 误判成 URL 的开头，
    页面会变成加载一个不存在的地址，这里会立刻失败。
    """
    from streamlit import url_util

    html = gv.build_network_html(graph, height=600)
    assert not url_util.is_url(html, allowed_schemas=("http", "https", "data"))


def test_tighten_layout_removes_empty_headings() -> None:
    raw = (
        "<html><head></head><body>"
        "<center><h1></h1></center>"
        "<div id='mynetwork'></div>"
        "<center>\n  <h1></h1>\n</center>"
        "</body></html>"
    )
    cleaned = gv.tighten_layout(raw)
    assert "<h1>" not in cleaned
    assert "</h1>" not in cleaned
    assert "id='mynetwork'" in cleaned
    assert "margin:0" in cleaned


def test_tighten_layout_keeps_real_heading() -> None:
    raw = "<html><head></head><body><center><h1>徽州知识图谱</h1></center></body></html>"
    assert "徽州知识图谱" in gv.tighten_layout(raw)


def test_network_html_inlines_vis_library(graph: nx.MultiDiGraph) -> None:
    html = gv.build_network_html(graph, height=600)
    assert len(html) > 400_000, "vis-network 库应已内联进 HTML"
    assert "vis.DataSet" in html or "DataSet" in html


def test_network_html_contains_all_nodes(graph: nx.MultiDiGraph) -> None:
    html = gv.build_network_html(graph, height=600)
    for node_id in ("hongcun", "xidi", "huizhou_region", "jianjiang"):
        assert f'"{node_id}"' in html


def test_network_html_escapes_labels(graph: nx.MultiDiGraph) -> None:
    """含特殊字符的名称不能破坏 HTML/JS 结构。"""
    g = nx.MultiDiGraph()
    g.add_node("x", name='"><script>alert(1)</script>', category="village",
               category_name="古村落", category_order=1, summary="<b>粗体</b>",
               source_count=0, aliases=(), degree=0, in_degree=0, out_degree=0)
    html = gv.build_network_html(g, height=300)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html or "\\u003cscript\\u003e" in html


def test_network_html_payload_contains_exact_data(graph: nx.MultiDiGraph) -> None:
    """把渲染产物里的 JS 数据载荷解析出来，逐项核对。

    这比「HTML 里出现了某个字符串」强得多：它证明交给 vis-network 的
    节点与边数量、属性与源数据完全一致，没有丢关系也没有多造节点。
    """
    html = gv.build_network_html(graph, height=600)
    nodes = _extract_payload(html, "nodes")
    edges = _extract_payload(html, "edges")

    assert len(nodes) == graph.number_of_nodes() == 90
    assert len(edges) == graph.number_of_edges() == 150

    node_ids = {n["id"] for n in nodes}
    assert node_ids == set(graph.nodes())

    for node in nodes:
        assert node["label"], "节点必须有标签"
        assert node["color"]["background"].startswith("#")
        assert "degree" in node

    for edge in edges:
        assert edge["from"] in node_ids and edge["to"] in node_ids
        assert edge["id"], "每条关系必须带可追溯的 id（即关系 id）"
        assert edge.get("title"), "每条关系都应有悬停说明"

    edge_ids = {e["id"] for e in edges}
    assert len(edge_ids) == len(edges), "关系 id 不应重复"
    assert edge_ids == {k for *_, k in graph.edges(keys=True)}


def _extract_payload(html: str, kind: str) -> list:
    """从 vis-network 初始化代码中取出 ``var <kind> = new vis.DataSet([...]);`` 的数组。"""
    marker = f"{kind} = new vis.DataSet("
    start = html.find(marker)
    assert start >= 0, f"渲染产物中未找到 {kind} 数据载荷"
    start += len(marker)
    end = html.find("]);", start)
    assert end > start, f"{kind} 数据载荷结构异常"
    return json.loads(html[start:end + 1])


def test_network_html_focus_highlight(graph: nx.MultiDiGraph) -> None:
    html = gv.build_network_html(graph, focus="hongcun", height=600)
    assert "#B23A2F" in html


def test_network_html_empty_graph_raises() -> None:
    with pytest.raises(gb.EmptyGraphError):
        gv.build_network_html(nx.MultiDiGraph())


def test_strip_external_resources_removes_tags() -> None:
    raw = (
        '<html><head>'
        '<link\n  href="https://cdn.jsdelivr.net/npm/bootstrap@5/x.css"\n  rel="stylesheet"\n/>'
        '<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/vis/vis.min.js"\n  defer\n></script>'
        '<script src="https://example.com/self-closing.js" defer />'
        '<script>var a = 1 < 2;</script>'
        "</head><body>ok</body></html>"
    )
    cleaned = gv.strip_external_resources(raw)
    assert "cdn.jsdelivr.net" not in cleaned
    assert "cdnjs.cloudflare.com" not in cleaned
    assert "self-closing.js" not in cleaned
    assert "defer" not in cleaned or "<script>" in cleaned
    assert "var a = 1 < 2;" in cleaned, "内联脚本不能被误删"


def test_strip_external_resources_detects_leftover() -> None:
    """清洗不彻底必须抛错，而不是交付一个断网就白屏的页面。

    这里用协议相对写法（``//cdn...``）——正则不主动清洗它，
    安全网必须把它抓出来并阻止交付。
    """
    sneaky = '<link rel="stylesheet" href="//cdn.example.com/a.css"/>'
    with pytest.raises(gv.GraphError):
        gv.strip_external_resources(sneaky)


def test_strip_external_resources_keeps_local_refs() -> None:
    """本地相对路径引用不应被误删，也不应触发安全网。"""
    raw = '<script src="lib/bindings/utils.js"></script><link href="lib/a.css" rel="x">'
    assert gv.strip_external_resources(raw) == raw


def test_build_path_html_only_keeps_route(graph: nx.MultiDiGraph) -> None:
    path = ga.shortest_path(graph, "xidi", "chengzhitang")
    assert path is not None
    html = gv.build_path_html(graph, list(path.nodes), height=360)
    assert "xidi" in html and "chengzhitang" in html
    assert '"hongcun"' not in html, "路径图不应包含线路之外的节点"


# --------------------------------------------------------------------------
# 展示辅助
# --------------------------------------------------------------------------


def test_truncate_label() -> None:
    assert gv.truncate_label("宏村") == "宏村"
    long_name = "这是一个非常长的实体名称需要截断"
    assert len(gv.truncate_label(long_name, 8)) == 8
    assert gv.truncate_label(long_name, 8).endswith("…")


def test_node_size_monotonic() -> None:
    assert gv.node_size(40, 40) > gv.node_size(10, 40) > gv.node_size(1, 40)
    assert gv.node_size(5, 0) == 14.0


def test_graph_legend_covers_every_category(graph: nx.MultiDiGraph) -> None:
    html = gv.graph_legend_html(graph)
    for _, data in graph.nodes(data=True):
        assert data["category_name"] in html


def test_path_chain_html_shows_direction(graph: nx.MultiDiGraph) -> None:
    path = ga.shortest_path(graph, "xidi", "chengzhitang")
    assert path is not None
    html = gv.path_chain_html(graph, path)
    assert "hz-path__node" in html
    assert "hz-path__rel" in html
    assert "←" in html and "→" in html, "链条必须同时体现两个方向"


def test_category_palette_covers_all_categories(graph: nx.MultiDiGraph) -> None:
    ids = {d["category"] for _, d in graph.nodes(data=True)}
    palette = gv.category_palette(ids)
    assert set(palette) == ids
    assert all(v.startswith("#") and len(v) == 7 for v in palette.values())
    # 每个分类都应有专属配色，不能全部落到兜底色
    assert len(set(palette.values())) == len(ids)


def test_network_options_is_json_serializable() -> None:
    opts = gv.network_options(physics=True)
    json.dumps(opts)
