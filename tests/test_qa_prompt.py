"""提示词与引用解析测试。

提示词决定了「答案能不能被核查」，因此这里重点验证三件事：
资料被正确编号、模型被明确约束、回答里的引用能被可靠解析出来。
"""

from __future__ import annotations

import pytest

from src.data.loader import Source
from src.qa import prompt as qa_prompt
from src.qa.errors import QuestionError
from src.qa.retriever import Passage


def _passage(
    title: str = "宏村",
    text: str = "位于黟县的古村落。",
    category: str = "古村落",
    with_source: bool = True,
) -> Passage:
    sources = (
        (
            Source(
                id="s1",
                type="web",
                title="皖南古村落",
                publisher="联合国教科文组织",
                url="https://example.org/a",
            ),
        )
        if with_source
        else ()
    )
    return Passage(
        entity_id=title,
        title=title,
        category_name=category,
        text=text,
        score=1.0,
        matched_terms=(title,),
        sources=sources,
        relation_count=1,
    )


# --------------------------------------------------------------------------
# 系统提示词
# --------------------------------------------------------------------------


def test_system_prompt_forbids_inventing_content() -> None:
    text = qa_prompt.SYSTEM_PROMPT
    assert "只能使用" in text, "必须明确限定只能使用给定资料"
    assert "不许补充" in text or "不要" in text
    assert "编造" in text


def test_system_prompt_requires_citation_format() -> None:
    text = qa_prompt.SYSTEM_PROMPT
    assert "[1]" in text, "必须给出引用编号的格式示例"
    assert "编号" in text


def test_system_prompt_tells_model_how_to_refuse() -> None:
    text = qa_prompt.SYSTEM_PROMPT
    assert "不足以回答" in text, "必须给出资料不足时的标准话术"
    assert "无关" in text, "必须给出与徽州文化无关时的处理方式"


# --------------------------------------------------------------------------
# 资料编号
# --------------------------------------------------------------------------


def test_passages_are_numbered_from_one() -> None:
    passages = [_passage("宏村"), _passage("西递"), _passage("南屏")]
    block = qa_prompt.format_passages(passages)
    assert "[1] 宏村" in block
    assert "[2] 西递" in block
    assert "[3] 南屏" in block
    assert "[0]" not in block, "编号必须从 1 开始"


def test_passage_block_includes_category_and_source() -> None:
    block = qa_prompt.format_passage(1, _passage())
    assert "古村落" in block, "应标注分类，帮助模型理解资料性质"
    assert "联合国教科文组织" in block, "应带上来源出版方"


def test_passage_without_source_is_still_formatted() -> None:
    block = qa_prompt.format_passage(2, _passage(with_source=False))
    assert "[2]" in block
    assert "来源：" not in block, "没有来源就不该伪造一行「来源：」"


def test_long_passage_is_truncated() -> None:
    long_text = "徽" * (qa_prompt.MAX_PASSAGE_CHARS + 500)
    block = qa_prompt.format_passage(1, _passage(text=long_text))
    assert len(block) < len(long_text)
    assert "…" in block, "截断应有可见标记"


def test_empty_passages_are_stated_explicitly() -> None:
    block = qa_prompt.format_passages([])
    assert "没有找到" in block, "空资料必须明说，而不是留白让模型自由发挥"


# --------------------------------------------------------------------------
# 提示词组装
# --------------------------------------------------------------------------


def test_user_prompt_contains_question_and_all_passages() -> None:
    passages = [_passage("宏村"), _passage("西递")]
    text = qa_prompt.build_user_prompt("宏村和西递有什么关系？", passages)
    assert "宏村和西递有什么关系？" in text
    assert "[1]" in text and "[2]" in text
    assert "【资料】" in text and "【问题】" in text
    assert "标注来源编号" in text, "结尾要再强调一次引用要求"


def test_build_messages_has_system_and_user_roles() -> None:
    messages = qa_prompt.build_messages("宏村是什么？", [_passage()])
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[0]["content"] == qa_prompt.SYSTEM_PROMPT
    assert "宏村是什么？" in messages[1]["content"]


def test_dify_query_merges_question_and_passages() -> None:
    query = qa_prompt.build_dify_query("徽墨是什么？", [_passage("徽墨")])
    assert query.startswith("徽墨是什么？")
    assert "[1] 徽墨" in query


# --------------------------------------------------------------------------
# 纠正指令（智能体工作流的自我纠正路径）
# --------------------------------------------------------------------------


