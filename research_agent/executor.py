import json
import time
import re
import urllib.parse
from difflib import SequenceMatcher
from typing import List, Callable, Optional, cast

from openai.types.chat import ChatCompletionChunk

from .utils import get_llm_client
from .schema import ToolCall, Chunk
from .search import extract_answer_from_search_results

def execute_tools_logic(state: dict, tool_functions_map: dict, memory) -> dict:
    client = get_llm_client(timeout=30.0)
    emitted: List[Chunk] = state.get("emitted", [])
    new_messages = state["messages"][:]
    meta = state.get("meta") or {"searched_keywords": [], "seen_entities": [], "last_skill_output": None, "dynamic_retrieval_count": 0}
    searched_before = set(meta.get("searched_keywords") or [])

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
                sim_high = False
                for old_q in searched_before:
                    if SequenceMatcher(None, q0, old_q).ratio() > 0.95: # Increased threshold to be less aggressive
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
    }
