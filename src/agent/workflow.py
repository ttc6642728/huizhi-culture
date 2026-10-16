"""可追踪的智能体工作流：把「检索 → 依据资料作答 → 自我核查引用 → 输出」编排成多步流程。

为什么要单独做一层，而不是继续用 ``QAEngine.ask()``
--------------------------------------------------
``ask()`` 把「检索 + 作答」压成一次调用，结果正确但过程不可见。
本模块把同一件事拆成**六个可分别追踪的步骤**，每一步都记录输入、输出、耗时与状态：

```
1. 问题解析与实体锚定   启发式判断提问类型，并把问题里出现的实体名/别名锚定出来
2. 资料检索             在锚定实体的帮助下检索资料；检索不到就地中止
3. 依据资料作答         交给 QAEngine 的后端降级链（Dify → 大模型 → 本地检索式）
4. 引用自我核查         逐项检查回答是否可溯源（编号是否存在、是否越界、是否只用了一条资料…）
5. 纠正重试             核查未通过时，带着「上一次没通过」的具体原因再问一次（至多一次）
6. 输出与归档           汇总答案、引用、核查结论与完整步骤日志
```

三条设计原则
------------
1. **失败要中止，并说清中止在哪一步**。检索不到资料时不会硬着头皮让模型自由发挥；
   中止后剩余步骤一律记为「跳过」并附原因，日志里能看出流程是在哪一步停下的。
2. **核查结论必须可信**。核查项是结构化的（有没有编号、编号是否越界、引用是否都有来源），
   不是让模型自我评价「我觉得没问题」。核查不通过就如实报告，不通过就是不通过。
3. **纠正只做一次**。反复重试会掩盖问题、消耗额度，也会让日志失真；
   一次不成功就以「核查未通过」的状态输出，把问题暴露给用户而不是藏起来。

可测试性
--------
工作流只依赖注入进来的 ``Repository`` / ``QAEngine`` / ``Retriever`` 与时钟，
因此单元测试可以完全离线运行：用假后端驱动各种分支，不需要联网也不需要 API Key。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from src.data.repository import Repository
from src.qa import prompt as qa_prompt
from src.qa.engine import QAEngine, QAResult
from src.qa.errors import (
    AllBackendsFailedError,
    QuestionError,
    describe_exception,
    split_degradations,
)
from src.qa.retriever import Passage

# --------------------------------------------------------------------------
# 步骤定义
# --------------------------------------------------------------------------

STEP_INTENT = "intent"
STEP_RETRIEVE = "retrieve"
STEP_ANSWER = "answer"
STEP_VERIFY = "verify"
STEP_REVISE = "revise"
STEP_FINALIZE = "finalize"

#: 步骤的固定顺序。工作流要么按这个顺序执行，要么在某一步中止后把余下的全部跳过。
STEP_ORDER: Tuple[str, ...] = (
    STEP_INTENT,
    STEP_RETRIEVE,
    STEP_ANSWER,
    STEP_VERIFY,
    STEP_REVISE,
    STEP_FINALIZE,
)

STEP_TITLES: Dict[str, str] = {
    STEP_INTENT: "问题解析与实体锚定",
    STEP_RETRIEVE: "资料检索",
    STEP_ANSWER: "依据资料作答",
    STEP_VERIFY: "引用自我核查",
    STEP_REVISE: "纠正重试",
    STEP_FINALIZE: "输出与归档",
}

#: 每一步做什么（供界面展示流程说明，与代码里的实现一一对应）
STEP_DUTIES: Dict[str, str] = {
    STEP_INTENT: "启发式判断提问类型，并把问题里出现的实体名称与别名锚定出来。",
    STEP_RETRIEVE: "据此检索文化资料；检索不到就地中止，不让模型凭记忆作答。",
    STEP_ANSWER: "把资料编号后交给后端降级链（Dify → 大模型 → 本地检索式）作答。",
    STEP_VERIFY: "结构化核查回答里的引用：有编号、不越界、每条都能落到来源。",
    STEP_REVISE: "核查未通过时带着具体原因再问一次（至多一次），不反复重试。",
    STEP_FINALIZE: "汇总答案、引用、核查结论与完整步骤日志，供人工复核。",
}

#: 步骤状态 → 中文标签
STATUS_LABELS: Dict[str, str] = {
    "ok": "完成",
    "warn": "有警告",
    "failed": "失败",
    "skipped": "跳过",
}

#: 工作流整体状态 → 中文标签
RESULT_LABELS: Dict[str, str] = {
    "completed": "已按预期完成",
    "corrected": "经自我纠正后完成",
    "degraded": "完成但存在问题",
    "aborted": "中途中止",
}

#: 核查项等级
LEVEL_PASS = "pass"
LEVEL_WARN = "warn"
LEVEL_FAIL = "fail"

#: 「检索资料被有效利用」的合格线：被引用的资料占检索结果的比例
UTILIZATION_TARGET = 0.5

#: 从问题里锚定实体的数量上限（锚得太多就失去「聚焦」的意义了）
MAX_ANCHORS = 3

# --------------------------------------------------------------------------
# 提问类型
# --------------------------------------------------------------------------

KIND_DEFINITION = "definition"
KIND_RELATION = "relation"
KIND_ATTRIBUTE = "attribute"
KIND_GENERAL = "general"

KIND_LABELS: Dict[str, str] = {
    KIND_DEFINITION: "定义/介绍类",
    KIND_RELATION: "关系类",
    KIND_ATTRIBUTE: "事实/属性类",
    KIND_GENERAL: "开放类",
}

#: 关键词表。顺序即优先级：先判关系，再判属性，最后判定义。
#: 这是**轻量启发式**而非语义理解——它的作用只是给检索与展示提供一点上下文，
#: 判错也不会影响最终答案的可溯源性，因此不引入模型来做这件事。
_KIND_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        KIND_RELATION,
        ("关系", "属于", "归属", "位于", "关联", "连接", "之间", "有关", "隶属", "辖"),
    ),
    (
        KIND_ATTRIBUTE,
        (
            "哪一年", "什么时候", "何时", "多久", "多少", "几级", "第几", "谁",
            "哪里人", "哪里", "面积", "批次", "年份", "特点", "特色", "区别", "不同",
        ),
    ),
    (
        KIND_DEFINITION,
        ("是什么", "什么是", "介绍", "简介", "含义", "指什么", "什么意思", "是什么样"),
    ),
)


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Intent:
    """第 1 步的产物：问题类型与锚定到的实体。"""

    question: str
    kind: str
    keywords: Tuple[str, ...]
    anchor_ids: Tuple[str, ...]
    anchor_names: Tuple[str, ...]

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    @property
    def summary(self) -> str:
        """一行式结论（步骤时间线上直接展示）。"""
        anchor = "、".join(self.anchor_names) if self.anchor_names else "无"
        return f"提问类型：{self.kind_label}；锚定实体：{anchor}"

    @property
    def detail(self) -> str:
        lines = [
            f"提问类型：{self.kind_label}（命中关键词：{'、'.join(self.keywords) or '无'}）",
            "实体锚定：" + ("、".join(self.anchor_names) if self.anchor_names else "未识别到已知实体"),
        ]
        if not self.anchor_names:
            lines.append(
                "未锚定实体意味着检索只能依赖词面匹配，"
                "可能召回不够聚焦——这一点会如实显示，便于人工判断检索质量。"
            )
        return "\n".join(lines)


@dataclass(frozen=True)
class CheckItem:
    """一条自我核查结论。``level`` 取 ``pass`` / ``warn`` / ``fail``。"""

    label: str
    level: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.level == LEVEL_PASS


@dataclass(frozen=True)
class StepRecord:
    """一步的执行记录：输入、输出、耗时与状态，缺一不可。"""

    key: str
    title: str
    status: str
    input_summary: str
    output_summary: str
    elapsed_ms: int
    detail: str = ""

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def executed(self) -> bool:
        return self.status != "skipped"

    def trace_line(self, index: int) -> str:
        """把一步压成可读的日志行。"""
        head = f"{index}. [{self.status_label}] {self.title}（{self.elapsed_ms} ms）"
        body = [f"   输入：{self.input_summary or '—'}", f"   输出：{self.output_summary or '—'}"]
        if self.status == "skipped" and self.detail:
            body.append(f"   原因：{self.detail.splitlines()[0]}")
        return "\n".join([head, *body])


@dataclass(frozen=True)
class WorkflowResult:
    """一次工作流运行的完整产物。"""

    question: str
    status: str
    steps: Tuple[StepRecord, ...]
    intent: Optional[Intent] = None
    answer_result: Optional[QAResult] = None
    checks: Tuple[CheckItem, ...] = ()
    verdict: str = LEVEL_PASS
    aborted_at: str = ""
    abort_reason: str = ""
    elapsed_ms: int = 0

    # -- 便捷属性 ----------------------------------------------------------

    @property
    def status_label(self) -> str:
        return RESULT_LABELS.get(self.status, self.status)

    @property
    def aborted(self) -> bool:
        return self.status == "aborted"

    @property
    def answer(self) -> str:
        return self.answer_result.answer if self.answer_result else ""

    @property
    def citations(self) -> Tuple:
        return self.answer_result.citations if self.answer_result else ()

    @property
    def passages(self) -> Tuple[Passage, ...]:
        return self.answer_result.passages if self.answer_result else ()

    @property
    def passed_checks(self) -> int:
        return sum(1 for c in self.checks if c.level == LEVEL_PASS)

    @property
    def failed_checks(self) -> Tuple[CheckItem, ...]:
        return tuple(c for c in self.checks if c.level == LEVEL_FAIL)

    @property
    def steps_executed(self) -> int:
        return sum(1 for s in self.steps if s.executed)

    def step(self, key: str) -> Optional[StepRecord]:
        """按 key 取某一步的记录（不存在时返回 ``None``）。"""
        return next((s for s in self.steps if s.key == key), None)

    def trace(self) -> Tuple[str, ...]:
        """完整日志：每一步一行头 + 输入/输出。用于界面展示与人工复核。"""
        return tuple(s.trace_line(i) for i, s in enumerate(self.steps, start=1))

    def trace_text(self) -> str:
        return "\n".join(self.trace())


# --------------------------------------------------------------------------
# 第 1 步：问题解析与实体锚定
# --------------------------------------------------------------------------


def _keyword_hits(question: str) -> Tuple[str, ...]:
    for kind, words in _KIND_KEYWORDS:
        hits = tuple(w for w in words if w in question)
        if hits:
            return (kind, *hits[:3])
    return (KIND_GENERAL,)


def detect_anchors(
    repository: Repository,
    question: str,
    limit: int = MAX_ANCHORS,
) -> Tuple[str, ...]:
    """从问题里锚定实体 id。

    名称与别名一起参与匹配，**长词优先**：否则「徽州三雕」这样的专名会被
    更短的「徽州」抢先匹配，锚定结果就偏了。为避免一个词被两个实体重复占用，
    匹配到的片段会被记录，后续实体不再匹配与之重叠的位置。
    """
    text = question or ""
    if not text:
        return ()

    candidates: List[Tuple[str, str]] = []
    for entity in repository.entities:
        candidates.append((entity.name, entity.id))
        for alias in entity.aliases:
            if len(alias) >= 2:
                candidates.append((alias, entity.id))
    candidates.sort(key=lambda item: (-len(item[0]), item[0]))

    taken: List[Tuple[int, int]] = []
    found: List[str] = []
    for name, entity_id in candidates:
        start = text.find(name)
        while start != -1:
            end = start + len(name)
            if not any(not (end <= s or start >= e) for s, e in taken):
                taken.append((start, end))
                if entity_id not in found:
                    found.append(entity_id)
                break
            start = text.find(name, start + 1)
        if len(found) >= limit:
            break
    return tuple(found)


def analyse_question(repository: Repository, question: str) -> Intent:
    """第 1 步的纯函数实现（独立出来便于单测）。"""
    hits = _keyword_hits(question)
    kind, keywords = hits[0], tuple(hits[1:])
    anchor_ids = detect_anchors(repository, question)
    names: List[str] = []
    for entity_id in anchor_ids:
        entity = repository.get(entity_id)
        if entity is not None:
            names.append(entity.name)
    return Intent(
        question=question,
        kind=kind,
        keywords=keywords,
        anchor_ids=anchor_ids,
        anchor_names=tuple(names),
    )


def suggest_questions(repository: Repository, limit: int = 4) -> List[str]:
    """生成示例问题。

    取自连接度最高的实体，因此这些问题**一定检索得到资料**，
    点下去不会出现「没反应」或「查无此物」的空跑。
    """
    questions: List[str] = []
    ranked = sorted(repository.entities, key=lambda e: (-repository.degree(e.id), e.name))
    for entity in ranked:
        neighbors = repository.neighbors(entity.id)
        questions.append(f"{entity.name}是什么？")
        if neighbors:
            questions.append(f"{entity.name}与{neighbors[0].entity.name}有什么关系？")
        if len(questions) >= limit * 2:
            break
    seen: set = set()
    unique: List[str] = []
    for question in questions:
        if question not in seen:
            seen.add(question)
            unique.append(question)
    return unique[:limit]


# --------------------------------------------------------------------------
# 第 4 步：自我核查
# --------------------------------------------------------------------------


def verify_answer(result: QAResult) -> Tuple[CheckItem, ...]:
    """结构化核查一次作答的引用质量。

    这里刻意**不使用模型自评**：核查项全部可由程序判定，
    因此结论可复现、可测试，也不会被「我觉得很好」这类话糊弄过去。
    """
    answer = (result.answer or "").strip()
    citations = result.citations
    passages = result.passages

    checks: List[CheckItem] = [
        CheckItem("回答非空", LEVEL_PASS if answer else LEVEL_FAIL, f"回答 {len(answer)} 字"),
    ]

    if citations:
        item = CheckItem("标注了来源编号", LEVEL_PASS, f"引用 {len(citations)} 处编号")
    else:
        item = CheckItem(
            "标注了来源编号",
            LEVEL_FAIL,
            "回答里没有任何 [n] 编号；本项目要求每个事实都必须可溯源",
        )
    checks.append(item)

    if result.invalid_citations:
        bad = "、".join(f"[{n}]" for n in result.invalid_citations)
        checks.append(
            CheckItem("引用编号均指向真实资料", LEVEL_FAIL, f"出现不存在的编号 {bad}")
        )
    else:
        checks.append(CheckItem("引用编号均指向真实资料", LEVEL_PASS, "未发现越界编号"))

    missing = [c.index for c in citations if not c.sources]
    if missing:
        checks.append(
            CheckItem(
                "每条引用都可核查",
                LEVEL_FAIL,
                "以下编号对应的资料没有登记来源：" + "、".join(f"[{n}]" for n in missing),
            )
        )
    elif citations:
        checks.append(CheckItem("每条引用都可核查", LEVEL_PASS, "全部引用都能落到登记来源"))
    else:
        checks.append(CheckItem("每条引用都可核查", LEVEL_FAIL, "没有可核查的引用"))

    if passages:
        used = len({c.index for c in citations})
        ratio = used / len(passages)
        level = LEVEL_PASS if ratio >= UTILIZATION_TARGET else LEVEL_WARN
        checks.append(
            CheckItem(
                "检索资料被有效利用",
                level,
                f"被引用 {used}/{len(passages)} 条（{ratio:.0%}）；"
                + ("其余资料未被回答使用，可人工核查检索是否偏了。" if level == LEVEL_WARN else "利用率正常"),
            )
        )

    # 降级要看性质：没配 Dify 之类的「配置性跳过」是预期行为，
    # 只有「配了却失败」（超时、5xx、空回答）才是真问题。
    config_skips, runtime_failures = split_degradations(result.degradations)
    if runtime_failures:
        checks.append(
            CheckItem(
                "未发生后端故障",
                LEVEL_WARN,
                "；".join(runtime_failures),
            )
        )
    elif config_skips:
        checks.append(
            CheckItem(
                "未发生后端故障",
                LEVEL_PASS,
                "以下后端未配置，属预期跳过：" + "；".join(config_skips),
            )
        )
    else:
        checks.append(CheckItem("未发生后端故障", LEVEL_PASS, "降级链完整可用"))
    return tuple(checks)


def verdict_of(checks: Sequence[CheckItem]) -> str:
    """由核查项汇总结论：任一项失败即失败，有警告则警告，否则通过。"""
    levels = {c.level for c in checks}
    if LEVEL_FAIL in levels:
        return LEVEL_FAIL
    if LEVEL_WARN in levels:
        return LEVEL_WARN
    return LEVEL_PASS


# --------------------------------------------------------------------------
# 工作流
# --------------------------------------------------------------------------


class AgentWorkflow:
    """六步可追踪工作流。"""

    def __init__(
        self,
        repository: Repository,
        *,
        engine: Optional[QAEngine] = None,
        top_k: Optional[int] = None,
        clock: Callable[[], float] = time.perf_counter,
    ):
        self._repo = repository
        self._engine = engine or QAEngine(repository, top_k=top_k)
        self._retriever = self._engine.retriever
        self._top_k = max(1, int(top_k)) if top_k else self._retriever.top_k
        self._clock = clock

    # ------------------------------------------------------------------
    # 组成信息
    # ------------------------------------------------------------------

    @property
    def engine(self) -> QAEngine:
        return self._engine

    @property
    def repository(self) -> Repository:
        return self._repo

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def run(self, question: str) -> WorkflowResult:
        """按 :data:`STEP_ORDER` 执行工作流，返回带完整步骤日志的结果。

        任何一步判定为致命失败（问题不合法 / 检索不到资料 / 后端全挂）时，
        立即中止并把余下步骤记为「跳过」——不做静默兜底，也不继续往下走。
        """
        started = self._clock()
        steps: List[StepRecord] = []

        # --- 第 1 步：问题解析与实体锚定 -------------------------------
        t0 = self._clock()
        try:
            text = qa_prompt.validate_question(question)
        except QuestionError as exc:
            steps.append(
                StepRecord(
                    key=STEP_INTENT,
                    title=STEP_TITLES[STEP_INTENT],
                    status="failed",
                    input_summary=_brief(question),
                    output_summary=f"问题不合法：{exc.reason}",
                    elapsed_ms=_ms(self._clock() - t0),
                    detail=exc.reason,
                )
            )
            _skip_remaining(steps, after=STEP_INTENT, reason=f"第 1 步未通过：{exc.reason}")
            return self._finish(
                question=(question or "").strip(),
                status="aborted",
                steps=steps,
                aborted_at=STEP_INTENT,
                abort_reason=exc.reason,
                started=started,
            )

        intent = analyse_question(self._repo, text)
        steps.append(
            StepRecord(
                key=STEP_INTENT,
                title=STEP_TITLES[STEP_INTENT],
                status="ok" if intent.anchor_ids else "warn",
                input_summary=_brief(text),
                output_summary=intent.summary,
                elapsed_ms=_ms(self._clock() - t0),
                detail=intent.detail,
            )
        )

        # --- 第 2 步：资料检索 -----------------------------------------
        t0 = self._clock()
        passages = self._retrieve(text, intent)
        if not passages:
            steps.append(
                StepRecord(
                    key=STEP_RETRIEVE,
                    title=STEP_TITLES[STEP_RETRIEVE],
                    status="failed",
                    input_summary=_brief(text),
                    output_summary="没有检索到任何相关资料",
                    elapsed_ms=_ms(self._clock() - t0),
                    detail="本地资料库中没有覆盖该主题的内容，工作流就此中止。",
                )
            )
            reason = "本地资料库中没有检索到与该问题相关的资料"
            _skip_remaining(steps, after=STEP_RETRIEVE, reason=reason)
            return self._finish(
                question=text,
                status="aborted",
                steps=steps,
                intent=intent,
                aborted_at=STEP_RETRIEVE,
                abort_reason=reason,
                started=started,
            )

        anchored_hits = [p for p in passages if p.entity_id in intent.anchor_ids]
        steps.append(
            StepRecord(
                key=STEP_RETRIEVE,
                title=STEP_TITLES[STEP_RETRIEVE],
                status="ok" if anchored_hits else "warn",
                input_summary=_brief(text) + (
                    f"（锚定实体：{'、'.join(intent.anchor_names)}）" if intent.anchor_names else ""
                ),
                output_summary=(
                    f"命中 {len(passages)} 条资料，其中 {len(anchored_hits)} 条来自锚定实体"
                    if anchored_hits
                    else f"命中 {len(passages)} 条资料，但没有一条来自锚定实体"
                ),
                elapsed_ms=_ms(self._clock() - t0),
                detail=_passage_detail(passages),
            )
        )

        # --- 第 3 步：依据资料作答 -------------------------------------
        t0 = self._clock()
        try:
            answer_result = self._engine.answer_from(text, passages, started=t0)
        except AllBackendsFailedError as exc:
            attempts = "\n".join(f"  - {a}" for a in exc.attempts)
            steps.append(
                StepRecord(
                    key=STEP_ANSWER,
                    title=STEP_TITLES[STEP_ANSWER],
                    status="failed",
                    input_summary=f"{len(passages)} 条资料",
                    output_summary="所有后端均不可用",
                    elapsed_ms=_ms(self._clock() - t0),
                    detail=attempts,
                )
            )
            reason = "问答后端全部不可用：" + "；".join(exc.attempts)
            _skip_remaining(steps, after=STEP_ANSWER, reason=reason)
            return self._finish(
                question=text,
                status="aborted",
                steps=steps,
                intent=intent,
                aborted_at=STEP_ANSWER,
                abort_reason=reason,
                started=started,
            )

        steps.append(
            StepRecord(
                key=STEP_ANSWER,
                title=STEP_TITLES[STEP_ANSWER],
                # 只有运行时故障才算「作答步骤有问题」；未配置的高优先后端被跳过属预期
                status="warn" if split_degradations(answer_result.degradations)[1] else "ok",
                input_summary=f"{len(passages)} 条资料 → {answer_result.backend_label}",
                output_summary=(
                    f"生成 {len(answer_result.answer)} 字回答，引用 {len(answer_result.citations)} 处，"
                    f"用时 {answer_result.elapsed_ms} ms"
                ),
                elapsed_ms=_ms(self._clock() - t0),
                detail=_answer_detail(answer_result),
            )
        )

        # --- 第 4 步：引用自我核查 -------------------------------------
        t0 = self._clock()
        checks = verify_answer(answer_result)
        verdict = verdict_of(checks)
        steps.append(
            StepRecord(
                key=STEP_VERIFY,
                title=STEP_TITLES[STEP_VERIFY],
                status="ok" if verdict == LEVEL_PASS else "warn",
                input_summary=f"回答 {len(answer_result.answer)} 字 / 引用 {len(answer_result.citations)} 处",
                output_summary=(
                    f"核查结论：{_verdict_label(verdict)}"
                    f"（{sum(1 for c in checks if c.ok)}/{len(checks)} 项通过）"
                ),
                elapsed_ms=_ms(self._clock() - t0),
                detail="\n".join(
                    f"[{'通过' if c.level == LEVEL_PASS else '警告' if c.level == LEVEL_WARN else '未通过'}] "
                    f"{c.label}：{c.detail}"
                    for c in checks
                ),
            )
        )

        # --- 第 5 步：纠正重试（至多一次） -----------------------------
        if verdict != LEVEL_FAIL:
            steps.append(
                StepRecord(
                    key=STEP_REVISE,
                    title=STEP_TITLES[STEP_REVISE],
                    status="skipped",
                    input_summary="—",
                    output_summary="核查未发现必须纠正的问题，无需重试",
                    elapsed_ms=0,
                    detail="只有核查结论为「未通过」时才会触发纠正，避免无谓的重复调用。",
                )
            )
        else:
            t0 = self._clock()
            try:
                revised = self._engine.answer_from(
                    text,
                    passages,
                    directive=qa_prompt.STRICT_RETRY_DIRECTIVE,
                    started=t0,
                )
            except Exception as exc:  # noqa: BLE001 - 纠正失败不应掩盖原有答案
                steps.append(
                    StepRecord(
                        key=STEP_REVISE,
                        title=STEP_TITLES[STEP_REVISE],
                        status="failed",
                        input_summary="带纠正指令重新作答",
                        output_summary=f"纠正未成功：{describe_exception(exc)}",
                        elapsed_ms=_ms(self._clock() - t0),
                        detail=(
                            "纠正失败不影响已有回答，上面展示的仍是第一次作答的结果。\n"
                            f"失败原因：{describe_exception(exc)}"
                        ),
                    )
                )
            else:
                new_checks = verify_answer(revised)
                new_verdict = verdict_of(new_checks)
                steps.append(
                    StepRecord(
                        key=STEP_REVISE,
                        title=STEP_TITLES[STEP_REVISE],
                        status="ok" if new_verdict == LEVEL_PASS else "warn",
                        input_summary="带纠正指令重新作答",
                        output_summary=(
                            f"重新作答后引用 {len(revised.citations)} 处，"
                            f"核查结论：{_verdict_label(new_verdict)}"
                            f"（{sum(1 for c in new_checks if c.ok)}/{len(new_checks)} 项通过）"
                        ),
                        elapsed_ms=_ms(self._clock() - t0),
                        detail=(
                            "纠正指令：\n" + qa_prompt.STRICT_RETRY_DIRECTIVE + "\n\n"
                            "纠正后再核查：\n"
                            + "\n".join(
                                f"[{'通过' if c.level == LEVEL_PASS else '警告' if c.level == LEVEL_WARN else '未通过'}] "
                                f"{c.label}：{c.detail}"
                                for c in new_checks
                            )
                        ),
                    )
                )
                answer_result, checks, verdict = revised, new_checks, new_verdict

        # --- 第 6 步：输出与归档 ---------------------------------------
        t0 = self._clock()
        final_status = _final_status(steps, verdict)
        steps.append(
            StepRecord(
                key=STEP_FINALIZE,
                title=STEP_TITLES[STEP_FINALIZE],
                status="ok" if final_status in {"completed", "corrected"} else "warn",
                input_summary=f"核查结论：{_verdict_label(verdict)}",
                output_summary=(
                    f"归档回答 {len(answer_result.answer)} 字、引用 {len(answer_result.citations)} 处、"
                    f"步骤日志 {len(steps) + 1} 条"
                ),
                elapsed_ms=_ms(self._clock() - t0),
                detail="完整步骤日志：\n" + "\n".join(
                    s.trace_line(i) for i, s in enumerate([*steps], start=1)
                ),
            )
        )

        return self._finish(
            question=text,
            status=final_status,
            steps=steps,
            intent=intent,
            answer_result=answer_result,
            checks=checks,
            verdict=verdict,
            started=started,
        )

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _retrieve(self, question: str, intent: Intent) -> List[Passage]:
        """检索资料，并用锚定实体做一轮补强。

        两步：
        1. 放宽条数检索（``top_k * 2``），让被 BM25 压在后面的锚定实体有机会露面；
        2. 锚定实体若仍未出现，直接用实体名再查一次并置顶——
           名字都锚出来了却拿不到它的资料，属于明显的浪费。
        """
        wide = max(self._top_k * 2, self._top_k + len(intent.anchor_ids))
        hits = list(self._retriever.retrieve(question, top_k=wide))
        found = {p.entity_id for p in hits}

        anchored: List[Passage] = []
        for entity_id in intent.anchor_ids:
            if entity_id in found:
                anchored.append(next(p for p in hits if p.entity_id == entity_id))
                continue
            entity = self._repo.get(entity_id)
            if entity is None:
                continue
            extra = self._retriever.retrieve_one(entity.name)
            if extra is not None:
                anchored.append(extra)

        if not anchored:
            return hits[: self._top_k]

        anchor_ids = {p.entity_id for p in anchored}
        ordered = anchored + [p for p in hits if p.entity_id not in anchor_ids]
        return ordered[: self._top_k]

    def _finish(
        self,
        *,
        question: str,
        status: str,
        steps: List[StepRecord],
        started: float,
        intent: Optional[Intent] = None,
        answer_result: Optional[QAResult] = None,
        checks: Sequence[CheckItem] = (),
        verdict: str = LEVEL_PASS,
        aborted_at: str = "",
        abort_reason: str = "",
    ) -> WorkflowResult:
        return WorkflowResult(
            question=question,
            status=status,
            steps=tuple(steps),
            intent=intent,
            answer_result=answer_result,
            checks=tuple(checks),
            verdict=verdict,
            aborted_at=aborted_at,
            abort_reason=abort_reason,
            elapsed_ms=_ms(self._clock() - started),
        )


# --------------------------------------------------------------------------
# 助手
# --------------------------------------------------------------------------


def _ms(seconds: float) -> int:
    return max(0, int(round(seconds * 1000)))


def _brief(text: str, limit: int = 40) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _verdict_label(verdict: str) -> str:
    return {LEVEL_PASS: "全部通过", LEVEL_WARN: "通过但有警告", LEVEL_FAIL: "未通过"}.get(
        verdict, verdict
    )


def _all_ok(steps: Sequence[StepRecord]) -> bool:
    """已执行的步骤是否都没有失败与警告（跳过的步骤不算问题）。"""
    return all(s.status in {"ok", "skipped"} for s in steps)


def _final_status(steps: Sequence[StepRecord], verdict: str) -> str:
    """按最终状态判定整体结论。

    - 核查通过且中途做过纠正 → ``corrected``（回答本身已可溯源，但过程值得记一笔）；
    - 核查通过且所有步骤干净 → ``completed``；
    - 其余（核查未通过，或存在失败 / 警告步骤）→ ``degraded``。
    """
    if verdict != LEVEL_PASS:
        return "degraded"
    revised = any(s.key == STEP_REVISE and s.status == "ok" for s in steps)
    if revised:
        return "corrected"
    return "completed" if _all_ok(steps) else "degraded"


def _skip_remaining(steps: List[StepRecord], after: str, reason: str) -> None:
    """把 ``after`` 之后的步骤全部记为「跳过」，并写明中止原因。"""
    index = STEP_ORDER.index(after)
    for key in STEP_ORDER[index + 1 :]:
        steps.append(
            StepRecord(
                key=key,
                title=STEP_TITLES[key],
                status="skipped",
                input_summary="—",
                output_summary="上一步中止，本步骤未执行",
                elapsed_ms=0,
                detail=reason,
            )
        )


def _passage_detail(passages: Sequence[Passage]) -> str:
    lines = []
    for index, passage in enumerate(passages, start=1):
        lines.append(
            f"[{index}] {passage.title}（{passage.category_name}）"
            f"　相关度 {passage.score:.2f}　来源 {len(passage.sources)} 条"
        )
    return "\n".join(lines)


def _answer_detail(result: QAResult) -> str:
    lines = [
        f"后端：{result.backend_label}",
        f"模型：{result.model or '—'}",
        f"耗时：{result.elapsed_ms} ms",
    ]
    if result.usage.get("total_tokens"):
        lines.append(f"tokens：{result.usage['total_tokens']}")
    lines.append(f"引用：{len(result.citations)} 处；未被引用资料：{len(result.unused_passages)} 条")
    if result.degradations:
        lines.append("降级说明：")
        lines.extend(f"  - {d}" for d in result.degradations)
    return "\n".join(lines)


__all__ = [
    "STEP_ORDER",
    "STEP_TITLES",
    "STEP_DUTIES",
    "STEP_INTENT",
    "STEP_RETRIEVE",
    "STEP_ANSWER",
    "STEP_VERIFY",
    "STEP_REVISE",
    "STEP_FINALIZE",
    "STATUS_LABELS",
    "RESULT_LABELS",
    "LEVEL_PASS",
    "LEVEL_WARN",
    "LEVEL_FAIL",
    "KIND_LABELS",
    "Intent",
    "CheckItem",
    "StepRecord",
    "WorkflowResult",
    "AgentWorkflow",
    "analyse_question",
    "detect_anchors",
    "verify_answer",
    "verdict_of",
    "suggest_questions",
]
