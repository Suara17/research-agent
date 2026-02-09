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
2. **语言一致性 (Language Consistency)**:
   - 分析 <question> 的主要语言（中文/英文等）。
   - **强制执行**: 答案语言必须与 <question> 保持一致。
   - **翻译规则**:
     - 如果问题是中文，但提取的答案是英文（包括人名、地名、公司名等实体），**必须**将其翻译成中文。
     - 如果没有标准译名，请提供音译。
     - 只有在问题明确要求英文（如 "in English"）时才保留英文。
     - 示例: "Fratelli Treves" -> "特雷维斯兄弟出版社"; "Newton" -> "牛顿"。
3. **清洗与规范化 (Cleaning)**:
   - 移除所有解释性文字（如"根据搜索结果...", "The answer is...", "Verified Final Answer:"）。
   - 移除所有Markdown格式（加粗、斜体、代码块）。
   - 移除句末标点符号。
   - 保持极其简洁：通常应为实体名、数字、年份或短语。
4. **有效性验证 (Validation)**:
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
