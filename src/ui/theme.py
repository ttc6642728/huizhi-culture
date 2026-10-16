"""设计系统：现代数字文化展馆风格的配色、字体、间距与全局样式注入。

设计关键词：简洁、现代、克制、清晰、具有文化气质。
- 背景：米白 / 暖白
- 文字：深墨色
- 点缀：徽州建筑黑白灰 + 朱砂色
- 不使用渐变、动画和无意义装饰。
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# 设计令牌 (design tokens)
# --------------------------------------------------------------------------

COLORS = {
    # 背景层
    "bg": "#FAF7F2",          # 米白主背景
    "bg_soft": "#F3EEE6",     # 次级背景 / 卡片分组
    "surface": "#FFFFFF",     # 卡片表面
    # 文字层
    "ink": "#22201C",         # 深墨色主文字
    "ink_soft": "#57534A",    # 次级文字
    "ink_mute": "#8C867A",    # 辅助 / 说明文字
    "on_accent": "#FFFFFF",
    # 线条
    "line": "#E5DED2",        # 常规边框
    "line_strong": "#D2C9B9",  # 强调边框
    # 徽州建筑黑白灰
    "stone_dark": "#3B3935",
    "stone": "#7C786F",
    "stone_light": "#D8D3C9",
    # 朱砂点缀
    "cinnabar": "#B23A2F",
    "cinnabar_soft": "#C9564A",
    "cinnabar_wash": "#F6E7E4",
    # 状态色（克制使用）
    "ok": "#3F6B4F",
    "ok_wash": "#EAF0EA",
    "warn": "#8A6A22",
    "warn_wash": "#F7F0DF",
    "error": "#9B3128",
    "error_wash": "#F8E9E7",
}

FONTS = {
    "serif": '"Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", Georgia, serif',
    "sans": '"Inter", "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", system-ui, sans-serif',
    "mono": '"JetBrains Mono", "Cascadia Code", Consolas, monospace',
}

RADIUS = {"sm": "6px", "md": "10px", "lg": "14px"}
SPACE = {"xs": "4px", "sm": "8px", "md": "16px", "lg": "24px", "xl": "40px"}


def _css() -> str:
    c = COLORS
    f = FONTS
    return f"""
<style>
/* ===== 全局基底 ===== */
.stApp {{
    background: {c['bg']};
    color: {c['ink']};
    font-family: {f['sans']};
}}
html, body, [class*="css"] {{
    font-family: {f['sans']};
}}
.block-container {{
    padding-top: 2.2rem;
    padding-bottom: 4rem;
    max-width: 1180px;
}}

/* ===== 排版 ===== */
h1, h2, h3, h4 {{
    font-family: {f['serif']};
    color: {c['ink']};
    letter-spacing: .01em;
    font-weight: 600;
}}
h1 {{ font-size: 2.05rem; line-height: 1.3; }}
h2 {{ font-size: 1.45rem; line-height: 1.35; margin-top: 1.6rem; }}
h3 {{ font-size: 1.12rem; line-height: 1.4; }}
p, li, .stMarkdown {{ color: {c['ink_soft']}; line-height: 1.78; }}
a {{ color: {c['cinnabar']}; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
code {{
    font-family: {f['mono']};
    background: {c['bg_soft']};
    border: 1px solid {c['line']};
    border-radius: {RADIUS['sm']};
    padding: 1px 5px;
    font-size: .86em;
    color: {c['stone_dark']};
}}
hr {{ border: none; border-top: 1px solid {c['line']}; margin: 1.6rem 0; }}

/* ===== 侧边栏 ===== */
[data-testid="stSidebar"] {{
    background: {c['bg_soft']};
    border-right: 1px solid {c['line']};
}}
[data-testid="stSidebar"] .block-container {{ padding-top: 1.4rem; }}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ font-size: 1rem; }}

/* 侧边栏导航按钮：整行、左对齐、无粗边框 */
[data-testid="stSidebar"] .stButton > button {{
    width: 100%;
    text-align: left;
    justify-content: flex-start;
    background: transparent;
    border: 1px solid transparent;
    color: {c['ink_soft']};
    border-radius: {RADIUS['md']};
    padding: .5rem .75rem;
    font-size: .94rem;
    font-weight: 500;
    transition: background .12s ease, color .12s ease;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: {c['surface']};
    border-color: {c['line']};
    color: {c['ink']};
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: {c['surface']};
    border-color: {c['line_strong']};
    color: {c['cinnabar']};
    font-weight: 600;
}}

