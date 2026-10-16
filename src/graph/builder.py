"""知识图谱建模：把文化实体与关系转换为 NetworkX 多重有向图。

为什么用 ``MultiDiGraph`` 而不是 ``DiGraph``：
同一对实体之间可能存在**多种关系类型**（例如「渐江 → 新安画派」同时存在
``founder_of`` 与 ``representative_of``）。``DiGraph`` 会把同向平行边合并，
导致关系条数从 150 悄悄变成 149——这是数据失真，不可接受。

本模块只负责「建模」与「筛选」，不做分析、不做可视化，也不依赖 Streamlit。
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

import networkx as nx

from src.data.loader import Dataset, load_dataset

# --------------------------------------------------------------------------
# 异常
# --------------------------------------------------------------------------


class GraphError(Exception):
    """图谱层基础异常。"""


class EmptyGraphError(GraphError):
    """图为空（没有任何节点）。"""


class NodeNotFoundError(GraphError):
    """指定的实体节点不存在。"""

    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(f"图谱中不存在实体节点：{node_id}")


# --------------------------------------------------------------------------
# 构建
# --------------------------------------------------------------------------


def build_graph(dataset: Optional[Dataset] = None) -> nx.MultiDiGraph:
    """由数据集构建多重有向图。

    节点属性：
        ``name`` 名称、``category`` 分类 id、``category_name`` 分类名称、
        ``category_order`` 分类排序、``summary`` 摘要、``aliases`` 别名、
        ``source_count`` 来源条数、``entity_id`` 实体 id。

    边属性：
        ``key`` 关系 id、``type`` 关系类型 id、``type_name`` 关系类型名称、
        ``inverse_name`` 反向名称、``label`` 展示标签、``description`` 关系说明、
        ``source_ids`` 来源 id、``source_count`` 来源条数。

    Args:
        dataset: 数据集，默认从 ``data/*.json`` 加载（加载时会做完整校验）。

    Raises:
        GraphError: 关系两端引用了不存在的实体（正常数据不会出现，属防御性检查）。
    """
    ds = dataset if dataset is not None else load_dataset()
    graph = nx.MultiDiGraph()
    graph.graph["version"] = ds.version

    category_names: Dict[str, str] = {c.id: c.name for c in ds.categories}
    category_orders: Dict[str, int] = {c.id: c.order for c in ds.categories}

    for entity in ds.entities:
        graph.add_node(
            entity.id,
            entity_id=entity.id,
            name=entity.name,
            category=entity.category,
            category_name=category_names.get(entity.category, entity.category),
            category_order=category_orders.get(entity.category, 0),
            summary=entity.summary,
            aliases=tuple(entity.aliases),
            image=entity.image,
            source_count=len(entity.source_ids),
        )

    rtypes = ds.relation_type_map()

    missing: List[str] = []
    for rel in ds.relations:
        if rel.source not in graph or rel.target not in graph:
            missing.append(rel.id)
            continue
        rtype = rtypes.get(rel.type)
        graph.add_edge(
            rel.source,
            rel.target,
            key=rel.id,
            rel_id=rel.id,
            type=rel.type,
            type_name=rtype.name if rtype else rel.type,
            inverse_name=rtype.inverse_name if rtype else "",
            label=rel.label or rel.type,
            description=rel.description,
            source_ids=tuple(rel.source_ids),
            source_count=len(rel.source_ids),
        )

    if missing:
        raise GraphError(
            f"以下关系引用了不存在的实体，无法建图：{', '.join(missing[:10])}"
            + ("（仅显示前 10 条）" if len(missing) > 10 else "")
        )

    return with_degree(graph)


# --------------------------------------------------------------------------
# 派生指标
# --------------------------------------------------------------------------


def with_degree(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """返回副本，并为每个节点补充 ``degree`` / ``in_degree`` / ``out_degree``。

    度数按「关系条数」统计（平行边各计一次），与数据中的关系总条数一致。
    节点尺寸、排名都基于该字段，因此筛选视图下也必须重算。
    """
    result = graph.copy()
    for node, attrs in result.nodes(data=True):
        attrs["degree"] = result.degree(node)
        attrs["in_degree"] = result.in_degree(node)
        attrs["out_degree"] = result.out_degree(node)
    return result


def max_degree(graph: nx.MultiDiGraph) -> int:
    """图中最大度数（空图为 0）。"""
    return max((d for _, d in graph.degree()), default=0)


# --------------------------------------------------------------------------
# 视图：筛选与聚焦
# --------------------------------------------------------------------------


def filter_graph(
    graph: nx.MultiDiGraph,
    categories: Optional[Iterable[str]] = None,
    relation_types: Optional[Iterable[str]] = None,
    node_ids: Optional[Iterable[str]] = None,
) -> nx.MultiDiGraph:
    """按分类、关系类型、节点集合筛选子图。

    参数为空或 ``None`` 表示该维度不做限制。筛选后只保留两端都在结果集中的边，
    并重算节点度数。

    Returns:
        新的 ``MultiDiGraph``（不修改入参）。
    """
    keep: Optional[Set[str]] = None

    if node_ids is not None:
        keep = {n for n in node_ids if graph.has_node(n)}

    cat_set: Optional[FrozenSet[str]] = None
    if categories is not None:
        cat_set = frozenset(categories) or None  # 显式空集合 = 不限制
        if cat_set:
            matched = {n for n, d in graph.nodes(data=True) if d.get("category") in cat_set}
            keep = matched if keep is None else (keep & matched)

    type_set: Optional[FrozenSet[str]] = None
    if relation_types is not None:
        type_set = frozenset(relation_types) or None  # 显式空集合 = 不限制

    if keep is None:
        keep = set(graph.nodes())

    if type_set is None:
        view = graph.subgraph(keep).copy()
    else:
        sub = nx.MultiDiGraph()
        sub.graph.update(graph.graph)
        for node in keep:
            sub.add_node(node, **dict(graph.nodes[node]))
        for u, v, k, data in graph.edges(keys=True, data=True):
            if u in keep and v in keep and data.get("type") in type_set:
                sub.add_edge(u, v, key=k, **dict(data))
        view = sub

    return with_degree(view)


def ego_graph(graph: nx.MultiDiGraph, node_id: str, radius: int = 1) -> nx.MultiDiGraph:
    """以某实体为中心、指定半径内的关联子图（忽略关系方向，视为关联网络）。

    Raises:
        NodeNotFoundError: 节点不存在。
    """
    if not graph.has_node(node_id):
        raise NodeNotFoundError(node_id)
    radius = max(0, int(radius))
    undirected = nx.Graph(graph)  # 关联强度不区分方向，便于「谁与它相关」
    nodes = nx.single_source_shortest_path_length(undirected, node_id, cutoff=radius).keys()
    return with_degree(graph.subgraph(set(nodes)).copy())


def subgraph_for_nodes(graph: nx.MultiDiGraph, node_ids: Iterable[str]) -> nx.MultiDiGraph:
    """由节点列表取诱导子图（忽略不存在的节点）。"""
    return with_degree(graph.subgraph([n for n in node_ids if graph.has_node(n)]).copy())


# --------------------------------------------------------------------------
# 元信息
# --------------------------------------------------------------------------


def node_option_label(node_id: str, graph: nx.MultiDiGraph) -> str:
    """下拉框展示用标签：``名称 · 分类``。"""
    data = graph.nodes[node_id]
    return f"{data.get('name', node_id)} · {data.get('category_name', '')}"


def sorted_node_options(graph: nx.MultiDiGraph) -> List[Tuple[str, str]]:
    """按分类顺序、名称排序的 ``(node_id, 标签)`` 列表。"""
    items = [
        (n, d.get("name", n), d.get("category_order", 0), d.get("category_name", ""))
        for n, d in graph.nodes(data=True)
    ]
    items.sort(key=lambda t: (t[2], t[3], t[1]))
    return [(n, f"{name} · {cat}") for n, name, _, cat in items]


__all__ = [
    "GraphError",
    "EmptyGraphError",
    "NodeNotFoundError",
    "build_graph",
    "with_degree",
    "max_degree",
    "filter_graph",
    "ego_graph",
    "subgraph_for_nodes",
    "node_option_label",
    "sorted_node_options",
]
