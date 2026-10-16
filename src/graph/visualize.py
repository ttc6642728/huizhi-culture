"""图谱可视化：用 PyVis 生成**完全离线自洽**的交互式图谱 HTML。

为什么必须离线自洽：
PyVis 默认模板除了 ``vis-network`` 之外，还会**无条件**从 jsDelivr 引入
Bootstrap 5 的 CSS 与 JS（``templates/template.html`` 第 41–51 行，不受
``cdn_resources`` 参数控制）。断网或内网环境下这些请求会失败，页面样式与
交互都会退化。因此本模块在生成后统一做一次资源清洗：

1. ``cdn_resources="in_line"`` 让 ``vis-network`` 的 CSS/JS 内联进 HTML；
2. :func:`strip_external_resources` 移除模板里遗留的外部 ``<script src>`` /
   ``<link href>``；
3. 清洗后立即**校验**是否仍存在外部资源引用，若存在则抛错——宁可报错，
   也不交付一个「看起来能用、断网就白屏」的页面。

配色遵循项目设计系统：克制、低饱和，用徽州黑白灰打底、朱砂作点缀。
"""

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import networkx as nx
from pyvis.network import Network

from src.graph.analysis import PathResult
from src.graph.builder import EmptyGraphError, GraphError, max_degree
from src.ui.theme import CATEGORY_COLORS, COLORS, FALLBACK_COLOR, FONTS

# --------------------------------------------------------------------------
# 配色
# --------------------------------------------------------------------------

#: 说明：分类配色统一定义在设计系统 ``src.ui.theme.CATEGORY_COLORS``，
#: 图谱节点、图例、实体卡片与详情页共用同一套颜色，保证同一实体在各处颜色一致。
#: 此处直接复用，不再单独维护一份，避免两处色值走偏。

LABEL_MAX = 12


def category_palette(category_ids: Iterable[str]) -> Dict[str, str]:
    """分类 id → 十六进制颜色，供界面图例使用。"""
    return {
        cid: CATEGORY_COLORS.get(cid, FALLBACK_COLOR)["bg"]
        for cid in category_ids
    }


# --------------------------------------------------------------------------
# 资源清洗
# --------------------------------------------------------------------------

_EXT_SCRIPT = re.compile(
    r"<script\b[^>]*\bsrc\s*=\s*[\"']https?://[^\"']+[\"'][^>]*>(?:\s*</script>)?", re.I | re.S
)
_EXT_LINK = re.compile(
    r"<link\b[^>]*\bhref\s*=\s*[\"']https?://[^\"']+[\"'][^>]*?/?>", re.I | re.S
)
#: 安全网：任何仍带外部 src/href 的 script/link（含 ``//cdn...`` 协议相对写法）
_ANY_EXT_REF = re.compile(
    r"<(?:script|link)\b[^>]*\b(?:src|href)\s*=\s*[\"'](?:https?:)?//", re.I
)


def strip_external_resources(html: str) -> str:
    """移除 HTML 中的外部 ``<script src>`` 与 ``<link href>`` 引用。

    Raises:
        GraphError: 清洗后仍检测到外部资源引用（说明模板结构发生变化，
            需要人工介入，不能静默交付）。
    """
    cleaned = _EXT_SCRIPT.sub("", html)
    cleaned = _EXT_LINK.sub("", cleaned)
    leftover = _ANY_EXT_REF.findall(cleaned)
    if leftover:
        raise GraphError(
            f"图谱 HTML 仍包含 {len(leftover)} 处外部资源引用，离线渲染无法保证。"
            "这通常意味着 PyVis 模板结构发生变化，请检查 pyvis 版本。"
        )
    return cleaned


#: PyVis 模板会渲染两处空标题（``<center><h1></h1></center>``），各占约 80px 高度
_EMPTY_HEADING_BLOCK = re.compile(r"<center>\s*<h1>\s*</h1>\s*</center>", re.I)
_EMPTY_H1 = re.compile(r"<h1>\s*</h1>", re.I)

