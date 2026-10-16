"""仓储查询能力测试：检索、筛选、详情、关联、子图、路径与统计。"""

from __future__ import annotations

import pytest

from src.data.loader import Dataset, load_dataset
from src.data.repository import Repository


@pytest.fixture(scope="module")
def repo() -> Repository:
    return Repository(load_dataset())


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return load_dataset()


# --------------------------------------------------------------------------
# 检索
# --------------------------------------------------------------------------


def test_search_exact_name_ranks_first(repo: Repository) -> None:
    hits = repo.search("宏村")
    assert hits, "未检索到「宏村」"
    assert hits[0].name == "宏村"
    assert hits[0].matched_field in {"名称", "别名"}
    assert hits[0].matched_all is True


def test_search_by_alias(repo: Repository) -> None:
    """别名「八脚牌楼」应命中许国石坊。"""
    hits = repo.search("八脚牌楼")
    assert hits and hits[0].entity.id == "xuguo_shifang"


def test_search_multi_term_prefers_full_match(repo: Repository) -> None:
    hits = repo.search("徽州 三雕")
    assert hits
    assert hits[0].matched_all is True
    assert hits[0].entity.id in {"huizhou_sandiao", "huizhou_sidiao"}


def test_search_returns_empty_for_unknown_term(repo: Repository) -> None:
    assert repo.search("这是一个完全不存在的词条xyzzy") == []


def test_search_returns_empty_for_blank_query(repo: Repository) -> None:
    assert repo.search("   ") == []
    assert repo.search("") == []


def test_search_respects_category_filter(repo: Repository) -> None:
    hits = repo.search("徽州", category="food")
    assert hits, "徽菜饮食分类下未检索到「徽州」"
    assert all(h.entity.category == "food" for h in hits)


def test_search_limit_applies(repo: Repository) -> None:
    assert len(repo.search("徽州", limit=3)) == 3


def test_search_is_deterministic(repo: Repository) -> None:
    first = [h.entity.id for h in repo.search("徽州建筑")]
    second = [h.entity.id for h in repo.search("徽州建筑")]
    assert first == second


# --------------------------------------------------------------------------
# 详情与分类
# --------------------------------------------------------------------------


def test_get_entity_and_require(repo: Repository) -> None:
    assert repo.get("hongcun") is not None
    assert repo.get("not-exist") is None
    with pytest.raises(KeyError):
        repo.require("not-exist")


def test_entity_by_name_supports_alias(repo: Repository) -> None:
    assert repo.entity_by_name("江苏") is None
    assert repo.entity_by_name("胡适一品锅") is not None
    assert repo.entity_by_name("胡适一品锅").id == "yipin_guo"  # type: ignore[union-attr]


def test_category_counts_sum_equals_entity_count(repo: Repository) -> None:
    assert sum(cc.count for cc in repo.category_counts()) == len(repo.entities)


def test_by_category_only_returns_that_category(repo: Repository) -> None:
    villages = repo.by_category("village")
    assert villages
    assert all(e.category == "village" for e in villages)


def test_sources_of_entity_resolve(repo: Repository) -> None:
    sources = repo.sources_of_entity("hongcun")
    assert sources, "宏村应有来源"
    assert all(s.url.startswith("http") for s in sources)


# --------------------------------------------------------------------------
# 关联关系
# --------------------------------------------------------------------------


def test_neighbors_include_expected_relation(repo: Repository) -> None:
    """承志堂属于宏村，宏村的邻居中应同时出现它。"""
    names = {nb.entity.name for nb in repo.neighbors("hongcun")}
    assert "承志堂" in names


def test_neighbor_direction_is_reported(repo: Repository) -> None:
    """承志堂 → 宏村 为 part_of；从宏村看该邻居方向应为 in。"""
    target = [nb for nb in repo.neighbors("hongcun") if nb.entity.id == "chengzhitang"]
    assert target and target[0].direction == "in"

    from_hongcun = [nb for nb in repo.neighbors("hongcun") if nb.entity.id == "huizhou_region"]
    assert from_hongcun and from_hongcun[0].direction == "out"


def test_neighbors_relation_type_filter(repo: Repository) -> None:
    only_part_of = repo.neighbors("huipai_architecture", relation_type="part_of")
    assert only_part_of
    assert all(nb.relation.type == "part_of" for nb in only_part_of)


def test_neighbors_of_missing_entity_raises(repo: Repository) -> None:
    with pytest.raises(KeyError):
        repo.neighbors("not-exist")


def test_subgraph_contains_center_and_grows_with_radius(repo: Repository) -> None:
    r0 = repo.subgraph_ids("hongcun", radius=0)
    r1 = repo.subgraph_ids("hongcun", radius=1)
    r2 = repo.subgraph_ids("hongcun", radius=2)

    assert r0 == ["hongcun"]
    assert set(r0) <= set(r1) <= set(r2)
    assert len(r1) > len(r0)
    assert len(r2) >= len(r1)


def test_shortest_path_between_connected_entities(repo: Repository) -> None:
    path = repo.shortest_path("chengzhitang", "huizhou_region")
    assert path is not None
    assert path[0] == "chengzhitang"
    assert path[-1] == "huizhou_region"


def test_shortest_path_same_node(repo: Repository) -> None:
    assert repo.shortest_path("hongcun", "hongcun") == ["hongcun"]


def test_shortest_path_unknown_entity_raises(repo: Repository) -> None:
    with pytest.raises(KeyError):
        repo.shortest_path("hongcun", "not-exist")


def test_degree_matches_neighbor_count(repo: Repository) -> None:
    assert repo.degree("huishang") == len(repo.neighbors("huishang"))


# --------------------------------------------------------------------------
# 统计
# --------------------------------------------------------------------------


def test_stats_relation_counts_sum_to_total(repo: Repository) -> None:
    stats = repo.stats()
    total = sum(stats["relation_type_counts"].values())  # type: ignore[union-attr]
    assert total == len(repo.relations)


def test_stats_top_connected_is_sorted(repo: Repository) -> None:
    top = repo.stats()["top_connected"]  # type: ignore[assignment]
    degrees = [row["degree"] for row in top]  # type: ignore[index]
    assert degrees == sorted(degrees, reverse=True)
    assert len(top) <= 10


def test_stats_entity_count_matches(repo: Repository) -> None:
    assert repo.stats()["entity_count"] == len(repo.entities)
