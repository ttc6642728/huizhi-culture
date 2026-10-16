"""界面组件：卡片、标签、区块标题、空/错误状态等可复用 HTML 片段。

所有函数返回可直接交给 ``st.markdown(..., unsafe_allow_html=True)`` 的 HTML 字符串，
或直接完成一次渲染（``render_*`` 前缀）。样式全部来自 :mod:`src.ui.theme` 的设计令牌，
不在此处硬编码颜色。
"""

from __future__ import annotations

import html as _html
import re
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


def card_html(
    title: str,
    body_html: str = "",
    meta_html: str = "",
    accent: bool = False,
    flat: bool = False,
) -> str:
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
    return card("".join(parts), accent=accent, flat=flat)


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


def table_html(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    aligns: Sequence[str] | None = None,
) -> str:
    """简易数据表，用于排名、属性等结构化展示。

    ``headers`` 会被转义；``rows`` 中的每个单元格视为**已是安全的 HTML 片段**
    （便于嵌入 ``<strong>``、标签徽标等），来自数据的部分需调用方自行 :func:`esc`。
    """
    aligns = aligns or ["left"] * len(headers)
    head = "".join(
        f'<th style="text-align:{a};">{esc(h)}</th>' for h, a in zip(headers, aligns)
    )
    body = "".join(
        "<tr>" + "".join(
            f'<td style="text-align:{a};">{cell}</td>' for cell, a in zip(row, aligns)
        ) + "</tr>"
        for row in rows
    )
    if not rows:
        body = f'<tr><td colspan="{len(headers)}" style="color:#8C867A;">暂无数据</td></tr>'
    return f'<table class="hz-rank"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


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


# --------------------------------------------------------------------------
# 文化百科 / 实体详情
# --------------------------------------------------------------------------


def crumb(parts: Sequence[str]) -> str:
    """面包屑，纯文字（点击入口由真实按钮提供，不使用假链接）。"""
    return f'<div class="hz-crumb">{"<span>/</span>".join(esc(p) for p in parts)}</div>'


def category_chip(name: str, color: str) -> str:
    """分类徽标：色点 + 名称。颜色与图谱节点保持一致。"""
    return (
        f'<span class="hz-cat"><span class="hz-cat__dot" style="background:{esc(color)};">'
        f"</span>{esc(name)}</span>"
    )


def entity_card(
    name: str,
    summary: str,
    category_name: str,
    category_color: str,
    degree: int,
    relation_count: int,
    source_count: int,
    has_image: bool = False,
) -> str:
    """百科列表中的实体卡片（纯展示；跳转由卡片下方的真实按钮完成）。"""
    meta_bits = [f"关联关系 {relation_count}", f"关联实体 {degree}", f"来源 {source_count}"]
    if has_image:
        meta_bits.append("含图")
    return (
        '<div class="hz-ecard">'
        f'<div class="hz-ecard__top">{category_chip(category_name, category_color)}</div>'
        f'<div class="hz-ecard__name">{esc(name)}</div>'
        f'<p class="hz-ecard__summary">{esc(summary)}</p>'
        f'<div class="hz-ecard__meta">{"".join(f"<span>{esc(m)}</span>" for m in meta_bits)}</div>'
        "</div>"
    )


def detail_head(
    name: str,
    category_name: str,
    category_color: str,
    summary: str,
    aliases: Iterable[str],
    eyebrow: str = "",
) -> str:
    """详情页头部：分类、名称、摘要、别名。"""
    alias_list = [a for a in aliases if str(a).strip()]
    alias_html = (
        f'<div class="hz-alias"><b>别名</b>　{esc("、".join(alias_list))}</div>'
        if alias_list
        else ""
    )
    return (
        '<div class="hz-detail">'
        f'<div class="hz-detail__eyebrow">{esc(eyebrow)}</div>'
        f'<div class="hz-detail__title">{esc(name)}</div>'
        f'{category_chip(category_name, category_color)}'
        f'<p class="hz-detail__summary">{esc(summary)}</p>'
        f"{alias_html}"
        "</div>"
    )


def relation_row(
    direction: str,
    relation_label: str,
    other_name: str,
    description: str = "",
    source_count: int = 0,
) -> str:
    """一行关联关系。

    ``direction`` 取 ``"out"``（本实体为起点）或 ``"in"``（本实体为终点），
    用箭头如实标出方向，避免把反向关系展示成同向。
    """
    arrow = "→" if direction == "out" else "←"
    dir_cls = "hz-rel__dir" if direction == "out" else "hz-rel__dir hz-rel__dir--in"
    desc = f'<span class="hz-rel__desc">{esc(description)}</span>' if description else ""
    src = f' <span class="hz-rel__src">（{source_count} 条来源）</span>' if source_count else ""
    return (
        '<div class="hz-rel">'
        f'<span class="{dir_cls}">{arrow}</span>'
        f'<span class="hz-rel__rel">{esc(relation_label)}</span>'
        f'<span><span class="hz-rel__who">{esc(other_name)}</span>{src}{desc}</span>'
        "</div>"
    )


def source_row(index: int, title: str, publisher: str, url: str, note: str = "") -> str:
    """一条参考资料：标题 + 出版方 + 可点击原文地址。"""
    link = (
        f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(url)}</a>'
        if url
        else '<span style="color:#8C867A;">未登记链接</span>'
    )
    note_html = f'<span class="hz-src__meta">{esc(note)}</span>' if note else ""
    return (
        '<div class="hz-src">'
        f'<span class="hz-src__idx">{index}</span>'
        "<span>"
        f'<span class="hz-src__title">{esc(title)}</span>'
        f'<span class="hz-src__meta">{esc(publisher)}</span>'
        f'<span class="hz-src__meta">{link}</span>'
        f"{note_html}"
        "</span>"
        "</div>"
    )


