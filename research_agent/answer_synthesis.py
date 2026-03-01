import logging
import re
from .utils import get_llm_client, clean_answer

logger = logging.getLogger(__name__)

# 答案兜底最大长度：超过此长度视为 trace 而非答案
_MAX_ANSWER_LENGTH = 500


def _extract_last_candidate(trace: str) -> str:
    """
    从推理链中提取最后一个有意义的候选答案。
    优先级：
    1. 最后一个 Final Answer: / 最终答案: 标记后的内容
    2. 最后一个非空段落（截断到合理长度）
    用于 LLM 调用失败时的兜底，避免把整个 trace 返回。
    """
    if not trace:
        return ""

    # 优先：从标记中提取
    markers = [r"Final Answer", r"最终答案", r"正确答案"]
    pattern = r"(?:" + "|".join(markers) + r")[:：]\s*(.+?)(?:\n\n|\Z)"
    matches = re.findall(pattern, trace, re.IGNORECASE | re.DOTALL)
    if matches:
        candidate = matches[-1].strip()
        if candidate:
            return candidate[:_MAX_ANSWER_LENGTH]

    # 次选：取最后一个非空段落（去掉推理标记行）
    paragraphs = [p.strip() for p in trace.split("\n\n") if p.strip()]
    # 过滤掉明显是推理过程的段落（以 Thought/Action/Step 等开头）
    _REASONING_PREFIXES = ("thought", "action", "observation", "step ", "[step", "[debug", "[agent", "[search")
    clean_paras = [
        p for p in paragraphs
        if not p.lower().startswith(_REASONING_PREFIXES)
    ]
    if clean_paras:
        last = clean_paras[-1]
        return last[:_MAX_ANSWER_LENGTH]

    # 兜底：截断 trace
    return trace[-_MAX_ANSWER_LENGTH:].strip()


def process_final_answer(question: str, raw_output: str, original_question: str | None = None) -> str:
    """
    统一处理最终答案：提取、清洗、语言一致性处理。
    合并了verify_and_clean_answer的功能，适用于单agent场景。

    流程：
    1. clean_answer() 纯正则预处理（提取 Final Answer 标记、去噪）
    2. LLM 做语言一致性校正（需要 question 上下文）
    """
    try:
        source_question = original_question if original_question else question
        if not source_question:
            logger.warning("[AnswerProcessor] Question is empty!")
            source_question = ""

        # 第1层：纯正则预处理，减少送入 LLM 的噪音
        preprocessed = clean_answer(raw_output)

        client = get_llm_client(timeout=30.0)

        # 检测问题语言
        is_chinese = any("\u4e00" <= c <= "\u9fff" for c in source_question[:100])
        target_lang = "中文" if is_chinese else "英文"

        prompt = f"""<instruction>
你是一个严格的答案处理专家。需要完成以下任务：
1. 从模型输出中提取最终答案
2. 确保答案语言与问题语言一致
3. 清洗格式
</instruction>
<input_data>
<original_question>
{source_question}
</original_question>
<question>
{source_question}
</question>
<model_output>
{raw_output}
</model_output>
<preprocessed_output>
{preprocessed}
</preprocessed_output>
</input_data>
<processing_rules>
## 任务1: 提取答案
- 定位最后一个 "Final Answer:" 或 "最终答案:" 标记
- 提取该标记之后的所有内容
- 如果未找到标记，从 model_output 的完整上下文中综合判断最可能的最终答案，不要机械地取最后一句

## 任务2: 语言一致性 (最重要)
- 问题语言: {target_lang}
- 答案语言必须与问题语言一致
- 翻译规则:
  - 中文问题 + 英文实体 -> 翻译为中文
  - 英文问题 + 中文实体 -> 翻译为英文
- 实体翻译:
  - 公司名: 使用标准中文译名（如 Mondadori -> 蒙达多利出版社 或 阿诺尔多·蒙达多利出版社）
  - 人名: 使用标准中文名/音译（如 Arnoldo Mondadori -> 阿诺尔多·蒙达多利）

## 任务3: 清洗
- 移除解释性文字
- 移除Markdown格式
- 保持简洁（实体名/数字/年份）
</rules>
<output_format>
直接输出清洗后的答案，不要有任何前缀或解释。
</output_format>"""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )

        if not response or not hasattr(response, "choices") or not response.choices:
            logger.error(f"[AnswerProcessor] Invalid response from LLM")
            # 兜底：preprocessed 可能是整个 trace，改用精确提取
            return preprocessed if len(preprocessed) <= _MAX_ANSWER_LENGTH else _extract_last_candidate(raw_output)

        result = response.choices[0].message.content.strip()
        logger.info(
            f"[AnswerProcessor] Original: {raw_output[:50]}... | Preprocessed: {preprocessed[:50]}... | Final: {result}"
        )
        return result

    except Exception as e:
        logger.error(f"[AnswerProcessor] Exception: {e}")
        fallback = preprocessed if 'preprocessed' in locals() else clean_answer(raw_output)
        # 兜底：如果 fallback 仍是整个 trace，改用精确提取
        return fallback if len(fallback) <= _MAX_ANSWER_LENGTH else _extract_last_candidate(raw_output)


