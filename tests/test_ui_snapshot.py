"""界面**结构快照**回归测试。

它是什么、不是什么
------------------

它捕捉的是「页面结构被意外改动」：区块标题增删改名、使用的样式类增减、
控件（按钮 / 输入框 / 下拉）增删或换名、侧边栏导航项变化。

它**不是**像素级视觉回归——本项目没有引入浏览器截图比对，
所以**不宣称**能发现「颜色变了、间距歪了」这类纯样式问题。
快照里刻意只保留结构与文案，不含耗时、时间戳、随机数等易变内容，
否则每次运行都会误报，测试很快就会被无视。

基线文件放在 ``tests/snapshots/<页面>.txt``。页面结构**有意**变更时，
用 ``UPDATE_SNAPSHOTS=1 pytest tests/test_ui_snapshot.py`` 重新生成基线，
并在提交信息里说明改了什么、为什么改。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List

import pytest
from streamlit.testing.v1 import AppTest

APP_FILE = Path(__file__).resolve().parent.parent / "app.py"
SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"

UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"

#: 页面标识 → 需要的 session_state（详情页需要先选定实体）
PAGES: Dict[str, Dict[str, str]] = {
    "home": {},
    "explore": {},
    "detail": {"entity_id": "hongcun"},
    "graph": {},
    "ask": {},
    "about": {},
}

#: 从渲染出的 markdown 里抽取的样式类
_CLASS = re.compile(r"hz-[a-z][a-z0-9-]*")
_SECTION_TITLE = re.compile(r'class="hz-section-title"[^>]*>(.*?)</div>', re.S)
_BLOCK_TAGS = re.compile(r"<[^>]+>")
_DIGITS = re.compile(r"\d+")


def _strip_tags(text: str) -> str:
    return re.sub(r"\s+", " ", _BLOCK_TAGS.sub("", text)).strip()


def _normalise(text: str) -> str:
    """抹掉易变内容：纯数字（耗时、计数、得分）与绝对路径。"""
    text = text.replace("\\", "/")
    text = re.sub(r"[A-Za-z]:/[^\s\"'<>]+", "<path>", text)
    return _DIGITS.sub("<n>", text)


def _widgets(app: AppTest) -> List[str]:
    """控件清单：类型 + 标识 + 文案（不含当前值，值会随交互变化）。"""
    out: List[str] = []
    for kind in ("button", "text_input", "text_area", "selectbox", "radio", "checkbox", "slider"):
        collection = getattr(app, kind, None)
        if collection is None:
            continue
        for widget in collection:
            label = _normalise(str(getattr(widget, "label", "") or ""))
            key = str(getattr(widget, "key", "") or "")
            out.append(f"{kind}|{key}|{label}")
    return sorted(out)


def _snapshot(app: AppTest) -> str:
    """把一个页面的渲染结果压成可比较的文本快照。

    只统计**页面内容**：全局样式表（含 ``<style>`` 的那几块）被排除在外，
    否则每个页面记录的都会是整份主题里的类名，快照失去区分度。
    """
    all_markdown = [m.value for m in app.markdown]
    content = [v for v in all_markdown if "<style>" not in v]
    joined = "\n".join(content)

    titles = [_normalise(_strip_tags(t)) for t in _SECTION_TITLE.findall(joined)]
    classes = sorted(set(_CLASS.findall(joined)))
    widgets = _widgets(app)

    sidebar_buttons = sorted(
        _normalise(f"{getattr(b, 'key', '')}|{b.label}") for b in app.sidebar.button
    )

    lines = ["# section titles (in order)"]
    lines += [f"- {t}" for t in titles if t]
    lines += ["", "# style classes used by this page (sorted)"]
    lines += [f"- {c}" for c in classes]
    lines += ["", "# widgets (sorted)"]
    lines += [f"- {w}" for w in widgets]
    lines += ["", "# sidebar nav (sorted)"]
    lines += [f"- {b}" for b in sidebar_buttons]
    lines += ["", "# content markdown blocks", f"- {len(content)}"]
    return "\n".join(lines) + "\n"


def _render(page: str, state: Dict[str, str], monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """渲染指定页面（强制本地后端，保证离线且结果确定）。"""
    monkeypatch.setenv("QA_FORCE_LOCAL", "1")
    app = AppTest.from_file(str(APP_FILE), default_timeout=180)
    app.run()
    for key, value in state.items():
        app.session_state[key] = value
    app.session_state["page"] = page
    app.run()
    assert not app.exception, f"{page} 页抛出异常：{app.exception}"
    return app


@pytest.mark.parametrize("page", sorted(PAGES))
def test_page_structure_matches_snapshot(page: str, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _render(page, PAGES[page], monkeypatch)
    actual = _snapshot(app)
    path = SNAPSHOT_DIR / f"{page}.txt"

    if UPDATE or not path.is_file():
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        if not UPDATE:
            pytest.fail(
                f"缺少基线快照，已生成 {path.relative_to(SNAPSHOT_DIR.parent.parent)}；"
                "请检查内容无误后重新运行测试"
            )
        return

    expected = path.read_text(encoding="utf-8")
    if actual != expected:
        diff = _diff(expected, actual)
        pytest.fail(
            f"{page} 页结构发生变化（若为有意变更，请用 UPDATE_SNAPSHOTS=1 重新生成基线）：\n{diff}"
        )


def _diff(expected: str, actual: str) -> str:
    """给出精简差异：逐行比较，标出新增与缺失。"""
    exp_lines = expected.splitlines()
    act_lines = actual.splitlines()
    exp_set, act_set = set(exp_lines), set(act_lines)
    missing = [ln for ln in exp_lines if ln not in act_set]
    added = [ln for ln in act_lines if ln not in exp_set]
    parts = []
    if missing:
        parts.append("  快照中有、页面上已无：\n" + "\n".join(f"    - {ln}" for ln in missing[:20]))
    if added:
        parts.append("  页面上新出现：\n" + "\n".join(f"    + {ln}" for ln in added[:20]))
    return "\n".join(parts) if parts else "  差异仅出现在行序上"


# --------------------------------------------------------------------------
# 快照逻辑自身的测试：确认它真的能发现问题，而不是永远为真
# --------------------------------------------------------------------------


def test_normalise_removes_volatile_numbers_and_paths() -> None:
    assert _normalise("耗时：1234 ms") == "耗时：<n> ms"
    assert _normalise("E:/huizhi-culture/data/x.json") == "<path>"
    assert _normalise("命中 5 条") == _normalise("命中 9 条"), "数字差异不应触发误报"


def test_snapshot_captures_sections_classes_and_widgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snap = _snapshot(_render("home", {}, monkeypatch))
    assert "# section titles (in order)" in snap
    assert "hz-card" in snap, "样式类应被记录"
    assert any(line.startswith("- button|") for line in snap.splitlines()), "控件应被记录"
    assert "# sidebar nav (sorted)" in snap


def test_diff_reports_added_and_missing_lines() -> None:
    expected = "a\nb\n"
    actual = "a\nc\n"
    text = _diff(expected, actual)
    assert "- b" in text and "+ c" in text


def test_all_nav_pages_are_covered() -> None:
    """新增页面时必须同步加进快照，避免「新页面没人管」。"""
    from src.ui import nav

    covered = set(PAGES)
    planned = set(nav.all_page_keys())
    assert planned <= covered | {"detail"}, f"有页面未纳入结构快照：{sorted(planned - covered)}"
