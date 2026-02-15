import re
import asyncio
import json
import os
import sys
import time
import logging
import argparse
from pathlib import Path
from typing import Any, Dict, List

from research_agent.core import agent_loop
from research_agent.search import web_search, web_fetch, get_weather, browse_page, x_keyword_search, search_pdf_attachment, browse_pdf_attachment
from research_agent.answer_synthesis import verify_and_clean_answer, synthesize_best_answer
from agent import QueryRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("batch_run.log", encoding="utf-8"),
        logging.FileHandler("batch_run.md", encoding="utf-8"),
        logging.StreamHandler()
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

_root_logger = logging.getLogger()
_file_handlers = [h for h in _root_logger.handlers if isinstance(h, logging.FileHandler)]
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

api_key = os.getenv("IFLOW_API_KEY", "")
masked_key = f"{api_key[:5]}...{api_key[-5:]}" if len(api_key) > 10 else "N/A"
logging.info(f"Using IFLOW_API_KEY: {masked_key}")


async def run_one(
    question: str,
    rejection_history: List[str] = None,
    is_retry: bool = False,
    inherited_memory=None,
    inherited_context: str = None
) -> tuple:
    """
    Returns: (answer, memory, search_summary, need_retry)
    """
    req = QueryRequest(question=question)
    base_messages = req.to_messages()

    if is_retry:
        max_steps = 15
        logging.info(f"[Retry] Using reduced max_steps={max_steps}")
    else:
        max_steps = 30
        logging.info(f"[Monitoring] Using fixed max_steps: {max_steps}")

    if rejection_history:
        hint_text = "\n\n".join(rejection_history)
        base_messages.append({
            "role": "system",
            "content": f"""SYSTEM REMINDER: Previous verification FAILED.

PREVIOUS REJECTIONS:
{hint_text}

INSTRUCTION: Analyze the rejection reasons. Change your search strategy to avoid repeating mistakes."""
        })

    tools = [web_search, web_fetch, get_weather, browse_page, x_keyword_search, search_pdf_attachment, browse_pdf_attachment]

    # Configure number of agents to run in parallel
    num_agents = int(os.environ.get("NUM_AGENTS", "1"))
    if num_agents < 1: num_agents = 1

    logging.info(f"[Single-Agent] Starting {num_agents} agent via API for batch QID...")

    async def run_single_agent(agent_id: int, tools: list):
        # Create a fresh copy of messages for each agent
        messages = json.loads(json.dumps(base_messages)) # Deep copy to be safe
        
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
                inherited_context=inherited_context
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
                            if isinstance(chunk.tool_result, str) and "Found:" in chunk.tool_result:
                                search_summary_parts.append(chunk.tool_result[:100])
                        except:
                            pass

                elif chunk.type == "text" and chunk.content:
                    raw_result += chunk.content
            
            if skill_usage_log:
                logging.info(f"[Agent {agent_id}] Skills used: {', '.join(skill_usage_log)}")
            
            # Clean individual result
            cleaned_ans = ""
            if raw_result:
                cleaned_ans = verify_and_clean_answer(raw_result, question)
                
            return {
                "id": agent_id,
                "trace": raw_result,
                "answer": cleaned_ans,
                "memory": final_memory,
                "search_summary": "\n".join(search_summary_parts)
            }
        except Exception as e:
            logging.error(f"[Agent {agent_id}] Failed: {e}")
            return {
                "id": agent_id,
                "trace": raw_result + f"\n\n[System Error]: {str(e)}",
                "answer": "",
                "memory": None,
                "search_summary": ""
            }

    tasks = [run_single_agent(i+1, tools) for i in range(num_agents)]
    agent_results = await asyncio.gather(*tasks)
    
    logging.info(f"[Multi-Agent] All {len(agent_results)} agents finished. Synthesizing best answer...")
    
    # Synthesize
    final_answer = synthesize_best_answer(question, agent_results)
    
    # Combine summaries and find last memory
    combined_summary = ""
    last_memory = None
    
    for res in agent_results:
        agent_id = res["id"]
        combined_summary += f"\n[Agent {agent_id} Summary]\n{res['search_summary']}"
        if res["memory"]:
            last_memory = res["memory"]

    return (final_answer, last_memory, combined_summary, False)

