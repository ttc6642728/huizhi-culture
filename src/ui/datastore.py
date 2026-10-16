"""界面层的共享数据入口（带 Streamlit 缓存）。

把「取仓储 / 取图片库 / 取问答引擎 / 取智能体工作流」集中到这里，页面只调用这几个函数：
- 数据文件很大时不会在每次交互里重复解析；
- 检索索引与后端链只构建一次，避免每次提问都重新分词建索引；
- 数据加载失败时抛出 :class:`~src.data.loader.DataError`，由页面统一转成错误状态；
- 页面之间共享同一份实例，避免同一实体在不同页面显示不一致。
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.agent.workflow import AgentWorkflow
from src.data.images import ImageLibrary
from src.data.loader import load_dataset
from src.data.repository import Repository
from src.qa.engine import QAEngine
from src.qa.retriever import Retriever


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


@st.cache_resource(show_spinner=False)
def _retriever() -> Retriever:
    """检索索引（分词与 BM25 统计只算一次）。"""
    return Retriever(repository(), top_k=config.qa_top_k())


def qa_engine() -> QAEngine:
    """问答引擎。

    索引（较重）走缓存；后端链每次按当前配置重建——
    这样改完 ``.env`` 刷新页面就生效，不需要清缓存，
    测试里也能通过环境变量切换后端。
    """
    return QAEngine(repository(), retriever=_retriever())


def agent_workflow() -> AgentWorkflow:
    """可追踪工作流。

    与 :func:`qa_engine` 一样每次新建：工作流本身很轻（只持有仓储、引擎与时钟），
    但它内部的引擎必须能看到最新的后端配置。
    """
    return AgentWorkflow(repository(), engine=qa_engine())


__all__ = ["repository", "images", "qa_engine", "agent_workflow"]