def process_multi_agent_answers(question: str, candidates: list[dict], original_question: str | None = None) -> str:
    """
    合并处理多agent答案：清洗、语言一致性、合成。
    一次性调用LLM完成所有处理，减少token消耗。
    """
    if not candidates:
        return ""

    source_question = original_question if original_question else question

    # 单agent直接处理
    if len(candidates) == 1:
        return process_final_answer(
            question,
            candidates[0].get("trace", ""),
            original_question=source_question,
        )

    # 多agent合并处理
    try:
        client = get_llm_client(timeout=45.0)

        # 检测问题语言
        is_chinese = any("\u4e00" <= c <= "\u9fff" for c in source_question[:100])
        target_lang = "中文" if is_chinese else "英文"

        candidates_text = ""
        for i, c in enumerate(candidates):
            candidates_text += f"""
--- Agent {i + 1} ---
[Final Answer]: {c.get("answer", "")}
"""

        prompt = f"""<instruction>
你是一个首席编辑和逻辑判断专家。需要从多个agent的答案中选择最佳答案，并确保语言一致性。
</instruction>
<input_data>
<question>{source_question}</question>
<candidates>{candidates_text}</candidates>
</input_data>
<processing_rules>
## 评估标准
1. **事实准确性**: 哪个答案有最强证据支持？
2. **逻辑性**: 哪个推理更合理？
3. **完整性**: 哪个完全回答了问题？

## 语言一致性 (最重要)
- 问题语言: {target_lang}
- 答案语言必须与问题语言一致
- 如果最佳候选答案语言错误，必须翻译

## 翻译示例
- Q: "这家公司的名字是什么？" -> A: "Mondadori" (错误) -> 修正: "蒙达多利出版社"
- Q: "What is the name?" -> A: "蒙达多利出版社" (错误) -> 修正: "Mondadori"
</rules>
<output_format>
直接输出最终答案，不要有任何解释或前缀。
</output_format>"""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512,
        )

        result = response.choices[0].message.content.strip()
        logger.info(f"[MultiAgentProcessor] Processed {len(candidates)} candidates")
        return result

    except Exception as e:
        logger.error(f"[MultiAgentProcessor] Error: {e}")
        # 兜底：answer 字段为空时从 trace 中提取
        if candidates:
            extracted = [_extract_last_candidate(c.get("trace", "")) for c in candidates]
            best = max(extracted, key=len)
            if best:
                return best
        return ""


# 保留旧接口以兼容
def verify_and_clean_answer(raw_output: str, question: str) -> str:
    """旧接口，保持兼容"""
    return process_final_answer(question, raw_output, original_question=question)


def synthesize_best_answer(question: str, candidates: list[dict], original_question: str | None = None) -> str:
    """旧接口，保持兼容，内部调用统一处理函数"""
    return process_multi_agent_answers(
        question,
        candidates,
        original_question=original_question if original_question else question,
    )
