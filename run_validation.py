import re
import asyncio
import json
import os
import sys
import time
import logging
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

# Add current directory to sys.path to ensure local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from research_agent.core import agent_loop
from research_agent.search import (
    web_search,
    web_fetch,
    get_weather,
    browse_page,
    x_keyword_search,
    search_pdf_attachment,
    browse_pdf_attachment,
)
from research_agent.answer_synthesis import (
    verify_and_clean_answer,
    synthesize_best_answer,
)
from agent import QueryRequest

# Setup logging specific to validation
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("validation_run.log", encoding="utf-8"),
        logging.FileHandler("validation_run.md", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


# Redirect stdout to also write to file handlers
class TeeStdout:
    def __init__(self, original_stdout, handlers):
        self.original_stdout = original_stdout
        self.handlers = handlers

    def write(self, message):
        self.original_stdout.write(message)
        for h in self.handlers:
            try:
                if hasattr(h, "stream") and h.stream:
                    h.stream.write(message)
                    h.stream.flush()
            except Exception:
                pass

    def flush(self):
        self.original_stdout.flush()
        for h in self.handlers:
            try:
                h.flush()
            except Exception:
                pass


_root_logger = logging.getLogger()
_file_handlers = [
    h for h in _root_logger.handlers if isinstance(h, logging.FileHandler)
]
if _file_handlers:
    sys.stdout = TeeStdout(sys.stdout, _file_handlers)

MAX_RETRIES = 1
TIMEOUT_SECONDS = 3600.0
RATE_DELAY_SECONDS = 0.2


def _load_env_from_dotenv():
    try:
        here = Path(__file__).resolve().parent
        candidates = [here / ".env", Path.cwd() / ".env"]
        seen = set()
        for p in candidates:
            if not p.exists():
                continue
            if str(p) in seen:
                continue
            seen.add(str(p))
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and v:
                        if k == "IFLOW_API_KEY" or k not in os.environ:
                            os.environ[k] = v
    except Exception:
        pass


_load_env_from_dotenv()


def normalize_for_compare(s):
    """标准化字符串用于精确匹配"""
    return str(s).lower().strip().replace("。", "").replace(".", "").replace(" ", "")


def clean_and_judge_answer(
    question: str, ground_truth: str, raw_output: str
) -> tuple[str, bool, str]:
    """
    合并答案清洗和评判到一个LLM调用中。
    返回: (cleaned_answer, is_correct, reason)
    """
    if not raw_output:
        return "", False, "Empty prediction"

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url="https://apis.iflow.cn/v1",
            api_key=os.getenv("IFLOW_API_KEY"),
            timeout=30.0,
        )

        # 检测问题语言
        is_chinese = any("\u4e00" <= c <= "\u9fff" for c in question[:100])

        prompt = f"""<instruction>
你是一个严格的答案处理专家。需要同时完成两项任务：答案清洗和正确性评判。
</instruction>
<task>
处理以下模型输出
</task>
<input_data>
<question>{question}</question>
<ground_truth>{ground_truth}</ground_truth>
<model_output>{raw_output}</model_output>
</input_data>
<processing_rules>
## 任务1: 答案清洗
1. **提取**: 定位最后一个 "Final Answer:" 或 "最终答案:" 标记，提取之后的内容
2. **语言一致性**: 
   - 如果问题是中文，答案必须翻译为中文
   - 如果问题是英文，答案必须翻译为英文
   - 实体名使用标准译名（如 "Mondadori" -> "蒙达多利出版社"）
3. **清洗**: 移除解释性文字、Markdown格式、句末标点

## 任务2: 正确性评判
1. **精确匹配**: 清洗后的答案与标准答案（标准化后）是否相同？
2. **包含匹配**: 如果标准答案较短（>4字符），是否被包含在清洗后的答案中？
3. **语义匹配**: 如果以上都不满足，使用常识判断答案是否正确表达了标准答案的含义

## 输出格式
请按以下JSON格式输出，不要包含任何其他内容：
{{
    "cleaned_answer": "清洗并翻译后的答案",
    "is_correct": true或false,
    "reason": "判断理由"
}}
</instruction>"""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )

        result_text = response.choices[0].message.content.strip()

        # 解析JSON结果
        try:
            import json

            # 尝试提取JSON
            if "{" in result_text and "}" in result_text:
                json_start = result_text.find("{")
                json_end = result_text.rfind("}") + 1
                json_str = result_text[json_start:json_end]
                result = json.loads(json_str)
                cleaned = result.get("cleaned_answer", "")
                is_correct = result.get("is_correct", False)
                reason = result.get("reason", "")
            else:
                # JSON解析失败，回退到简单逻辑
                cleaned = raw_output
                is_correct = False
                reason = "JSON解析失败"
        except Exception as e:
            # 回退到简单匹配逻辑
            cleaned = raw_output
            norm_gt = normalize_for_compare(ground_truth)
            norm_pred = normalize_for_compare(cleaned)

            if norm_gt == norm_pred:
                is_correct = True
                reason = "Exact match (normalized)"
            elif len(norm_gt) > 4 and norm_gt in norm_pred:
                is_correct = True
                reason = "Containment match"
            else:
                is_correct = False
                reason = f"Parse error: {str(e)[:50]}"

        return cleaned, is_correct, reason

    except Exception as e:
        logging.error(f"Clean+Judge error: {e}")
        return raw_output, False, f"Error: {str(e)[:50]}"


