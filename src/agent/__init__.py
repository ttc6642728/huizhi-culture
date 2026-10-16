"""智能体层：可追踪的多步问答工作流。

对外入口：
    :class:`~src.agent.workflow.AgentWorkflow`   六步工作流（检索 → 作答 → 自我核查 → 输出）
    :class:`~src.agent.workflow.WorkflowResult`  一次运行的完整产物（含逐步日志）
    :func:`~src.agent.workflow.verify_answer`    结构化的引用核查（可单独调用）

步骤顺序、职责与状态标签均以常量形式导出（:data:`~src.agent.workflow.STEP_ORDER`、
:data:`~src.agent.workflow.STEP_DUTIES`），界面直接引用这些常量，
避免「文档写一套、代码做另一套」。
"""

from src.agent.workflow import (
    LEVEL_FAIL,
    LEVEL_PASS,
    LEVEL_WARN,
    RESULT_LABELS,
    STATUS_LABELS,
    STEP_ANSWER,
    STEP_DUTIES,
    STEP_FINALIZE,
    STEP_INTENT,
    STEP_ORDER,
    STEP_RETRIEVE,
    STEP_REVISE,
    STEP_TITLES,
    STEP_VERIFY,
    AgentWorkflow,
    CheckItem,
    Intent,
    StepRecord,
    WorkflowResult,
    analyse_question,
    detect_anchors,
    suggest_questions,
    verdict_of,
    verify_answer,
)

__all__ = [
    "AgentWorkflow",
    "WorkflowResult",
    "StepRecord",
    "CheckItem",
    "Intent",
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
    "analyse_question",
    "detect_anchors",
    "verify_answer",
    "verdict_of",
    "suggest_questions",
]
