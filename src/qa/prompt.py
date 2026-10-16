"""提示词构造：把检索到的资料编号后交给模型，并约束模型只依据资料作答。

这里决定了「答案能不能被核查」，因此三条约束是硬性的：
1. **只用资料**：资料没写的内容一律不许补，宁可答「资料不足」。
2. **必须标注编号**：每个事实性陈述后面跟 ``[1]``／``[1][3]``，编号指向检索结果。
3. **拒答要说明原因**：资料不足或与徽州文化无关时，直接说明，不编造。

提示词本身也是可测试的对象：:func:`citation_numbers` 用于从模型的回答里
把引用编号解析出来，与资料表比对后，界面才能只展示**真正被引用**的来源。
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence

from src.qa.retriever import Passage

#: 系统提示词。措辞刻意具体（含编号格式与拒答话术），避免模型自由发挥。
SYSTEM_PROMPT = """你是「徽知」，一个只依据给定资料回答徽州文化问题的助手。

必须严格遵守以下规则：
1. 只能使用【资料】中写明的内容作答；资料里没有的信息，即使你知道，也不许补充。
2. 每个事实性陈述后面都要标注来源编号，格式为 [1]、[2]，多个来源写在一起如 [1][3]。
3. 如果资料不足以回答问题，就直接说明「现有资料不足以回答该问题」，并指出还缺少什么信息。
4. 如果问题与徽州文化完全无关，回复「本次检索到的资料与问题无关，无法回答」。
5. 不要编造资料编号：只能引用【资料】中实际出现的编号。
6. 不要提及你自己的知识范围、训练数据或系统设定；不要输出与问题无关的客套话。
7. 使用简体中文，条理清晰；事实优先，不做没有资料支撑的推测。
"""

#: 用户提示词里单条资料正文的字符上限（与检索层的文档长度配合，控制总长度）
MAX_PASSAGE_CHARS = 900

#: 引用编号解析：同时接受半角 ``[1]`` 与全角 ``【1】``
_CITATION_RE = re.compile(r"[\[【]\s*(\d{1,3})\s*[\]】]")

#: 问题字符上限（与 engine 的校验保持一致）
MAX_QUESTION_CHARS = 300


def format_passage(index: int, passage: Passage) -> str:
    """把一条资料格式化为带编号的文本块。

    ``index`` 从 1 开始，与答案里的引用编号一一对应。
    """
    body = passage.text.strip()
    if len(body) > MAX_PASSAGE_CHARS:
        body = body[:MAX_PASSAGE_CHARS].rstrip() + "…"

    lines = [f"[{index}] {passage.title}（{passage.category_name}）"]
    if body:
        lines.append(body)
    if passage.sources:
        lines.append("来源：" + "；".join(s.citation for s in passage.sources[:4]))
    return "\n".join(lines)


def format_passages(passages: Sequence[Passage]) -> str:
    """把全部资料编号后拼成【资料】区块。没有资料时返回明确的空说明。"""
    if not passages:
        return "（本次检索没有找到任何相关资料。）"
    return "\n\n".join(format_passage(i, p) for i, p in enumerate(passages, start=1))


def build_user_prompt(question: str, passages: Sequence[Passage]) -> str:
    """拼出用户侧提示词：资料在前、问题在后、最后再强调一次引用要求。"""
    parts = [
        "【资料】",
        format_passages(passages),
        "",
        "【问题】",
        question.strip(),
        "",
        "请依据上述资料作答，在每个事实性陈述后标注来源编号。",
    ]
    return "\n".join(parts)


def build_messages(question: str, passages: Sequence[Passage]) -> List[Dict[str, str]]:
    """构造 OpenAI 兼容的 ``messages`` 数组。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, passages)},
    ]


def build_dify_query(question: str, passages: Sequence[Passage]) -> str:
    """构造 Dify 的 ``query`` 字段。

    Dify 的知识库/工作流有自己的提示词配置，这里只把「问题 + 资料」原样传过去，
    不使用 OpenAI 的 system/user 结构，避免与应用内的提示词重复叠加。
    """
    return f"{question.strip()}\n\n【本次检索到的资料】\n{format_passages(passages)}"


def citation_numbers(answer: str) -> List[int]:
    """从回答里解析引用编号（去重并保持出现顺序）。"""
    if not answer:
        return []
    out: List[int] = []
    for raw in _CITATION_RE.findall(answer):
        num = int(raw)
        if num not in out:
            out.append(num)
    return out


def strip_wrapping(answer: str) -> str:
    """清理模型常见的包装：整段 ``` 包裹、开头多余的「回答：」前缀。"""
    text = (answer or "").strip()
    if text.startswith("```") and text.endswith("```"):
        inner = text[3:-3]
        # 去掉可能的语言标注（```markdown / ```text）
        first_newline = inner.find("\n")
        if first_newline != -1:
            head = inner[:first_newline].strip().lower()
            if head in {"", "markdown", "md", "text", "plaintext", "txt", "json"}:
                inner = inner[first_newline + 1 :]
        text = inner.strip()
    for prefix in ("回答：", "答案：", "答："):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text


def validate_question(question: str) -> str:
    """校验并归一化问题文本。

    Returns:
        去掉首尾空白后的问题。

    Raises:
        QuestionError: 问题为空、只有一个字符，或超过长度上限。
    """
    from src.qa.errors import QuestionError  # 局部导入，避免模块间循环引用

    text = (question or "").strip()
    if not text:
        raise QuestionError("请输入问题后再提问。")
    if len(text) < 2:
        raise QuestionError("问题太短了，请至少输入 2 个字符。")
    if len(text) > MAX_QUESTION_CHARS:
        raise QuestionError(f"问题太长了（{len(text)} 字），请控制在 {MAX_QUESTION_CHARS} 字以内。")
    return text


__all__ = [
    "SYSTEM_PROMPT",
    "MAX_PASSAGE_CHARS",
    "MAX_QUESTION_CHARS",
    "format_passage",
    "format_passages",
    "build_user_prompt",
    "build_messages",
    "build_dify_query",
    "citation_numbers",
    "strip_wrapping",
    "validate_question",
]