/* ===== 主区域按钮 ===== */
.stButton > button {{
    background: {c['surface']};
    color: {c['ink']};
    border: 1px solid {c['line_strong']};
    border-radius: {RADIUS['md']};
    padding: .42rem .95rem;
    font-weight: 500;
    transition: border-color .12s ease, color .12s ease, background .12s ease;
}}
.stButton > button:hover {{
    border-color: {c['cinnabar']};
    color: {c['cinnabar']};
    background: {c['surface']};
}}
.stButton > button:focus:not(:active) {{
    border-color: {c['cinnabar']};
    box-shadow: 0 0 0 3px {c['cinnabar_wash']};
    color: {c['cinnabar']};
}}
.stButton > button[kind="primary"] {{
    background: {c['cinnabar']};
    border-color: {c['cinnabar']};
    color: {c['on_accent']};
}}
.stButton > button[kind="primary"]:hover {{
    background: {c['cinnabar_soft']};
    border-color: {c['cinnabar_soft']};
    color: {c['on_accent']};
}}

/* ===== 输入控件 ===== */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] {{
    background: {c['surface']};
    border-radius: {RADIUS['md']};
}}
input, textarea, [data-baseweb="select"] > div {{
    font-family: {f['sans']} !important;
    color: {c['ink']} !important;
}}
[data-testid="stTextInput"] input,
[data-testid="stChatInput"] textarea {{
    background: {c['surface']};
}}
/* 聚焦态：朱砂描边 */
.stTextInput div[data-baseweb="input"]:focus-within,
.stTextArea div[data-baseweb="textarea"]:focus-within,
.stSelectbox div[data-baseweb="select"]:focus-within {{
    border-color: {c['cinnabar']} !important;
    box-shadow: 0 0 0 3px {c['cinnabar_wash']} !important;
}}

/* ===== 标签页 ===== */
.stTabs [data-baseweb="tab-list"] {{
    gap: .35rem;
    border-bottom: 1px solid {c['line']};
}}
.stTabs [data-baseweb="tab"] {{
    color: {c['ink_mute']};
    font-weight: 500;
    padding: .4rem .8rem;
}}
.stTabs [aria-selected="true"] {{
    color: {c['cinnabar']} !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{ background: {c['cinnabar']}; }}
.stTabs [data-baseweb="tab-border"] {{ background: transparent; }}

/* ===== 展开面板 ===== */
[data-testid="stExpander"] {{
    border: 1px solid {c['line']};
    border-radius: {RADIUS['md']};
    background: {c['surface']};
}}
[data-testid="stExpander"] summary {{
    font-weight: 500;
    color: {c['ink']};
}}

/* ===== 图表 / 组件容器 ===== */
[data-testid="stImage"] img {{
    border-radius: {RADIUS['md']};
    border: 1px solid {c['line']};
}}
[data-testid="stDataFrame"] {{ border: 1px solid {c['line']}; border-radius: {RADIUS['md']}; }}
[data-testid="stMetric"] {{
    background: {c['surface']};
    border: 1px solid {c['line']};
    border-radius: {RADIUS['md']};
    padding: .8rem 1rem;
}}
[data-testid="stMetricValue"] {{
    font-family: {f['serif']};
    color: {c['ink']};
}}
[data-testid="stMetricLabel"] {{ color: {c['ink_mute']}; }}
[data-testid="stAlert"] {{ border-radius: {RADIUS['md']}; }}
[data-testid="stSpinner"] > div {{ color: {c['cinnabar']}; }}

/* ===== 自定义组件 ===== */
.hz-card {{
    background: {c['surface']};
    border: 1px solid {c['line']};
    border-radius: {RADIUS['lg']};
    padding: 1.15rem 1.3rem;
    margin-bottom: .85rem;
}}
.hz-card--flat {{ background: {c['bg_soft']}; }}
.hz-card--accent {{ border-left: 3px solid {c['cinnabar']}; }}

.hz-section-title {{
    font-family: {f['serif']};
    font-size: 1.28rem;
    font-weight: 600;
    color: {c['ink']};
    margin: 0 0 .15rem 0;
}}
.hz-section-sub {{
    font-size: .89rem;
    color: {c['ink_mute']};
    margin: 0 0 1rem 0;
}}

.hz-tag {{
    display: inline-block;
    padding: 2px 9px;
    border-radius: 999px;
    font-size: .76rem;
    line-height: 1.65;
    border: 1px solid {c['line_strong']};
    background: {c['bg_soft']};
    color: {c['ink_soft']};
    margin: 0 .35rem .35rem 0;
    white-space: nowrap;
}}
.hz-tag--accent {{
    background: {c['cinnabar_wash']};
    border-color: {c['cinnabar_wash']};
    color: {c['cinnabar']};
}}
.hz-tag--stone {{
    background: {c['surface']};
    border-color: {c['line']};
    color: {c['stone_dark']};
}}

.hz-hero {{
    background: {c['surface']};
    border: 1px solid {c['line']};
    border-radius: {RADIUS['lg']};
    padding: 2.4rem 2.2rem;
    margin-bottom: 1.6rem;
}}
.hz-hero__eyebrow {{
    font-size: .78rem;
    letter-spacing: .18em;
    text-transform: uppercase;
    color: {c['cinnabar']};
    margin-bottom: .6rem;
}}
.hz-hero__title {{
    font-family: {f['serif']};
    font-size: 2.3rem;
    line-height: 1.25;
    font-weight: 700;
    color: {c['ink']};
    margin: 0 0 .7rem 0;
}}
.hz-hero__desc {{
    font-size: 1rem;
    color: {c['ink_soft']};
    line-height: 1.8;
    max-width: 62ch;
    margin: 0;
}}

.hz-state {{
    border: 1px dashed {c['line_strong']};
    border-radius: {RADIUS['lg']};
    padding: 2.1rem 1.6rem;
    text-align: center;
    background: {c['bg_soft']};
}}
.hz-state--error {{
    border-style: solid;
    border-color: {c['error_wash']};
    background: {c['error_wash']};
}}
.hz-state__title {{
    font-family: {f['serif']};
    font-size: 1.02rem;
    font-weight: 600;
    color: {c['ink']};
    margin: 0 0 .35rem 0;
}}
.hz-state--error .hz-state__title {{ color: {c['error']}; }}
.hz-state__desc {{ font-size: .89rem; color: {c['ink_mute']}; margin: 0; }}

.hz-kv {{ display: flex; gap: .6rem; font-size: .9rem; padding: .3rem 0; }}
.hz-kv__k {{ color: {c['ink_mute']}; min-width: 5.5rem; }}
.hz-kv__v {{ color: {c['ink']}; }}

.hz-source {{
    font-size: .86rem;
    color: {c['ink_soft']};
    border-top: 1px solid {c['line']};
    padding-top: .5rem;
    margin-top: .5rem;
}}
.hz-source__idx {{
    display: inline-block;
    min-width: 1.35rem;
    height: 1.35rem;
    line-height: 1.35rem;
    text-align: center;
    border-radius: 4px;
    background: {c['cinnabar']};
    color: {c['on_accent']};
    font-size: .72rem;
    margin-right: .45rem;
    font-weight: 600;
}}

/* ===== 图谱图例 ===== */
.hz-legend {{
    display: flex;
    flex-wrap: wrap;
    gap: .45rem 1.1rem;
    margin: .3rem 0 1rem 0;
}}
.hz-legend__item {{
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    font-size: .82rem;
    color: {c['ink_soft']};
}}
.hz-legend__dot {{
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 3px;
    flex: none;
}}
.hz-legend__count {{ color: {c['ink_mute']}; font-size: .76rem; }}

/* ===== 关联路径链条 ===== */
.hz-path {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .3rem .4rem;
    padding: .2rem 0;
}}
.hz-path__node {{
    background: {c['bg_soft']};
    border: 1px solid {c['line_strong']};
    border-radius: {RADIUS['sm']};
    padding: 2px 9px;
    font-size: .84rem;
    color: {c['ink']};
    white-space: nowrap;
}}
.hz-path__node--end {{
    background: {c['cinnabar_wash']};
    border-color: {c['cinnabar_wash']};
    color: {c['cinnabar']};
    font-weight: 600;
}}
.hz-path__rel {{ font-size: .74rem; color: {c['cinnabar']}; white-space: nowrap; }}
.hz-path__arrow {{ color: {c['ink_mute']}; font-size: .8rem; }}

