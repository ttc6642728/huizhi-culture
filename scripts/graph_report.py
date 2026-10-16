"""知识图谱验证脚本（CLI）。

用途：不启动 Web 界面，直接输出图谱的建图保真度、结构指标、核心枢纽与文化聚类，
以及可视化产物的离线自洽检查结果。既可作为开发时的自检，也可作为验收证据。

用法::

    python scripts/graph_report.py
    python scripts/graph_report.py --focus hongcun --radius 1
    python scripts/graph_report.py --path xidi chengzhitang
    python scripts/graph_report.py --export outputs/graph.html
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 允许以 `python scripts/graph_report.py` 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.loader import DataError, load_dataset  # noqa: E402
from src.graph import analysis as ga  # noqa: E402
from src.graph import builder as gb  # noqa: E402
from src.graph import visualize as gv  # noqa: E402

EXTERNAL_REF = re.compile(r"<(?:script|link)\b[^>]*\b(?:src|href)\s*=\s*[\"'](?:https?:)?//", re.I)


def _rule(title: str) -> None:
    print()
    print(f"── {title} " + "─" * max(0, 58 - len(title)))


def main() -> int:
    parser = argparse.ArgumentParser(description="徽知 · 知识图谱验证报告")
    parser.add_argument("--focus", help="聚焦实体 id，输出其关联子图规模")
    parser.add_argument("--radius", type=int, default=1, help="聚焦半径（默认 1）")
    parser.add_argument("--path", nargs=2, metavar=("起点", "终点"), help="查询两个实体 id 之间的最短关联路径")
    parser.add_argument("--export", metavar="路径", help="把交互式图谱导出为可独立打开的 HTML 文件")
    args = parser.parse_args()

    try:
        dataset = load_dataset()
    except DataError as exc:
        print(f"[失败] 数据加载未通过：{exc}")
        return 1

    graph = gb.build_graph(dataset)

    _rule("建图保真度")
    print(f"数据实体数　　　　: {len(dataset.entities)}")
    print(f"图谱节点数　　　　: {graph.number_of_nodes()}"
          f"　{'✔ 一致' if graph.number_of_nodes() == len(dataset.entities) else '✘ 不一致'}")
    print(f"数据关系数　　　　: {len(dataset.relations)}")
    print(f"图谱边数　　　　　: {graph.number_of_edges()}"
          f"　{'✔ 一致（平行边未被合并）' if graph.number_of_edges() == len(dataset.relations) else '✘ 不一致，存在关系丢失'}")
    print(f"图类型　　　　　　: {type(graph).__name__}")

    stats = ga.graph_stats(graph)
    _rule("结构指标")
    print(f"图密度　　　　　　: {stats.density}")
    print(f"平均度 / 最大度　 : {stats.avg_degree} / {stats.max_degree}")
    print(f"连通分量　　　　　: {stats.component_count}（最大块 {stats.largest_component_size} 个实体，"
          f"占 {stats.largest_component_ratio:.0%}）")
    print(f"网络直径　　　　　: {stats.diameter}")
    print(f"平均最短关联距离　: {stats.avg_shortest_path}")
    print(f"环形结构 / 自环　 : {stats.cycle_count} / {stats.self_loop_count}")
    print(f"孤立实体　　　　　: {stats.isolated_count}")

    _rule("关系类型分布")
    for name, count in stats.relation_type_counts.items():
        print(f"  {name:<14}{count:>4} 条")

    _rule("核心枢纽 · 度数排名 Top 8")
    for i, row in enumerate(ga.degree_ranking(graph, top_n=8), 1):
        print(f"  {i:>2}. {row.name:<14}{row.category_name:<12}"
              f"度 {row.degree:>3}（出 {row.out_degree:>2} / 入 {row.in_degree:>2}）")

    _rule("核心枢纽 · 介数中心性 Top 8")
    for i, row in enumerate(ga.betweenness_ranking(graph, top_n=8), 1):
        print(f"  {i:>2}. {row.name:<14}{row.category_name:<12}{row.betweenness:.4f}")

    _rule("文化聚类")
    comms = ga.communities(graph)
    for comm in comms:
        names = [graph.nodes[n].get("name", n) for n in comm.node_ids]
        print(f"  聚类 {comm.index + 1}　规模 {comm.size:<3} 内聚 {comm.cohesion:.3f}　"
              f"涉及 {len(comm.category_names)} 类")
        print(f"      {'、'.join(names[:12])}{'…' if comm.size > 12 else ''}")

    if args.focus:
        _rule(f"聚焦 {args.focus}（半径 {args.radius}）")
        try:
            ego = gb.ego_graph(graph, args.focus, args.radius)
            print(f"  节点 {ego.number_of_nodes()} 个，关系 {ego.number_of_edges()} 条")
            for i, row in enumerate(ga.degree_ranking(ego, top_n=8), 1):
                print(f"  {i:>2}. {row.name:<14}{row.category_name:<12}度 {row.degree}")
        except gb.NodeNotFoundError as exc:
            print(f"  [失败] {exc}")

    if args.path:
        src, dst = args.path
        _rule(f"关联路径 {src} → {dst}")
        try:
            path = ga.shortest_path(graph, src, dst)
            if path is None:
                print("  两者之间没有关联路径（分属不同连通分量）。")
            else:
                print(f"  长度 {path.length} 条关系")
                for i, edge in enumerate(path.edges, 1):
                    arrow = "—%s→" % edge.label if edge.is_forward else "←%s—" % edge.label
                    print(f"  {i}. {edge.from_name} {arrow} {edge.to_name}"
                          f"　[{edge.type_name} · 来源 {edge.source_count}]")
                alts = ga.shortest_path_all(graph, src, dst, limit=4)
                if len(alts) > 1:
                    print(f"  另有 {len(alts) - 1} 条等长线路。")
        except gb.NodeNotFoundError as exc:
            print(f"  [失败] {exc}")

    _rule("可视化离线自洽检查")
    html = gv.build_network_html(graph, height=600)
    external = EXTERNAL_REF.findall(html)
    css_url = re.search(r"url\(\s*[\"']?(?:https?:)?//", html, re.I)
    print(f"HTML 体积　　　　 : {len(html) / 1024:.1f} KB")
    print(f"vis-network 内联　: {'✔ 是' if 'DataSet' in html else '✘ 否'}")
    print(f"外部资源引用　　　: {'✔ 无' if not external else '✘ 发现 %d 处' % len(external)}")
    print(f"外部 CSS url()　　: {'✘ 存在' if css_url else '✔ 无'}")

    if args.export:
        out = Path(args.export)
        if not out.is_absolute():
            out = Path(__file__).resolve().parent.parent / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"已导出　　　　　　: {out}（{out.stat().st_size / 1024:.1f} KB，可直接用浏览器打开）")

    print()
    ok = (
        graph.number_of_nodes() == len(dataset.entities)
        and graph.number_of_edges() == len(dataset.relations)
        and not external
        and stats.isolated_count == 0
    )
    print("结果：" + ("全部检查通过。" if ok else "存在未通过项，请查看上方输出。"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
