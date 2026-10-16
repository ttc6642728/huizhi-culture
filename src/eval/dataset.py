"""评估标注集的数据模型、加载与校验。

标注集是评估的**基准**，所以它的加载比一般配置更严格：
文件缺失、字段类型不对、引用了不存在的实体、同一个 id 重复出现……
都在这里直接报错并指出具体位置，绝不「跳过坏样本继续跑」——
带着脏标注跑出来的指标比没有指标更糟，因为它看起来像真的。

标注集格式
----------

``data/eval/retrieval_eval.json``::

    {
      "version": "1.0",
      "cases": [
        {
          "id": "r001",
          "query": "宏村",
          "relevant": {"hongcun": 3},        // 或 ["hongcun", "yixian"]
          "tags": ["专名"],
          "note": "实体名称本身即是查询词"
        }
      ]
    }

``data/eval/qa_eval.json``::

    {
      "version": "1.0",
      "cases": [
        {
          "id": "q001",
          "question": "宏村位于哪个县？",
          "expect_citations": ["hongcun"],
          "required_terms": ["黟县"],
          "must_abstain": false,
          "tags": ["关系类"],
          "note": "答案要点必须落在资料里"
        }
      ]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from src.data.repository import Repository

#: 标注集默认目录
EVAL_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "eval"

RETRIEVAL_FILE = "retrieval_eval.json"
QA_FILE = "qa_eval.json"


class EvalDataError(Exception):
    """标注集本身有问题（缺失 / 结构错误 / 引用了不存在的实体）。"""


# --------------------------------------------------------------------------
# 模型
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalCase:
    """一条检索标注：给定查询，哪些实体是**应该**被检索到的。"""

    id: str
    query: str
    relevant: Mapping[str, float]
    tags: Tuple[str, ...] = ()
    note: str = ""

    @property
    def is_negative(self) -> bool:
        """负样本：数据集中确实没有与该查询相关的实体，检索器应当返回空。"""
        return not self.relevant

    @property
    def max_grade(self) -> float:
        return max(self.relevant.values()) if self.relevant else 0.0


@dataclass(frozen=True)
class QACase:
    """一条问答标注：给定问题，答案应引用哪些资料、包含哪些要点，还是应当拒答。"""

    id: str
    question: str
    expect_citations: Tuple[str, ...] = ()
    required_terms: Tuple[str, ...] = ()
    must_abstain: bool = False
    tags: Tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class RetrievalSet:
    """检索标注集。"""

    version: str
    cases: Tuple[RetrievalCase, ...]
    path: Path = field(default=Path())

    @property
    def positives(self) -> Tuple[RetrievalCase, ...]:
        return tuple(c for c in self.cases if not c.is_negative)

    @property
    def negatives(self) -> Tuple[RetrievalCase, ...]:
        return tuple(c for c in self.cases if c.is_negative)

    def tags(self) -> Tuple[str, ...]:
        return tuple(sorted({t for c in self.cases for t in c.tags}))


@dataclass(frozen=True)
class QASet:
    """问答标注集。"""

    version: str
    cases: Tuple[QACase, ...]
    path: Path = field(default=Path())

    @property
    def answerable(self) -> Tuple[QACase, ...]:
        return tuple(c for c in self.cases if not c.must_abstain)

    @property
    def abstain(self) -> Tuple[QACase, ...]:
        return tuple(c for c in self.cases if c.must_abstain)


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalDataError(message)


def _as_str_tuple(value: Any, where: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    _require(isinstance(value, list), f"{where} 应为字符串数组")
    out: List[str] = []
    for item in value:
        _require(isinstance(item, str) and item.strip(), f"{where} 中存在空项或非字符串")
        out.append(item.strip())
    return tuple(out)


def _parse_relevant(raw: Any, where: str) -> Dict[str, float]:
    """解析相关性标注，支持列表（二元）与映射（分级）两种写法。"""
    if raw is None:
        return {}
    if isinstance(raw, list):
        return {str(item): 1.0 for item in _as_str_tuple(raw, where)}
    _require(isinstance(raw, dict), f"{where} 应为数组或对象")
    out: Dict[str, float] = {}
    for key, value in raw.items():
        _require(isinstance(value, (int, float)) and not isinstance(value, bool),
                 f"{where} 中「{key}」的等级应为数字")
        grade = float(value)
        _require(0 <= grade <= 3, f"{where} 中「{key}」的等级应在 0–3 之间")
        if grade > 0:
            out[str(key)] = grade
    return out


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise EvalDataError(f"标注集文件不存在：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvalDataError(f"标注集不是合法 JSON：{path}（{exc}）") from exc
    _require(isinstance(data, dict), f"标注集顶层应为对象：{path}")
    return data


def load_retrieval_set(path: Path | None = None) -> RetrievalSet:
    """加载检索标注集（只做结构校验，实体存在性由 :func:`validate_retrieval_set` 检查）。"""
    path = Path(path) if path else EVAL_DIR / RETRIEVAL_FILE
    data = _read_json(path)
    version = str(data.get("version") or "1.0")

    raw_cases = data.get("cases")
    _require(isinstance(raw_cases, list) and raw_cases, f"{path.name} 缺少非空的 cases 数组")

    cases: List[RetrievalCase] = []
    seen: set = set()
    for index, raw in enumerate(raw_cases):
        where = f"{path.name} cases[{index}]"
        _require(isinstance(raw, dict), f"{where} 应为对象")
        case_id = str(raw.get("id") or "").strip()
        _require(bool(case_id), f"{where} 缺少 id")
        _require(case_id not in seen, f"{path.name} 中 id 重复：{case_id}")
        seen.add(case_id)

        query = str(raw.get("query") or "").strip()
        _require(bool(query), f"{path.name} 的 {case_id} 缺少 query")

        cases.append(
            RetrievalCase(
                id=case_id,
                query=query,
                relevant=_parse_relevant(raw.get("relevant"), f"{case_id}.relevant"),
                tags=_as_str_tuple(raw.get("tags"), f"{case_id}.tags"),
                note=str(raw.get("note") or "").strip(),
            )
        )

    _require(
        any(not c.is_negative for c in cases),
        f"{path.name} 里没有任何有答案的样本，无法计算检索指标",
    )
    return RetrievalSet(version=version, cases=tuple(cases), path=path)


def load_qa_set(path: Path | None = None) -> QASet:
    """加载问答标注集。"""
    path = Path(path) if path else EVAL_DIR / QA_FILE
    data = _read_json(path)
    version = str(data.get("version") or "1.0")

    raw_cases = data.get("cases")
    _require(isinstance(raw_cases, list) and raw_cases, f"{path.name} 缺少非空的 cases 数组")

    cases: List[QACase] = []
    seen: set = set()
    for index, raw in enumerate(raw_cases):
        where = f"{path.name} cases[{index}]"
        _require(isinstance(raw, dict), f"{where} 应为对象")
        case_id = str(raw.get("id") or "").strip()
        _require(bool(case_id), f"{where} 缺少 id")
        _require(case_id not in seen, f"{path.name} 中 id 重复：{case_id}")
        seen.add(case_id)

        question = str(raw.get("question") or "").strip()
        _require(bool(question), f"{path.name} 的 {case_id} 缺少 question")

        must_abstain = bool(raw.get("must_abstain", False))
        cites = _as_str_tuple(raw.get("expect_citations"), f"{case_id}.expect_citations")
        terms = _as_str_tuple(raw.get("required_terms"), f"{case_id}.required_terms")

        if must_abstain:
            _require(
                not cites and not terms,
                f"{case_id} 标了 must_abstain，却同时写了期望引用或必答要点（二者互斥）",
            )
        else:
            _require(
                bool(cites) or bool(terms),
                f"{case_id} 既不是必答（未标 must_abstain），又没有写任何期望引用/要点",
            )

        cases.append(
            QACase(
                id=case_id,
                question=question,
                expect_citations=cites,
                required_terms=terms,
                must_abstain=must_abstain,
                tags=_as_str_tuple(raw.get("tags"), f"{case_id}.tags"),
                note=str(raw.get("note") or "").strip(),
            )
        )

    _require(
        any(not c.must_abstain for c in cases),
        f"{path.name} 里没有任何有答案的问答样本",
    )
    return QASet(version=version, cases=tuple(cases), path=path)


# --------------------------------------------------------------------------
# 与真实数据的对照校验
# --------------------------------------------------------------------------


def validate_retrieval_set(rs: RetrievalSet, repository: Repository) -> List[str]:
    """检查标注里引用的实体是否真实存在，以及标注本身是否自洽。

    Returns:
        问题描述列表；空列表表示全部通过。
    """
    problems: List[str] = []
    known = {e.id for e in repository.entities}

    for case in rs.cases:
        for entity_id in case.relevant:
            if entity_id not in known:
                problems.append(f"[{case.id}] 标注了不存在的实体：{entity_id}")

    if not rs.negatives:
        problems.append("标注集里没有负样本（无答案查询），无法评估「不该召回时是否空手而归」")

    queries = [c.query for c in rs.cases]
    duplicates = {q for q in queries if queries.count(q) > 1}
    if duplicates:
        problems.append(f"存在重复查询：{', '.join(sorted(duplicates))}")

    return problems


def validate_qa_set(qs: QASet, repository: Repository) -> List[str]:
    """检查问答标注引用的实体是否存在。"""
    problems: List[str] = []
    known = {e.id for e in repository.entities}

    for case in qs.cases:
        for entity_id in case.expect_citations:
            if entity_id not in known:
                problems.append(f"[{case.id}] 期望引用了不存在的实体：{entity_id}")

    if not qs.abstain:
        problems.append("问答标注集里没有「应当拒答」的样本，无法评估拒答行为")
    if not qs.answerable:
        problems.append("问答标注集里没有可回答的样本")

    return problems


def load_all(repository: Repository, eval_dir: Path | None = None) -> Tuple[RetrievalSet, QASet]:
    """一次加载两套标注集并完成对照校验；任何问题都直接报错。

    Raises:
        EvalDataError: 结构错误，或标注与真实数据对不上。
    """
    base = Path(eval_dir) if eval_dir else EVAL_DIR
    rs = load_retrieval_set(base / RETRIEVAL_FILE)
    qs = load_qa_set(base / QA_FILE)

    problems = validate_retrieval_set(rs, repository) + validate_qa_set(qs, repository)
    if problems:
        raise EvalDataError("标注集校验未通过：\n  " + "\n  ".join(problems))
    return rs, qs


__all__ = [
    "EvalDataError",
    "RetrievalCase",
    "QACase",
    "RetrievalSet",
    "QASet",
    "load_retrieval_set",
    "load_qa_set",
    "load_all",
    "validate_retrieval_set",
    "validate_qa_set",
    "EVAL_DIR",
    "RETRIEVAL_FILE",
    "QA_FILE",
]
