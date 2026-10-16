"""徽知 · Huizhou Culture Explorer —— Streamlit 应用入口。

职责：页面基础配置、设计系统注入、侧边栏导航、页面路由与页脚。
具体页面逻辑位于 ``src/ui/pages/``，每个页面模块导出一个 ``render()`` 函数。
"""

from __future__ import annotations

import importlib
from typing import Callable, Dict, List, Optional

import streamlit as st

from src import __version__, config
from src.ui import components as ui
from src.ui.theme import inject_theme

# --------------------------------------------------------------------------
# 页面配置（必须是第一个 Streamlit 调用）
# --------------------------------------------------------------------------

st.set_page_config(
    page_title=config.app_title(),
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()


# --------------------------------------------------------------------------
# 导航定义
# --------------------------------------------------------------------------

#: 侧边栏导航项：key 同时作为 ``src.ui.pages.<key>`` 模块名
NAV_ITEMS: List[Dict[str, str]] = [
    {"key": "home", "label": "文化探索", "phase": ""},
    {"key": "explore", "label": "文化百科", "phase": "P3"},
    {"key": "graph", "label": "知识图谱", "phase": "P2"},
    {"key": "ask", "label": "AI 问答", "phase": "P4"},
    {"key": "about", "label": "关于项目", "phase": "P5"},
]

_DEFAULT_PAGE = "home"


def _load_page(key: str) -> Optional[Callable[[], None]]:
    """加载页面模块的 ``render`` 函数；模块尚未实现时返回 ``None``。

    只有「模块本身不存在」才返回 ``None``；模块内部的其他导入错误会照常抛出，
    避免把真实的代码缺陷伪装成「尚未开发」。
    """
    module_name = f"src.ui.pages.{key}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        raise
    renderer = getattr(module, "render", None)
    if renderer is None:
        raise AttributeError(f"页面模块 {module_name} 未导出 render() 函数")
    return renderer


def _render_pending(label: str, phase: str) -> None:
    """尚未实现的页面：如实说明所处阶段，不展示任何虚假功能。"""
    ui.render(
        ui.hero(
            "MODULE PENDING",
            label,
            f"该模块计划在 {phase} 阶段交付。当前阶段尚未实现，因此不提供入口内容，"
            "以免出现只有外观、没有实际功能的界面。",
        )
    )
    ui.render_empty(
        f"{phase} 阶段开发中",
        "完成后此页将接入真实的文化数据与交互逻辑，并附带对应的自动化测试。",
    )


# --------------------------------------------------------------------------
# 侧边栏
# --------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        '<div style="font-family:\'Noto Serif SC\',serif;font-size:1.5rem;'
        'font-weight:700;letter-spacing:.06em;color:#22201C;margin-bottom:.1rem;">徽知</div>'
        '<div style="font-size:.76rem;color:#8C867A;letter-spacing:.04em;margin-bottom:1rem;">'
        "HUIZHOU CULTURE EXPLORER</div>",
        unsafe_allow_html=True,
    )

    current = st.session_state.get("page", _DEFAULT_PAGE)
    for item in NAV_ITEMS:
        is_active = item["key"] == current
        label = item["label"] if not item["phase"] else f"{item['label']}"
        if st.button(
            label,
            key=f"nav_{item['key']}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state["page"] = item["key"]
            st.rerun()

    st.markdown("<hr/>", unsafe_allow_html=True)

    backend = config.resolve_qa_backend()
    st.markdown(
        '<div style="font-size:.72rem;color:#8C867A;letter-spacing:.1em;">问答后端</div>'
        f'<div style="font-size:.86rem;color:#B23A2F;font-weight:600;margin-bottom:.6rem;">'
        f"{ui.esc(config.qa_backend_label())}</div>",
        unsafe_allow_html=True,
    )
    if backend == config.BACKEND_LOCAL:
        st.caption("未检测到模型凭证，已自动使用本地检索式后端。")

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.caption(f"v{__version__}　·　P0 脚手架")


# --------------------------------------------------------------------------
# 路由
# --------------------------------------------------------------------------

_page_key = st.session_state.get("page", _DEFAULT_PAGE)
_item = next((i for i in NAV_ITEMS if i["key"] == _page_key), None)

if _item is None:
    st.session_state["page"] = _DEFAULT_PAGE
    st.rerun()

_renderer = _load_page(_page_key)
if _renderer is not None:
    _renderer()
elif _item["phase"]:
    _render_pending(_item["label"], _item["phase"])
else:
    st.error(f"页面模块 src/ui/pages/{_page_key}.py 缺失，且未标注交付阶段。")


# --------------------------------------------------------------------------
# 页脚
# --------------------------------------------------------------------------

ui.render_footer(
    "徽知 · Huizhou Culture Explorer　|　徽州文化知识图谱与 AI 智能问答平台　|　"
    "所有文化事实均标注可核查来源，AI 回答严格基于检索到的资料。"
)
