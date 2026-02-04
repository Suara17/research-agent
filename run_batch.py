import re
import asyncio
import json
import os
import time
import logging
from pathlib import Path
from typing import Any, Dict, List

from agent_loop import agent_loop
from agent import web_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("batch_run.log", encoding="utf-8"), logging.StreamHandler()],
)

MAX_RETRIES = 2
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
                        # Force overwrite IFLOW_API_KEY to ensure latest value is used
                        if k == "IFLOW_API_KEY" or k not in os.environ:
                            os.environ[k] = v
    except Exception:
        pass

_load_env_from_dotenv()

# Log the API key being used (masked)
api_key = os.getenv("IFLOW_API_KEY", "")
masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "N/A"
logging.info(f"Using IFLOW_API_KEY: {masked_key}")

from agent import web_search, web_fetch, get_weather, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, QueryRequest, clean_answer, verify_answer

async def run_one(question: str) -> str:
    # Use QueryRequest from agent.py to ensure consistency with the API service
    req = QueryRequest(question=question)
    messages = req.to_messages()

    result = ""
    skill_usage_log = []  # 记录 Skill 使用情况
    # Use the same toolset as agent.py
    tools = [web_search, web_fetch, get_weather, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment]
    # 用户要求深度推理，最大步数增加到 200，以支持多轮搜索验证
    async for chunk in agent_loop(messages, tools, max_steps=200):
        if chunk.type == "tool_call":
            # 记录所有工具调用，特别标注 Skill 相关调用
            tool_name = chunk.tool_call.tool_name if chunk.tool_call else "unknown"
            tool_args = chunk.tool_call.tool_arguments if chunk.tool_call else {}

            # 检测是否是 Skill 相关调用
            if tool_name == "load_skill_file":
                skill_name = tool_args.get("skill_name", "unknown")
                logging.info(f"[SKILL] Loading skill: {skill_name}")
                skill_usage_log.append(f"load:{skill_name}")
            elif tool_name == "execute_script":
                skill_name = tool_args.get("skill_name", "unknown")
                skill_args = tool_args.get("args", {})
                logging.info(f"[SKILL] Executing skill: {skill_name} with args: {json.dumps(skill_args, ensure_ascii=False)[:100]}")
                skill_usage_log.append(f"execute:{skill_name}")
            else:
                # 普通工具调用也记录，但不加 [SKILL] 前缀
                logging.debug(f"[TOOL] {tool_name} called with args: {json.dumps(tool_args, ensure_ascii=False)[:100]}")

            # result = ""  # Don't clear result, keep the thought chain
        elif chunk.type == "tool_call_result":
            # 记录 Skill 执行结果
            tool_name = chunk.tool_call.tool_name if chunk.tool_call else "unknown"
            if tool_name in ("load_skill_file", "execute_script"):
                result_preview = str(chunk.tool_result)[:200] if chunk.tool_result else "empty"
                logging.info(f"[SKILL] Result from {tool_name}: {result_preview}")
        elif chunk.type == "text" and chunk.content:
            result += chunk.content

    # 在函数结束时输出 Skill 使用统计
    if skill_usage_log:
        logging.info(f"[SKILL_SUMMARY] Skills used: {', '.join(skill_usage_log)}")
    else:
        logging.warning("[SKILL_SUMMARY] No skills were used in this iteration")
    
    # Post-processing: Extract last line logic
    if result:
        result = result.strip()
        if "\n" in result:
            lines = [line.strip() for line in result.split('\n') if line.strip()]
            if lines:
                last_line = lines[-1]
                # If the last line starts with "Final Answer:", extract the content
                if ":" in last_line:
                     # Check common prefixes
                     if re.match(r'^(Answer|Therefore|Thus|So|In conclusion|Final Answer)[:：]', last_line, re.IGNORECASE):
                          last_line = re.sub(r'^(Answer|Therefore|Thus|So|In conclusion|Final Answer)[:：]?\s*', '', last_line, flags=re.IGNORECASE)
                
                last_line = re.sub(r'\*\*|__|\*|_', '', last_line)
                result = last_line
        
        result = clean_answer(result)
        
    
    # --- Final Verification & Refinement ---
    # Use LLM to strictly enforce format requirements and fix repetitions
    if result:
        original = result
        result = verify_answer(question, result)
        if result != original:
             logging.info(f"Verified answer: '{original}' -> '{result}'")
    
    return result

async def run_with_policy(qid: int, question: str, stats: Dict[str, int]) -> str:
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        t0 = time.time()
        try:
            logging.info(f"start qid={qid} attempt={attempt}")
            ans = await asyncio.wait_for(run_one(question), timeout=TIMEOUT_SECONDS)
            if isinstance(ans, str) and ans.strip():
                logging.info(f"ok qid={qid} attempt={attempt} dur={time.time()-t0:.3f}s")
                stats["ok"] += 1
                return ans
            else:
                raise ValueError("empty_answer")
        except asyncio.TimeoutError:
             last_err = "timeout"
             logging.warning(f"timeout qid={qid} attempt={attempt}")
             stats["timeout"] += 1
        except Exception as e:
            last_err = e
            logging.warning(f"fail qid={qid} attempt={attempt} err={str(e)}")
            stats["error"] += 1
            if "empty_answer" in str(e):
                 stats["empty"] += 1
            
        await asyncio.sleep(RATE_DELAY_SECONDS * (attempt + 1))
    
    logging.error(f"giveup qid={qid} err={str(last_err) if last_err else ''}")
    stats["failed"] += 1
    return ""

async def main():
    src = "question.jsonl"
    out = "submission.jsonl"
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    items: List[Dict[str, Any]] = []
    with open(src, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    results: List[Dict[str, Any]] = []
    start_all = time.time()
    
    stats = {
        "ok": 0,
        "empty": 0,
        "timeout": 0,
        "error": 0,
        "failed": 0
    }
    
    # Load existing results to support resume
    processed_ids = set()
    if os.path.exists(out):
        with open(out, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    res = json.loads(line)
                    pid = res.get("id")
                    if pid is not None:
                        processed_ids.add(int(pid))
                except Exception:
                    pass
    logging.info(f"resuming found={len(processed_ids)} processed items")

    for it in items:
        qid = int(it.get("id") or 0)
        if qid in processed_ids:
            # Skip already processed
            continue

        # Pass stats to run_with_policy to update in real-time (simplified)
        # Better: return status from run_with_policy, but this works for now
        ans = await run_with_policy(qid, str(it.get("question") or ""), stats)
        result_item = {"id": it.get("id"), "answer": ans}
        results.append(result_item)
        
        # Append to file immediately
        try:
            with open(out, "a", encoding="utf-8") as f:
                f.write(json.dumps(result_item, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            logging.info(f"written qid={qid}")
        except Exception as e:
            logging.error(f"write_fail qid={qid} err={e}")
            
        await asyncio.sleep(RATE_DELAY_SECONDS)
        
    logging.info(f"done count={len(items)} dur={time.time()-start_all:.3f}s stats={json.dumps(stats)}")


if __name__ == "__main__":
    asyncio.run(main())
