"""界面层的共享数据入口（带 Streamlit 缓存）。

把「取仓储 / 取图片库」集中到这里，页面只调用这几个函数：
- 数据文件很大时不会在每次交互里重复解析；
- 数据加载失败时抛出 :class:`~src.data.loader.DataError`，由页面统一转成错误状态；
- 页面之间共享同一份实例，避免同一实体在不同页面显示不一致。
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.data.images import ImageLibrary
from src.data.loader import load_dataset
from src.data.repository import Repository


@st.cache_resource(show_spinner=False)
def repository() -> Repository:
    """实体仓储（进程内复用）。

    Raises:
        DataError: 数据文件缺失或校验不通过。
    """
    return Repository(load_dataset())


@st.cache_resource(show_spinner=False)
def images() -> ImageLibrary:
    """图片库。清单不存在时返回空库（属正常状态，不是错误）。"""
    return ImageLibrary(config.BASE_DIR)


__all__ = ["repository", "images"]
