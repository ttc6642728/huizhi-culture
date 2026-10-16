"""真实数据文件完整性测试。

这些测试直接校验 ``data/*.json``，把「文化事实必须有可核查来源」这一原则固化为可执行的检查。
数据被误改（来源丢失、id 断链、事实性字段被清空）时测试会立即失败。
"""

from __future__ import annotations

import re

import pytest

from src.data.loader import Dataset, dataset_summary, load_dataset, validate_dataset
from src.data.repository import Repository

#: 项目规模下限，防止数据被意外截断
MIN_ENTITIES = 70
MIN_RELATIONS = 120
MIN_SOURCES = 20
MIN_CATEGORIES = 10


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return load_dataset()


@pytest.fixture(scope="module")
def repo(dataset: Dataset) -> Repository:
    return Repository(dataset)


def test_dataset_loads_and_passes_validation(dataset: Dataset) -> None:
    """加载成功即说明文件存在且 JSON 合法；校验必须零问题。"""
    assert validate_dataset(dataset) == []


def test_dataset_scale_meets_minimum(dataset: Dataset) -> None:
    summary = dataset_summary(dataset)
    assert summary["entities"] >= MIN_ENTITIES, f"实体过少：{summary['entities']}"
    assert summary["relations"] >= MIN_RELATIONS, f"关系过少：{summary['relations']}"
    assert summary["sources"] >= MIN_SOURCES, f"来源过少：{summary['sources']}"
    assert summary["categories"] >= MIN_CATEGORIES, f"分类过少：{summary['categories']}"


def test_all_ids_unique(dataset: Dataset) -> None:
    entity_ids = [e.id for e in dataset.entities]
    relation_ids = [r.id for r in dataset.relations]
    source_ids = [s.id for s in dataset.sources]
    assert len(entity_ids) == len(set(entity_ids))
    assert len(relation_ids) == len(set(relation_ids))
    assert len(source_ids) == len(set(source_ids))


def test_every_entity_is_sourced_and_described(dataset: Dataset) -> None:
    """每个实体都必须有来源、摘要与正文，且来源均可解析。"""
    for entity in dataset.entities:
        assert entity.source_ids, f"{entity.name} 未标注来源"
        assert len(entity.summary) >= 8, f"{entity.name} 的摘要过短"
        assert len(entity.description) >= 20, f"{entity.name} 的正文过短"
        assert entity.attributes, f"{entity.name} 缺少结构化属性"
        for sid in entity.source_ids:
            assert dataset.get_source(sid) is not None, f"{entity.name} 的来源 {sid} 不存在"


def test_all_sources_have_resolvable_url(dataset: Dataset) -> None:
    """来源必须带有可访问的 http(s) 地址。"""
    for source in dataset.sources:
        assert re.match(r"^https?://", source.url), f"来源 {source.id} 的 url 非法：{source.url!r}"
        assert source.publisher, f"来源 {source.id} 缺少出版方"
        assert source.accessed, f"来源 {source.id} 缺少访问日期"


def test_no_isolated_entities(repo: Repository) -> None:
    """所有实体都至少有一条关系，保证图谱连通可用。"""
    isolated = [e.name for e in repo.entities if repo.is_isolated(e.id)]
    assert isolated == [], f"存在孤立实体：{isolated}"


def test_every_relation_is_sourced(dataset: Dataset) -> None:
    for rel in dataset.relations:
        assert rel.source_ids, f"关系 {rel.id} 未标注来源"
        for sid in rel.source_ids:
            assert dataset.get_source(sid) is not None, f"关系 {rel.id} 的来源 {sid} 不存在"


def test_every_category_is_used(dataset: Dataset, repo: Repository) -> None:
    """不允许出现空分类。"""
    for cc in repo.category_counts():
        assert cc.count > 0, f"分类「{cc.category.name}」下没有任何实体"


# --------------------------------------------------------------------------
# 关键事实抽查：防止事实性内容被误改
# --------------------------------------------------------------------------


def test_world_heritage_facts(repo: Repository) -> None:
    """西递、宏村、黄山的遗产地位必须有明确标注。"""
    hongcun = repo.require("hongcun")
    xidi = repo.require("xidi")
    huangshan = repo.require("huangshan")

    assert "1002" in hongcun.attributes.get("遗产地位", "")
    assert "2000" in hongcun.attributes.get("遗产地位", "")
    assert "1047" in xidi.attributes.get("始建", "")
    assert "547" in huangshan.attributes.get("遗产类型", "")
    assert "1990" in huangshan.attributes.get("遗产类型", "")
    assert "双重遗产" in huangshan.attributes.get("遗产类型", "")


def test_unesco_sources_are_present(dataset: Dataset) -> None:
    """UNESCO 官方条目必须作为来源存在，并带有 whc.unesco.org 地址。"""
    ids = {s.id for s in dataset.sources}
    assert {"src_unesco_1002", "src_unesco_547"} <= ids
    for sid in ("src_unesco_1002", "src_unesco_547"):
        source = dataset.get_source(sid)
        assert source is not None and "whc.unesco.org" in source.url


def test_intangible_heritage_batch_facts(repo: Repository) -> None:
    """非遗项目的批次与申报地区须与黄山市官方名录一致。"""
    assert "2006" in repo.require("huiju").attributes.get("名录批次", "")
    assert "婺源" in repo.require("huiju").attributes.get("申报地区", "")
    assert "2006" in repo.require("huimo").attributes.get("名录批次", "")
    assert repo.require("wanan_luopan").attributes.get("申报地区") == "黄山市休宁县"
    assert "2021" in repo.require("huicai").attributes.get("非遗编号", "")


def test_architecture_facts(repo: Repository) -> None:
    """徽州古建三绝与牌坊群的关键数字应保持稳定。"""
    sandiao = repo.require("xuguo_shifang")
    assert "1584" in sandiao.attributes.get("立坊时间", "")

    paifang = repo.require("tangyue_paifangqun")
    assert "七座" in paifang.attributes.get("牌坊数量", "")

    arch = repo.require("huipai_architecture")
    assert "民居、祠堂、牌坊" == arch.attributes.get("古建三绝")


def test_person_ranking_facts(repo: Repository) -> None:
    """「千年徽州杰出历史人物评选」名次应与官方页面一致。"""
    assert "第一位" in repo.require("taoxingzhi").attributes.get("评选名次", "")
    assert "第二位" in repo.require("zhuxi").attributes.get("评选名次", "")
    assert "第三位" in repo.require("hushi").attributes.get("评选名次", "")


def test_category_names_match_approved_dimensions(repo: Repository) -> None:
    """十个既定分类必须存在且命名稳定。"""
    names = [c.name for c in repo.categories()]
    for expected in [
        "古村落",
        "徽派建筑",
        "非物质文化遗产",
        "历史名人",
        "徽商",
        "传统工艺与艺术",
        "民俗节庆",
        "徽菜饮食",
        "宗族与文教",
        "文献典籍",
    ]:
        assert expected in names, f"缺少既定分类：{expected}"
