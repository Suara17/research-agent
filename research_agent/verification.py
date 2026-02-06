import os
from openai import BadRequestError
from .utils import get_llm_client, clean_answer

def check_answer_type(question: str, answer: str) -> str:
    """
    Lightweight Type Guard: Checks if answer type matches question type.
    """
    try:
        # Quick Heuristics
        q_lower = question.lower()
        if "who" in q_lower or "name" in q_lower:
            if "constitution" in answer.lower() or "agreement" in answer.lower() and len(answer) > 20:
                 pass # Suspicious
            else:
                 return answer

        client = get_llm_client()
        prompt = [
            {"role": "system", "content": "Check if Answer type matches Question type. If yes, output [OK]. If no (e.g. Q: Who? A: Constitution), try to extract the Person from the Answer. If impossible, output [MISMATCH]."},
            {"role": "user", "content": f"Q: {question}\nA: {answer}"}
        ]
        resp = client.chat.completions.create(model="qwen3-max", messages=prompt, max_tokens=100)
        out = resp.choices[0].message.content.strip()
        if "[OK]" in out:
            return answer
        if "[MISMATCH]" in out:
            print(f"[TypeGuard] Mismatch detected for '{answer}'")
            return "" 
            
        return clean_answer(out) # Return fixed answer
    except:
        return answer

def verify_answer(question: str, candidate_answer: str) -> str:
    """
    Use LLM to verify and refine the answer based on the question.
    Performs fuzzy logic verification and confidence scoring.
    """
    if not candidate_answer:
        return ""
        
    try:
        # Create a temporary client (using same env key)
        # Use a shorter timeout for verification
        verify_client = get_llm_client()
        
        current_date = "2026-02-05" # Should ideally come from env or tool
        
        verify_prompt = [
            {"role": "system", "content": f"""You are a strict answer validator.
Your goal is to verify the Candidate Answer based on TWO specific criteria:

1. **Language Consistency**:
   - UNLESS the question explicitly asks for a specific language (e.g., "English name", "in English"), the answer MUST be in the same language as the question.
   - Example: Chinese Question -> Chinese Answer. English Question -> English Answer.

2. **Entity Type Check**:
   - The answer must match the expected entity type asked in the question (e.g., Person, Location, Number, Year, Organization).
   - If Q asks "Who", A must be a Person/Group.
   - If Q asks "Where", A must be a Location.
   - If Q asks "How many/Year", A must be a Number/Year.

**Output Format (CRITICAL)**:
   - You must output the result in a JSON block:
     ```json
     {{
       "status": "ACCEPTED" | "REJECTED" | "PARTIAL",
       "reason": "Brief explanation of failure or correction",
       "refined_answer": "The corrected answer string. REQUIRED if status is ACCEPTED or PARTIAL."
     }}
     ```
   - **PARTIAL / CORRECTION Strategy**:
     - If the candidate answer contains the correct entity but includes extra garbage, repetition, or wrong language, set status to "PARTIAL" (or "ACCEPTED" with correction) and put the CLEANED correct entity in `refined_answer`.
     - Example: Candidate "The answer is Apple Inc. (Apple)", Question "What company..." -> Refined: "Apple Inc."
     - Example: Candidate "英国金融行为监管局 (FCA) FCA", Question (Chinese) -> Refined: "英国金融行为监管局"
   - If the answer violates Language Consistency or Entity Type completely, set status to "REJECTED".
"""},
            {"role": "user", "content": f"Question: {question}\nCandidate Answer: {candidate_answer}"}
        ]
        
        verify_resp = verify_client.chat.completions.create(model="qwen3-max", messages=verify_prompt, max_tokens=512)
        content = verify_resp.choices[0].message.content.strip()
        
        # Parse JSON
        import json
        try:
            # Try to find JSON block
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                json_str = content[start:end+1]
                data = json.loads(json_str)
                status = data.get("status", "UNCERTAIN")
                refined = data.get("refined_answer", "")
                reason = data.get("reason", "")
                
                if status == "ACCEPTED":
                    if refined:
                        print(f"[Verification] Accepted: '{refined}' (Reason: {reason[:50]}...)")
                        return refined
                    else:
                        return candidate_answer
                elif status == "PARTIAL":
                     if refined:
                        print(f"[Verification] Partial/Correction: '{refined}' (Reason: {reason[:50]}...)")
                        return refined
                     else:
                        return candidate_answer
                elif status == "REJECTED":
                    # If rejected but provided a refined answer (correction), use it!
                    if refined and len(refined) > 1 and "unknown" not in refined.lower():
                         print(f"[Verification] Rejected but proposed correction: '{refined}'")
                         return refined
                    
                    print(f"[Verification] Rejected: {reason}")
                    return f"[REJECTED]: {reason}"
                else:
                    # Uncertain
                    return f"[NEED_MORE_EVIDENCE]: {reason}"
        except Exception as e:
            print(f"[Verification] JSON Parse Failed: {e}. Raw content: {content[:100]}")
            
        # Fallback if no JSON found (old behavior, but safer)
        if "REJECTED" in content:
            return "[REJECTED]: Verification failed."
        return candidate_answer

                
    except BadRequestError as e:
        if "DataInspectionFailed" in str(e) or "inappropriate" in str(e):
             print(f"[Verification] Safety Filter Triggered: {e}")
             return "[REJECTED]: Answer verification failed due to safety policy violation."
        print(f"[Verification] BadRequest Failed: {e}")
        
    except Exception as e:
        print(f"[Verification] Failed: {e}")
        # Fallback to the original result if verification fails
    
    return candidate_answer

async def force_fix_answer(question: str, candidate_answer: str, rejection_reason: str) -> str:
    """
    Last resort: Use LLM to extract the best possible answer from the rejected candidate
    or make a best guess that satisfies the type constraints.
    """
    try:
        client = get_llm_client()
        prompt = [
            {"role": "system", "content": "You are a final decision maker. The previous answer was rejected due to type mismatch or other issues. You MUST output a valid answer string that best fits the question."},
            {"role": "user", "content": f"Question: {question}\nRejected Answer: {candidate_answer}\nRejection Reason: {rejection_reason}\n\nTask: Provide the single best answer string. If the rejected answer mentions a correct entity (e.g. a person name inside a long text), extract it. If it's completely wrong, make your best guess based on the context. Output ONLY the answer string."}
        ]
        resp = client.chat.completions.create(model="qwen3-max", messages=prompt, max_tokens=100)
        fixed = resp.choices[0].message.content.strip()
        fixed = clean_answer(fixed)
        print(f"[Monitoring] Force fixed answer: '{candidate_answer[:50]}...' -> '{fixed[:50]}...'")
        return fixed
    except Exception as e:
        print(f"[Monitoring] Force fix failed: {e}")
        return candidate_answer # Fallback to original
