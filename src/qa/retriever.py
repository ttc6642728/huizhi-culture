"""基于徽州文化资料的 BM25 检索。

设计要点
--------
1. **资料单元 = 一个文化实体**。实体的名称、别名、摘要、正文、结构化属性，
   以及它与其它实体之间的关系叙述，共同构成一份可被引用的资料。
   关系叙述按「关系读法」分组压缩（例如 ``位于：黟县``、``包含组成：歙县、休宁…``），
   这样「宏村属于哪个县」这类问题才检索得到答案，而不是只匹配到实体简介。
2. **中文分词**：jieba 切词后过滤停用词与纯标点。查询串另加两路补充——
   整串（去标点后 ≤12 字）与按标点切分的片段——避免分词把专名切碎后漏召回。
3. **打分 = BM25 + 精确命中加成**。BM25（k1=1.5，b=0.75）负责词频与长度归一，
   加成项负责「宏村」这类专名：原词出现在标题/别名里权重最高，出现在正文次之。
4. **必须可溯源**：每条结果都带上该实体的登记来源；没有来源的资料不返回。
   检索不到就是空列表，绝不用低相关度的结果凑数。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

import jieba

from src.data.loader import Source
from src.data.repository import Repository

# --------------------------------------------------------------------------
# 参数
# --------------------------------------------------------------------------

#: Okapi BM25 词频饱和参数
K1 = 1.5
#: Okapi BM25 长度归一参数
B = 0.75

#: 原词精确命中的加成。
#: 标题完全等于查询词时给最高加成——否则「徽州」这类被大量实体复用的词
#: 会让「徽州婚俗」与「徽州」本身得分几乎并列，用户拿不到最主要的那个实体。
EXACT_TITLE_BONUS = 9.0
TITLE_BONUS = 4.0
ALIAS_BONUS = 3.5
BODY_BONUS = 0.9

#: 单份资料送入模型的正文上限（字符）。过长会挤占提示词预算且引入噪声。
MAX_DOC_CHARS = 1200

#: 关系叙述最多列举的邻居数（超出部分只统计条数，避免超长）
MAX_RELATION_NEIGHBORS = 30

#: 默认返回的资料条数
DEFAULT_TOP_K = 5


# --------------------------------------------------------------------------
# 分词
# --------------------------------------------------------------------------

#: 停用词：中文虚词与英文常见功能词。这些词几乎出现在每份资料里，
#: 保留它们只会稀释 IDF、把真正有区分度的专名淹没。
STOPWORDS = frozenset(
    {
        "的", "了", "和", "与", "及", "或", "是", "在", "有", "为", "被", "把", "对",
        "从", "到", "由", "于", "以", "并", "而", "则", "之", "其", "该", "这", "那",
        "等", "都", "也", "就", "还", "又", "很", "更", "最", "不", "无", "未", "可",
        "一", "个", "些", "这", "那", "上", "下", "中", "内", "外", "前", "后", "里",
        "什么", "怎么", "怎样", "如何", "哪", "哪些", "多少", "吗", "呢", "啊", "吧",
        "请", "问", "说", "表示", "进行", "以及", "同时", "其中", "通过", "由于",
        "the", "a", "an", "of", "is", "are", "was", "were", "and", "or", "to", "in",
        "on", "for", "with", "by", "as", "at", "be", "it", "this", "that", "what",
    }
)

#: 纯标点 / 纯符号（Unicode 下中文算 \w，因此不会被误伤）
_PUNCT_ONLY = re.compile(r"^[\W_]+$", re.UNICODE)

#: 查询串切分用（与仓储层的关键词分隔保持一致）
_QUERY_SPLIT = re.compile(r"[\s,，、;；/|]+")

#: 构造「整串」查询词时要去掉的标点
_STRIP_PUNCT = re.compile(r"[\s,，、;；/|。！？：:!?（）()【】\[\]「」『』\"'`]+")


@lru_cache(maxsize=4096)
def tokenize(text: str) -> Tuple[str, ...]:
    """jieba 分词 → 过滤停用词与纯标点 → 小写化。

    结果带缓存：同一段文本在多次检索中只切一次。
    """
    if not text:
        return ()
    out: List[str] = []
    for raw in jieba.lcut(text):
        word = raw.strip().lower()
        if not word or word in STOPWORDS or _PUNCT_ONLY.match(word):
            continue
        out.append(word)
    return tuple(out)


def _query_terms(query: str) -> Tuple[str, ...]:
    """从查询串得到检索词。

    三路合并，互为兜底：
    1. jieba 分词结果（处理「马头墙有什么特点」这类自然语句）；
    2. 去除标点后的整串（≤12 字，保住「徽州三雕」这类被切碎的专名）；
    3. 按标点/空白切分的片段（处理「宏村、西递」这种并列罗列）。
    """
    text = (query or "").strip()
    if not text:
        return ()

    terms: List[str] = list(tokenize(text))

    compact = _STRIP_PUNCT.sub("", text).lower()
    if 1 < len(compact) <= 12:
        terms.append(compact)

    for piece in _QUERY_SPLIT.split(text):
        piece = piece.strip().lower()
        if len(piece) > 1:
            terms.append(piece)

    # 去重且保持顺序
    return tuple(dict.fromkeys(t for t in terms if t and t not in STOPWORDS))


# --------------------------------------------------------------------------
# 资料
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Passage:
    """一条可被引用的资料。

    编号（``[1]`` 这种）不在这里，由调用方在排序定位后按展示顺序分配，
    避免同一份资料在不同检索结果里带着两套编号。
    """

    entity_id: str
    title: str
    category_name: str
    text: str
    score: float
    matched_terms: Tuple[str, ...]
    sources: Tuple[Source, ...]
    relation_count: int

    @property
    def has_source(self) -> bool:
        return bool(self.sources)

    @property
    def citation(self) -> str:
        """首选引用串：出版方《标题》。"""
        return self.sources[0].citation if self.sources else ""


@dataclass(frozen=True)
class _Document:
    """检索索引中的一份资料。"""

    entity_id: str
    title: str
    alias_text: str
    category_name: str
    text: str
    tokens: Tuple[str, ...]
    sources: Tuple[Source, ...]
    relation_count: int


# --------------------------------------------------------------------------
# 检索器
# --------------------------------------------------------------------------


class Retriever:
    """文化资料检索器（内存索引 + BM25）。"""

    def __init__(
        self,
        repository: Repository,
        top_k: int = DEFAULT_TOP_K,
        max_doc_chars: int = MAX_DOC_CHARS,
    ):
        self._repo = repository
        self._top_k = max(1, int(top_k))
        self._max_doc_chars = max(200, int(max_doc_chars))
        self._docs: Tuple[_Document, ...] = tuple(self._build_documents())
        self._df: Dict[str, int] = self._build_df()
        self._avgdl: float = self._compute_avgdl()

    # ------------------------------------------------------------------
    # 索引构建
    # ------------------------------------------------------------------

    def _relation_summary(self, entity_id: str) -> Tuple[str, int]:
        """把一度关系压成一句可检索的叙述。

        按「关系读法」分组，例如：``位于：黟县；包含组成：歙县、休宁``。
        入向关系用 ``inverse_name`` 读，保证方向不会被说反。
        """
        neighbors = self._repo.neighbors(entity_id)
        if not neighbors:
            return "", 0

        groups: Dict[str, List[str]] = {}
        for nb in neighbors:
            label = self._relation_label(nb.relation.type, nb.direction)
            groups.setdefault(label, []).append(nb.entity.name)

        parts: List[str] = []
        counted = 0
        for label, names in groups.items():
            shown = names[:10]
            tail = f"等 {len(names)} 个" if len(names) > len(shown) else ""
            parts.append(f"{label}：{'、'.join(shown)}{tail}")
            counted += len(names)
            if counted >= MAX_RELATION_NEIGHBORS:
                break

        return "；".join(parts), len(neighbors)

    def _relation_label(self, type_id: str, direction: str) -> str:
        for rt in self._repo.relation_types():
            if rt.id == type_id:
                if direction == "out":
                    return rt.name or type_id
                return rt.inverse_name or rt.name or type_id
        return self._repo.relation_type_name(type_id)

    def _build_documents(self) -> List[_Document]:
        docs: List[_Document] = []
        for entity in self._repo.entities:
            sources = tuple(self._repo.sources_of(entity))
            # 没有来源的内容不进检索结果——检索结果要能被核查
            if not sources:
                continue

            category = self._repo.category(entity.category)
            category_name = category.name if category else entity.category

            blocks: List[str] = [entity.summary, entity.description]
            # 别名必须进正文：它本来就已经参与分词与匹配，却不出现在送给后端的资料里，
            # 于是「徽商又被称为什么」这类问题会命中条目、却看不到答案
            # （评估脚本正是靠这一条抓到了这个缺陷）。
            if entity.aliases:
                blocks.append("别名：" + "、".join(entity.aliases))
            if entity.attributes:
                blocks.append(
                    "属性：" + "；".join(f"{k}：{v}" for k, v in entity.attributes.items())
                )
            rel_text, rel_count = self._relation_summary(entity.id)
            if rel_text:
                blocks.append("关联：" + rel_text)

            text = "\n".join(b for b in blocks if b).strip()
            if len(text) > self._max_doc_chars:
                text = text[: self._max_doc_chars].rstrip() + "…"

            alias_text = " ".join(entity.aliases)
            # 分词覆盖标题、别名与正文，标题重复一次以提升专名权重
            tokens = tokenize(f"{entity.name} {entity.name} {alias_text} {text}")

            docs.append(
                _Document(
                    entity_id=entity.id,
                    title=entity.name,
                    alias_text=alias_text,
                    category_name=category_name,
                    text=text,
                    tokens=tokens,
                    sources=sources,
                    relation_count=rel_count,
                )
            )
        return docs

    def _build_df(self) -> Dict[str, int]:
        df: Dict[str, int] = {}
        for doc in self._docs:
            for term in set(doc.tokens):
                df[term] = df.get(term, 0) + 1
        return df

    def _compute_avgdl(self) -> float:
        if not self._docs:
            return 1.0
        return max(1.0, sum(len(d.tokens) for d in self._docs) / len(self._docs))

    # ------------------------------------------------------------------
    # 打分
    # ------------------------------------------------------------------

    def _idf(self, term: str) -> float:
        n = len(self._docs)
        if n == 0:
            return 0.0
        df = self._df.get(term, 0)
        # 加 1 保证严格为正：一个词即使出现在全部资料里，也不应把得分压成 0 或负
        return math.log(1.0 + (n - df + 0.5) / (df + 0.5))

    def _score(self, doc: _Document, terms: Sequence[str]) -> Tuple[float, Tuple[str, ...]]:
        tf = Counter(doc.tokens)
        dl = max(1, len(doc.tokens))
        score = 0.0
        matched: List[str] = []

        for term in terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            denom = freq + K1 * (1 - B + B * dl / self._avgdl)
            score += self._idf(term) * freq * (K1 + 1) / denom
            matched.append(term)

        if not matched:
            return 0.0, ()

        # 精确命中加成：BM25 按词频打分，对「宏村」这类只出现一两次的专名偏保守；
        # 而「徽州」这种被近百个实体复用的词 IDF 又极低，光靠 BM25 排不出来。
        title = doc.title.lower()
        alias = doc.alias_text.lower()
        body = doc.text.lower()
        for term in matched:
            if term == title:
                score += EXACT_TITLE_BONUS
            elif term in title:
                score += TITLE_BONUS
            elif alias and term in alias:
                score += ALIAS_BONUS
            elif term in body:
                score += BODY_BONUS

        return score, tuple(matched)

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    @property
    def document_count(self) -> int:
        """已建索引的资料数（等于有来源的实体数）。"""
        return len(self._docs)

    @property
    def vocabulary_size(self) -> int:
        return len(self._df)

    @property
    def top_k(self) -> int:
        return self._top_k

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Passage]:
        """检索资料，按相关度降序返回。

        Args:
            query: 用户问题（自然语句或关键词均可）。
            top_k: 覆盖构造时的默认条数。

        Returns:
            资料片段列表；检索不到时返回**空列表**（不返回低分结果凑数）。
        """
        terms = _query_terms(query)
        if not terms:
            return []

        limit = max(1, int(top_k)) if top_k else self._top_k

        scored: List[Tuple[float, _Document, Tuple[str, ...]]] = []
        for doc in self._docs:
            score, matched = self._score(doc, terms)
            if score > 0:
                scored.append((score, doc, matched))

        # 先按分数降序，同分用标题稳定排序，保证结果可复现
        scored.sort(key=lambda item: (-item[0], item[1].title))

        return [
            Passage(
                entity_id=doc.entity_id,
                title=doc.title,
                category_name=doc.category_name,
                text=doc.text,
                score=round(score, 4),
                matched_terms=matched,
                sources=doc.sources,
                relation_count=doc.relation_count,
            )
            for score, doc, matched in scored[:limit]
        ]

    def retrieve_one(self, query: str) -> Optional[Passage]:
        """只取最相关的一条资料（供示例问题等场景使用）。"""
        hits = self.retrieve(query, top_k=1)
        return hits[0] if hits else None

    def stats(self) -> Dict[str, float]:
        """索引概况，供界面与文档展示。"""
        return {
            "documents": len(self._docs),
            "vocabulary": len(self._df),
            "avg_length": round(self._avgdl, 1),
            "top_k": self._top_k,
        }


__all__ = [
    "Retriever",
    "Passage",
    "tokenize",
    "STOPWORDS",
    "K1",
    "B",
    "DEFAULT_TOP_K",
    "MAX_DOC_CHARS",
    "EXACT_TITLE_BONUS",
    "TITLE_BONUS",
]
