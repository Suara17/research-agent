import logging
import re
from .utils import get_llm_client

logger = logging.getLogger(__name__)

def verify_and_clean_answer(raw_output: str, question: str) -> str:
    """
    Cleans and verifies the final answer using an LLM.
    1. Extracts content after "Final Answer:" or "最终答案:".
    2. Ensures language consistency with the question.
    3. Cleans formatting and explanations.
    4. Validates validity.
    """
    try:
        if not question:
            logger.warning("[AnswerCleaner] Question is empty! Answer verification may be less accurate.")
            question = ""

        client = get_llm_client(timeout=30.0)
        prompt = f"""<instruction>
你是一个严格的答案提取与清洗专家。请根据以下要求处理模型输出。
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
1. **提取 (Extraction)**: 
   - 定位 **最后一个** "Final Answer：" 或 "最终答案:" 或 "Final Answer:" 标记。
   - 提取该标记之后的所有内容作为初步答案。
   - 如果未找到标记，尝试提取文本的最后一句作为答案。
3. **语言一致性 (Language Consistency - STRICT)**:
   - **默认规则**: 答案语言 **必须** 与题目语言保持一致（中文题 -> 中文答；英文题 -> 英文答）。
   - **特殊指令优先**: 如果题目显式要求特定语言（如 "in English", "回答英文名", "give the Chinese name"），**必须** 遵循该指令，覆盖默认规则。
   - **翻译要求**:
     - 中文题目 + 英文实体答案 -> **必须翻译为中文**（除非题目要求保留英文）。
     - 英文题目 + 中文实体答案 -> **必须翻译为英文**（除非题目要求保留中文）。
     - 如果没有标准译名，请提供最通用的音译。
   - **示例**:
     - 题: "这家公司的名字是什么？" (中文) -> 答: "Fratelli Treves" (错误) -> 修正: "特雷维斯兄弟出版社" (正确)
     - 题: "What is the name of the company?" (英文) -> 答: "特雷维斯兄弟出版社" (错误) -> 修正: "Fratelli Treves" (正确)
     - 题: "这家公司的英文名是什么？" (中文+显式要求) -> 答: "Fratelli Treves" (正确)
     - 题: "Who is Newton?" (英文) -> 答: "牛顿" (错误) -> 修正: "Isaac Newton" (正确)
4. **清洗与规范化 (Cleaning)**:
   - 移除所有解释性文字（如"根据搜索结果...", "The answer is...", "Verified Final Answer:"）。
   - 移除所有Markdown格式（加粗、斜体、代码块）。
   - 移除句末标点符号。
   - 保持极其简洁：通常应为实体名、数字、年份或短语。
5. **有效性验证 (Validation)**:
   - 如果提取内容为空，返回 "ERROR: EMPTY_CONTENT"。
</processing_rules>
<output_format>
直接输出最终清洗后的答案文本，不要包含任何标签、前缀或解释。
</output_format>"""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200
        )
        
        # Debug response structure if needed
        if not response or not hasattr(response, 'choices') or not response.choices:
            logger.error(f"[AnswerCleaner] Invalid response from LLM: {response}")
            return raw_output
            
        cleaned_result = response.choices[0].message.content.strip()
        
        if cleaned_result.startswith("ERROR:"):
            logger.warning(f"[AnswerCleaner] Cleaning failed: {cleaned_result}")
            return raw_output
            
        logger.info(f"[AnswerCleaner] Original: {raw_output[:50]}... | Cleaned: {cleaned_result}")
        return cleaned_result
        
    except Exception as e:
        logger.error(f"[AnswerCleaner] Exception during cleaning: {e}")
        return raw_output

def synthesize_best_answer(question: str, candidates: list[dict]) -> str:
    """
    Synthesize the best answer from multiple agent outputs.
    candidates: list of dicts with 'trace' and 'answer'.
    """
    # If there is only 1 candidate, just return its answer without synthesis
    if len(candidates) == 1:
        return candidates[0].get('answer', '')

    try:
        client = get_llm_client(timeout=45.0)
        
        candidates_text = ""
        for i, c in enumerate(candidates):
            candidates_text += f"""
--- Agent {i+1} ---
[Reasoning Trace]:
{c.get('trace', '')[-2000:]} 
[Final Answer]:
{c.get('answer', '')}
"""
# Note: Truncating trace to last 2000 chars to fit context if needed, 
# but usually we want the full reasoning. Let's try to keep as much as possible 
# or rely on the final answer + key steps.

        prompt = f"""<instruction>
You are a Chief Editor and Logic Judge. You have assigned 3 independent research agents to answer the same question.
Your task is to evaluate their responses and synthesize the single BEST final answer.

<question>
{question}
</question>

<candidates>
{candidates_text}
</candidates>

<evaluation_criteria>
1. **Factuality**: Which answer is supported by the strongest evidence in the trace?
2. **Logic**: Which agent's reasoning is sound and avoids jumping to conclusions?
3. **Completeness**: Which answer fully addresses the user's question?
4. **Consensus**: If 2 or 3 agents agree on a fact, it is likely correct (but verify logic).
5. **Entity Semantics**: Recognize that different names for the same entity (e.g., "USSR" vs "Soviet Union") are equivalent.
</evaluation_criteria>

<task>
1. Compare the candidates.
2. Select the most accurate and well-supported answer.
3. If they disagree, choose the one with the best evidence/reasoning.
4. If candidates use different valid names for the same entity, prefer the one that best matches the user's terminology or the most standard local name.
5. Output the final refined answer.
</task>

<language_consistency>
1. **Language Matching**: The answer language **MUST** match the Question language (Chinese -> Chinese, English -> English) unless the question explicitly asks for a specific language (e.g., "give the English name").
2. **Translation**: If the best candidate answer is in the wrong language (e.g., English entity for Chinese question), you **MUST** translate it to the target language.
3. **Examples**:
   - Q: "这家公司的名字是什么？" -> A: "Fratelli Treves" (Wrong) -> Fix: "特雷维斯兄弟出版社"
   - Q: "What is the name of the company?" -> A: "特雷维斯兄弟出版社" (Wrong) -> Fix: "Fratelli Treves"
   - Q: "Who is Newton?" -> A: "牛顿" (Wrong) -> Fix: "Isaac Newton"
</language_consistency>

<output_format>
Output ONLY the final refined answer text. Do not include "Agent 1 was better because..." or any meta-commentary.
</output_format>
</instruction>"""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=512
        )
        
        final_answer = response.choices[0].message.content.strip()
        logger.info(f"[Synthesizer] Synthesized answer from {len(candidates)} candidates.")
        return final_answer

    except Exception as e:
        logger.error(f"[Synthesizer] Error synthesizing answers: {e}")
        # Fallback: return the longest answer from candidates
        if candidates:
            return max([c.get('answer', '') for c in candidates], key=len)
        return ""