#: 去掉 iframe 内 body 的默认外边距，使画布与容器严丝合缝
_FLUSH_STYLE = (
    "<style>html,body{margin:0;padding:0;border:0;background:%s;}"
    "#mynetwork{border:0;}</style>" % COLORS["bg"]
)


def tighten_layout(html: str) -> str:
    """压缩 PyVis 产物的空白：去掉空标题块、移除 body 默认边距。

    PyVis 模板在 ``heading`` 为空时仍会渲染两个空的 ``<h1>``，
    合计约 160px 的无效高度，会把画布往下推、并让 iframe 出现滚动条。
    """
    cleaned = _EMPTY_HEADING_BLOCK.sub("", html)
    cleaned = _EMPTY_H1.sub("", cleaned)
    if "</head>" in cleaned:
        cleaned = cleaned.replace("</head>", _FLUSH_STYLE + "</head>", 1)
    else:  # 模板结构变化时的兜底：插到最前面
        cleaned = _FLUSH_STYLE + cleaned
    return cleaned


# --------------------------------------------------------------------------
# 标题与提示
# --------------------------------------------------------------------------


def _esc(text: object) -> str:
    return _html.escape(str(text if text is not None else ""), quote=True)


def truncate_label(name: str, limit: int = LABEL_MAX) -> str:
    """过长名称截断为 ``前 N 字…``，避免中文标签互相压盖。"""
    name = (name or "").strip()
    return name if len(name) <= limit else name[: limit - 1] + "…"


def _edge_tooltip(data: Mapping[str, object]) -> str:
    lines = [
        f'<div style="font-weight:600;font-size:12px;">{_esc(data.get("type_name", ""))}'
        f'（{_esc(data.get("type", ""))}）</div>'
    ]
    if data.get("description"):
        lines.append(f'<div style="font-size:11px;max-width:260px;">{_esc(data["description"])}</div>')
    lines.append(
        f'<div style="color:#B23A2F;font-size:11px;">来源 {_esc(data.get("source_count", 0))} 项</div>'
    )
    return "".join(lines)


# --------------------------------------------------------------------------
# 选项
# --------------------------------------------------------------------------


def network_options(
    *,
    physics: bool = True,
    highlight_neighbors: bool = True,
) -> Dict[str, object]:
    """vis-network 配置。

    ``layout.randomSeed`` 固定为 42：同一张图每次打开的初始布局一致，
    便于截图对比与问题复现。
    """
    return {
        "nodes": {
            "shape": "dot",
            "borderWidth": 1.2,
            "borderWidthSelected": 2.6,
            "font": {
                "size": 13,
                "face": FONTS["sans"],
                "color": COLORS["ink"],
                "strokeWidth": 3,
                "strokeColor": COLORS["bg"],
                "vadjust": 2,
            },
        },
        "edges": {
            "width": 1.1,
            "selectionWidth": 2.2,
            "arrowStrikethrough": False,
            "smooth": {"enabled": True, "type": "continuous", "roundness": 0.2},
            "color": {
                "color": COLORS["line_strong"],
                "highlight": COLORS["cinnabar"],
                "hover": COLORS["cinnabar_soft"],
                "opacity": 0.85,
            },
            "font": {
                "size": 10,
                "face": FONTS["sans"],
                "color": COLORS["ink_mute"],
                "strokeWidth": 3,
                "strokeColor": COLORS["bg"],
                "align": "middle",
            },
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.42}},
        },
        "physics": {
            "enabled": bool(physics),
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
                "gravitationalConstant": -62,
                "centralGravity": 0.012,
                "springLength": 130,
                "springConstant": 0.09,
                "damping": 0.55,
                "avoidOverlap": 0.35,
            },
            "stabilization": {"enabled": True, "iterations": 320, "fit": True},
            "minVelocity": 0.7,
        },
        "interaction": {
            "hover": True,
            "tooltipDelay": 110,
            "hideEdgesOnDrag": False,
            "navigationButtons": False,
            "multiselect": False,
            "selectConnectedEdges": True,
        },
        "layout": {"randomSeed": 42, "improvedLayout": True},
    }


