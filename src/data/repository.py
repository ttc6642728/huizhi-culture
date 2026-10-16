"""实体查询仓储。

在 :class:`~src.data.loader.Dataset` 之上提供面向界面与问答层的查询能力：
关键词检索、分类筛选、详情、关联关系、邻居子图、路径与统计。

本模块不依赖界面，也不依赖 NetworkX，便于独立单元测试。
"""

from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.data.loader import Category, Dataset, Entity, Relation, RelationType, Source, load_dataset

#: 关键词分隔符（中英文标点与空白）
_TERM_SPLIT = re.compile(r"[\s,，、;；/|]+")

#: 各字段命中权重
_W_NAME_EXACT = 100
_W_ALIAS_EXACT = 90
_W_NAME_PART = 70
_W_ALIAS_PART = 55
_W_SUMMARY = 30
_W_DESCRIPTION = 15
_W_ATTRIBUTE = 10


@dataclass(frozen=True)
class SearchHit:
    """一次检索命中。"""

    entity: Entity
    score: int
    matched_field: str
    matched_terms: Tuple[str, ...]
    matched_all: bool

    @property
    def name(self) -> str:
        return self.entity.name


@dataclass(frozen=True)
class Neighbor:
    """实体的一度邻居。"""

    entity: Entity
    relation: Relation
    direction: str  # "out" 表示当前实体是起点，"in" 表示当前实体是终点

    @property
    def relation_type(self) -> str:
        return self.relation.type

    @property
    def display_label(self) -> str:
        """以当前实体为主语的展示标签。"""
        return self.relation.label or self.relation.type


@dataclass(frozen=True)
class CategoryCount:
    category: Category
    count: int


