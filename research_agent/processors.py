import json
import re
import logging
from .utils import get_llm_client
from .sensitive_filter import sanitize_text_for_llm, is_content_inspection_error

logger = logging.getLogger(__name__)


def _optimize_search_query(query: str) -> str:
    """
    应用高阶搜索策略优化查询
    """
    try:
        optimized = query.strip()

        # 策略1: 检测并标记专有名词
        proper_nouns = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', optimized)
        for noun in proper_nouns:
            if f'"{noun}"' not in optimized and f"'{noun}'" not in optimized:
                optimized = optimized.replace(noun, f'"{noun}"')

        # 策略2: 检测学术/百科类问题
        wiki_keywords = [
            'nobel prize', 'founding', 'established', 'founded',
            'biography', 'history of', 'discovered', 'invented',
            'born', 'died', 'award', 'winner'
        ]
        is_wiki_query = any(kw in optimized.lower() for kw in wiki_keywords)
        # (Pass implementation as in original)

        # 策略4: 去除冗余词汇
        redundant_prefixes = [
            'please search for', 'find information about',
            'look up', 'search', 'find', 'what is', 'who is'
        ]
        for prefix in redundant_prefixes:
            if optimized.lower().startswith(prefix):
                optimized = optimized[len(prefix):].strip()

        print(f"[Monitoring] query_optimization: '{query}' → '{optimized}'")
        return optimized

    except Exception as e:
        print(f"[Monitoring] query_optimization_error: {e}")
        return query

def _simplify_search_query(query: str) -> str:
    """
    当搜索失败时，尝试简化查询
    """
    try:
        # Remove site: and filetype:
        simplified = re.sub(r'site:\S+', '', query, flags=re.IGNORECASE)
        simplified = re.sub(r'filetype:\S+', '', simplified, flags=re.IGNORECASE)
        
        # Remove quotes if they might be overly restrictive
        if len(simplified) > 30:
            simplified = simplified.replace('"', '').replace("'", "")
            
        # Collapse spaces
        simplified = re.sub(r'\s+', ' ', simplified).strip()
        return simplified
    except Exception:
        return query

def _translate_query(query: str, target_lang: str = "English") -> str:
    try:
        client = get_llm_client()

        # 【关键】在发送给LLM前过滤敏感词
        sanitized_query, replacements = sanitize_text_for_llm(query, log_replacement=False)

        if replacements:
            logger.debug(f"[SensitiveFilter] 翻译查询时过滤了 {len(replacements)} 个敏感词")

        resp = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": f"<instruction><task>Translate search query for search engine optimization</task><target_lang>{target_lang}</target_lang><constraint>Keep proper nouns and key terms accurate</constraint><query>{sanitized_query}</query></instruction>"}],
            max_tokens=128
        )
        return resp.choices[0].message.content.strip().strip('"')
    except Exception as e:
        if is_content_inspection_error(e):
            logger.warning(f"[SensitiveFilter] 查询翻译触发内容审核: {query[:50]}...")
        return query

def expand_query_language(query: str) -> list:
    queries = []
    
    # 策略 1: 如果是中文，尝试翻译成英文 (国际化覆盖)
    if any("\u4e00" <= ch <= "\u9fff" for ch in query):
        en_q = _translate_query(query, "English")
        if en_q and en_q.lower() != query.lower():
            queries.append(en_q)
            
    # 策略 2: 如果是英文，尝试翻译成中文 (针对中国特有实体或事件)
    # 通过启发式判断：如果查询看起来是寻找中国相关内容，或者为了更广泛的覆盖，可以尝试中文
    # 这里我们放宽限制：只要是纯英文查询，就尝试生成一个中文版本
    elif all(ord(ch) < 128 for ch in query.strip()):
        cn_q = _translate_query(query, "Chinese")
        if cn_q and cn_q != query:
            queries.append(cn_q)
            
    return queries

def _fallback_slot_extraction(query: str) -> dict:
    """LLM 失败时的降级槽位提取（纯正则，零延迟）"""
    import re

    is_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in query)
    years = re.findall(r"\b(19|20)\d{2}s?\b", query)
    quoted = re.findall(r'"([^"]+)"', query)
    books = re.findall(r"《([^》]+)》", query)
    anchors = quoted + books

    return {
        "type": "Unknown",
        "hard_constraints": years if years else [],
        "soft_constraints": [],
        "anchors": anchors,
        "target_country": None,
    }


def _extract_search_slots(query: str) -> dict:
    try:
        client = get_llm_client()

        # 【关键】在发送给LLM前过滤敏感词
        sanitized_query, replacements = sanitize_text_for_llm(query, log_replacement=False)

        if replacements:
            logger.debug(f"[SensitiveFilter] 搜索槽位提取时过滤了 {len(replacements)} 个敏感词")

        prompt = [
            {"role": "system", "content": """<instruction>
<task>Extract search slots from the query.</task>
<output_format>json_object</output_format>
<keys>
  <key name="type">"Person" | "Organization" | "Event" | "Object" | "Other"</key>
  <key name="hard_constraints">list of strict conditions (year, location, role, specific event)</key>
  <key name="soft_constraints">list of descriptive conditions (scandals, education, family)</key>
  <key name="anchors">list of unique keywords for search (names, specific terms)</key>
  <key name="target_country">country name (English) if applicable, else null</key>
</keys>
</instruction>"""},
            {"role": "user", "content": f"<input><query>{sanitized_query}</query></input>"}
        ]
        resp = client.chat.completions.create(
            model="qwen3-max",
            messages=prompt,
            max_tokens=256,
            response_format={"type": "json_object"}
        )
        result = resp.choices[0].message.content
        if result:
            return json.loads(result)
        return {}
    except Exception as e:
        print(f"[Monitoring] Slot extraction failed: {e}")
        return _fallback_slot_extraction(query)
