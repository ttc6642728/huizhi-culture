"""徽知首页：项目引导 + 徽州主视觉 + 数据概况 + 图谱概况 + 快捷入口。

页面上出现的每个数字都来自实时加载的数据或实时计算的图谱，不写死；
运行依赖、数据文件与模块交付进度等**开发者自检信息**统一放在「关于项目」页，
首页只保留面向访客的内容。
"""

from __future__ import annotations

import sys

import streamlit as st

from src import __version__, config
from src.data.loader import DataError, dataset_summary, load_dataset
from src.data.repository import Repository
from src.graph import analysis as ga
from src.graph import runtime as graph_runtime
from src.ui import components as ui
from src.ui import datastore, nav

#: 首页主视觉选用的实体图片（取自 assets/images/manifest.json，可核查、已署名）
#: 选「徽派建筑」：粉墙黛瓦是徽州最具辨识度的视觉符号，与平台的文化主题最贴合。
HERO_IMAGE_ENTITY = "huipai_architecture"


def _render_hero_image() -> None:
    """首页主视觉：一张已署名的徽州代表图片。

    图片来自与详情页相同的图片库，因此同样带作者、许可与来源页面，可点击核对；
    没有图片（或图片清单缺失）时**整块不渲染**，页面照常工作，不以占位图充数。
    """
    image = datastore.images().get(HERO_IMAGE_ENTITY)
    if image is None or not image.exists:
        return

    _, mid, _ = st.columns([1, 4, 1], gap="medium")
    with mid:
        try:
            st.image(str(image.path), use_container_width=True)
        except Exception as exc:  # noqa: BLE001 - 图片损坏不应让整页崩溃
            ui.render_error("首页图片无法显示", f"本地图片读取失败：{exc}")
            return
        ui.render(
            ui.figure_caption(
                caption=image.caption,
                credit=image.credit,
                source_url=image.source_url,
                license_url=image.license_url,
            )
        )
    st.caption("图片为自由授权作品，署名与许可见图注；完整清单见 assets/images/CREDITS.md。")


def _render_backend() -> None:
    ui.render_section("问答后端", "按 Dify → 大模型 → 本地检索式 自动降级，未配置凭证时自动使用本地检索式。")

    backend = config.resolve_qa_backend()
    dify = config.get_dify_config()
    llm = config.get_llm_config()

    rows = [
        ui.kv_row(
            "当前生效",
            f'<strong style="color:#B23A2F;">{ui.esc(config.qa_backend_label())}</strong>',
        ),
        ui.kv_row(
            "Dify",
            ("已配置 " + ui.esc(dify.base_url)) if dify.configured else "未配置",
        ),
        ui.kv_row(
            "大模型",
            (
                f"已配置 {ui.esc(llm.model)} @ {ui.esc(llm.base_url)}"
                if llm.configured
                else "未配置"
            ),
        ),
        ui.kv_row("检索片段数", f"top-{config.qa_top_k()}"),
    ]
    ui.render(ui.card_html("后端状态", "".join(rows)))

    if backend == config.BACKEND_LOCAL:
        st.info(
            "当前为本地检索式后端：回答完全基于本地文化资料抽取并强制标注来源，无需任何 API Key，可离线运行。\n\n"
            "如需启用真实大模型生成，请复制 `.env.example` 为 `.env` 并填写 `LLM_API_KEY`（或 `DIFY_BASE_URL` / `DIFY_API_KEY`），"
            "然后重启应用。"
        )


def _render_data_overview() -> None:
    """数据概况：全部数值来自真实加载的数据集，加载失败时显示错误状态。"""
    ui.render_section("文化数据概况", "以下统计由程序读取 data/*.json 实时计算得出。")

    try:
        dataset = load_dataset()
    except DataError as exc:
        ui.render_error("文化数据加载失败", str(exc).splitlines()[0])
        with st.expander("查看详细错误"):
            st.code(str(exc))
        return

    repo = Repository(dataset)
    summary = dataset_summary(dataset)

    cols = st.columns(5, gap="medium")
    for col, (label, key) in zip(
        cols,
        [("文化实体", "entities"), ("实体关系", "relations"),
         ("参考资料", "sources"), ("内容分类", "categories"),
         ("关系类型", "relation_types")],
    ):
        col.metric(label, summary[key])

    rows = []
    for cc in repo.category_counts():
        if cc.count == 0:
            continue
        rows.append(
            ui.kv_row(
                cc.category.name,
                f'<strong>{cc.count}</strong> 个实体　'
                f'<span style="color:#8C867A;">{ui.esc(cc.category.description)}</span>',
            )
        )
    ui.render(ui.card_html("分类分布", "".join(rows)))

    isolated = repo.stats()["isolated_entities"]
    if isolated:
        ui.render_error(
            f"存在 {len(isolated)} 个孤立实体",
            "这些实体没有任何关系，图谱中会显示为游离节点，建议补充关系。",
        )
    else:
        st.caption(f"图谱连通性检查通过：全部 {summary['entities']} 个实体均至少有一条关系。")


