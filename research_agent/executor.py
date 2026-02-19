import json
import time
import re
import urllib.parse
from difflib import SequenceMatcher
from typing import List, Callable, Optional, cast, Dict

from openai.types.chat import ChatCompletionChunk

from .utils import get_llm_client
from .schema import ToolCall, Chunk
from .search import extract_answer_from_search_results


# 用于跟踪搜索循环的计数器
_SEARCH_LOOP_COUNTER: Dict[str, int] = {}
_MAX_LOOP_COUNT = 3  # 同一查询重复3次后触发换词


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
        print(f"[LoopDetection] Detected repeated query: '{query}' ({len(recent_same)} times)")
        
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
                temperature=0.7
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
    meta = state.get("meta") or {"searched_keywords": [], "seen_entities": [], "last_skill_output": None, "dynamic_retrieval_count": 0}
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
        tool_call = ToolCall(tool_call_id=call_id, tool_name=func_name, tool_arguments={})
        try:
            parsed_args = json.loads(func_args_str)
            tool_call.tool_arguments = parsed_args
            emitted.append(Chunk(step_index=state["step_index"], type="tool_call", tool_call=tool_call))
            
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
            emitted.append(Chunk(step_index=state["step_index"], type="tool_call", tool_call=tool_call))
        except Exception as e:
            tool_result_content = f"Error: Execution failed - {str(e)}"
        
        msg_display_content = tool_result_content

        # Simple summarization for long content
        if func_name in ["web_fetch", "browse_page"] and len(tool_result_content) > 1000:
            distill_instruction = "<instruction><task>Summarize key facts from the text.</task><details>Extract entities, dates, numbers; remove ads and navigation.</details></instruction>"
            try:
                distill_resp = client.chat.completions.create(
                    model="qwen3-max",
                    messages=[
                        {"role": "system", "content": distill_instruction},
                        {"role": "user", "content": f"<input><text>{tool_result_content[:4000]}</text></input>"}
                    ],
                    max_tokens=512
                )
                summary = distill_resp.choices[0].message.content
                memory.add_long(f"Fact Summary from {parsed_args.get('url')}: {summary}")
                msg_display_content = f"[Fact Summary from {parsed_args.get('url')}]:\n{summary}"
            except Exception as e:
                memory.add_long(tool_result_content)
        else:
            memory.add_long(tool_result_content)

        emitted.append(Chunk(type="tool_call_result", tool_result=msg_display_content, step_index=state["step_index"], tool_call=tool_call))
        new_messages.append({"role": "tool", "tool_call_id": call_id, "content": msg_display_content})
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