async def _run_agent_async_logic(
    agent_id,
    base_messages,
    tools,
    max_steps,
    inherited_memory,
    inherited_context,
    question,
):
    """
    Async logic to run a single agent.
    This is meant to be run inside a dedicated event loop in a separate thread.
    """
    # Create a fresh copy of messages for each agent
    messages = json.loads(json.dumps(base_messages))  # Deep copy to be safe

    raw_result = ""
    skill_usage_log = []
    search_summary_parts = []
    final_memory = None

    try:
        # Import inside function to avoid potential circular import issues if moved
        from research_agent.core import agent_loop

        async for chunk in agent_loop(
            messages,
            tools,
            max_steps=max_steps,
            inherited_memory=inherited_memory,
            inherited_context=inherited_context,
        ):
            if chunk.type == "final_state":
                final_memory = chunk.tool_result

            if chunk.type == "tool_call":
                tool_name = chunk.tool_call.tool_name if chunk.tool_call else "unknown"
                tool_args = chunk.tool_call.tool_arguments if chunk.tool_call else {}
                if tool_name == "web_search":
                    query = tool_args.get("query", "")
                    search_summary_parts.append(f"[Agent {agent_id}] Searched: {query}")
                if tool_name == "load_skill_file":
                    skill_name = tool_args.get("skill_name", "unknown")
                    skill_usage_log.append(f"load:{skill_name}")
                elif tool_name == "execute_script":
                    skill_name = tool_args.get("skill_name", "unknown")
                    skill_usage_log.append(f"execute:{skill_name}")

            elif chunk.type == "tool_call_result":
                tool_name = chunk.tool_call.tool_name if chunk.tool_call else "unknown"
                if tool_name == "web_search" and chunk.tool_result:
                    try:
                        if (
                            isinstance(chunk.tool_result, str)
                            and "Found:" in chunk.tool_result
                        ):
                            search_summary_parts.append(chunk.tool_result[:100])
                    except:
                        pass

            elif chunk.type == "text" and chunk.content:
                raw_result += chunk.content

        if skill_usage_log:
            logging.info(
                f"[Agent {agent_id}] Skills used: {', '.join(skill_usage_log)}"
            )

        # Clean individual result
        cleaned_ans = ""
        if raw_result:
            cleaned_ans = verify_and_clean_answer(raw_result, question)

        return {
            "id": agent_id,
            "trace": raw_result,
            "answer": cleaned_ans,
            "memory": final_memory,
            "search_summary": "\n".join(search_summary_parts),
        }
    except Exception as e:
        logging.error(f"[Agent {agent_id}] Failed: {e}")
        return {
            "id": agent_id,
            "trace": f"Error: {str(e)}",
            "answer": "",
            "memory": None,
            "search_summary": "",
        }


def _run_agent_in_thread(
    agent_id,
    base_messages,
    tools,
    max_steps,
    inherited_memory,
    inherited_context,
    question,
):
    """
    Entry point for thread. Creates a new event loop and runs the async logic.
    """
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        return new_loop.run_until_complete(
            _run_agent_async_logic(
                agent_id,
                base_messages,
                tools,
                max_steps,
                inherited_memory,
                inherited_context,
                question,
            )
        )
    finally:
        new_loop.close()


