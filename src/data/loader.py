"""数据加载与校验。

职责：把 ``data/*.json`` 读成带类型的数据对象，并在加载时执行严格校验。
校验失败时抛出 :class:`DatasetError`，错误信息逐条列出，便于定位数据问题。

设计要点：
- 校验覆盖：必填字段、id 唯一性、分类存在性、来源引用有效性、关系两端存在性、
  关系类型合法性、重复关系。
- 结果带缓存，避免 Streamlit 每次重跑都重新读盘与校验。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src import config

# --------------------------------------------------------------------------
# 异常
# --------------------------------------------------------------------------


class DataError(Exception):
    """数据层基础异常。"""


class DatasetError(DataError):
    """数据集校验失败。``issues`` 为逐条可读的问题描述。"""

    def __init__(self, issues: Sequence[str]):
        self.issues: Tuple[str, ...] = tuple(issues)
        super().__init__(f"数据校验未通过，共 {len(self.issues)} 个问题：\n" + "\n".join(f"  - {i}" for i in self.issues))


class DataFileMissingError(DataError):
    """数据文件不存在。"""

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"数据文件不存在：{path}")


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """参考资料。"""

    id: str
    type: str
    title: str
    publisher: str
    url: str
    accessed: str = ""
    note: str = ""

    @property
    def display(self) -> str:
        """列表展示用的简短标题。"""
        return self.title

    @property
    def citation(self) -> str:
        """引用串：出版方 + 标题。"""
        return f"{self.publisher}《{self.title}》" if self.publisher else self.title


@dataclass(frozen=True)
class Category:
    """实体分类。"""

    id: str
    name: str
    order: int
    description: str = ""


@dataclass(frozen=True)
class Entity:
    """文化实体。"""

    id: str
    name: str
    category: str
    summary: str
    description: str
    aliases: Tuple[str, ...] = ()
    attributes: Mapping[str, str] = field(default_factory=dict)
    source_ids: Tuple[str, ...] = ()
    image: str = ""

    @property
    def search_text(self) -> str:
        """用于关键词匹配的全部可检索文本。"""
        parts = [self.name, *self.aliases, self.summary, self.description]
        parts.extend(f"{k}{v}" for k, v in self.attributes.items())
        return "\n".join(p for p in parts if p)


@dataclass(frozen=True)
class RelationType:
    """关系类型。"""

    id: str
    name: str
    inverse_name: str = ""
    description: str = ""


@dataclass(frozen=True)
class Relation:
    """实体之间的关系。方向为 source → target。"""

    id: str
    source: str
    target: str
    type: str
    label: str = ""
    description: str = ""
    source_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Dataset:
    """完整数据集。所有集合均为只读，便于安全共享与缓存。"""

    entities: Tuple[Entity, ...]
    relations: Tuple[Relation, ...]
    sources: Tuple[Source, ...]
    categories: Tuple[Category, ...]
    relation_types: Tuple[RelationType, ...]
    version: str = ""

    # ---- 索引（在 __post_init__ 中一次性构建，frozen 实例不可变）----
    _entity_map: Dict[str, Entity] = field(default=None, repr=False, compare=False)  # type: ignore[assignment]
    _source_map: Dict[str, Source] = field(default=None, repr=False, compare=False)  # type: ignore[assignment]
    _category_map: Dict[str, Category] = field(default=None, repr=False, compare=False)  # type: ignore[assignment]
    _relation_type_map: Dict[str, RelationType] = field(default=None, repr=False, compare=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # frozen=True 下需通过 object.__setattr__ 写入派生索引
        object.__setattr__(self, "_entity_map", {e.id: e for e in self.entities})
        object.__setattr__(self, "_source_map", {s.id: s for s in self.sources})
        object.__setattr__(self, "_category_map", {c.id: c for c in self.categories})
        object.__setattr__(self, "_relation_type_map", {t.id: t for t in self.relation_types})

    def entity_map(self) -> Dict[str, Entity]:
        return self._entity_map

    def source_map(self) -> Dict[str, Source]:
        return self._source_map

    def category_map(self) -> Dict[str, Category]:
        return self._category_map

    def relation_type_map(self) -> Dict[str, RelationType]:
        return self._relation_type_map

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        return self.entity_map().get(entity_id)

    def get_source(self, source_id: str) -> Optional[Source]:
        return self.source_map().get(source_id)

    def category_of(self, entity: Entity) -> Optional[Category]:
        return self.category_map().get(entity.category)

    def sources_of(self, source_ids: Iterable[str]) -> List[Source]:
        smap = self.source_map()
        return [smap[s] for s in source_ids if s in smap]


# --------------------------------------------------------------------------
# 读取与解析
# --------------------------------------------------------------------------


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise DataFileMissingError(path)
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise DataError(f"{path.name} 不是合法 JSON：第 {exc.lineno} 行第 {exc.colno} 列 — {exc.msg}") from exc
    if not isinstance(data, dict):
        raise DataError(f"{path.name} 的顶层结构必须是对象（JSON object）。")
    return data


def _as_str(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) else default


def _as_str_tuple(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return ()


def _parse_sources(raw: Mapping[str, Any]) -> Tuple[Source, ...]:
    items = raw.get("sources") or []
    return tuple(
        Source(
            id=_as_str(it.get("id")),
            type=_as_str(it.get("type"), "unknown"),
            title=_as_str(it.get("title")),
            publisher=_as_str(it.get("publisher")),
            url=_as_str(it.get("url")),
            accessed=_as_str(it.get("accessed")),
            note=_as_str(it.get("note")),
        )
        for it in items
        if isinstance(it, Mapping)
    )


def _parse_categories(raw: Mapping[str, Any]) -> Tuple[Category, ...]:
    items = raw.get("categories") or []
    cats = [
        Category(
            id=_as_str(it.get("id")),
            name=_as_str(it.get("name")),
            order=int(it.get("order") or 0),
            description=_as_str(it.get("description")),
        )
        for it in items
        if isinstance(it, Mapping)
    ]
    return tuple(sorted(cats, key=lambda c: (c.order, c.id)))


def _parse_entities(raw: Mapping[str, Any]) -> Tuple[Entity, ...]:
    items = raw.get("entities") or []
    out: List[Entity] = []
    for it in items:
        if not isinstance(it, Mapping):
            continue
        attrs = it.get("attributes") or {}
        if not isinstance(attrs, Mapping):
            attrs = {}
        out.append(
            Entity(
                id=_as_str(it.get("id")),
                name=_as_str(it.get("name")),
                category=_as_str(it.get("category")),
                summary=_as_str(it.get("summary")),
                description=_as_str(it.get("description")),
                aliases=_as_str_tuple(it.get("aliases")),
                attributes={str(k): _as_str(v) for k, v in attrs.items()},
                source_ids=_as_str_tuple(it.get("source_ids")),
                image=_as_str(it.get("image")),
            )
        )
    return tuple(out)


def _parse_relation_types(raw: Mapping[str, Any]) -> Tuple[RelationType, ...]:
    items = raw.get("relation_types") or []
    return tuple(
        RelationType(
            id=_as_str(it.get("id")),
            name=_as_str(it.get("name")),
            inverse_name=_as_str(it.get("inverse_name")),
            description=_as_str(it.get("description")),
        )
        for it in items
        if isinstance(it, Mapping)
    )


def _parse_relations(raw: Mapping[str, Any]) -> Tuple[Relation, ...]:
    items = raw.get("relations") or []
    return tuple(
        Relation(
            id=_as_str(it.get("id")),
            source=_as_str(it.get("source")),
            target=_as_str(it.get("target")),
            type=_as_str(it.get("type")),
            label=_as_str(it.get("label")),
            description=_as_str(it.get("description")),
            source_ids=_as_str_tuple(it.get("source_ids")),
        )
        for it in items
        if isinstance(it, Mapping)
    )


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------


def validate_dataset(dataset: Dataset) -> List[str]:
    """校验数据集，返回问题列表（空列表表示通过）。

    校验项：
    1. 实体必填字段非空
    2. 实体 id 唯一
    3. 实体分类存在于 categories
    4. 实体 source_ids 非空且均存在
    5. 关系必填字段非空
    6. 关系 id 唯一
    7. 关系两端实体存在
    8. 关系类型存在于 relation_types
    9. 关系 source_ids 非空且均存在
    10. 不存在重复关系（source, target, type 三元组唯一）
    11. 关系类型 id 唯一
    """
    issues: List[str] = []

    # ---- 来源 ----
    src_ids = [s.id for s in dataset.sources]
    for sid in _duplicates(src_ids):
        issues.append(f"来源 id 重复：{sid}")
    valid_sources = set(src_ids)
    for s in dataset.sources:
        if not s.title:
            issues.append(f"来源 {s.id or '(空 id)'} 缺少 title")
        if not s.url:
            issues.append(f"来源 {s.id or '(空 id)'} 缺少 url")

    # ---- 分类 ----
    cat_ids = [c.id for c in dataset.categories]
    for cid in _duplicates(cat_ids):
        issues.append(f"分类 id 重复：{cid}")
    valid_categories = set(cat_ids)

    # ---- 关系类型 ----
    rt_ids = [t.id for t in dataset.relation_types]
    for tid in _duplicates(rt_ids):
        issues.append(f"关系类型 id 重复：{tid}")
    valid_relation_types = set(rt_ids)

    # ---- 实体 ----
    ent_ids = [e.id for e in dataset.entities]
    for eid in _duplicates(ent_ids):
        issues.append(f"实体 id 重复：{eid}")
    valid_entities = set(ent_ids)
    for e in dataset.entities:
        label = e.id or f"(空 id，name={e.name!r})"
        for fname, value in (("id", e.id), ("name", e.name), ("category", e.category),
                             ("summary", e.summary), ("description", e.description)):
            if not value:
                issues.append(f"实体 {label} 缺少必填字段 {fname}")
        if e.category and e.category not in valid_categories:
            issues.append(f"实体 {label} 的分类 {e.category!r} 未在 categories 中定义")
        if not e.source_ids:
            issues.append(f"实体 {label} 未标注任何来源")
        for sid in e.source_ids:
            if sid not in valid_sources:
                issues.append(f"实体 {label} 引用了不存在的来源 {sid!r}")

    # ---- 关系 ----
    rel_ids = [r.id for r in dataset.relations]
    for rid in _duplicates(rel_ids):
        issues.append(f"关系 id 重复：{rid}")
    seen_triples: Dict[Tuple[str, str, str], str] = {}
    for r in dataset.relations:
        label = r.id or f"(空 id，{r.source}->{r.target})"
        for fname, value in (("id", r.id), ("source", r.source), ("target", r.target), ("type", r.type)):
            if not value:
                issues.append(f"关系 {label} 缺少必填字段 {fname}")
        if r.source and r.source not in valid_entities:
            issues.append(f"关系 {label} 的 source {r.source!r} 不存在")
        if r.target and r.target not in valid_entities:
            issues.append(f"关系 {label} 的 target {r.target!r} 不存在")
        if r.type and r.type not in valid_relation_types:
            issues.append(f"关系 {label} 的关系类型 {r.type!r} 未在 relation_types 中定义")
        if not r.source_ids:
            issues.append(f"关系 {label} 未标注任何来源")
        for sid in r.source_ids:
            if sid not in valid_sources:
                issues.append(f"关系 {label} 引用了不存在的来源 {sid!r}")
        triple = (r.source, r.target, r.type)
        if triple in seen_triples:
            issues.append(f"重复关系：{r.source} -[{r.type}]-> {r.target}（{seen_triples[triple]} 与 {r.id}）")
        else:
            seen_triples[triple] = r.id
        if r.source and r.source == r.target:
            issues.append(f"关系 {label} 的起点与终点相同（自环）")

    return issues


def _duplicates(items: Iterable[str]) -> List[str]:
    seen: set = set()
    dup: List[str] = []
    for it in items:
        if it in seen and it not in dup:
            dup.append(it)
        seen.add(it)
    return dup


# --------------------------------------------------------------------------
# 对外入口
# --------------------------------------------------------------------------


def _build_dataset(data_dir: Path) -> Dataset:
    entities_raw = _read_json(data_dir / "entities.json")
    relations_raw = _read_json(data_dir / "relations.json")
    sources_raw = _read_json(data_dir / "sources.json")

    dataset = Dataset(
        entities=_parse_entities(entities_raw),
        relations=_parse_relations(relations_raw),
        sources=_parse_sources(sources_raw),
        categories=_parse_categories(entities_raw),
        relation_types=_parse_relation_types(relations_raw),
        version=_as_str(entities_raw.get("version")),
    )
    return dataset


@lru_cache(maxsize=8)
def _load_dataset_cached(data_dir_str: str) -> Dataset:
    dataset = _build_dataset(Path(data_dir_str))
    issues = validate_dataset(dataset)
    if issues:
        raise DatasetError(issues)
    return dataset


def load_dataset(data_dir: Optional[Path | str] = None) -> Dataset:
    """加载并校验数据集。

    Args:
        data_dir: 数据目录，默认 ``config.DATA_DIR``。

    Raises:
        DataFileMissingError: 数据文件缺失。
        DatasetError: 数据校验未通过。
    """
    target = Path(data_dir) if data_dir is not None else config.DATA_DIR
    return _load_dataset_cached(str(Path(target).resolve()))


def clear_cache() -> None:
    """清空数据集缓存（数据文件变更后调用）。"""
    _load_dataset_cached.cache_clear()


def dataset_summary(dataset: Dataset) -> Dict[str, int]:
    """数据集规模统计，供界面与文档使用。"""
    return {
        "entities": len(dataset.entities),
        "relations": len(dataset.relations),
        "sources": len(dataset.sources),
        "categories": len(dataset.categories),
        "relation_types": len(dataset.relation_types),
    }


__all__ = [
    "DataError",
    "DatasetError",
    "DataFileMissingError",
    "Source",
    "Category",
    "Entity",
    "RelationType",
    "Relation",
    "Dataset",
    "load_dataset",
    "validate_dataset",
    "clear_cache",
    "dataset_summary",
]
