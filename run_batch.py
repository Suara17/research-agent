import re
import asyncio
import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Any, Dict, List

from agent_loop import agent_loop
from agent import web_search
from research_agent.complexity import calculate_max_steps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("batch_run.log", encoding="utf-8"),
        logging.FileHandler("batch_run.md", encoding="utf-8"),
        logging.StreamHandler()
    ],
)

# Redirect stdout to also write to file handlers to capture print statements (e.g. Planner output)
class TeeStdout:
    def __init__(self, original_stdout, handlers):
        self.original_stdout = original_stdout
        self.handlers = handlers

    def write(self, message):
        self.original_stdout.write(message)
        for h in self.handlers:
            try:
                # Write to the file stream of the handler
                if hasattr(h, 'stream') and h.stream:
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

# Get file handlers from root logger
_root_logger = logging.getLogger()
_file_handlers = [h for h in _root_logger.handlers if isinstance(h, logging.FileHandler)]
if _file_handlers:
    sys.stdout = TeeStdout(sys.stdout, _file_handlers)


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

class AnswerRejectedError(Exception):
    def __init__(self, message, candidate_answer=""):
        self.message = message
        self.candidate_answer = candidate_answer
        super().__init__(message)

async def force_fix_answer(question: str, candidate_answer: str, rejection_reason: str) -> str:
    """
    Last resort: Use LLM to extract the best possible answer from the rejected candidate
    or make a best guess that satisfies the type constraints.
    """
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://apis.iflow.cn/v1",
            api_key=os.getenv("IFLOW_API_KEY"),
            timeout=20.0,
        )
        prompt = [
            {"role": "system", "content": "You are a final decision maker. The previous answer was rejected due to type mismatch or other issues. You MUST output a valid answer string that best fits the question."},
            {"role": "user", "content": f"Question: {question}\nRejected Answer: {candidate_answer}\nRejection Reason: {rejection_reason}\n\nTask: Provide the single best answer string. If the rejected answer mentions a correct entity (e.g. a person name inside a long text), extract it. If it's completely wrong, make your best guess based on the context. Output ONLY the answer string."}
        ]
        resp = client.chat.completions.create(model="qwen3-max", messages=prompt, max_tokens=100)
        fixed = resp.choices[0].message.content.strip()
        fixed = clean_answer(fixed)
        logging.info(f"Force fixed answer: '{candidate_answer}' -> '{fixed}'")
        return fixed
    except Exception as e:
        logging.error(f"Force fix failed: {e}")
        return candidate_answer # Fallback to original

async def run_one(question: str, rejection_history: List[str] = None) -> str:
    # Use QueryRequest from agent.py to ensure consistency with the API service
    req = QueryRequest(question=question)
    messages = req.to_messages()

    # 🔥 动态计算最大步数（方案2）
    max_steps = calculate_max_steps(question, base_steps=20)
    logging.info(f"[Monitoring] Dynamic max_steps calculated: {max_steps} for question: {question[:50]}...")

    if rejection_history:
        hint_text = "\n\n".join(rejection_history)
        messages.append({
            "role": "system",
            "content": f"SYSTEM REMINDER: You previously attempted to answer this question but were REJECTED by verification.\n\nPREVIOUS REJECTIONS:\n{hint_text}\n\nINSTRUCTION: Please analyze the rejection reasons above. You MUST change your search strategy, explore different entities/paths, or verify details more strictly to avoid repeating the same mistake."
        })

    result = ""
    skill_usage_log = []  # 记录 Skill 使用情况
    # Use the same toolset as agent.py
    tools = [web_search, web_fetch, get_weather, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment]
    # 🔥 使用动态计算的步数（替代原来固定的30步）
    async for chunk in agent_loop(messages, tools, max_steps=max_steps):
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
        
    # --- Three-Round Verification Strategy ---
    # Round 1: Deduplication (Filter duplicate answers)
    if result:
        result = clean_answer(result)
    
    # Round 2: LLM Verification (Accuracy & Strict Format)
    if result:
        original = result
        verified = verify_answer(question, result)
        
        # Check for Rejection
        if "[REJECTED]" in verified:
             logging.warning(f"Answer rejected by verification: {verified}")
             # If rejected, we treat it as empty to trigger retry (if retries available)
             # or we might want to keep the original if we trust it more? 
             # No, if LLM rejects it, it's likely bad. Better to retry.
             # result = "" 
             raise AnswerRejectedError(verified, candidate_answer=original)
        else:
             if verified != original:
                 logging.info(f"Verified answer: '{original}' -> '{verified}'")
             result = verified
    
    # Round 3: Deduplication again (Final safety net)
    if result:
        result = clean_answer(result)
    
    return result

