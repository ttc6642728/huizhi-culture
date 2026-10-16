"""徽知首页：项目引导 + 环境自检 + 模块交付进度。

P1 阶段起，这里会补充真实的实体 / 关系 / 资料来源统计。
"""

from __future__ import annotations

import importlib.util
import sys
from typing import List, Tuple

import streamlit as st

from src import __version__, config
from src.ui import components as ui


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
    ("src.graph.visualize", "图谱可视化", "P2"),
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

    cols = st.columns([3, 2], gap="large")
    with cols[0]:
        _render_backend()
    with cols[1]:
        _render_runtime()

    _render_checklist()

    st.warning(
        "当前为 P0 脚手架阶段：文化数据、知识图谱与问答链路尚未接入，"
        "上方「待开发」状态即为真实进度。后续每个阶段都会在界面与测试中体现实际完成度。"
    )


__all__ = ["render"]