# --------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------


def node_size(degree: int, max_deg: int) -> float:
    """节点半径：按度数开方缩放，保证差异明显但不过分夸张。"""
    if max_deg <= 0:
        return 14.0
    ratio = (max(degree, 0) / max_deg) ** 0.5
    return round(10.0 + 16.0 * ratio, 2)


def build_network_html(
    graph: nx.MultiDiGraph,
    *,
    focus: Optional[str] = None,
    height: int = 720,
    physics: bool = True,
    show_edge_labels: bool = False,
    highlight_neighbors: bool = True,
) -> str:
    """生成离线自洽的交互式图谱 HTML。

    Args:
        graph: 待渲染的图（建议先经 :func:`~src.graph.builder.with_degree` 处理）。
        focus: 需要突出显示的节点 id（加粗描边并放大）。
        height: 画布高度（像素）。
        physics: 是否启用力导向布局；关闭后为静态布局（大图更流畅）。
        show_edge_labels: 是否常显关系标签（关系较多时建议关闭）。
        highlight_neighbors: 点击节点时是否高亮其邻居并淡化其余节点。

    Notes:
        **节点不带悬停说明**：鼠标移到节点上不会弹出任何浮层，
        以免浮层跟随光标遮挡画布、打断查看关系。关系（边）仍保留悬停说明。

    Raises:
        EmptyGraphError: 图中没有任何节点。
        GraphError: 生成结果仍依赖外部资源。
    """
    if graph.number_of_nodes() == 0:
        raise EmptyGraphError("图为空，无法生成图谱可视化。")

    net = Network(
        height=f"{int(height)}px",
        width="100%",
        directed=True,
        notebook=False,
        bgcolor=COLORS["bg"],
        font_color=COLORS["ink"],
        cdn_resources="in_line",
        neighborhood_highlight=bool(highlight_neighbors),
        heading="",
    )

    top_degree = max_degree(graph)

    for node_id, data in graph.nodes(data=True):
        palette = CATEGORY_COLORS.get(str(data.get("category", "")), FALLBACK_COLOR)
        is_focus = node_id == focus
        degree = graph.degree(node_id)
        # 节点**刻意不设** ``title``：vis-network 有 title 就会在鼠标悬停时弹出浮层，
        # 浮层会随光标移动遮挡画布、打断「顺着连线看关系」这件事，
        # 而节点要看的信息在页面下方的实体清单与详情页里都有。
        # 关系的悬停说明（``_edge_tooltip``）保留——关系没有别的入口可看。
        net.add_node(
            node_id,
            label=truncate_label(str(data.get("name", node_id))),
            size=node_size(degree, top_degree) * (1.35 if is_focus else 1.0),
            color={
                "background": palette["bg"],
                "border": COLORS["cinnabar"] if is_focus else palette["border"],
                "highlight": {"background": palette["bg"], "border": COLORS["cinnabar"]},
                "hover": {"background": palette["bg"], "border": COLORS["ink"]},
            },
            borderWidth=3.2 if is_focus else 1.2,
            category=data.get("category_name", ""),
            degree=degree,
            shape="dot",
        )

    for u, v, key, data in graph.edges(keys=True, data=True):
        attrs: Dict[str, object] = {
            "id": key,
            "title": _edge_tooltip(data),
            "type": data.get("type", ""),
            "label_type": data.get("type_name", ""),
        }
        if show_edge_labels:
            label = str(data.get("label") or data.get("type_name") or "")
            attrs["label"] = truncate_label(label, 8)
        net.add_edge(u, v, **attrs)

    options = network_options(
        physics=physics,
        highlight_neighbors=highlight_neighbors,
    )
    net.set_options(json.dumps(options, ensure_ascii=False))

    return tighten_layout(strip_external_resources(net.generate_html()))


# --------------------------------------------------------------------------
# 规模守卫：节点过多时按分类分片
# --------------------------------------------------------------------------

