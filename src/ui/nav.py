"""页面导航模型。

把「有哪些页面、如何跳转、非法页面怎么处理」集中到一处，
``app.py`` 与各页面都从这里取信息，避免导航规则散落在多处而互相不一致。

导航机制统一使用 ``st.session_state`` + ``st.rerun()``：
不使用 URL 查询参数做跳转，因为查询参数会残留在地址栏里，
用户再点侧边栏时容易被旧参数「拽回」上一页。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import streamlit as st

#: 侧边栏导航项。``key`` 同时是 ``src.ui.pages.<key>`` 的模块名。
NAV_ITEMS: List[Dict[str, str]] = [
    {"key": "home", "label": "文化探索", "phase": ""},
    {"key": "explore", "label": "文化百科", "phase": "P3"},
    {"key": "graph", "label": "知识图谱", "phase": "P2"},
    {"key": "ask", "label": "AI 问答", "phase": "P4"},
    {"key": "about", "label": "关于项目", "phase": "P5"},
]

#: 不在侧边栏出现、但可被跳转到的页面 → 该页应高亮哪个导航项。
HIDDEN_PAGES: Dict[str, str] = {"detail": "explore"}

#: 默认页面（也是非法页面标识的回退目标）
DEFAULT_PAGE = "home"

#: session_state 中保存当前实体 id 的键
STATE_ENTITY = "entity_id"

#: state 键 → 各页面读取时的键名（图谱聚焦）
STATE_GRAPH_FOCUS = "graph_focus"


def nav_keys() -> Tuple[str, ...]:
    """侧边栏导航项的 key。"""
    return tuple(item["key"] for item in NAV_ITEMS)


def all_page_keys() -> Tuple[str, ...]:
    """全部可路由页面（含隐藏页）。"""
    return nav_keys() + tuple(HIDDEN_PAGES)


def label_of(page: str) -> str:
    """页面中文名；隐藏页回退到其所属导航项的名称。"""
    for item in NAV_ITEMS:
        if item["key"] == page:
            return item["label"]
    parent = HIDDEN_PAGES.get(page)
    return label_of(parent) if parent else page


def highlight_of(page: str) -> str:
    """当前页面应高亮哪个导航项（隐藏页映射到父导航项）。"""
    if page in nav_keys():
        return page
    return HIDDEN_PAGES.get(page, DEFAULT_PAGE)


def resolve_route(page: Optional[str]) -> str:
    """把任意页面标识解析为可路由的页面 key。

    非法或缺失的标识一律回退到 :data:`DEFAULT_PAGE`。
    纯函数，便于单元测试。
    """
    if page and page in all_page_keys():
        return page
    return DEFAULT_PAGE


def goto(page: str, **state: object) -> None:
    """跳转到指定页面并立即重跑。

    ``state`` 中的键值会写入 ``session_state``（例如 ``entity_id``、
    ``graph_focus``），目标页面据此决定渲染哪条数据。
    """
    st.session_state["page"] = resolve_route(page)
    for key, value in state.items():
        st.session_state[key] = value
    st.rerun()


def nav_button(
    label: str,
    page: str,
    key: str,
    use_container_width: bool = True,
    type: str = "secondary",
    **state: object,
) -> None:
    """渲染一个真实可用的跳转按钮（点击后跳转，绝不出现「假按钮」）。"""
    if st.button(label, key=key, use_container_width=use_container_width, type=type):
        goto(page, **state)


__all__ = [
    "NAV_ITEMS",
    "HIDDEN_PAGES",
    "DEFAULT_PAGE",
    "STATE_ENTITY",
    "STATE_GRAPH_FOCUS",
    "nav_keys",
    "all_page_keys",
    "label_of",
    "highlight_of",
    "resolve_route",
    "goto",
    "nav_button",
]
