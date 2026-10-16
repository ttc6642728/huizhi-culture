"""图谱运行时：进程内缓存的全量图谱（界面专用适配层）。

``builder`` / ``analysis`` / ``visualize`` 三个模块刻意保持**纯 Python、不依赖
Streamlit**，以便独立单元测试。本模块是它们与界面之间的缓存适配层：
把「加载数据集 → 建图」的结果在 Streamlit 会话内复用，避免每次重跑都重建。
"""

from __future__ import annotations

from typing import Tuple

import networkx as nx
import streamlit as st

from src.data.loader import load_dataset
from src.graph.builder import build_graph


@st.cache_resource(show_spinner=False)
def get_graph() -> nx.MultiDiGraph:
    """全量知识图谱（数据文件更新后需重启应用或清缓存）。"""
    return build_graph(load_dataset())


def signature(graph: nx.MultiDiGraph) -> Tuple[int, int, str]:
    """图的轻量指纹：``(节点数, 边数, 数据版本)``。

    用作 ``st.cache_data`` 的缓存键——数据文件变化时键随之改变，缓存自动失效。
    """
    return (
        graph.number_of_nodes(),
        graph.number_of_edges(),
        str(graph.graph.get("version", "")),
    )


def clear() -> None:
    """清除图谱缓存（数据变更后调用）。"""
    get_graph.clear()


__all__ = ["get_graph", "signature", "clear"]
