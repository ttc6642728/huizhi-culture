"""数据加载与校验的边界测试。

使用人工构造的小数据集，验证 :func:`validate_dataset` 能捕获各类数据缺陷。
这些测试保证「数据出问题时一定会在开发阶段暴露，而不是在界面上悄悄降级」。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pytest

from src.data import loader
from src.data.loader import (
    Category,
    DataError,
    DataFileMissingError,
    Dataset,
    DatasetError,
    Entity,
    Relation,
    RelationType,
    Source,
    load_dataset,
    validate_dataset,
)


# --------------------------------------------------------------------------
# 构造工具
# --------------------------------------------------------------------------


def _source(sid: str = "s1") -> Source:
    return Source(id=sid, type="government", title="测试来源", publisher="测试机构",
                  url="https://example.com/a", accessed="2026-10-16")


def _category(cid: str = "c1") -> Category:
    return Category(id=cid, name="测试分类", order=1, description="")


def _rtype(tid: str = "t1") -> RelationType:
    return RelationType(id=tid, name="相关", inverse_name="相关", description="")


def _entity(eid: str = "e1", category: str = "c1", sources: Sequence[str] = ("s1",)) -> Entity:
    return Entity(
        id=eid,
        name=f"实体{eid}",
        category=category,
        summary="这是一个用于测试的实体摘要。",
        description="这是一个用于测试的实体详细描述，长度足够通过校验。",
        attributes={"属性": "值"},
        source_ids=tuple(sources),
    )


def _relation(rid: str = "r1", source: str = "e1", target: str = "e2",
              type_: str = "t1", sources: Sequence[str] = ("s1",)) -> Relation:
    return Relation(id=rid, source=source, target=target, type=type_,
                    label="相关", source_ids=tuple(sources))


def _dataset(
    entities: Optional[List[Entity]] = None,
    relations: Optional[List[Relation]] = None,
    sources: Optional[List[Source]] = None,
    categories: Optional[List[Category]] = None,
    relation_types: Optional[List[RelationType]] = None,
) -> Dataset:
    return Dataset(
        entities=tuple(entities if entities is not None else [_entity("e1"), _entity("e2")]),
        relations=tuple(relations if relations is not None else [_relation()]),
        sources=tuple(sources if sources is not None else [_source()]),
        categories=tuple(categories if categories is not None else [_category()]),
        relation_types=tuple(relation_types if relation_types is not None else [_rtype()]),
    )


def _issues_containing(issues: Sequence[str], needle: str) -> bool:
    return any(needle in i for i in issues)


# --------------------------------------------------------------------------
# 基线
# --------------------------------------------------------------------------


def test_valid_synthetic_dataset_has_no_issues() -> None:
    assert validate_dataset(_dataset()) == []


# --------------------------------------------------------------------------
# 实体缺陷
# --------------------------------------------------------------------------


def test_missing_required_entity_field_is_reported() -> None:
    bad = Entity(id="e1", name="", category="c1", summary="s", description="d",
                 source_ids=("s1",))
    issues = validate_dataset(_dataset(entities=[bad, _entity("e2")]))
    assert _issues_containing(issues, "缺少必填字段 name")


def test_duplicate_entity_id_is_reported() -> None:
    issues = validate_dataset(_dataset(entities=[_entity("e1"), _entity("e1")]))
    assert _issues_containing(issues, "实体 id 重复：e1")


def test_unknown_entity_category_is_reported() -> None:
    issues = validate_dataset(_dataset(entities=[_entity("e1"), _entity("e2", category="nope")]))
    assert _issues_containing(issues, "未在 categories 中定义")


def test_entity_without_source_is_reported() -> None:
    issues = validate_dataset(_dataset(entities=[_entity("e1", sources=()), _entity("e2")]))
    assert _issues_containing(issues, "未标注任何来源")


def test_entity_with_dangling_source_reference_is_reported() -> None:
    issues = validate_dataset(_dataset(entities=[_entity("e1", sources=("ghost",)), _entity("e2")]))
    assert _issues_containing(issues, "引用了不存在的来源 'ghost'")


# --------------------------------------------------------------------------
# 关系缺陷
# --------------------------------------------------------------------------


def test_relation_with_unknown_endpoint_is_reported() -> None:
    issues = validate_dataset(_dataset(relations=[_relation(target="ghost")]))
    assert _issues_containing(issues, "target 'ghost' 不存在")


def test_relation_with_unknown_type_is_reported() -> None:
    issues = validate_dataset(_dataset(relations=[_relation(type_="ghost")]))
    assert _issues_containing(issues, "关系类型 'ghost' 未在 relation_types 中定义")


def test_duplicate_relation_triple_is_reported() -> None:
    issues = validate_dataset(_dataset(relations=[_relation("r1"), _relation("r2")]))
    assert _issues_containing(issues, "重复关系")


def test_self_loop_relation_is_reported() -> None:
    issues = validate_dataset(_dataset(relations=[_relation(source="e1", target="e1")]))
    assert _issues_containing(issues, "自环")


def test_relation_without_source_is_reported() -> None:
    issues = validate_dataset(_dataset(relations=[_relation(sources=())]))
    assert _issues_containing(issues, "未标注任何来源")


def test_duplicate_relation_id_is_reported() -> None:
    issues = validate_dataset(
        _dataset(relations=[_relation("r1", target="e2"), _relation("r1", source="e2", target="e1")])
    )
    assert _issues_containing(issues, "关系 id 重复：r1")


# --------------------------------------------------------------------------
# 来源与分类
# --------------------------------------------------------------------------


def test_source_without_url_is_reported() -> None:
    bad = Source(id="s1", type="government", title="无链接", publisher="p", url="")
    issues = validate_dataset(_dataset(sources=[bad], entities=[_entity("e1"), _entity("e2")],
                                       relations=[_relation()]))
    assert _issues_containing(issues, "缺少 url")


def test_duplicate_source_id_is_reported() -> None:
    issues = validate_dataset(_dataset(sources=[_source("s1"), _source("s1")]))
    assert _issues_containing(issues, "来源 id 重复：s1")


def test_duplicate_relation_type_id_is_reported() -> None:
    issues = validate_dataset(_dataset(relation_types=[_rtype("t1"), _rtype("t1")]))
    assert _issues_containing(issues, "关系类型 id 重复：t1")


# --------------------------------------------------------------------------
# 文件层错误
# --------------------------------------------------------------------------


def test_missing_data_files_raise(tmp_path: Path) -> None:
    with pytest.raises(DataFileMissingError):
        load_dataset(tmp_path / "empty-dir")


def test_invalid_json_raises_data_error(tmp_path: Path) -> None:
    (tmp_path / "entities.json").write_text("{ not valid json", encoding="utf-8")
    (tmp_path / "relations.json").write_text(json.dumps({"relations": []}), encoding="utf-8")
    (tmp_path / "sources.json").write_text(json.dumps({"sources": []}), encoding="utf-8")
    with pytest.raises(DataError):
        load_dataset(tmp_path)


def test_non_object_top_level_raises_data_error(tmp_path: Path) -> None:
    (tmp_path / "entities.json").write_text("[]", encoding="utf-8")
    (tmp_path / "relations.json").write_text("{}", encoding="utf-8")
    (tmp_path / "sources.json").write_text("{}", encoding="utf-8")
    with pytest.raises(DataError):
        load_dataset(tmp_path)


def test_invalid_dataset_raises_with_all_issues(tmp_path: Path) -> None:
    """校验失败时应一次性抛出全部问题，便于批量修复。"""
    (tmp_path / "entities.json").write_text(
        json.dumps({"categories": [{"id": "c1", "name": "分类", "order": 1}], "entities": [
            {"id": "e1", "name": "实体一", "category": "c1", "summary": "摘要文本",
             "description": "描述文本内容", "attributes": {}, "source_ids": ["ghost"]}
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "relations.json").write_text(
        json.dumps({"relations": []}), encoding="utf-8")
    (tmp_path / "sources.json").write_text(
        json.dumps({"sources": []}), encoding="utf-8")

    with pytest.raises(DatasetError) as excinfo:
        load_dataset(tmp_path)
    assert _issues_containing(excinfo.value.issues, "ghost")
    assert len(excinfo.value.issues) >= 1


def test_cache_returns_same_instance_and_can_be_cleared() -> None:
    first = load_dataset()
    second = load_dataset()
    assert first is second
    loader.clear_cache()
    third = load_dataset()
    assert third is not first
    assert len(third.entities) == len(first.entities)