def test_prompt_without_directive_has_no_extra_section() -> None:
    """正常提问的提示词不能凭空多出一个区块（保持与 P4 完全一致）。"""
    text = qa_prompt.build_user_prompt("宏村是什么？", [_passage()])
    assert "【补充要求】" not in text
    query = qa_prompt.build_dify_query("宏村是什么？", [_passage()])
    assert "【补充要求】" not in query


def test_user_prompt_appends_directive() -> None:
    text = qa_prompt.build_user_prompt(
        "宏村是什么？", [_passage()], qa_prompt.STRICT_RETRY_DIRECTIVE
    )
    assert "【补充要求】" in text
    assert qa_prompt.STRICT_RETRY_DIRECTIVE in text


def test_messages_and_dify_query_carry_directive() -> None:
    messages = qa_prompt.build_messages("宏村是什么？", [_passage()], "请补上编号")
    assert "请补上编号" in messages[1]["content"]
    query = qa_prompt.build_dify_query("宏村是什么？", [_passage()], "请补上编号")
    assert "请补上编号" in query


def test_blank_directive_is_ignored() -> None:
    """空白指令不应产生空区块——否则等于给模型一段无意义的噪声。"""
    text = qa_prompt.build_user_prompt("宏村是什么？", [_passage()], "   ")
    assert "【补充要求】" not in text


def test_retry_directive_states_the_specific_defect() -> None:
    """纠正指令要直指缺陷（缺编号 / 编号不存在），而不是笼统的「请重答」。"""
    directive = qa_prompt.STRICT_RETRY_DIRECTIVE
    assert "编号" in directive
    assert "不存在的编号" in directive
    assert "重新作答" in directive


# --------------------------------------------------------------------------
# 引用解析
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("宏村位于黟县 [1]。", [1]),
        ("两者同属黟县 [1][2]。", [1, 2]),
        ("同属黟县 [1] 、[3]。", [1, 3]),
        ("全角编号也支持【2】。", [2]),
        ("没有引用编号。", []),
        ("", []),
    ],
)
def test_citation_numbers_parses(answer: str, expected: list) -> None:
    assert qa_prompt.citation_numbers(answer) == expected


def test_citation_numbers_dedupes_and_keeps_order() -> None:
    assert qa_prompt.citation_numbers("[3] 甲 [1] 乙 [3] 丙 [1]") == [3, 1]


def test_citation_numbers_ignores_non_numeric_brackets() -> None:
    assert qa_prompt.citation_numbers("见 [注] 与 [abc] 以及 []") == []


def test_citation_numbers_handles_multi_digit() -> None:
    assert qa_prompt.citation_numbers("见 [12] 与 [3]") == [12, 3]


# --------------------------------------------------------------------------
# 回答清理
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("```\n宏村位于黟县。\n```", "宏村位于黟县。"),
        ("```markdown\n宏村位于黟县。\n```", "宏村位于黟县。"),
        ("回答：宏村位于黟县。", "宏村位于黟县。"),
        ("答案：宏村位于黟县。", "宏村位于黟县。"),
        ("宏村位于黟县。", "宏村位于黟县。"),
        ("  宏村位于黟县。  ", "宏村位于黟县。"),
    ],
)
def test_strip_wrapping_cleans_model_output(raw: str, expected: str) -> None:
    assert qa_prompt.strip_wrapping(raw) == expected


def test_strip_wrapping_keeps_inner_code_block() -> None:
    raw = "说明如下：\n```json\n{}\n```"
    assert "```json" in qa_prompt.strip_wrapping(raw), "内层代码块不应被误删"


# --------------------------------------------------------------------------
# 问题校验
# --------------------------------------------------------------------------


def test_validate_question_strips_and_returns() -> None:
    assert qa_prompt.validate_question("  宏村是什么？  ") == "宏村是什么？"


@pytest.mark.parametrize("bad", ["", "   ", "好"])
def test_validate_question_rejects_too_short(bad: str) -> None:
    with pytest.raises(QuestionError):
        qa_prompt.validate_question(bad)


def test_validate_question_rejects_too_long() -> None:
    with pytest.raises(QuestionError) as excinfo:
        qa_prompt.validate_question("徽" * (qa_prompt.MAX_QUESTION_CHARS + 1))
    assert str(qa_prompt.MAX_QUESTION_CHARS) in str(excinfo.value)


def test_validate_question_error_message_is_user_facing() -> None:
    with pytest.raises(QuestionError) as excinfo:
        qa_prompt.validate_question("")
    assert excinfo.value.reason, "异常必须带可展示给用户的原因"
    assert "请输入" in excinfo.value.reason