class Repository:
    """实体查询仓储。"""

    def __init__(self, dataset: Optional[Dataset] = None):
        self.dataset: Dataset = dataset if dataset is not None else load_dataset()
        self._out_index, self._in_index = self._build_adjacency()

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    def _build_adjacency(self) -> Tuple[Dict[str, List[Relation]], Dict[str, List[Relation]]]:
        out: Dict[str, List[Relation]] = {e.id: [] for e in self.dataset.entities}
        inc: Dict[str, List[Relation]] = {e.id: [] for e in self.dataset.entities}
        for rel in self.dataset.relations:
            out.setdefault(rel.source, []).append(rel)
            inc.setdefault(rel.target, []).append(rel)
        return out, inc

    # ------------------------------------------------------------------
    # 基础访问
    # ------------------------------------------------------------------

    @property
    def entities(self) -> Tuple[Entity, ...]:
        return self.dataset.entities

    @property
    def relations(self) -> Tuple[Relation, ...]:
        return self.dataset.relations

    def get(self, entity_id: str) -> Optional[Entity]:
        return self.dataset.get_entity(entity_id)

    def require(self, entity_id: str) -> Entity:
        entity = self.get(entity_id)
        if entity is None:
            raise KeyError(f"实体不存在：{entity_id}")
        return entity

    def categories(self) -> Tuple[Category, ...]:
        return self.dataset.categories

    def category(self, category_id: str) -> Optional[Category]:
        return self.dataset.category_map().get(category_id)

    def category_counts(self) -> List[CategoryCount]:
        """按分类统计实体数量（按 category.order 排序）。"""
        counter = Counter(e.category for e in self.dataset.entities)
        return [CategoryCount(c, counter.get(c.id, 0)) for c in self.dataset.categories]

    def relation_types(self) -> Tuple[RelationType, ...]:
        return self.dataset.relation_types

    def relation_type_name(self, type_id: str) -> str:
        rt = self.dataset.relation_type_map().get(type_id)
        return rt.name if rt else type_id

    def sources_of(self, entity: Entity) -> List[Source]:
        return self.dataset.sources_of(entity.source_ids)

    def sources_of_relation(self, relation: Relation) -> List[Source]:
        return self.dataset.sources_of(relation.source_ids)

    def sources_of_entity(self, entity_id: str) -> List[Source]:
        entity = self.get(entity_id)
        return self.sources_of(entity) if entity else []

    def entity_by_name(self, name: str) -> Optional[Entity]:
        """按名称或别名精确查找（忽略首尾空白）。"""
        target = name.strip()
        if not target:
            return None
        for e in self.dataset.entities:
            if e.name == target or target in e.aliases:
                return e
        return None

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    @staticmethod
    def _terms(query: str) -> List[str]:
        return [t.lower() for t in _TERM_SPLIT.split(query.strip()) if t]

    @staticmethod
    def _score_entity(entity: Entity, terms: Sequence[str]) -> Tuple[int, str, Tuple[str, ...]]:
        """返回 (得分, 最高权重字段名, 命中的词)。得分为 0 表示一个词都没命中。"""
        name = entity.name.lower()
        aliases = [a.lower() for a in entity.aliases]
        summary = entity.summary.lower()
        description = entity.description.lower()
        attrs = " ".join(f"{k}{v}" for k, v in entity.attributes.items()).lower()

        total = 0
        best_field = ""
        matched: List[str] = []

        for term in terms:
            score = 0
            field = ""
            if term == name:
                score, field = _W_NAME_EXACT, "名称"
            elif term in name:
                score, field = _W_NAME_PART, "名称"
            for alias in aliases:
                if term == alias and _W_ALIAS_EXACT > score:
                    score, field = _W_ALIAS_EXACT, "别名"
                elif term in alias and _W_ALIAS_PART > score:
                    score, field = _W_ALIAS_PART, "别名"
            if term in summary and _W_SUMMARY > score:
                score, field = _W_SUMMARY, "摘要"
            if term in description and _W_DESCRIPTION > score:
                score, field = _W_DESCRIPTION, "简介"
            if term in attrs and _W_ATTRIBUTE > score:
                score, field = _W_ATTRIBUTE, "属性"

            if score:
                total += score
                matched.append(term)
                if not best_field:
                    best_field = field

        return total, best_field, tuple(matched)

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[SearchHit]:
        """关键词检索实体。

        多个关键词时，全部命中的结果排在只命中部分的结果之前；完全未命中的不返回。
        """
        terms = self._terms(query)
        if not terms:
            return []

        hits: List[SearchHit] = []
        for entity in self.dataset.entities:
            if category and entity.category != category:
                continue
            score, field, matched = self._score_entity(entity, terms)
            if score <= 0:
                continue
            hits.append(
                SearchHit(
                    entity=entity,
                    score=score,
                    matched_field=field,
                    matched_terms=matched,
                    matched_all=len(matched) == len(terms),
                )
            )

        hits.sort(key=lambda h: (not h.matched_all, -h.score, h.entity.name))
        return hits[:limit] if limit else hits

    def by_category(self, category_id: str) -> List[Entity]:
        """按分类列出实体（保持数据文件顺序）。"""
        return [e for e in self.dataset.entities if e.category == category_id]

    # ------------------------------------------------------------------
    # 关联关系
    # ------------------------------------------------------------------

    def relations_of(self, entity_id: str) -> Tuple[List[Relation], List[Relation]]:
        """返回 (以该实体为起点的关系, 以该实体为终点的关系)。"""
        return list(self._out_index.get(entity_id, ())), list(self._in_index.get(entity_id, ()))

    def neighbors(self, entity_id: str, relation_type: Optional[str] = None) -> List[Neighbor]:
        """一度邻居。``relation_type`` 可按关系类型过滤。"""
        if self.get(entity_id) is None:
            raise KeyError(f"实体不存在：{entity_id}")

        result: List[Neighbor] = []
        for rel in self._out_index.get(entity_id, ()):
            if relation_type and rel.type != relation_type:
                continue
            other = self.get(rel.target)
            if other is not None:
                result.append(Neighbor(other, rel, "out"))
        for rel in self._in_index.get(entity_id, ()):
            if relation_type and rel.type != relation_type:
                continue
            other = self.get(rel.source)
            if other is not None:
                result.append(Neighbor(other, rel, "in"))

        result.sort(key=lambda n: (n.relation.type, n.entity.name))
        return result

    def subgraph_ids(self, entity_id: str, radius: int = 1) -> List[str]:
        """以某实体为中心、指定半径内的实体 id 集合（含中心）。"""
        if self.get(entity_id) is None:
            raise KeyError(f"实体不存在：{entity_id}")
        radius = max(0, radius)
        visited = {entity_id}
        frontier = deque([(entity_id, 0)])
        while frontier:
            current, depth = frontier.popleft()
            if depth >= radius:
                continue
            for nb in self.neighbors(current):
                if nb.entity.id not in visited:
                    visited.add(nb.entity.id)
                    frontier.append((nb.entity.id, depth + 1))
        return sorted(visited)

    def shortest_path(self, source_id: str, target_id: str) -> Optional[List[str]]:
        """无权最短路（BFS）。不可达时返回 ``None``。"""
        if self.get(source_id) is None:
            raise KeyError(f"实体不存在：{source_id}")
        if self.get(target_id) is None:
            raise KeyError(f"实体不存在：{target_id}")
        if source_id == target_id:
            return [source_id]

        prev: Dict[str, str] = {source_id: source_id}
        queue = deque([source_id])
        while queue:
            current = queue.popleft()
            for nb in self.neighbors(current):
                nid = nb.entity.id
                if nid in prev:
                    continue
                prev[nid] = current
                if nid == target_id:
                    path = [nid]
                    while path[-1] != source_id:
                        path.append(prev[path[-1]])
                    return list(reversed(path))
                queue.append(nid)
        return None

    def degree(self, entity_id: str) -> int:
        """节点度数（出边 + 入边）。"""
        return len(self._out_index.get(entity_id, ())) + len(self._in_index.get(entity_id, ()))

    def is_isolated(self, entity_id: str) -> bool:
        return self.degree(entity_id) == 0

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, object]:
        """整体统计，供首页与图谱页展示。"""
        type_counter = Counter(r.type for r in self.dataset.relations)
        isolated = [e.name for e in self.dataset.entities if self.is_isolated(e.id)]
        top = sorted(
            ({"entity": e, "degree": self.degree(e.id)} for e in self.dataset.entities),
            key=lambda d: (-int(d["degree"]), d["entity"].name),  # type: ignore[arg-type]
        )[:10]
        return {
            "entity_count": len(self.dataset.entities),
            "relation_count": len(self.dataset.relations),
            "source_count": len(self.dataset.sources),
            "category_count": len(self.dataset.categories),
            "relation_type_counts": {self.relation_type_name(t): type_counter.get(t, 0) for t in
                                     [rt.id for rt in self.dataset.relation_types]},
            "isolated_entities": isolated,
            "top_connected": top,
        }


def get_repository() -> Repository:
    """获取仓储实例（Streamlit 场景下可用作缓存的便捷入口）。"""
    return Repository(load_dataset())


__all__ = ["Repository", "SearchHit", "Neighbor", "CategoryCount", "get_repository"]
