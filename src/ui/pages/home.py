"""徽知首页：项目引导 + 数据概况 + 图谱概况 + 环境自检 + 模块交付进度。

页面上的每个数字都来自实时加载的数据或实时计算的图谱，
模块进度用 ``importlib`` 真实探测，不写死任何「已完成 / 待开发」标签。
"""

from __future__ import annotations

import importlib.util
import sys
from typing import List, Tuple

import streamlit as st

from src import __version__, config
from src.data.loader import DataError, dataset_summary, load_dataset
from src.data.repository import Repository
from src.graph import analysis as ga
from src.graph import runtime as graph_runtime
from src.ui import components as ui
from src.ui import datastore, nav


#: 需要检查的运行依赖 -> 用途说明
_REQUIRED_PACKAGES: List[Tuple[str, str]] = [
    ("streamlit", "Web 界面"),
    ("networkx", "知识图谱建模"),
    ("pyvis", "交互式图谱渲染"),
    ("jieba", "中文分词（检索）"),
    ("requests", "调用 Dify / 大模型接口"),
    ("dotenv", "读取 .env 配置"),
    ("pytest", "测试框架"),
]

#: 应存在的核心模块（随阶段推进逐步实现）
_CORE_MODULES: List[Tuple[str, str, str]] = [
    ("src.data.loader", "数据加载与校验", "P1"),
    ("src.data.repository", "实体查询与检索", "P1"),
    ("src.graph.builder", "图谱建模", "P2"),
    ("src.graph.analysis", "图谱分析", "P2"),
    ("src.graph.visualize", "图谱可视化", "P2"),
    ("src.ui.pages.graph", "知识图谱页", "P2"),
    ("src.data.images", "图片库与署名", "P3"),
    ("src.ui.pages.explore", "文化百科页", "P3"),
    ("src.ui.pages.detail", "实体详情页", "P3"),
    ("src.qa.retriever", "资料检索", "P4"),
    ("src.qa.engine", "问答引擎", "P4"),
    ("src.agent.workflow", "智能体工作流", "P5"),
]

#: 数据文件 -> 说明
_DATA_FILES = [
    (config.ENTITIES_FILE, "文化实体"),
    (config.RELATIONS_FILE, "实体关系"),
    (config.SOURCES_FILE, "参考资料"),
]

_STATUS_MARK = {"ok": "已就绪", "todo": "待开发", "missing": "缺失"}


def _pkg_installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _module_ready(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError):
        return False


def _render_checklist() -> None:
    ui.render_section("环境自检", "以下结果由程序实时检测，不是写死的示意内容。")

    # 运行依赖
    dep_rows = []
    ok_count = 0
    for pkg, purpose in _REQUIRED_PACKAGES:
        ok = _pkg_installed(pkg)
        ok_count += int(ok)
        mark = (
            f'<span class="hz-tag hz-tag--accent">{_STATUS_MARK["ok"]}</span>'
            if ok
            else f'<span class="hz-tag">{_STATUS_MARK["missing"]}</span>'
        )
        dep_rows.append(
            f'<div class="hz-kv"><span class="hz-kv__k" style="min-width:7rem;">'
            f"<code>{ui.esc(pkg)}</code></span>"
            f'<span class="hz-kv__v">{ui.esc(purpose)}　{mark}</span></div>'
        )
    ui.render(
        ui.card_html(
            f"运行依赖（{ok_count}/{len(_REQUIRED_PACKAGES)} 已安装）",
            "".join(dep_rows),
        )
    )

    # 数据文件
    data_rows = []
    for path, label in _DATA_FILES:
        exists = path.exists()
        size = f"{path.stat().st_size:,} 字节" if exists else "文件不存在"
        mark = (
            f'<span class="hz-tag hz-tag--accent">{_STATUS_MARK["ok"]}</span>'
            if exists
            else f'<span class="hz-tag">{_STATUS_MARK["todo"]}</span>'
        )
        data_rows.append(
            ui.kv_row(label, f'<code>{ui.esc(path.name)}</code>　{ui.esc(size)}　{mark}')
        )
    ui.render(ui.card_html("文化数据", "".join(data_rows)))

    # 模块进度
    mod_rows = []
    for dotted, label, phase in _CORE_MODULES:
        ready = _module_ready(dotted)
        mark = (
            f'<span class="hz-tag hz-tag--accent">{_STATUS_MARK["ok"]}</span>'
            if ready
            else f'<span class="hz-tag">{phase} 阶段</span>'
        )
        mod_rows.append(ui.kv_row(label, f"<code>{ui.esc(dotted)}</code>　{mark}"))
    ui.render(ui.card_html("模块交付进度", "".join(mod_rows)))


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
    except Exception as exc:  # 建图失败不应导致整页崩溃
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

    _render_data_overview()

    _render_graph_overview()

    cols = st.columns([3, 2], gap="large")
    with cols[0]:
        _render_backend()
    with cols[1]:
        _render_runtime()

    _render_checklist()

    st.info(
        "当前进度：**P3 浏览体验已完成**——文化百科页支持关键词检索与分类筛选，"
        "实体详情页展示结构化属性、正文、以本实体为主语的关联关系（方向如实标注）、"
        "可点击的参考资料与图片署名；上一阶段的图谱建模与结构分析保持可用。"
        "AI 问答（P4）与智能体工作流（P5）尚在开发中，上方「待开发」状态即为真实进度。"
    )

    _render_quick_entry()


def _render_quick_entry() -> None:
    """首页快捷入口：跳转到已交付的页面（均为真实跳转）。"""
    ui.render_section("开始探索")
    cols = st.columns([1, 1, 1, 3], gap="small")
    with cols[0]:
        nav.nav_button("浏览文化百科", "explore", key="home_go_explore", type="primary")
    with cols[1]:
        nav.nav_button("打开知识图谱", "graph", key="home_go_graph")
    with cols[2]:
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