def figure_caption(caption: str, credit: str, source_url: str = "", license_url: str = "") -> str:
    """图片署名：图注 + 作者 + 许可 + 来源页面。"""
    parts = []
    if credit:
        parts.append(esc(credit))
    if source_url:
        parts.append(
            f'<a href="{esc(source_url)}" target="_blank" rel="noopener noreferrer">来源页面</a>'
        )
    if license_url:
        parts.append(
            f'<a href="{esc(license_url)}" target="_blank" rel="noopener noreferrer">许可原文</a>'
        )
    tail = "　·　".join(parts)
    head = esc(caption) if caption else ""
    return (
        '<div class="hz-figure" style="margin-top:.5rem;">'
        f'<span style="color:#57534A;">{head}</span>'
        f'<br/><span>{tail}</span>'
        "</div>"
    )


def count_line(text: str) -> str:
    return f'<div class="hz-count">{esc(text)}</div>'


def group_title(text: str) -> str:
    return f'<div class="hz-group-title">{esc(text)}</div>'


# --------------------------------------------------------------------------
# AI 问答（P4）
# --------------------------------------------------------------------------

#: 引用编号：与 :mod:`src.qa.prompt` 的解析规则保持一致
_CITATION_PATTERN = re.compile(r"[\[【]\s*(\d{1,3})\s*[\]】]")


def question_box(question: str, label: str = "你问") -> str:
    """回显用户提问。"""
    return (
        '<div class="hz-qbox">'
        f'<span class="hz-qbox__label">{esc(label)}</span>{esc(question)}'
        "</div>"
    )


def answer_block(text: str, valid_numbers: Sequence[int] = ()) -> str:
    """把回答渲染成 HTML，并把 ``[n]`` 变成可读的引用徽标。

    先做 HTML 转义再替换编号，因此模型输出无法注入标签；
    指向不存在资料的编号会渲染成划掉的错误样式，**不隐藏模型的错误引用**。
    """
    allowed = set(int(n) for n in valid_numbers)
    safe = esc(text)

    def _mark(match: "re.Match[str]") -> str:
        number = int(match.group(1))
        if allowed and number not in allowed:
            return f'<span class="hz-cite hz-cite--missing">{number}</span>'
        return f'<span class="hz-cite">{number}</span>'

    safe = _CITATION_PATTERN.sub(_mark, safe)
    body = safe.replace("\n", "<br/>")
    return f'<div class="hz-answer">{body}</div>'


def backend_badge(label: str, active: bool = False, available: bool = True) -> str:
    """后端状态徽标：当前生效的后端用朱砂高亮，不可用的降透明度。"""
    cls = "hz-backend"
    if active:
        cls += " hz-backend--active"
    elif not available:
        cls += " hz-backend--off"
    return f'<span class="{cls}">{esc(label)}</span>'


def hit_chips(terms: Iterable[str]) -> str:
    """命中词标签（说明这条资料为什么被检索到）。"""
    items = [t for t in terms if str(t).strip()]
    if not items:
        return ""
    return "".join(f'<span class="hz-hit">{esc(t)}</span>' for t in items)


def passage_block(
    index: int,
    title: str,
    category_name: str,
    category_color: str,
    text: str,
    source_titles: Sequence[str] = (),
    score: float = 0.0,
    hits: Sequence[str] = (),
    used: bool = True,
) -> str:
    """一条检索到的资料。``used=False`` 表示未被回答引用，会显示为次要状态。"""
    cls = "hz-passage" if used else "hz-passage hz-passage--unused"
    meta_bits = [f"相关度 {score:.2f}"]
    if not used:
        meta_bits.append("未被回答引用")
    src = ""
    if source_titles:
        src = (
            '<div class="hz-src__meta" style="margin-top:.3rem;">来源：'
            + esc("；".join(source_titles))
            + "</div>"
        )
    return (
        f'<div class="{cls}">'
        '<div class="hz-passage__head">'
        f'<span class="hz-cite">{index}</span>'
        f'<span class="hz-passage__title">{esc(title)}</span>'
        f"{category_chip(category_name, category_color)}"
        f'<span class="hz-src__meta" style="display:inline;">{esc("　·　".join(meta_bits))}</span>'
        "</div>"
        f'<div>{hit_chips(hits)}</div>'
        f'<p class="hz-passage__body">{esc(text)}</p>'
        f"{src}"
        "</div>"
    )


def note_line(text: str, kind: str = "info") -> str:
    """提示条。``kind`` 可为 ``info`` / ``ok`` / ``warn`` / ``error``。"""
    cls = "hz-note" + (f" hz-note--{kind}" if kind != "info" else "")
    return f'<div class="{cls}">{esc(text)}</div>'


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
    "table_html",
    "render",
    "render_section",
    "render_empty",
    "render_error",
    "render_footer",
    "source_item",
    "crumb",
    "category_chip",
    "entity_card",
    "detail_head",
    "relation_row",
    "source_row",
    "figure_caption",
    "count_line",
    "group_title",
    "question_box",
    "answer_block",
    "backend_badge",
    "hit_chips",
    "passage_block",
    "note_line",
]