/* ===== 排名表 ===== */
.hz-rank {{
    width: 100%;
    border-collapse: collapse;
    font-size: .86rem;
}}
.hz-rank th {{
    text-align: left;
    color: {c['ink_mute']};
    font-weight: 500;
    font-size: .78rem;
    padding: .35rem .5rem;
    border-bottom: 1px solid {c['line']};
}}
.hz-rank td {{
    padding: .38rem .5rem;
    border-bottom: 1px solid {c['line']};
    color: {c['ink_soft']};
}}
.hz-rank td strong {{ color: {c['ink']}; }}
.hz-rank tr:last-child td {{ border-bottom: none; }}

/* ===== 步骤 / 追踪列表 ===== */
.hz-steps {{ margin: 0; padding: 0; list-style: none; }}
.hz-steps li {{
    display: flex;
    gap: .55rem;
    align-items: baseline;
    font-size: .84rem;
    color: {c['ink_soft']};
    padding: .22rem 0;
}}
.hz-steps__mark {{ color: {c['cinnabar']}; font-size: .72rem; flex: none; }}

/* 页脚 */
.hz-footer {{
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid {c['line']};
    font-size: .8rem;
    color: {c['ink_mute']};
}}
</style>
"""


def inject_theme() -> None:
    """把全局设计系统样式注入当前 Streamlit 页面。

    应在 ``st.set_page_config`` 之后、渲染任何内容之前调用一次。
    重复调用是安全的（Streamlit 会去重等价的 markdown 块）。
    """
    import streamlit as st

    st.markdown(_css(), unsafe_allow_html=True)


__all__ = ["COLORS", "FONTS", "RADIUS", "SPACE", "inject_theme"]
