"""图谱分析：连通性、度数中心性、介数中心性、最短关联路径与文化聚类。

设计约定：
- 关系是有向的（``MultiDiGraph``），但**连通性、路径、聚类**在无向视图上进行，
  因为「二者是否相关」不因方向而改变；方向信息在展示层单独给出。
- 所有排名结果在数据不变时**确定**（排序键包含名称作为兜底），便于测试断言。
- 本模块不依赖 Streamlit 与 PyVis。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import networkx as nx

from src.graph.builder import GraphError, NodeNotFoundError

# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphStats:
    """图谱整体统计。"""

    node_count: int
    edge_count: int
    density: float
    avg_degree: float
    max_degree: int
    isolated_count: int
    component_count: int
    largest_component_size: int
    largest_component_ratio: float
    diameter: Optional[int]
    avg_shortest_path: Optional[float]
    cycle_count: int
    self_loop_count: int
    relation_type_counts: Mapping[str, int]
    category_counts: Mapping[str, int]

    @property
    def strongly_connected(self) -> bool:
        """弱连通即视为整体连通（关系方向不代表可达方向）。"""
        return self.component_count == 1


@dataclass(frozen=True)
class NodeScore:
    """节点排名条目。"""

    node_id: str
    name: str
    category_name: str
    degree: int
    in_degree: int
    out_degree: int
    degree_centrality: float
    betweenness: float = 0.0


@dataclass(frozen=True)
class PathEdge:
    """关联路径中的一段。

    ``from_id → to_id`` 始终是**路径行进方向**；``reversed`` 表示底层关系的真实
    方向与之相反（例如路径「西递 → 宏村」实际由「宏村 —位于→ 徽州」的反向构成）。
    展示层据此区分 ``A —标签→ B`` 与 ``A ←标签— B``，不隐瞒方向。
    """

    from_id: str
    from_name: str
    to_id: str
    to_name: str
    relation_id: str
    type: str
    type_name: str
    label: str
    description: str
    source_count: int
    reversed: bool = False

    @property
    def is_forward(self) -> bool:
        """关系的真实方向是否与路径行进方向一致。"""
        return not self.reversed


@dataclass(frozen=True)
class PathResult:
    """关联路径查询结果。"""

    nodes: Tuple[str, ...]
    edges: Tuple[PathEdge, ...]

    @property
    def length(self) -> int:
        """路径长度（中间经过的关系条数）。"""
        return len(self.edges)


@dataclass(frozen=True)
class Community:
    """一个文化聚类。"""

    index: int
    node_ids: Tuple[str, ...]
    category_names: Tuple[str, ...]
    cohesion: float

    @property
    def size(self) -> int:
        return len(self.node_ids)


# --------------------------------------------------------------------------
# 视图转换
# --------------------------------------------------------------------------


def to_undirected_simple(graph: nx.MultiDiGraph) -> nx.Graph:
    """转成无向简单图（平行边折叠，自环保留）。

    用于连通分量、最短路、聚类等只关心「是否相连」的算法。
    """
    simple = nx.Graph()
    simple.add_nodes_from((n, dict(d)) for n, d in graph.nodes(data=True))
    for u, v, _k, data in graph.edges(keys=True, data=True):
        if simple.has_edge(u, v):
            # 折叠时保留类型集合，便于需要时追溯
            types = simple[u][v].setdefault("types", [])
            if data.get("type") not in types:
                types.append(data.get("type"))
            simple[u][v]["count"] = simple[u][v].get("count", 1) + 1
        else:
            simple.add_edge(u, v, count=1, types=[data.get("type")])
    return simple


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------


def graph_stats(graph: nx.MultiDiGraph) -> GraphStats:
    """计算图谱整体统计。

    直径与平均最短路径在**最大连通分量**上计算（不连通图在全图上无定义），
    因此当存在多个连通分量时，这两个值只描述最大的那块。
    密度按无向简单图（平行边折叠）计算，避免同一对实体的多类型关系把密度算高。
    """
    n = graph.number_of_nodes()
    m = graph.number_of_edges()

    type_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    for *_, data in graph.edges(keys=True, data=True):
        key = data.get("type_name") or data.get("type", "")
        type_counts[key] = type_counts.get(key, 0) + 1
    for _, data in graph.nodes(data=True):
        key = data.get("category_name") or data.get("category", "")
        category_counts[key] = category_counts.get(key, 0) + 1

    degrees = [d for _, d in graph.degree()]
    isolated = sum(1 for d in degrees if d == 0)

    if n == 0:
        return GraphStats(
            node_count=0, edge_count=0, density=0.0, avg_degree=0.0, max_degree=0,
            isolated_count=0, component_count=0, largest_component_size=0,
            largest_component_ratio=0.0, diameter=None, avg_shortest_path=None,
            cycle_count=0, self_loop_count=0,
            relation_type_counts={}, category_counts={},
        )

    undirected = to_undirected_simple(graph)
    components = [sorted(c) for c in nx.connected_components(undirected)]
    components.sort(key=lambda c: (-len(c), c[0]))
    largest = components[0] if components else []

    diameter: Optional[int] = None
    avg_path: Optional[float] = None
    if len(largest) > 1:
        sub = undirected.subgraph(largest)
        try:
            diameter = int(nx.diameter(sub))
            avg_path = round(float(nx.average_shortest_path_length(sub)), 3)
        except nx.NetworkXError:  # 理论上不会发生（已保证连通且 >1 节点）
            diameter, avg_path = None, None
    elif len(largest) == 1:
        diameter, avg_path = 0, 0.0

    return GraphStats(
        node_count=n,
        edge_count=m,
        density=round(nx.density(undirected), 5),
        avg_degree=round(sum(degrees) / n, 3),
        max_degree=max(degrees),
        isolated_count=isolated,
        component_count=len(components),
        largest_component_size=len(largest),
        largest_component_ratio=round(len(largest) / n, 4),
        diameter=diameter,
        avg_shortest_path=avg_path,
        cycle_count=max(m - n + len(components), 0),
        self_loop_count=int(nx.number_of_selfloops(graph)),
        relation_type_counts=dict(sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        category_counts=dict(sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    )


# --------------------------------------------------------------------------
# 排名
# --------------------------------------------------------------------------


def _score_row(node_id: str, graph: nx.MultiDiGraph, betweenness: float = 0.0) -> NodeScore:
    data = graph.nodes[node_id]
    centrality = graph.degree(node_id) / max(graph.number_of_nodes() - 1, 1)
    return NodeScore(
        node_id=node_id,
        name=data.get("name", node_id),
        category_name=data.get("category_name", ""),
        degree=graph.degree(node_id),
        in_degree=graph.in_degree(node_id),
        out_degree=graph.out_degree(node_id),
        degree_centrality=round(centrality, 4),
        betweenness=round(betweenness, 4),
    )


def degree_ranking(graph: nx.MultiDiGraph, top_n: Optional[int] = None) -> List[NodeScore]:
    """按度数排名（关系条数最多的实体，即图谱中的核心枢纽）。"""
    rows = sorted(
        graph.nodes(),
        key=lambda n: (-graph.degree(n), -graph.in_degree(n), graph.nodes[n].get("name", n)),
    )
    return [_score_row(n, graph) for n in (rows[:top_n] if top_n else rows)]


def betweenness_ranking(graph: nx.MultiDiGraph, top_n: Optional[int] = None) -> List[NodeScore]:
    """按介数中心性排名（在无向视图上计算：担当「文化桥梁」的实体）。

    介数中心性衡量一个节点出现在其他节点最短路径上的频率，
    与度数排名互补：度数高说明「关系多」，介数高说明「跨领域连接作用强」。
    """
    undirected = to_undirected_simple(graph)
    if undirected.number_of_nodes() == 0:
        return []
    scores = nx.betweenness_centrality(undirected, normalized=True)
    rows = sorted(
        graph.nodes(),
        key=lambda n: (-scores.get(n, 0.0), -graph.degree(n), graph.nodes[n].get("name", n)),
    )
    if top_n:
        rows = rows[:top_n]
    return [_score_row(n, graph, scores.get(n, 0.0)) for n in rows]


# --------------------------------------------------------------------------
# 连通性
# --------------------------------------------------------------------------


def connected_components(graph: nx.MultiDiGraph) -> List[List[str]]:
    """连通分量（无向意义），按规模降序，块内按分类顺序与名称排序。"""
    undirected = to_undirected_simple(graph)
    comps = [list(c) for c in nx.connected_components(undirected)]
    for comp in comps:
        comp.sort(key=lambda n: (
            graph.nodes[n].get("category_order", 99),
            graph.nodes[n].get("name", n),
        ))
    comps.sort(key=lambda c: (-len(c), c[0] if c else ""))
    return comps


def isolated_nodes(graph: nx.MultiDiGraph) -> List[str]:
    """没有任何关系的孤立节点 id。"""
    return sorted(
        (n for n in graph.nodes() if graph.degree(n) == 0),
        key=lambda n: graph.nodes[n].get("name", n),
    )


# --------------------------------------------------------------------------
# 关联路径
# --------------------------------------------------------------------------


def _path_edge(graph: nx.MultiDiGraph, u: str, v: str) -> PathEdge:
    """取路径行进方向 ``u → v`` 上的展示用关系。

    同一对实体间若有多条关系，取类型名排序最小的一条（结果确定）。
    若只有 ``v → u`` 的方向，则标记 ``reversed=True``。
    """
    forward = graph.has_edge(u, v)
    holder = graph[u][v] if forward else graph[v][u]
    data = min(
        (holder[k] for k in holder),
        key=lambda d: (d.get("type", ""), str(d.get("rel_id", ""))),
    )
    return PathEdge(
        from_id=u,
        from_name=graph.nodes[u].get("name", u),
        to_id=v,
        to_name=graph.nodes[v].get("name", v),
        relation_id=data.get("rel_id", ""),
        type=data.get("type", ""),
        type_name=data.get("type_name", data.get("type", "")),
        label=data.get("label", ""),
        description=data.get("description", ""),
        source_count=data.get("source_count", 0),
        reversed=not forward,
    )


def shortest_path(graph: nx.MultiDiGraph, source: str, target: str) -> Optional[PathResult]:
    """最短关联路径（无向意义，忽略关系方向）。

    Returns:
        :class:`PathResult`；两点之间不可达时返回 ``None``。
        起点与终点相同返回长度为 0 的结果。

    Raises:
        NodeNotFoundError: 起点或终点不存在。
    """
    for node in (source, target):
        if not graph.has_node(node):
            raise NodeNotFoundError(node)

    if source == target:
        return PathResult(nodes=(source,), edges=())

    undirected = to_undirected_simple(graph)
    try:
        nodes: Sequence[str] = nx.shortest_path(undirected, source, target)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None

    edges = tuple(_path_edge(graph, u, v) for u, v in zip(nodes, nodes[1:]))
    return PathResult(nodes=tuple(nodes), edges=edges)


def shortest_path_all(graph: nx.MultiDiGraph, source: str, target: str, limit: int = 3) -> List[PathResult]:
    """最短路径的全部等价解（最多 ``limit`` 条），用于展示「不止一条关联线路」。"""
    for node in (source, target):
        if not graph.has_node(node):
            raise NodeNotFoundError(node)
    if source == target:
        return [PathResult(nodes=(source,), edges=())]

    undirected = to_undirected_simple(graph)
    results: List[PathResult] = []
    try:
        for nodes in nx.all_shortest_paths(undirected, source, target):
            edges = tuple(_path_edge(graph, u, v) for u, v in zip(nodes, nodes[1:]))
            results.append(PathResult(nodes=tuple(nodes), edges=edges))
            if len(results) >= limit:
                break
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    return results


# --------------------------------------------------------------------------
# 文化聚类
# --------------------------------------------------------------------------


def communities(graph: nx.MultiDiGraph, max_groups: int = 8) -> List[Community]:
    """基于模块度优化的社区发现（无向视图，贪心模块度算法）。

    结果用于回答「徽州文化在结构上聚成哪几块」。
    该算法在给定图上结果确定；仅用于探索性观察，不作为定论。

    Returns:
        按规模降序的 :class:`Community` 列表。
    """
    if graph.number_of_nodes() == 0:
        return []
    undirected = to_undirected_simple(graph)
    if undirected.number_of_edges() == 0:
        return []

    groups = nx.community.greedy_modularity_communities(undirected, cutoff=max_groups)
    result: List[Community] = []
    for idx, group in enumerate(groups):
        node_ids = tuple(sorted(
            group,
            key=lambda n: (graph.nodes[n].get("category_order", 99), graph.nodes[n].get("name", n)),
        ))
        cats: List[str] = []
        for n in node_ids:
            name = graph.nodes[n].get("category_name", "")
            if name and name not in cats:
                cats.append(name)
        cohesion = 0.0
        for edge in undirected.subgraph(node_ids).edges():
            cohesion += 1
        possible = len(node_ids) * (len(node_ids) - 1) / 2
        result.append(
            Community(
                index=idx,
                node_ids=node_ids,
                category_names=tuple(cats),
                cohesion=round(cohesion / possible, 4) if possible else 0.0,
            )
        )

    result.sort(key=lambda c: (-c.size, c.node_ids[0] if c.node_ids else ""))
    return [Community(i, c.node_ids, c.category_names, c.cohesion) for i, c in enumerate(result)]


def communities_of(graph: nx.MultiDiGraph, node_id: str) -> Optional[Community]:
    """某个实体所属的聚类。"""
    if not graph.has_node(node_id):
        raise NodeNotFoundError(node_id)
    for comm in communities(graph):
        if node_id in comm.node_ids:
            return comm
    return None


# --------------------------------------------------------------------------
# 便捷汇总
# --------------------------------------------------------------------------


def summarize(graph: nx.MultiDiGraph) -> Dict[str, object]:
    """图谱概览：统计 + 核心枢纽 + 聚类数，供界面与报告复用。"""
    if graph.number_of_nodes() == 0:
        raise GraphError("空图无法汇总。")
    stats = graph_stats(graph)
    return {
        "stats": stats,
        "top_degree": degree_ranking(graph, top_n=5),
        "top_betweenness": betweenness_ranking(graph, top_n=5),
        "community_count": len(communities(graph)),
    }


__all__ = [
    "GraphStats",
    "NodeScore",
    "PathEdge",
    "PathResult",
    "Community",
    "to_undirected_simple",
    "graph_stats",
    "degree_ranking",
    "betweenness_ranking",
    "connected_components",
    "isolated_nodes",
    "shortest_path",
    "shortest_path_all",
    "communities",
    "communities_of",
    "summarize",
]