async def run_one(
    question: str,
    rejection_history: List[str] = None,
    is_retry: bool = False,
    inherited_memory=None,
    inherited_context: str = None,
) -> tuple:
    # Use QueryRequest from agent.py to ensure consistency with the API service
    req = QueryRequest(question=question)
    base_messages = req.to_messages()

    # Dynamic max_steps
    if is_retry:
        max_steps = 15
        logging.info(f"[Retry] Using reduced max_steps={max_steps}")
    else:
        max_steps = 30  # Fixed max steps for new agent
        logging.info(f"[Monitoring] Using fixed max_steps: {max_steps}")

    if rejection_history:
        hint_text = "\n\n".join(rejection_history)
        base_messages.append(
            {
                "role": "system",
                "content": f"""SYSTEM REMINDER: Previous verification FAILED.

PREVIOUS REJECTIONS:
{hint_text}

INSTRUCTION: Analyze the rejection reasons. Change your search strategy to avoid repeating mistakes.""",
            }
        )

    tools = [
        web_search,
        web_fetch,
        get_weather,
        browse_page,
        x_keyword_search,
        search_pdf_attachment,
        browse_pdf_attachment,
    ]

    # Configure number of agents to run in parallel
    # Default to 1, but allow override (e.g. for single agent mode)
    # Since run_one signature is fixed, we can use a global or env var, or just hardcode logic here.
    # For now, let's check an env var or just keep it hardcoded to 1 unless modified.
    # But to answer the user's request "can run single agent", we should allow it.
    # Let's check os.environ for 'NUM_AGENTS'
    num_agents = int(os.environ.get("NUM_AGENTS", "1"))
    if num_agents < 1:
        num_agents = 1

    logging.info(
        f"[Single-Agent] Starting {num_agents} agent via API for validation QID..."
    )

    # We will simulate the parallel call by calling the agent.py logic directly but we must ensure parallelism.
    # Since agent.py now implements threading for parallelism internally in its / endpoint,
    # we can simply call the agent's logic or replicate the threading here.
    # To keep run_validation.py simple as requested: "不需要实现异步运行逻辑",
    # we will revert to simple asyncio.gather calling the async agent_loop,
    # BUT assuming agent_loop is async-friendly.
    # If agent_loop blocks, we need the threading.
    # The user instruction was: "e:\Research_Agent\run_validation.py 不需要实现异步运行逻辑"
    # and "我希望修改agent核心逻辑，达到并行3个agent同时处理同一个问题的效果".
    # This implies the complexity should be in agent.py (which we just did),
    # and run_validation.py should call agent.py's parallel capability OR be simple.

    # If we want run_validation.py to be simple and NOT implement complex threading:
    # We can just call the agent_loop 3 times with asyncio.gather.
    # If agent_loop is blocking, they will run sequentially.
    # However, since we moved the threading logic to agent.py, maybe we should import `query` from agent.py?
    # Or just keep it simple here as requested.

    # Let's revert to the simple asyncio.gather implementation.
    # If agent_loop has blocking calls (like sync HTTP), they will block the loop.
    # But the user explicitly said "run_validation.py 不需要实现异步运行逻辑" (no complex async logic).
    # So we will provide the clean, standard asyncio.gather version.

    async def run_single_agent(agent_id: int, tools: list):
        # Create a fresh copy of messages for each agent
        messages = json.loads(json.dumps(base_messages))  # Deep copy to be safe

        raw_result = ""
        skill_usage_log = []
        search_summary_parts = []
        final_memory = None

        try:
            async for chunk in agent_loop(
                messages,
                tools,
                max_steps=max_steps,
                inherited_memory=inherited_memory,
                inherited_context=inherited_context,
            ):
                if chunk.type == "final_state":
                    final_memory = chunk.tool_result

                if chunk.type == "tool_call":
                    tool_name = (
                        chunk.tool_call.tool_name if chunk.tool_call else "unknown"
                    )
                    tool_args = (
                        chunk.tool_call.tool_arguments if chunk.tool_call else {}
                    )
                    if tool_name == "web_search":
                        query = tool_args.get("query", "")
                        search_summary_parts.append(
                            f"[Agent {agent_id}] Searched: {query}"
                        )
                    if tool_name == "load_skill_file":
                        skill_name = tool_args.get("skill_name", "unknown")
                        skill_usage_log.append(f"load:{skill_name}")
                    elif tool_name == "execute_script":
                        skill_name = tool_args.get("skill_name", "unknown")
                        skill_usage_log.append(f"execute:{skill_name}")

                elif chunk.type == "tool_call_result":
                    tool_name = (
                        chunk.tool_call.tool_name if chunk.tool_call else "unknown"
                    )
                    if tool_name == "web_search" and chunk.tool_result:
                        try:
                            if (
                                isinstance(chunk.tool_result, str)
                                and "Found:" in chunk.tool_result
                            ):
                                search_summary_parts.append(chunk.tool_result[:100])
                        except:
                            pass

                elif chunk.type == "text" and chunk.content:
                    raw_result += chunk.content

            if skill_usage_log:
                logging.info(
                    f"[Agent {agent_id}] Skills used: {', '.join(skill_usage_log)}"
                )

            # Clean individual result
            cleaned_ans = ""
            if raw_result:
                cleaned_ans = verify_and_clean_answer(raw_result, question)

            return {
                "id": agent_id,
                "trace": raw_result,
                "answer": cleaned_ans,
                "memory": final_memory,
                "search_summary": "\n".join(search_summary_parts),
            }
        except Exception as e:
            logging.error(f"[Agent {agent_id}] Failed: {e}")
            return {
                "id": agent_id,
                "trace": raw_result + f"\n\n[System Error]: {str(e)}",
                "answer": "",
                "memory": None,
                "search_summary": "",
            }

    tasks = [run_single_agent(i + 1, tools) for i in range(num_agents)]
    agent_results = await asyncio.gather(*tasks)

    logging.info(
        f"[Multi-Agent] All {len(agent_results)} agents finished. Synthesizing best answer..."
    )

    # Synthesize
    final_answer = synthesize_best_answer(
        question,
        agent_results,
        original_question=question,
    )

    # Combine traces and summaries for logging/debugging
    combined_trace = ""
    combined_summary = ""
    last_memory = None

    for res in agent_results:
        agent_id = res["id"]
        combined_trace += f"\n\n=== Agent {agent_id} Trace ===\n{res['trace']}\n=== End Agent {agent_id} ===\n"
        combined_summary += f"\n[Agent {agent_id} Summary]\n{res['search_summary']}"
        if res["memory"]:
            last_memory = res["memory"]

    # Append synthesis result to trace
    combined_trace += f"\n\n=== Synthesis ===\nFinal Answer: {final_answer}\n"

    return (final_answer, combined_trace, last_memory, combined_summary, False)


