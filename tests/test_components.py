"""界面组件测试：转义、结构与方向表达。

这些组件把数据渲染成 HTML，因此两条底线必须成立：
1. 来自数据的文本一律转义，不能让数据里的 ``<>`` 破坏页面结构；
2. 关系方向不能画反——正向用 ``→``，反向用 ``←``。
"""

from __future__ import annotations

from src.ui import components as ui
from src.ui.theme import CATEGORY_COLORS, category_color


def test_esc_handles_dangerous_text() -> None:
    assert ui.esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert ui.esc('a "b" & c') == "a &quot;b&quot; &amp; c"
    assert ui.esc(None) == ""


def test_entity_card_escapes_data() -> None:
    html = ui.entity_card(
        name="<b>宏村</b>",
        summary="含 <script> 的摘要",
        category_name="古村落",
        category_color="#7A7355",
        degree=3,
        relation_count=4,
        source_count=2,
        has_image=True,
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert 'class="hz-ecard"' in html
    assert "关联关系 4" in html
    assert "含图" in html


def test_entity_card_without_image_hides_badge() -> None:
    html = ui.entity_card("宏村", "摘要", "古村落", "#7A7355", 3, 4, 2, has_image=False)
    assert "含图" not in html


def test_relation_row_direction_arrows() -> None:
    out_row = ui.relation_row("out", "位于", "徽州", "宏村位于徽州。", 2)
    in_row = ui.relation_row("in", "辖有", "歙县", "", 0)
    assert "→" in out_row and "←" not in out_row
    assert "←" in in_row and "→" not in in_row
    assert "hz-rel__dir--in" in in_row
    assert "2 条来源" in out_row
    assert "条来源" not in in_row, "来源数为 0 时不应显示来源计数"


def test_category_chip_uses_category_color() -> None:
    color = category_color("food")
    html = ui.category_chip("徽菜饮食", color)
    assert color in html
    assert "徽菜饮食" in html


def test_category_color_fallback() -> None:
    assert category_color("no-such-category") == "#8C867A"
    assert set(CATEGORY_COLORS) >= {"village", "nature", "food"}


def test_source_row_link_is_clickable_and_target_blank() -> None:
    html = ui.source_row(1, "黄山市非遗名录", "黄山市人民政府", "https://example.com/a", "备注")
    assert 'href="https://example.com/a"' in html
    assert 'target="_blank"' in html
    assert "rel=\"noopener noreferrer\"" in html


def test_source_row_without_url_is_marked() -> None:
    html = ui.source_row(1, "无链接来源", "某出版方", "")
    assert "未登记链接" in html
    assert "<a href" not in html


def test_figure_caption_includes_credit_and_links() -> None:
    html = ui.figure_caption(
        caption="宏村月沼",
        credit="某摄影师 · CC BY-SA 4.0",
        source_url="https://commons.wikimedia.org/wiki/File:A.jpg",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
    )
    assert "某摄影师" in html
    assert html.count("<a href") == 2


def test_crumb_escapes() -> None:
    html = ui.crumb(["徽州文化", "<img>"])
    assert "<img>" not in html
    assert "&lt;img&gt;" in html


def test_table_html_escapes_headers_and_handles_empty_rows() -> None:
    html = ui.table_html(["<h>"], [[ui.esc("值")]])
    assert "&lt;h&gt;" in html
    empty = ui.table_html(["列"], [])
    assert "暂无数据" in empty


def test_group_title_and_count_line_escape() -> None:
    assert "&lt;x&gt;" in ui.group_title("<x>")
    assert "&lt;y&gt;" in ui.count_line("<y>")
