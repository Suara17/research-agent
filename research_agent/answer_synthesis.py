import logging
import re
from .utils import get_llm_client

logger = logging.getLogger(__name__)


def process_final_answer(question: str, raw_output: str) -> str:
    """
    统一处理最终答案：提取、清洗、语言一致性处理。
    合并了verify_and_clean_answer的功能，适用于单agent场景。
    """
    try:
        if not question:
            logger.warning("[AnswerProcessor] Question is empty!")
            question = ""

        client = get_llm_client(timeout=30.0)

        # 检测问题语言
        is_chinese = any("\u4e00" <= c <= "\u9fff" for c in question[:100])
        target_lang = "中文" if is_chinese else "英文"

        prompt = f"""<instruction>
你是一个严格的答案处理专家。需要完成以下任务：
1. 从模型输出中提取最终答案
2. 确保答案语言与问题语言一致
3. 清洗格式
</instruction>
<input_data>
<question>
{question}
</question>
<model_output>
{raw_output}
</model_output>
</input_data>
<processing_rules>
## 任务1: 提取答案
- 定位最后一个 "Final Answer:" 或 "最终答案:" 标记
- 提取该标记之后的所有内容
- 如果未找到标记，提取文本最后一句

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
            return raw_output

        result = response.choices[0].message.content.strip()
        logger.info(
            f"[AnswerProcessor] Original: {raw_output[:50]}... | Processed: {result}"
        )
        return result

    except Exception as e:
        logger.error(f"[AnswerProcessor] Exception: {e}")
        return raw_output


def process_multi_agent_answers(question: str, candidates: list[dict]) -> str:
    """
    合并处理多agent答案：清洗、语言一致性、合成。
    一次性调用LLM完成所有处理，减少token消耗。
    """
    if not candidates:
        return ""

    # 单agent直接处理
    if len(candidates) == 1:
        return process_final_answer(question, candidates[0].get("trace", ""))

    # 多agent合并处理
    try:
        client = get_llm_client(timeout=45.0)

        # 检测问题语言
        is_chinese = any("\u4e00" <= c <= "\u9fff" for c in question[:100])
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
<question>{question}</question>
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
        # 回退到返回最长答案
        if candidates:
            return max([c.get("answer", "") for c in candidates], key=len)
        return ""


# 保留旧接口以兼容
def verify_and_clean_answer(raw_output: str, question: str) -> str:
    """旧接口，保持兼容"""
    return process_final_answer(question, raw_output)


def synthesize_best_answer(question: str, candidates: list[dict]) -> str:
    """旧接口，保持兼容，内部调用统一处理函数"""
    return process_multi_agent_answers(question, candidates)
