"""检索层测试：分词、BM25 排序、可溯源性。

这些测试**不联网**，只依赖本地数据文件，因此可离线复现。
"""

from __future__ import annotations

import pytest

from src.data.loader import load_dataset
from src.data.repository import Repository
from src.qa.retriever import (
    MAX_DOC_CHARS,
    STOPWORDS,
    Passage,
    Retriever,
    tokenize,
)


@pytest.fixture(scope="module")
def repo() -> Repository:
    return Repository(load_dataset())


@pytest.fixture(scope="module")
def retriever(repo: Repository) -> Retriever:
    return Retriever(repo, top_k=5)


# --------------------------------------------------------------------------
# 分词
# --------------------------------------------------------------------------


def test_tokenize_splits_chinese_into_words() -> None:
    tokens = tokenize("徽州宏村承志堂是徽派民居的代表")
    assert "徽州" in tokens
    assert "宏村" in tokens
    assert "承志堂" in tokens


def test_tokenize_drops_stopwords_and_punctuation() -> None:
    tokens = tokenize("的和是了，。！？ the of and")
    assert tokens == (), f"停用词与标点应被过滤，实际得到 {tokens}"
    assert "的" in STOPWORDS and "the" in STOPWORDS


def test_tokenize_is_case_insensitive() -> None:
    assert "hongcun" in tokenize("Hongcun")


def test_tokenize_is_cached_and_stable() -> None:
    first = tokenize("徽州三雕")
    second = tokenize("徽州三雕")
    assert first == second
    assert first is second, "同一段文本应命中缓存，避免重复分词"


# --------------------------------------------------------------------------
# 检索排序
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query, expected_first",
    [
        ("宏村", "宏村"),
        ("西递", "西递"),
        ("宏村和西递有什么关系", "宏村"),
        ("马头墙有什么特点", "马头墙"),
        ("徽州三雕是什么", "徽州三雕"),
        ("程大位", "程大位"),
    ],
)
def test_relevant_entity_ranks_first(
    retriever: Retriever, query: str, expected_first: str
) -> None:
    hits = retriever.retrieve(query)
    assert hits, f"「{query}」应当检索到资料"
    assert hits[0].title == expected_first, (
        f"「{query}」的首位应为 {expected_first}，实际为 {hits[0].title}"
    )


def test_entity_exact_name_outranks_compound_names(retriever: Retriever) -> None:
    """「徽州」这种被大量实体复用的词，必须让实体本身排在派生名称之前。"""
    hits = retriever.retrieve("徽州")
    assert hits[0].title == "徽州"
    assert hits[0].score > hits[1].score, "实体本身必须明显高于派生名称"


def test_alias_is_searchable(retriever: Retriever, repo: Repository) -> None:
    """实体别名也要能检索到——数据里登记了别名就是要用上的。"""
    target = next((e for e in repo.entities if e.aliases), None)
    assert target is not None, "数据集中应当存在带别名的实体"
    hits = retriever.retrieve(target.aliases[0])
    assert hits, f"别名「{target.aliases[0]}」应当检索到资料"
    assert target.id in {h.entity_id for h in hits}


def test_relation_text_is_indexed(retriever: Retriever, repo: Repository) -> None:
    """关系叙述必须进索引，否则「宏村属于哪个县」这类问题检索不到。"""
    hits = retriever.retrieve("宏村 黟县")
    assert hits, "应当能通过关系检索到资料"
    by_id = {h.entity_id: h for h in hits}
    assert "hongcun" in by_id, "同时检索两个实体时应同时召回"
    assert "黟县" in by_id["hongcun"].text, "宏村的资料里应包含所属县份（来自关系叙述）"


def test_scores_are_non_increasing(retriever: Retriever) -> None:
    hits = retriever.retrieve("徽州文化")
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True), "结果必须按相关度降序"


# --------------------------------------------------------------------------
# 边界情况
# --------------------------------------------------------------------------


