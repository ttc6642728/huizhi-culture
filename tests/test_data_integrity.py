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


# --------------------------------------------------------------------------
# 一府六县
# --------------------------------------------------------------------------

#: 徽州一府六县
SIX_COUNTIES = (
    ("shexian", "歙县", "安徽省黄山市"),
    ("xiuning", "休宁", "安徽省黄山市"),
    ("yixian", "黟县", "安徽省黄山市"),
    ("qimen", "祁门", "安徽省黄山市"),
    ("jixi", "绩溪", "安徽省宣城市"),
    ("wuyuan", "婺源", "江西省上饶市"),
)


@pytest.mark.parametrize("county_id,name,location", SIX_COUNTIES)
def test_six_counties_are_present(repo: Repository, county_id: str, name: str, location: str) -> None:
    """一府六县必须作为实体存在，且所在地与史料一致。"""
    county = repo.require(county_id)
    assert county.name == name
    assert location in county.attributes.get("所在地", "")


def test_county_placement_follows_historical_record(repo: Repository) -> None:
    """《歙县徽州古城》所载置县年代必须落实到各属性中。"""
    expected = {
        "shexian": "秦（公元前 221 年）",
        "xiuning": "东汉建安十三年（208 年）",
        "yixian": "秦（公元前 221 年）",
        "qimen": "唐永泰二年（766 年）",
        "jixi": "唐永泰二年（766 年）",
        "wuyuan": "唐开元二十八年（740 年）",
    }
    assert set(expected) == {c[0] for c in SIX_COUNTIES}
    for county_id, era in expected.items():
        assert repo.require(county_id).attributes.get("置县", "").startswith(era)


def test_huizhou_has_outgoing_relations(repo: Repository) -> None:
    """徽州不能是纯汇点：必须存在以徽州为起点的关系。

    否则图谱中心只有入边，无法从「徽州」出发浏览其下辖县份。
    """
    out, inc = repo.relations_of("huizhou_region")
    assert out, "徽州没有任何出向关系"
    assert inc, "徽州应当同时保留大量入向关系"
    targets = {r.target for r in out}
    assert targets == {c[0] for c in SIX_COUNTIES}, "徽州的出向关系应指向一府六县"
    assert all(r.type == "composed_of" for r in out)


def test_counties_are_not_isolated(repo: Repository) -> None:
    """六个县都应有实际连接，不能是孤立节点。"""
    for county_id, name, _ in SIX_COUNTIES:
        assert repo.degree(county_id) > 0, f"{name} 是孤立节点"


def test_ich_declarations_point_to_correct_county(repo: Repository) -> None:
    """国家级非遗项目的申报地区必须与官方名录一致。"""
    expected = {
        "sheyan": "shexian",
        "wanan_luopan": "xiuning",
        "qiyunshan_yinyue": "xiuning",
        "huizhou_bandenglong": "xiuning",
        "mulianxi": "qimen",
        "qimen_nuowu": "qimen",
        "huizhou_ciji": "qimen",
        "huipai_penjing": "shexian",
        "zhangyitie": "shexian",
        "xiyuan_houke": "shexian",
    }
    for project_id, county_id in expected.items():
        declared = [r for r in repo.relations_of(project_id)[0] if r.type == "declared_in"]
        assert declared, f"{repo.require(project_id).name} 缺少申报地区关系"
        assert [r.target for r in declared] == [county_id]


def test_village_county_placement(repo: Repository) -> None:
    """村落所属县份应与黄山市行政区划、黟县文保清单一致。"""
    expected = {
        "hongcun": "yixian",
        "xidi": "yixian",
        "nanping": "yixian",
        "pingshan": "yixian",
        "guanlu": "yixian",
        "tangyue": "shexian",
        "xucun": "shexian",
        "yuliang": "shexian",
    }
    for village_id, county_id in expected.items():
        placed = [
            r for r in repo.relations_of(village_id)[0]
            if r.type == "located_in" and r.target == county_id
        ]
        assert placed, f"{repo.require(village_id).name} 未挂到 {repo.require(county_id).name}"


def test_six_counties_are_sourced(repo: Repository) -> None:
    """新增的县份实体与关系都必须有可核查来源。"""
    for county_id, name, _ in SIX_COUNTIES:
        county = repo.require(county_id)
        assert county.source_ids, f"{name} 没有来源"
        assert repo.sources_of(county), f"{name} 的来源无法解析"
