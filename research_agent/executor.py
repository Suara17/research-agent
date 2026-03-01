import json
import time
import re
import urllib.parse
from difflib import SequenceMatcher
from typing import List, Callable, Optional, cast, Dict

# 可信度评分常量
_HIGH_CREDIBILITY_DOMAINS = [
    "wikipedia.org", "britannica.com", "reuters.com",
    "xinhua.net", "gov.cn", ".gov", ".edu",
    "wikidata.org", "scholar.google.com",
]
_LOW_CREDIBILITY_DOMAINS = [
    "reddit.com/r/", "quora.com", "answers.yahoo.com",
    "zhidao.baidu.com", "tieba.baidu.com",
]
_CREDIBILITY_THRESHOLD = 0.15  # 低于此分值的结果直接丢弃

from openai.types.chat import ChatCompletionChunk

from .utils import get_llm_client
from .schema import ToolCall, Chunk
from .search import extract_answer_from_search_results

# Pre-load jieba to avoid loading delay on each call
try:
    import jieba
    import jieba.posseg as pseg

    jieba.initialize()
    _JIEBA_AVAILABLE = True
except ImportError:
    _JIEBA_AVAILABLE = False


# 用于跟踪搜索循环的计数器
_SEARCH_LOOP_COUNTER: Dict[str, int] = {}
_MAX_LOOP_COUNT = 2  # 同一查询重复2次后触发换词（更早介入）


def _compute_credibility(result: dict) -> float:
    """
    计算单条搜索结果的可信度分值 [0.0, 1.0]。
    基于域名启发式，零 LLM 调用。
    """
    url = (result.get("url") or "").lower()
    score = 0.5  # baseline

    for domain in _HIGH_CREDIBILITY_DOMAINS:
        if domain in url:
            score = min(1.0, score + 0.4)
            break

    for domain in _LOW_CREDIBILITY_DOMAINS:
        if domain in url:
            score = max(0.0, score - 0.3)
            break

    return round(score, 2)


def _filter_and_tag_results(results: list) -> list:
    """
    过滤极低可信度结果，并为每条结果附加 credibility 字段。
    返回过滤后的结果列表（已按可信度降序排列）。
    """
    tagged = []
    for r in results:
        cred = _compute_credibility(r)
        if cred < _CREDIBILITY_THRESHOLD:
            print(f"[Credibility] Filtered low-credibility result: {r.get('url', '')[:60]} (score={cred})")
            continue
        r = dict(r)  # 浅拷贝，不改原数据
        r["credibility"] = cred
        tagged.append(r)

    tagged.sort(key=lambda x: x.get("credibility", 0.5), reverse=True)
    return tagged


