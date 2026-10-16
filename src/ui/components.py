"""界面组件：卡片、标签、区块标题、空/错误状态等可复用 HTML 片段。

所有函数返回可直接交给 ``st.markdown(..., unsafe_allow_html=True)`` 的 HTML 字符串，
或直接完成一次渲染（``render_*`` 前缀）。样式全部来自 :mod:`src.ui.theme` 的设计令牌，
不在此处硬编码颜色。
"""

from __future__ import annotations

import html as _html
from typing import Iterable, Sequence

import streamlit as st


def esc(text: object) -> str:
    """HTML 转义，防止数据中的 ``<`` ``>`` ``&`` 破坏页面结构。"""
    return _html.escape(str(text if text is not None else ""), quote=True)


# --------------------------------------------------------------------------
# 结构
# --------------------------------------------------------------------------


def hero(eyebrow: str, title: str, desc: str) -> str:
    """首页头图区（纯排版，不使用装饰图片）。"""
    return (
        '<div class="hz-hero">'
        f'<div class="hz-hero__eyebrow">{esc(eyebrow)}</div>'
        f'<div class="hz-hero__title">{esc(title)}</div>'
        f'<p class="hz-hero__desc">{esc(desc)}</p>'
        "</div>"
    )


def section_title(title: str, subtitle: str = "") -> str:
    sub = f'<p class="hz-section-sub">{esc(subtitle)}</p>' if subtitle else ""
    return f'<div><div class="hz-section-title">{esc(title)}</div>{sub}</div>'


def card(content_html: str, accent: bool = False, flat: bool = False) -> str:
    """把任意 HTML 内容包进统一样式的卡片。"""
    cls = "hz-card"
    if accent:
        cls += " hz-card--accent"
    if flat:
        cls += " hz-card--flat"
    return f'<div class="{cls}">{content_html}</div>'


def card_html(title: str, body_html: str = "", meta_html: str = "", accent: bool = False) -> str:
    """带标题的卡片。"""
    parts = []
    if title:
        parts.append(
            f'<div class="hz-section-title" style="font-size:1.05rem;margin-bottom:.35rem;">'
            f"{esc(title)}</div>"
        )
    if body_html:
        parts.append(body_html)
    if meta_html:
        parts.append(meta_html)
    return card("".join(parts), accent=accent)


def kv_row(key: str, value: str) -> str:
    """键值行。

    ``key`` 会被 HTML 转义；``value`` 视为**已是安全的 HTML 片段**（便于嵌入 ``<code>``、
    标签徽标等），调用方需自行对其中来自数据的部分使用 :func:`esc`。
    """
    return (
        f'<div class="hz-kv"><span class="hz-kv__k">{esc(key)}</span>'
        f'<span class="hz-kv__v">{value}</span></div>'
    )


def tags(items: Iterable[str], kind: str = "") -> str:
    """渲染一组标签。``kind`` 可为 ``""`` / ``"accent"`` / ``"stone"``。"""
    cls = "hz-tag" + (f" hz-tag--{kind}" if kind else "")
    return "".join(f'<span class="{cls}">{esc(i)}</span>' for i in items if str(i).strip())


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------


def empty_state(title: str, desc: str = "") -> str:
    """空状态：无搜索结果、无关联关系等。"""
    d = f'<p class="hz-state__desc">{esc(desc)}</p>' if desc else ""
    return (
        '<div class="hz-state">'
        f'<div class="hz-state__title">{esc(title)}</div>{d}'
        "</div>"
    )


def error_state(title: str, desc: str = "") -> str:
    """错误状态：数据缺失、接口异常等。"""
    d = f'<p class="hz-state__desc">{esc(desc)}</p>' if desc else ""
    return (
        '<div class="hz-state hz-state--error">'
        f'<div class="hz-state__title">{esc(title)}</div>{d}'
        "</div>"
    )


# --------------------------------------------------------------------------
# 渲染助手
# --------------------------------------------------------------------------


def render(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


def render_section(title: str, subtitle: str = "") -> None:
    st.markdown(section_title(title, subtitle), unsafe_allow_html=True)


def render_empty(title: str, desc: str = "") -> None:
    st.markdown(empty_state(title, desc), unsafe_allow_html=True)


def render_error(title: str, desc: str = "") -> None:
    st.markdown(error_state(title, desc), unsafe_allow_html=True)


def render_footer(text: str) -> None:
    st.markdown(f'<div class="hz-footer">{esc(text)}</div>', unsafe_allow_html=True)


def source_item(index: int, title: str, detail: str = "") -> str:
    """参考资料条目（带编号徽标，供问答页溯源使用）。"""
    d = f'<span style="color:#8C867A;">{esc(detail)}</span>' if detail else ""
    return (
        '<div class="hz-source">'
        f'<span class="hz-source__idx">{index}</span>{esc(title)} {d}'
        "</div>"
    )


__all__ = [
    "esc",
    "hero",
    "section_title",
    "card",
    "card_html",
    "kv_row",
    "tags",
    "empty_state",
    "error_state",
    "render",
    "render_section",
    "render_empty",
    "render_error",
    "render_footer",
    "source_item",
]