def _render_graph_overview() -> None:
    """知识图谱概况：全部数值由图谱实时计算，不写死。"""
    ui.render_section("知识图谱概况", "由文化实体与关系构建的多重有向图，实时计算结果。")

    try:
        graph = graph_runtime.get_graph()
    except DataError as exc:
        ui.render_error("知识图谱构建失败", str(exc).splitlines()[0])
        return
    except Exception as exc:  # noqa: BLE001 - 建图失败不应导致整页崩溃
        ui.render_error("知识图谱构建失败", f"{type(exc).__name__}：{exc}")
        return

    stats = ga.graph_stats(graph)

    cols = st.columns(5, gap="medium")
    cols[0].metric("图谱节点", stats.node_count)
    cols[1].metric("图谱连线", stats.edge_count)
    cols[2].metric("连通分量", stats.component_count)
    cols[3].metric("网络直径", stats.diameter if stats.diameter is not None else "—")
    cols[4].metric(
        "平均最短关联",
        f"{stats.avg_shortest_path:.2f}" if stats.avg_shortest_path is not None else "—",
    )

    deg = ga.degree_ranking(graph, top_n=3)
    btw = ga.betweenness_ranking(graph, top_n=3)
    rows = [
        ui.kv_row(
            "连接最多",
            "　".join(
                f'<strong>{ui.esc(r.name)}</strong><span style="color:#8C867A;">'
                f'（{r.degree} 条）</span>'
                for r in deg
            ),
        ),
        ui.kv_row(
            "桥梁作用最强",
            "　".join(
                f'<strong>{ui.esc(r.name)}</strong><span style="color:#8C867A;">'
                f'（介数 {r.betweenness:.2f}）</span>'
                for r in btw
            ),
        ),
        ui.kv_row("文化聚类", f"{len(ga.communities(graph))} 个（基于模块度优化，探索性分析）"),
    ]
    ui.render(ui.card_html("图谱结构与核心枢纽", "".join(rows), flat=True))

    if stats.isolated_count:
        ui.render_error(
            f"存在 {stats.isolated_count} 个孤立实体",
            "这些实体没有任何关系，图谱中会显示为游离节点。",
        )
    st.caption("完整交互式图谱、关联路径查询与文化聚类详见左侧「知识图谱」页。")


def _render_runtime() -> None:
    rows = [
        ui.kv_row("应用版本", f"v{ui.esc(__version__)}"),
        ui.kv_row("Python", ui.esc(sys.version.split()[0])),
        ui.kv_row("解释器", f"<code>{ui.esc(sys.executable)}</code>"),
        ui.kv_row("项目根目录", f"<code>{ui.esc(config.BASE_DIR)}</code>"),
    ]
    ui.render(ui.card_html("运行环境", "".join(rows)))


def render() -> None:
    """首页入口。"""
    ui.render(
        ui.hero(
            "Huizhou Culture Explorer",
            "徽知",
            "徽州文化知识图谱与 AI 智能问答平台。浏览徽州文化实体，检索结构化文化知识，"
            "查看实体之间真实可核查的关系，并基于资料向 AI 提问、获得带来源引用的回答。",
        )
    )

    _render_hero_image()

    _render_data_overview()

    _render_graph_overview()

    cols = st.columns([3, 2], gap="large")
    with cols[0]:
        _render_backend()
    with cols[1]:
        _render_runtime()

    _render_quick_entry()


def _render_quick_entry() -> None:
    """首页快捷入口：跳转到已交付的页面（均为真实跳转）。"""
    ui.render_section("开始探索")
    cols = st.columns([1, 1, 1, 1, 1, 3], gap="small")
    with cols[0]:
        nav.nav_button("浏览文化百科", "explore", key="home_go_explore", type="primary")
    with cols[1]:
        nav.nav_button("打开知识图谱", "graph", key="home_go_graph")
    with cols[2]:
        nav.nav_button("向 AI 提问", "ask", key="home_go_ask")
    with cols[3]:
        nav.nav_button("运行智能体工作流", "about", key="home_go_agent")
    with cols[4]:
        try:
            dataset = load_dataset()
        except DataError:
            dataset = None
        first = dataset.entities[0].id if dataset and dataset.entities else ""
        if first:
            nav.nav_button(
                "随机看一个实体",
                "detail",
                key="home_go_random",
                entity_id=first,
            )


__all__ = ["render"]