def _extract_key_facts(content: str, max_length: int = 800) -> str:
    """
    Fast extraction of key facts from web content without LLM.
    Uses jieba for better Chinese entity extraction + regex for numbers/dates.
    """
    if not content:
        return ""

    facts = []

    # Extract dates first (regex is reliable)
    date_patterns = [
        r"(?:19|20)\d{2}年\d{1,2}月\d{1,2}日?",
        r"(?:19|20)\d{2}年\d{1,2}月?",
        r"(?:19|20)\d{2}年",
        r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(?:19|20)\d{2}",
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for m in matches[:3]:
            if m and m not in facts:
                facts.append(m)

    # Extract numbers with Chinese units (like 504个, 500人)
    # Simple pattern that captures most cases
    number_patterns = [
        r"\d+\s*个",
        r"\d+\s*名",
        r"\d+\s*次",
        r"\d+\s*件",
        r"\d+\s*位",
        r"\d+亿",
        r"\d+万",
    ]
    for pattern in number_patterns:
        matches = re.findall(pattern, content)
        for m in matches[:3]:
            if m and m not in facts:
                facts.append(m)

    # Use pre-loaded jieba for better entity extraction
    if _JIEBA_AVAILABLE:
        # Cut with part-of-speech tagging
        words = pseg.cut(content[:5000])

        # Collect entities by POS
        entities = {
            "nr": [],  # Person name
            "ns": [],  # Place name
            "nt": [],  # Organization
            "nz": [],  # Other proper noun
        }

        for word, flag in words:
            if len(word) >= 2:
                if flag in entities and word not in facts:
                    entities[flag].append(word)

        # Add entities (person > place > org)
        for etype in ["nr", "ns", "nt"]:
            for e in entities[etype][:3]:
                if e not in facts:
                    facts.append(e)
    else:
        # Fallback to regex for Chinese entities
        cn_entity_pattern = r"[\u4e00-\u9fff]{2,4}"
        cn_entities = re.findall(cn_entity_pattern, content)
        stop_words = {
            "的",
            "是",
            "在",
            "有",
            "和",
            "了",
            "与",
            "或",
            "等",
            "为",
            "以",
            "及",
            "于",
            "从",
            "被",
            "这",
            "那",
            "中",
            "大",
            "小",
            "上",
            "下",
            "也",
            "就",
            "都",
            "而",
            "其",
            "所",
            "并",
            "但",
        }
        filtered = [e for e in cn_entities if e not in stop_words and len(set(e)) > 1]
        for entity in filtered[:5]:
            if entity not in facts:
                facts.append(entity)

    # Extract quoted text
    quoted = re.findall(r'"([^"]{10,80})"', content)
    for q in quoted[:2]:
        if q and q not in facts:
            facts.append(q[:50])

    result = " | ".join(facts[:8])

    if len(result) > max_length:
        result = result[:max_length] + "..."

    return result


def _detect_and_rewrite_query(query: str, search_history: List[str]) -> str:
    """
    检测搜索循环并尝试重写查询

    Args:
        query: 原始查询
        search_history: 历史搜索记录

    Returns:
        改进后的查询（如果检测到循环），否则返回原查询
    """
    # 归一化查询（去除空格，转小写）
    normalized_q = query.lower().strip()

    # 检查是否在短时间内重复相同查询
    recent_same = [q for q in search_history[-5:] if q.lower().strip() == normalized_q]

    if len(recent_same) >= _MAX_LOOP_COUNT:
        print(
            f"[LoopDetection] Detected repeated query: '{query}' ({len(recent_same)} times)"
        )

        # 尝试生成替代查询
        try:
            client = get_llm_client()
            # 使用LLM生成替代搜索词
            rewrite_prompt = f"""<instruction>
<task>生成一个不同的搜索查询来解决当前问题。</task>
<original_query>{query}</original_query>
<search_history>
{chr(10).join(search_history[-10:])}
</search_history>
<constraint>
1. 生成一个语义相似但措辞不同的查询
2. 尝试使用不同的关键词、同义词或更具体的描述
3. 如果原查询是英文，尝试不同的英文表达
4. 如果原查询是中文，可以尝试混合英文或使用不同的中文表达
</constraint>
</instruction>"""

            resp = client.chat.completions.create(
                model="qwen3-max",
                messages=[{"role": "user", "content": rewrite_prompt}],
                max_tokens=128,
                temperature=0.7,
            )

            new_query = resp.choices[0].message.content.strip().strip('"').strip("'")

            if new_query and new_query != query:
                print(f"[LoopDetection] Rewriting query: '{query}' -> '{new_query}'")
                return new_query
        except Exception as e:
            print(f"[LoopDetection] Query rewrite failed: {e}")

    return query


def _normalize_for_loop_detection(query: str) -> str:
    """归一化查询用于循环检测（忽略大小写和多余空格）"""
    return " ".join(query.lower().split())


def execute_tools_logic(state: dict, tool_functions_map: dict, memory) -> dict:
    client = get_llm_client(timeout=30.0)
    emitted: List[Chunk] = state.get("emitted", [])
    new_messages = state["messages"][:]
    meta = state.get("meta") or {
        "searched_keywords": [],
        "seen_entities": [],
        "last_skill_output": None,
        "dynamic_retrieval_count": 0,
    }
    searched_before = set(meta.get("searched_keywords") or [])

    # Handle force_continue case: when early Final Answer was blocked
    # but no tool calls were made, we still need to increment step and reset flag
    force_continue = state.get("force_continue", False)

    new_memory_items = []
    for tool_data in state.get("pending_tool_calls") or []:
        call_id = tool_data["id"]
        func_name = tool_data["function"]["name"]
        func_args_str = tool_data["function"]["arguments"]
        tool_result_content = ""
        parsed_args = {}
        tool_call = ToolCall(
            tool_call_id=call_id, tool_name=func_name, tool_arguments={}
        )
        try:
            parsed_args = json.loads(func_args_str)
            tool_call.tool_arguments = parsed_args
            emitted.append(
                Chunk(
                    step_index=state["step_index"],
                    type="tool_call",
                    tool_call=tool_call,
                )
            )

            if func_name == "web_search":
                q0 = str(parsed_args.get("query") or "")

                # === 搜索循环检测与重写 ===
                # 获取搜索历史
                search_history = meta.get("searched_keywords", [])

                # 检测并可能重写查询
                rewritten_query = _detect_and_rewrite_query(q0, search_history)

                if rewritten_query != q0:
                    # 查询被重写，更新参数
                    parsed_args["query"] = rewritten_query
                    q0 = rewritten_query
                    # 更新tool_call的arguments
                    func_args_str = json.dumps(parsed_args)
                    tool_call.tool_arguments = parsed_args
                    print(f"[Executor] Using rewritten query: '{rewritten_query}'")

                # 原有相似度检测（保留作为额外检查）
                sim_high = False
                for old_q in searched_before:
                    if SequenceMatcher(None, q0, old_q).ratio() > 0.95:
                        sim_high = True
                        break
                if sim_high:
                    # Warn but allow if it's not exact duplicate
                    print(f"[Executor] Warning: Similar search '{q0}' detected.")

            if func_name in tool_functions_map and not tool_result_content:
                func = tool_functions_map[func_name]
                attempt = 0
                last_err = None
                while attempt < 2:
                    try:
                        result = func(**parsed_args)
                        tool_result_content = str(result)
                        last_err = None
                        break
                    except Exception as e:
                        last_err = e
                        time.sleep(0.2 * (attempt + 1))
                        attempt += 1
                if last_err is not None and not tool_result_content:
                    tool_result_content = f"Error: Execution failed - {str(last_err)}"

            else:
                if func_name not in tool_functions_map:
                    tool_result_content = f"Error: Tool '{func_name}' not found."

        except json.JSONDecodeError as e:
            tool_result_content = f"Error: Failed to parse tool arguments JSON: {func_args_str}. Error: {e}"
            emitted.append(
                Chunk(
                    step_index=state["step_index"],
                    type="tool_call",
                    tool_call=tool_call,
                )
            )
        except Exception as e:
            tool_result_content = f"Error: Execution failed - {str(e)}"

        msg_display_content = tool_result_content

        # Fast extraction instead of LLM summarization for long content
        if (
            func_name in ["web_fetch", "browse_page"]
            and len(tool_result_content) > 1000
        ):
            try:
                # Extract key facts (for quick recall)
                facts = _extract_key_facts(tool_result_content)

                # Store BOTH: extracted facts + truncated original content
                if facts and len(facts) > 20:
                    # Truncate original content for backup (first 2000 chars)
                    truncated = tool_result_content[:2000]
                    memory.add_long(
                        f"[Facts] {facts}\n\n[Original Truncated]\n{truncated}"
                    )
                    msg_display_content = f"[Key Facts]: {facts}\n\n[Content Preview]: {truncated[:500]}..."
                else:
                    memory.add_long(tool_result_content)
            except Exception as e:
                memory.add_long(tool_result_content)
        elif func_name == "web_search":
            # 可信度过滤 + 标注
            try:
                raw = json.loads(tool_result_content) if tool_result_content.strip().startswith(("{", "[")) else None
                if isinstance(raw, dict) and "results" in raw:
                    # 兼容 {"results": [...]} 格式（备用）
                    original_count = len(raw["results"])
                    filtered = _filter_and_tag_results(raw["results"])
                    raw["results"] = filtered
                    credibility_tagged = json.dumps(raw, ensure_ascii=False)
                    memory.add_long(credibility_tagged)
                    msg_display_content = credibility_tagged
                    print(f"[Credibility] {len(filtered)}/{original_count} results kept after filtering")
                elif isinstance(raw, list):
                    # 实际路径：serper / bocha / searxng 均返回裸 List[Dict]
                    original_count = len(raw)
                    filtered = _filter_and_tag_results(raw)
                    credibility_tagged = json.dumps(filtered, ensure_ascii=False)
                    memory.add_long(credibility_tagged)
                    msg_display_content = credibility_tagged
                    print(f"[Credibility] {len(filtered)}/{original_count} results kept after filtering")
                else:
                    memory.add_long(tool_result_content)
            except Exception as e:
                print(f"[Credibility] Filter error: {e}")
                memory.add_long(tool_result_content)
        else:
            memory.add_long(tool_result_content)

        emitted.append(
            Chunk(
                type="tool_call_result",
                tool_result=msg_display_content,
                step_index=state["step_index"],
                tool_call=tool_call,
            )
        )
        new_messages.append(
            {"role": "tool", "tool_call_id": call_id, "content": msg_display_content}
        )
        memory.add_short(msg_display_content)

        if func_name == "web_search":
            q = str(parsed_args.get("query") or "")
            if q and q not in meta["searched_keywords"]:
                meta["searched_keywords"].append(q)

    return {
        **state,
        "messages": new_messages,
        "emitted": emitted,
        "pending_tool_calls": [],
        "step_index": state["step_index"] + 1,
        "meta": meta,
        "force_continue": False,  # Reset flag after processing
    }