#: 单份 HTML 建议承载的节点上限。
#:
#: 实测（96 节点 / 180 边）：产物约 830 KB，一次性渲染流畅。
#: 节点数上千时单份产物会到十几 MB、首屏明显卡顿，此时按分类拆成多份更实际。
#: 阈值取 400：当前数据规模（96）远低于它，因此默认行为与不引入本功能时完全一致。
DEFAULT_NODE_BUDGET = 400


@dataclass(frozen=True)
class GraphShard:
    """一份图谱 HTML 及其覆盖范围。"""

    label: str
    node_count: int
    edge_count: int
    html: str

    @property
    def size_kb(self) -> float:
        return len(self.html.encode("utf-8")) / 1024


def shard_graph(
    graph: nx.MultiDiGraph,
    budget: int = DEFAULT_NODE_BUDGET,
    *,
    category_attr: str = "category_name",
) -> List[Tuple[str, nx.MultiDiGraph]]:
    """把图按分类拆成每片不超过 ``budget`` 个节点的子图。

    规则：

    1. 节点数不超过 ``budget`` 时**原样返回一张全图**（当前 96 节点的实际路径）；
    2. 超过时按分类打包（分类按节点数降序，保证结果可复现），凑满一片就另起一片；
    3. 单个分类自身超过 ``budget`` 时，按度数降序切成若干块——
       度数高的实体通常是与其它分类的枢纽，单独成片更便于查看。

    **注意**：分片视图只展示片内的关系；跨片的关系会在片间边界处不可见，
    需要查看跨片关联时应使用「聚焦实体」视图或全图视图。
    与其把跨片边画成断头线让人误判，不如明确不画并在界面上说明。
    """
    count = graph.number_of_nodes()
    if count == 0:
        return []
    if count <= budget:
        return [("全图", graph)]

    groups: Dict[str, List[str]] = {}
    for node_id, data in graph.nodes(data=True):
        key = str(data.get(category_attr) or data.get("category") or "未分类")
        groups.setdefault(key, []).append(node_id)

    # 分片结果可复现：分类按「节点数降序 + 名称」排序，片内节点按 id 排序
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    shards: List[Tuple[str, List[str]]] = []
    pending: List[str] = []
    pending_labels: List[str] = []

    def flush() -> None:
        if pending:
            shards.append((" + ".join(pending_labels), list(pending)))
            pending.clear()
            pending_labels.clear()

    for label, nodes in ordered:
        if len(nodes) > budget:
            flush()
            ranked = sorted(nodes, key=lambda n: (-graph.degree(n), n))
            chunks = [ranked[i : i + budget] for i in range(0, len(ranked), budget)]
            for index, chunk in enumerate(chunks, start=1):
                shards.append((f"{label}（{index}/{len(chunks)}）", chunk))
            continue

        if len(pending) + len(nodes) > budget:
            flush()
        pending.extend(nodes)
        pending_labels.append(label)
    flush()

    out: List[Tuple[str, nx.MultiDiGraph]] = []
    for label, nodes in shards:
        sub = graph.subgraph(nodes).copy()
        out.append((label, sub))
    return out


def build_sharded_html(
    graph: nx.MultiDiGraph,
    *,
    budget: int = DEFAULT_NODE_BUDGET,
    focus: Optional[str] = None,
    **kwargs: object,
) -> List[GraphShard]:
    """按规模守卫渲染图谱：小图一份，大图多份。

    ``focus`` 只在包含该节点的分片里生效，其余分片不传，
    免得在不相干的片里画出一个「重点」。
    """
    shards = shard_graph(graph, budget)
    out: List[GraphShard] = []
    for label, sub in shards:
        shard_focus = focus if (focus and sub.has_node(focus)) else None
        html = build_network_html(sub, focus=shard_focus, **kwargs)  # type: ignore[arg-type]
        out.append(
            GraphShard(
                label=label,
                node_count=sub.number_of_nodes(),
                edge_count=sub.number_of_edges(),
                html=html,
            )
        )
    return out