async def run_with_policy(qid: int, question: str, stats: Dict[str, int]) -> str:
    last_err = None
    rejection_history = []
    
    for attempt in range(MAX_RETRIES + 1):
        t0 = time.time()
        try:
            logging.info(f"start qid={qid} attempt={attempt}")
            ans = await asyncio.wait_for(run_one(question, rejection_history), timeout=TIMEOUT_SECONDS)
            if isinstance(ans, str) and ans.strip():
                logging.info(f"ok qid={qid} attempt={attempt} dur={time.time()-t0:.3f}s")
                stats["ok"] += 1
                return ans
            else:
                raise ValueError("empty_answer")
        except AnswerRejectedError as e:
             last_err = e
             logging.warning(f"rejected qid={qid} attempt={attempt} reason={e.message[:100]}...")
             rejection_history.append(f"Attempt {attempt+1}: {e.message}")
             
             # Last Attempt Logic: If this was the last attempt, try to force a fix
             if attempt == MAX_RETRIES:
                 logging.warning(f"Max retries reached. Forcing fix for rejected candidate...")
                 try:
                     fixed_ans = await force_fix_answer(question, e.candidate_answer, e.message)
                     if fixed_ans:
                         logging.info(f"ok (forced) qid={qid} attempt={attempt}")
                         stats["ok"] += 1
                         return fixed_ans
                 except Exception as ex:
                     logging.error(f"Force fix failed completely: {ex}")
                     
             # stats["error"] += 1 # Optional: count rejections as errors or just retries?
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
    last_processed_id = -1
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
                        pid_int = int(pid)
                        processed_ids.add(pid_int)
                        if pid_int > last_processed_id:
                            last_processed_id = pid_int
                except Exception as e:
                    logging.warning(f"Failed to parse line in {out}: {line[:50]}... Error: {e}")
                    pass
    
    # [Fix] Robust Resume Logic
    # 1. Use set check (existing)
    # 2. ALSO ensure we don't accidentally re-process the last item if the file write wasn't flushed or if logic was ambiguous
    # The current logic `if qid in processed_ids: continue` is correct for skipping SPECIFIC IDs.
    # However, if the user sees "found=52" (IDs 0-51 processed?) and it starts from 52 (ID 52), that is actually CORRECT (0-based index).
    # Wait, if IDs are 1-based (1..100), then found=52 means 1..52 are done. Next should be 53.
    # If IDs are 0-based (0..99), then found=52 means 0..51 are done. Next should be 52.
    
    # Let's check the input file "question.jsonl" structure.
    # Assuming IDs are sequential integers.
    
    # User Complaint: "detected 52 answers, but started from 52?"
    # If the file contains IDs 1, 2, ..., 52. The set `processed_ids` has size 52.
    # The loop iterates `items`. If `items` has an item with `id: 52`.
    # `if 52 in processed_ids`: it should skip.
    # If it started from 52, it means ID 52 was NOT in `processed_ids`.
    # This implies ID 52 was missing from `submission.jsonl`, OR the IDs in `submission.jsonl` are 0, 1, ..., 51 (total 52 items).
    # If IDs are 0..51, then ID 52 is indeed the next one.
    
    # However, if the user implies that ID 52 IS already done but being re-processed:
    # It might be a type mismatch (str vs int) or `processed_ids` not populated correctly.
    # Code uses `int(pid)` and `int(it.get("id"))`. This looks correct.
    
    # Another possibility: Duplicate IDs in input?
    
    # To be safe, let's explicitly log the skip/start decision.
    
    logging.info(f"resuming found={len(processed_ids)} processed items. Last ID: {last_processed_id}")

    for it in items:
        qid = int(it.get("id") or 0)
        
        # [Fix] Double check against processed_ids
        if qid in processed_ids:
            # Skip already processed
            continue
            
        # [Fix] Additional check: If qid <= last_processed_id, we might have a gap or out-of-order execution.
        # But generally we trust processed_ids.


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