async def run_with_policy(qid: int, question: str) -> tuple[str, str]:
    last_err = None

    # Simple single run for validation now, as retry logic is built into the agent loop prompts or simplified
    t0 = time.time()
    try:
        logging.info(f"start qid={qid}")

        result_tuple = await asyncio.wait_for(
            run_one(question), timeout=TIMEOUT_SECONDS
        )

        ans, trace, mem_obj, search_summary, need_retry = result_tuple

        if isinstance(ans, str) and ans.strip():
            logging.info(f"ok qid={qid} dur={time.time() - t0:.3f}s")
            return ans, trace
        else:
            logging.warning(f"empty answer qid={qid}")
            return "", trace

    except asyncio.TimeoutError:
        logging.warning(f"timeout qid={qid}")
        return "", "TIMEOUT"

    except Exception as e:
        logging.warning(f"fail qid={qid} err={str(e)}")
        return "", f"ERROR: {str(e)}"


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, help="Limit number of questions to process"
    )
    args = parser.parse_args()

    src = "validation.jsonl"
    out = "validation_results.jsonl"
    debug_out = "validation_results_debug.jsonl"

    if not os.path.exists(src):
        logging.error(f"File not found: {src}")
        return

    items: List[Dict[str, Any]] = []
    with open(src, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "id" not in data:
                    data["id"] = i + 1
                items.append(data)
            except:
                pass

    if args.limit:
        items = items[: args.limit]

    logging.info(f"Loaded {len(items)} validation items")

    processed_ids = set()
    if os.path.exists(out):
        with open(out, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    res = json.loads(line)
                    processed_ids.add(res.get("id"))
                except:
                    pass

    logging.info(f"Resuming... {len(processed_ids)} already processed.")

    correct_count = 0
    total_processed = 0

    for it in items:
        qid = it.get("id")
        if qid in processed_ids:
            continue

        question = it.get("question", "")
        ground_truth = it.get("answer", "")

        logging.info(f"Processing QID {qid}: {question[:50]}...")

        prediction, trace = await run_with_policy(qid, question)

        cleaned_prediction, is_correct, reason = clean_and_judge_answer(
            question, ground_truth, prediction
        )

        # Submission format: only id + answer
        result_item = {
            "id": qid,
            "answer": cleaned_prediction,
        }

        # Keep rich diagnostics in a separate file for debugging/analysis
        debug_item = {
            "id": qid,
            "question": question,
            "ground_truth": ground_truth,
            "prediction": cleaned_prediction,
            "trace": trace,
            "is_correct": is_correct,
            "judge_reason": reason,
        }

        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(result_item, ensure_ascii=False) + "\n")
        with open(debug_out, "a", encoding="utf-8") as f:
            f.write(json.dumps(debug_item, ensure_ascii=False) + "\n")

        total_processed += 1
        if is_correct:
            correct_count += 1

        logging.info(
            f"Result QID {qid}: Correct={is_correct} ({reason}) | Acc: {correct_count}/{total_processed} ({correct_count / total_processed:.2%})"
        )

        await asyncio.sleep(RATE_DELAY_SECONDS)

    logging.info(
        f"Validation Complete. processed={total_processed}, correct={correct_count}, accuracy={correct_count / total_processed if total_processed else 0:.2%}"
    )


if __name__ == "__main__":
    asyncio.run(main())
