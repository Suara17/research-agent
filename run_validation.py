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

# Add current directory to sys.path to ensure local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from research_agent.core import agent_loop
from research_agent.search import web_search, web_fetch, get_weather, browse_page, x_keyword_search, search_pdf_attachment, browse_pdf_attachment
from research_agent.answer_synthesis import verify_and_clean_answer
from agent import QueryRequest

# Setup logging specific to validation
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("validation_run.log", encoding="utf-8"),
        logging.FileHandler("validation_run.md", encoding="utf-8"),
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

async def judge_answer(question: str, ground_truth: str, prediction: str) -> tuple[bool, str]:
    """
    Compare prediction with ground truth using normalization and LLM fallback.
    Returns (is_correct, reason)
    """
    if not prediction:
        return False, "Empty prediction"
        
    def normalize(s):
        return str(s).lower().strip().replace("。", "").replace(".", "").replace(" ", "")
    
    # 1. Exact match (normalized)
    if normalize(prediction) == normalize(ground_truth):
        return True, "Exact match (normalized)"
        
    # 2. Containment (if ground truth is short and inside prediction)
    norm_gt = normalize(ground_truth)
    norm_pred = normalize(prediction)
    if len(norm_gt) > 4 and norm_gt in norm_pred:
         return True, "Containment match"

    # 3. LLM Judge
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://apis.iflow.cn/v1",
            api_key=os.getenv("IFLOW_API_KEY"),
            timeout=20.0,
        )
        prompt = [
            {"role": "system", "content": "You are a judge. Compare the predicted answer with the ground truth for the given question. Determine if they convey the same meaning. Output ONLY 'TRUE' or 'FALSE'."},
            {"role": "user", "content": f"Question: {question}\nGround Truth: {ground_truth}\nPredicted Answer: {prediction}\n\nIs the prediction correct?"}
        ]
        resp = client.chat.completions.create(model="qwen3-max", messages=prompt, max_tokens=10)
        result = resp.choices[0].message.content.strip().upper()
        if "TRUE" in result:
            return True, "LLM Judge: TRUE"
        else:
            return False, f"LLM Judge: FALSE ({result})"
    except Exception as e:
        logging.error(f"Judge error: {e}")
        return False, f"Judge error: {e}"

async def run_one(
    question: str,
    rejection_history: List[str] = None,
    is_retry: bool = False,
    inherited_memory=None,
    inherited_context: str = None
) -> tuple:
    # Use QueryRequest from agent.py to ensure consistency with the API service
    req = QueryRequest(question=question)
    messages = req.to_messages()

    # Dynamic max_steps
    if is_retry:
        max_steps = 15
        logging.info(f"[Retry] Using reduced max_steps={max_steps}")
    else:
        max_steps = 30 # Fixed max steps for new agent
        logging.info(f"[Monitoring] Using fixed max_steps: {max_steps}")

    if rejection_history:
        hint_text = "\n\n".join(rejection_history)
        messages.append({
            "role": "system",
            "content": f"""SYSTEM REMINDER: Previous verification FAILED.

PREVIOUS REJECTIONS:
{hint_text}

INSTRUCTION: Analyze the rejection reasons. Change your search strategy to avoid repeating mistakes."""
        })

    raw_result = ""
    skill_usage_log = []
    search_summary_parts = []

    tools = [web_search, web_fetch, get_weather, browse_page, x_keyword_search, search_pdf_attachment, browse_pdf_attachment]

    final_memory = None
    
    async for chunk in agent_loop(
        messages,
        tools,
        max_steps=max_steps,
        inherited_memory=inherited_memory,
        inherited_context=inherited_context
    ):
        if chunk.type == "final_state":
            # chunk.tool_result might be memory object if yield by agent_loop, check implementation
            # In new agent_loop, final_state content is json, tool_result is memory
            final_memory = chunk.tool_result

        if chunk.type == "tool_call":
            tool_name = chunk.tool_call.tool_name if chunk.tool_call else "unknown"
            tool_args = chunk.tool_call.tool_arguments if chunk.tool_call else {}
            if tool_name == "web_search":
                query = tool_args.get("query", "")
                search_summary_parts.append(f"Searched: {query}")
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
                    # In new agent, tool_result is string, need to check format
                    # If it's json string, parse it? 
                    # Actually agent_loop returns string representation for display
                    if isinstance(chunk.tool_result, str) and "Found:" in chunk.tool_result:
                         search_summary_parts.append(chunk.tool_result[:100])
                except:
                    pass

        elif chunk.type == "text" and chunk.content:
            raw_result += chunk.content

    if skill_usage_log:
        logging.info(f"[SKILL_SUMMARY] Skills used: {', '.join(skill_usage_log)}")
    
    final_answer = raw_result
    if raw_result:
        # Use verify_and_clean_answer to ensure language consistency
        final_answer = verify_and_clean_answer(raw_result, question)

    search_summary = "\n".join(search_summary_parts[-10:]) if search_summary_parts else ""
    return (final_answer, raw_result, final_memory, search_summary, False) # Return raw_result as trace

async def run_with_policy(qid: int, question: str) -> tuple[str, str]:
    last_err = None
    
    # Simple single run for validation now, as retry logic is built into the agent loop prompts or simplified
    t0 = time.time()
    try:
        logging.info(f"start qid={qid}")

        result_tuple = await asyncio.wait_for(
            run_one(question),
            timeout=TIMEOUT_SECONDS
        )

        ans, trace, mem_obj, search_summary, need_retry = result_tuple

        if isinstance(ans, str) and ans.strip():
            logging.info(f"ok qid={qid} dur={time.time()-t0:.3f}s")
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
    parser.add_argument("--limit", type=int, help="Limit number of questions to process")
    args = parser.parse_args()

    src = "validation.jsonl"
    out = "validation_results.jsonl"
    
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
        items = items[:args.limit]

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
        
        is_correct, reason = await judge_answer(question, ground_truth, prediction)
        
        result_item = {
            "id": qid,
            "question": question,
            "ground_truth": ground_truth,
            "prediction": prediction,
            "trace": trace,  # Added trace field
            "is_correct": is_correct,
            "judge_reason": reason
        }
        
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(result_item, ensure_ascii=False) + "\n")
            
        total_processed += 1
        if is_correct:
            correct_count += 1
            
        logging.info(f"Result QID {qid}: Correct={is_correct} ({reason}) | Acc: {correct_count}/{total_processed} ({correct_count/total_processed:.2%})")
        
        await asyncio.sleep(RATE_DELAY_SECONDS)

    logging.info(f"Validation Complete. processed={total_processed}, correct={correct_count}, accuracy={correct_count/total_processed if total_processed else 0:.2%}")

if __name__ == "__main__":
    asyncio.run(main())
