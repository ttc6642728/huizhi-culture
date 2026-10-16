"""导航模型测试：路由解析、导航高亮、页面注册完整性。

导航规则集中在一处之后，这里用纯函数把边界情况钉死：
非法页面必须回退到默认页，隐藏页必须映射到正确的父导航项。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ui import nav

PAGES_DIR = Path(__file__).resolve().parent.parent / "src" / "ui" / "pages"


def test_default_page_is_in_nav() -> None:
    assert nav.DEFAULT_PAGE in nav.nav_keys()


@pytest.mark.parametrize(
    "page,expected",
    [
        ("home", "home"),
        ("explore", "explore"),
        ("graph", "graph"),
        ("ask", "ask"),
        ("about", "about"),
        ("detail", "detail"),          # 隐藏页可路由
        ("not-a-page", nav.DEFAULT_PAGE),
        ("", nav.DEFAULT_PAGE),
        (None, nav.DEFAULT_PAGE),
        ("Home", nav.DEFAULT_PAGE),    # 区分大小写，避免拼写错误被静默接受
    ],
)
def test_resolve_route(page, expected: str) -> None:
    assert nav.resolve_route(page) == expected


def test_hidden_page_maps_to_parent_highlight() -> None:
    """隐藏的详情页应把「文化百科」这一导航项点亮。"""
    assert nav.highlight_of("detail") == "explore"
    assert nav.highlight_of("explore") == "explore"
    for key in nav.nav_keys():
        assert nav.highlight_of(key) == key


def test_label_of_hidden_page() -> None:
    assert nav.label_of("detail") == "文化百科"
    assert nav.label_of("graph") == "知识图谱"


def test_all_page_keys_covers_nav_and_hidden() -> None:
    keys = set(nav.all_page_keys())
    assert set(nav.nav_keys()) <= keys
    assert set(nav.HIDDEN_PAGES) <= keys
    assert len(keys) == len(nav.all_page_keys()), "页面 key 不应重复"


def test_nav_item_is_either_implemented_or_marked_pending() -> None:
    """每个导航项要么有真实模块，要么如实标注了交付阶段。

    不允许出现「既没有模块、也没标阶段」的入口——那会变成一个点了就报错的空按钮。
    """
    for item in nav.NAV_ITEMS:
        module_path = PAGES_DIR / f"{item['key']}.py"
        if module_path.is_file():
            continue
        assert item["phase"], f"导航项 {item['key']} 既无页面模块，也未标注交付阶段"


def test_hidden_page_module_exists() -> None:
    for key in nav.HIDDEN_PAGES:
        assert (PAGES_DIR / f"{key}.py").is_file(), f"隐藏页 {key} 缺少模块"