def build_path_html(
    graph: nx.MultiDiGraph,
    node_ids: Sequence[str],
    *,
    height: int = 380,
) -> str:
    """只渲染一条关联路径所涉及的节点与关系，便于「聚焦看这条线」。

    Args:
        graph: 全图。
        node_ids: 路径上的节点顺序。
    """
    if not node_ids:
        raise EmptyGraphError("路径为空，无法渲染。")
    keep = [n for n in node_ids if graph.has_node(n)]
    if not keep:
        raise EmptyGraphError("路径节点均不在图中，无法渲染。")
    sub = graph.subgraph(keep).copy()
    # 只保留路径上相邻两两之间的关系，避免出现「捷径」干扰视觉判断
    allowed = {(a, b) for a, b in zip(keep, keep[1:])}
    pruned = nx.MultiDiGraph()
    pruned.add_nodes_from((n, dict(d)) for n, d in sub.nodes(data=True))
    for u, v, k, data in sub.edges(keys=True, data=True):
        if (u, v) in allowed or (v, u) in allowed:
            pruned.add_edge(u, v, key=k, **dict(data))
    return build_network_html(pruned, height=height, physics=True)


def graph_legend_html(graph: nx.MultiDiGraph) -> str:
    """图例 HTML：按分类展示颜色与实体数量（数值取自真实图）。"""
    counts: Dict[str, int] = {}
    names: Dict[str, str] = {}
    for _, data in graph.nodes(data=True):
        cid = str(data.get("category", ""))
        counts[cid] = counts.get(cid, 0) + 1
        names[cid] = str(data.get("category_name", cid))
    rows = []
    for cid, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        color = CATEGORY_COLORS.get(cid, FALLBACK_COLOR)["bg"]
        rows.append(
            '<span class="hz-legend__item">'
            f'<span class="hz-legend__dot" style="background:{color};"></span>'
            f"{_esc(names.get(cid, cid))}"
            f'<span class="hz-legend__count">{count}</span></span>'
        )
    return f'<div class="hz-legend">{"".join(rows)}</div>'


def path_chain_html(graph: nx.MultiDiGraph, path: PathResult) -> str:
    """把关联路径渲染成可读链条：``西递 —相关→ 徽州民居 ←属于— 承志堂``。

    方向如实呈现：``reversed=True`` 的一段渲染为 ``←标签—``，
    以区别于关系真实方向与路径行进方向一致的情况。
    """
    if not isinstance(path, PathResult):
        raise GraphError("path_chain_html 需要 PathResult 对象。")
    if not path.nodes:
        return ""

    parts: List[str] = []
    for idx, node_id in enumerate(path.nodes):
        name = _esc(graph.nodes[node_id].get("name", node_id)) if graph.has_node(node_id) else _esc(node_id)
        cls = "hz-path__node hz-path__node--end" if idx in (0, len(path.nodes) - 1) else "hz-path__node"
        parts.append(f'<span class="{cls}">{name}</span>')
        if idx < len(path.edges):
            edge = path.edges[idx]
            label = _esc(edge.label or edge.type_name or edge.type)
            if edge.reversed:
                parts.append(
                    f'<span class="hz-path__arrow">←</span>'
                    f'<span class="hz-path__rel">{label}</span>'
                    f'<span class="hz-path__arrow">—</span>'
                )
            else:
                parts.append(
                    f'<span class="hz-path__arrow">—</span>'
                    f'<span class="hz-path__rel">{label}</span>'
                    f'<span class="hz-path__arrow">→</span>'
                )
    return f'<div class="hz-path">{"".join(parts)}</div>'


__all__ = [
    "CATEGORY_COLORS",
    "FALLBACK_COLOR",
    "category_palette",
    "strip_external_resources",
    "tighten_layout",
    "truncate_label",
    "network_options",
    "node_size",
    "build_network_html",
    "build_path_html",
    "shard_graph",
    "build_sharded_html",
    "GraphShard",
    "DEFAULT_NODE_BUDGET",
    "graph_legend_html",
    "path_chain_html",
]