async def run_with_policy(qid: int, question: str, stats: Dict[str, int]) -> str:
    last_err = None
    inherited_context = None
    inherited_mem_obj = None
    rejection_summary = []

    for attempt in range(MAX_RETRIES + 1):
        t0 = time.time()
        is_retry = (attempt > 0)

        try:
            logging.info(f"start qid={qid} attempt={attempt}")

            result_tuple = await asyncio.wait_for(
                run_one(
                    question,
                    rejection_history=rejection_summary,
                    is_retry=is_retry,
                    inherited_memory=inherited_mem_obj,
                    inherited_context=inherited_context
                ),
                timeout=TIMEOUT_SECONDS
            )

            ans, mem_obj, search_summary, need_retry = result_tuple

            if isinstance(ans, str) and ans.strip():
                if need_retry and attempt < MAX_RETRIES:
                    logging.warning(f"[Retry] Verification failed. Preparing retry with context...")
                    if mem_obj:
                        inherited_mem_obj = mem_obj
                    inherited_context = f"Previous attempt summary:\nAnswer candidate: {ans}\nSearch queries executed:\n{search_summary}\n\nVerification rejected this answer."
                    rejection_summary.append(f"Attempt {attempt+1}: Verification rejected answer '{ans}'")
                    await asyncio.sleep(RATE_DELAY_SECONDS)
                    continue

                logging.info(f"ok qid={qid} attempt={attempt} dur={time.time()-t0:.3f}s")
                stats["ok"] += 1
                return ans
            else:
                logging.warning(f"empty answer qid={qid} attempt={attempt}")
                if attempt < MAX_RETRIES:
                    logging.info("Retrying due to empty answer...")
                    continue
                else:
                    stats["empty"] += 1
                    return ""

        except asyncio.TimeoutError:
             last_err = "timeout"
             logging.warning(f"timeout qid={qid} attempt={attempt}")
             stats["timeout"] += 1
             if attempt < MAX_RETRIES:
                 logging.info("Retrying due to timeout...")
                 await asyncio.sleep(RATE_DELAY_SECONDS * (attempt + 1))
                 continue

        except Exception as e:
            last_err = e
            logging.warning(f"fail qid={qid} attempt={attempt} err={str(e)}")
            stats["error"] += 1
            if attempt < MAX_RETRIES:
                logging.info("Retrying due to exception...")
                await asyncio.sleep(RATE_DELAY_SECONDS * (attempt + 1))
                continue

    logging.error(f"giveup qid={qid} err={str(last_err) if last_err else ''}")
    stats["failed"] += 1
    return ""

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question_id", type=int, help="Run specific question ID")
    parser.add_argument("--force", action="store_true", help="Force re-run even if already processed")
    args = parser.parse_args()

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
    
    if args.question_id is not None:
        items = [it for it in items if int(it.get("id") or 0) == args.question_id]
        if not items:
            logging.error(f"Question ID {args.question_id} not found in {src}")
            return

    results: List[Dict[str, Any]] = []
    start_all = time.time()
    
    stats = {
        "ok": 0,
        "empty": 0,
        "timeout": 0,
        "error": 0,
        "failed": 0
    }
    
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
    
    logging.info(f"resuming found={len(processed_ids)} processed items. Last ID: {last_processed_id}")

    for it in items:
        qid = int(it.get("id") or 0)
        
        if qid in processed_ids and not args.force:
            if args.question_id is not None:
                logging.info(f"Force running question {qid} (explicitly requested)")
            else:
                continue
            
        ans = await run_with_policy(qid, str(it.get("question") or ""), stats)
        result_item = {"id": it.get("id"), "answer": ans}
        results.append(result_item)
        
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