def test_empty_query_returns_nothing(retriever: Retriever) -> None:
    assert retriever.retrieve("") == []
    assert retriever.retrieve("   ") == []


def test_punctuation_only_query_returns_nothing(retriever: Retriever) -> None:
    assert retriever.retrieve("？？？") == []
    assert retriever.retrieve("，。！") == []


def test_stopword_only_query_returns_nothing(retriever: Retriever) -> None:
    assert retriever.retrieve("的是什么") == [], "纯虚词查询不应返回任何结果"


def test_unrelated_topic_returns_nothing(retriever: Retriever) -> None:
    """词表中不存在的词不应命中任何资料——检索不到就是检索不到，不凑数。"""
    assert retriever.retrieve("xylophone quantum entanglement") == []
    assert retriever.retrieve("zzzqqqxx") == []
    assert retriever.retrieve("абракадабра") == []


def test_top_k_is_respected(retriever: Retriever) -> None:
    assert len(retriever.retrieve("徽州", top_k=2)) <= 2
    assert len(retriever.retrieve("徽州", top_k=1)) <= 1
    assert len(retriever.retrieve("徽州")) <= retriever.top_k


def test_retrieve_one_returns_single(retriever: Retriever) -> None:
    one = retriever.retrieve_one("宏村")
    assert one is not None and one.title == "宏村"
    assert retriever.retrieve_one("zzzqqqxx") is None


# --------------------------------------------------------------------------
# 结果质量与可溯源性
# --------------------------------------------------------------------------


def test_every_passage_carries_sources(retriever: Retriever) -> None:
    """可溯源是硬要求：每条检索结果的来源都不能为空。"""
    for query in ("宏村", "徽州三雕", "徽商", "黄山"):
        for passage in retriever.retrieve(query):
            assert passage.sources, f"「{query}」的 {passage.title} 没有来源"
            assert all(s.url for s in passage.sources), "来源必须有可点击地址"
            assert passage.citation, "每条资料都应能给出引用串"


def test_passage_text_is_bounded(retriever: Retriever) -> None:
    for passage in retriever.retrieve("徽州"):
        assert len(passage.text) <= MAX_DOC_CHARS + 1  # 截断会补一个省略号
        assert passage.text.strip(), "正文不应为空"


def test_passage_records_matched_terms(retriever: Retriever) -> None:
    hits = retriever.retrieve("马头墙 徽派建筑")
    assert hits
    assert hits[0].matched_terms, "应记录命中的词，便于界面解释为什么检索到这条"
    assert all(isinstance(t, str) and t for t in hits[0].matched_terms)


def test_passage_is_frozen() -> None:
    passage = Passage(
        entity_id="x",
        title="t",
        category_name="c",
        text="body",
        score=1.0,
        matched_terms=("a",),
        sources=(),
        relation_count=0,
    )
    with pytest.raises(Exception):
        passage.title = "changed"  # type: ignore[misc]


# --------------------------------------------------------------------------
# 索引统计
# --------------------------------------------------------------------------


def test_document_count_matches_sourced_entities(retriever: Retriever, repo: Repository) -> None:
    """只有「有来源」的实体才进索引——没有来源的内容不进检索结果。"""
    sourced = [e for e in repo.entities if e.source_ids]
    assert retriever.document_count == len(sourced)
    assert retriever.document_count > 0


def test_stats_reports_index_shape(retriever: Retriever) -> None:
    stats = retriever.stats()
    assert stats["documents"] > 0
    assert stats["vocabulary"] > stats["documents"]
    assert stats["avg_length"] > 0
    assert stats["top_k"] == retriever.top_k


def test_metric_retrieval_is_deterministic(retriever: Retriever) -> None:
    """同样的查询必须给出同样的排序，否则界面结果无法复现。"""
    first = [(h.entity_id, h.score) for h in retriever.retrieve("徽州文化")]
    second = [(h.entity_id, h.score) for h in retriever.retrieve("徽州文化")]
    assert first == second
