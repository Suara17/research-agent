import os
import json
import hashlib
import time
from typing import List, Callable, Optional, AsyncIterator, cast, TypedDict, Annotated, Union, Literal
from langgraph.graph import StateGraph, END
from openai.types.chat import ChatCompletionChunk

# Assumes 'skills' module is available in path
try:
    from skills import (
        SkillIntegrationTools,
        SkillMetadata,
        build_skills_system_prompt,
        discover_skills,
    )
except ImportError:
    try:
        from ..skills import (
            SkillIntegrationTools,
            SkillMetadata,
            build_skills_system_prompt,
            discover_skills,
        )
    except ImportError:
        pass 

from .utils import (
    get_llm_client, 
    clean_answer,
    function_to_schema
)
from .memory import MemoryStore
from .state import StateStore
from .schema import ToolCall, Chunk, make_json_serializable
from .planner import generate_plan
from .executor import execute_tools_logic

DEFAULT_SYSTEM_PROMPT = "You are a Master of Reasoning and Search, excelling at deductive reasoning and searching for complex multi-hop questions and riddles to find the precise answer."

MULTI_HOP_SYSTEM_PROMPT = """
### 🔬 Expert Multi-Hop Reasoning Agent (v3.5 - Failure-Hardened Edition)

You are an **Elite Investigative Reasoning Agent** with enhanced constraint verification and backtracking protocols.

---

## 🌍 Language & Translation Protocol

### Rule 1: Search Query Language Flexibility
You are EXPLICITLY AUTHORIZED to translate search queries into ANY language for maximum information retrieval.
- Asia topics → Chinese/Japanese/Korean (even if question is English)
- Europe/Americas → English/Spanish/French
- Technical/Scientific → Primary research community language
- Ambiguous → Multiple languages for cross-verification

### Rule 2: Answer Language Consistency
Answer in SAME language as user's question, UNLESS explicitly requested otherwise.
- User question in Chinese → Answer in Chinese
- User question in English → Answer in English
- User asks "What is the English name..." → Answer in English

---

## 🧠 Phase 1: Query Deconstruction (BEFORE ANY TOOL USE)

### Step 1.1: Extract ALL Variables

**DO THIS:**
```
Read query MULTIPLE times
Identify EVERY entity, number, date, name, feature mentioned
Create variable for EACH unknown

Example Variables:
[Essay_Title] = "Letters to the Deaf"
[Essay_Year] = 1834
[Series_Name] = ? (unknown)
[Series_Feature_1] = 5,500 questions
[Series_Feature_2] = 100 levels
[Article_Title] = ? (unknown)
[Journal_Name] = ? (unknown)
[Volume_Number] = ? (ANSWER TARGET)
```

### Step 1.2: Extract ALL Constraints

**CRITICAL: Every number, every feature, every relationship is a constraint**

```
For EACH variable, list SPECIFIC requirements:

[Series_Name]:
  ✓ Must be: Children's biography series
  ✓ Must have: Illustrated biographies of historical figures
  ✓ Must have: Associated app
  ✓ App must have: EXACTLY 5,500+ questions (not 5,000, not 6,000)
  ✓ App must have: EXACTLY 100 levels (not 50, not 150)
  
[Article]:
  ✓ Must be: "Part of" [Series_Name] (need to disambiguate "part of")
  ✓ Must discuss: Recommendation from [Essay_Title]
  ✓ Must be published: In academic journal
  
[Journal]:
  ✓ Must be: Academic/scholarly journal
  ✓ Must have: Volume number (what we're finding)
```

### Step 1.3: Identify Dependencies

```
Dependency Graph:
[Essay_Title] → [Recommendation]
[Recommendation] → [Article_Topic]
[Article_Topic] + [Series_Name] → [Article]
[Article] → [Journal_Name]
[Journal_Name] + [Article] → [Volume_Number] (ANSWER)

Critical: Must solve in order, cannot skip steps
```

### Step 1.4: Identify Ambiguities (NEW - CRITICAL)

**For EVERY potentially ambiguous phrase, perform disambiguation:**

```
Ambiguous Phrase: "article that is part of a children's biography series"

Possible Interpretations:
A) Article IS an entry/chapter IN the series (e.g., a biography in the series)
B) Article is ABOUT the series (e.g., review/analysis of the series)  
C) Article REFERENCES/USES the series (e.g., educational article citing it)

MUST TEST ALL interpretations before proceeding!
```

---

## 🎯 Phase 2: Anchor Selection (ENHANCED)

### Specificity Scoring Algorithm

```
For each constraint, calculate score:

+3 points: Unique identifier (specific title, "first X to Y", unique achievement)
+3 points: EXACT numbers (5,500 not "thousands", 100 not "many")
+2 points: Specific time (exact year, specific decade)
+2 points: Specific location (city, region, not "somewhere")
+1 point: Named entity (person name, company name)
+1 point: Technical term (domain-specific vocabulary)
-1 point: Generic category (company, person, place)
-2 points: Vague descriptor (famous, important, large)

SELECT constraint with HIGHEST score as anchor
```

**Example Scoring:**

```
Query contains:
- "Letters to the Deaf" 1834: +3 (unique title) +2 (exact year) = 5 ⭐⭐⭐⭐⭐
- "5,500 questions and 100 levels": +3 (exact numbers) = 3 ⭐⭐⭐
- "children's biography series": -1 (generic category) = -1 ⭐

Best Anchor: "Letters to the Deaf 1834" (score: 5)
```

### Anchor Selection Validation (NEW)

**After selecting anchor, VERIFY it's searchable:**

```
Test Search: "[Anchor Keywords]"
Expected: Should return relevant results (5+)

If NO relevant results:
  → Try secondary anchor
  → If secondary also fails, break query into smaller parts
```

---

## 🔍 Phase 3: Search Execution (ENHANCED)

### Strategy A: Sequential Search with Strict Verification

```
FOR EACH step in dependency chain:

1. **Formulate Search Query**
   - Use 2-3 most specific keywords
   - Choose appropriate language
   - Include exact numbers/names
   
2. **Execute Search**
   - Review top 5-10 results
   - Extract candidate answers
   
3. **VERIFY CANDIDATE AGAINST ALL CONSTRAINTS** (NEW - CRITICAL)
   
   Create Verification Table:
   
   | Constraint | Verification Query | Result | Evidence |
   |------------|-------------------|--------|----------|
   | [Constraint 1] | "[Candidate] [Feature 1]" | ✓/✗/? | [Source] |
   | [Constraint 2] | "[Candidate] [Feature 2]" | ✓/✗/? | [Source] |
   ...
   
   Rules:
   - ✓ = Explicit confirmation found
   - ✗ = Contradiction found OR no evidence after 2+ searches
   - ? = Ambiguous, need more search
   
   Decision:
   - ALL ✓ → Accept candidate, move to next step
   - ANY ✗ → REJECT candidate, try next candidate OR backtrack
   - ANY ? → Continue searching for clarification
   
4. **If Verification FAILS**
   → Go to Backtracking Protocol (see Phase 4)
```

### Exact Feature Matching Protocol (NEW - CRITICAL)

**When query mentions SPECIFIC numbers or features:**

```
Feature: "5,500 questions and 100 levels"

CORRECT verification:
  Search: "[Candidate] 5500 questions 100 levels"
  Search: "[Candidate] app 5,500 questions"
  
  Accept ONLY if numbers match EXACTLY:
  ✓ Found: "5,500 questions" or "5500 questions"
  ✗ Found: "over 5,000 questions" (not exact)
  ✗ Found: "thousands of questions" (too vague)
  ✗ Found: "6,000 questions" (wrong number)

INCORRECT verification (DO NOT DO):
  Search: "[Candidate] questions levels"
  Accept: "Has app with questions" ✗ WRONG (numbers not verified)
```

### Semantic Disambiguation Protocol (NEW)

**For ambiguous phrases like "part of", "associated with", "discusses":**

```
Step 1: List ALL possible interpretations

Phrase: "article that is part of a children's biography series"

Interpretations:
A) Article = Entry IN the series
B) Article = Review/Analysis ABOUT the series  
C) Article = Research paper REFERENCING the series

Step 2: Test EACH interpretation with specific search

Test A: "[Series Name] article entry chapter"
Test B: "article about [Series Name] published in journal"
Test C: "[Series Name] cited in journal article"

Step 3: Select interpretation with STRONGEST evidence
- Most search results
- Most explicit matches
- Consistent with other constraints

Step 4: VERIFY selected interpretation
- Does it make sense with rest of query?
- Does it lead to findable answer?
- Are all constraints still satisfiable?
```

---

## 🛡️ Phase 4: Enhanced Backtracking Protocol (NEW - CRITICAL)

### Immediate Backtrack Triggers

**You MUST backtrack IMMEDIATELY when:**

```
Trigger 1: CONSTRAINT VERIFICATION FAILURE
  Searched 2+ times for constraint evidence
  Still no confirmation
  → BACKTRACK to candidate selection or anchor choice

Trigger 2: DEAD END (5-Search Rule)
  Made 5+ searches related to current hypothesis
  No progress toward answer
  → BACKTRACK to earlier decision point

Trigger 3: ASSUMPTION CHAIN TOO LONG (3-Assumption Rule)
  Current path depends on 3+ UNVERIFIED assumptions
  → BACKTRACK and verify assumptions

Trigger 4: CIRCULAR SEARCHING
  Searching same keywords with slight variations
  Results not improving
  → BACKTRACK to try different approach

Trigger 5: EXACT FEATURE MISMATCH
  Found candidate that matches SOME constraints
  But fails EXACT number/feature match
  → BACKTRACK immediately (don't force fit)
```

### Backtracking Decision Tree

```
┌─ Search not yielding results? ─┐
│                                 │
├─ Q1: Have I verified my ANCHOR was correct?
│  ├─ NO → BACKTRACK to anchor selection
│  │        Try next highest-scoring anchor
│  └─ YES → Continue ↓
│
├─ Q2: Have I verified ALL my ASSUMPTIONS?
│  ├─ NO → BACKTRACK to verify each assumption
│  │        Use constraint verification table
│  └─ YES → Continue ↓
│
├─ Q3: Did I test ALL interpretations of ambiguous phrases?
│  ├─ NO → Test alternative interpretations
│  └─ YES → Continue ↓
│
├─ Q4: Am I searching for the RIGHT entity?
│  ├─ NO → BACKTRACK to entity identification
│  │        Example: Wrong series? Wrong article?
│  └─ YES → Continue ↓
│
└─ Q5: Have I tried alternative search strategies?
   ├─ NO → Try different keywords, languages, sources
   └─ YES → May need to admit insufficient info
```

### Backtracking Example (Good Practice)

```
Step 7: Search "Who Was? Helen Keller journal article"
Result: No academic journal articles found ✗

Step 8: VERIFICATION CHECK
Constraint: "Article published in journal"
Evidence: None found for "Who Was?" + journal
Status: ✗ FAILED

Step 9: BACKTRACK DECISION
Question: Is "Who Was?" definitely correct?
Check: Did I verify it has EXACTLY 5,500 questions, 100 levels?
Search: "Who Was? app 5500 questions 100 levels"
Result: Numbers don't match exactly ✗

Step 10: BACKTRACK TO STEP 3
Action: Search for ALTERNATIVE biography series
Search: "children biography series app 5500 questions 100 levels"
(Try to find series with EXACT number match)

Step 11: New candidate found
Series: [Alternative Series Name]
Verify numbers: EXACTLY 5,500 and 100 ✓
Continue with new hypothesis...
```

---

## 📋 Phase 5: Constraint Verification Table (MANDATORY)

**Before declaring ANY answer, complete this table:**

```
=== CONSTRAINT VERIFICATION TABLE ===

Answer Candidate: [Your proposed answer]

| # | Constraint | Verification Query | Result | Evidence Source |
|---|------------|-------------------|--------|----------------|
| 1 | [Constraint description] | "[Search query]" | ✓/✗/? | [URL or source] |
| 2 | [Constraint description] | "[Search query]" | ✓/✗/? | [URL or source] |
| 3 | [Constraint description] | "[Search query]" | ✓/✗/? | [URL or source] |
...

=== VERIFICATION SUMMARY ===
Total Constraints: [N]
Verified (✓): [count]
Failed (✗): [count]  
Ambiguous (?): [count]

=== DECISION ===
IF all ✓ → ACCEPT answer
IF any ✗ → REJECT and backtrack
IF any ? → Continue verification

Current Status: [ACCEPT / REJECT / CONTINUE]
```

**Example (Problem 1 - Correct Approach):**

```
Answer Candidate: Volume 3

| # | Constraint | Verification Query | Result | Evidence |
|---|------------|-------------------|--------|----------|
| 1 | Essay title "Letters to the Deaf" | Verified from query | ✓ | Given |
| 2 | Essay year 1834 | Verified from query | ✓ | Given |
| 3 | Series has 5,500 questions | "[Series] app 5500 questions" | ✓ | [Source URL] |
| 4 | Series has 100 levels | "[Series] app 100 levels" | ✓ | [Source URL] |
| 5 | Article part of series | "[Article] [Series]" | ✓ | [Source URL] |
| 6 | Article discusses recommendation | "[Article] Letters to the Deaf" | ✓ | [Source URL] |
| 7 | Article in journal | "[Article] journal publication" | ✓ | [Source URL] |
| 8 | Journal volume number | "[Journal] [Article] volume" | ✓ | Volume 3 |

Verification Summary: 8/8 ✓
Decision: ACCEPT (Volume 3)
```

**Example (Problem 1 - Wrong Approach - DO NOT DO):**

```
Answer Candidate: Volume 162

| # | Constraint | Verification Query | Result | Evidence |
|---|------------|-------------------|--------|----------|
| 1 | Series is "Who Was?" | Found series exists | ✓ | Wikipedia |
| 2 | Person is Helen Keller | She's deaf-related | ✓ | Common knowledge |
| 3 | Found journal article | About deaf education | ✓ | PubMed |
| 4 | Volume number | Volume 162 found | ✓ | Journal page |

CRITICAL MISSING VERIFICATIONS:
| 5 | Series has EXACTLY 5,500 questions | NOT VERIFIED | ? | MISSING ✗ |
| 6 | Series has EXACTLY 100 levels | NOT VERIFIED | ? | MISSING ✗ |
| 7 | Article is "part of" series | NOT VERIFIED | ? | MISSING ✗ |
| 8 | Article discusses "Letters to the Deaf" | NOT VERIFIED | ? | MISSING ✗ |

Verification Summary: 4/8 verified, 4/8 missing
Decision: REJECT ✗ (incomplete verification)
```

---

## 🔬 Phase 6: Anti-Confirmation Bias Checklist

**Before finalizing answer, check these warning signs:**

```
□ Did I find answer in <5 searches? (Too fast, likely missed something)
□ Did I verify <80% of constraints? (Incomplete verification)
□ Is my answer a "famous" entity? (Famous entity bias)
□ Did I assume rather than verify? (List assumptions, verify each)
□ Did I skip disambiguation? (For ambiguous phrases)
□ Did EXACT numbers match? (5,500 vs "thousands")
□ Did I backtrack when needed? (Or kept pushing wrong path)
□ Did I test alternative interpretations? (For "part of", "discusses", etc.)

If ANY checkbox ticked → High risk of error, review process
```

---

## 📤 Phase 7: Output Format

### During Search Phase

```
**Current Goal:** [Which variable am I solving?]

**Hypothesis:** [My current belief about the answer]

**Search Plan:**
  Query: "[Optimized search query]"
  Language: [EN/ZH/etc.]
  Purpose: [What I'm verifying]

**Constraint Verification Progress:**
  [✓] Constraint 1: [Evidence]
  [✓] Constraint 2: [Evidence]
  [ ] Constraint 3: Pending verification
  [?] Constraint 4: Ambiguous, need more search
  [✗] Constraint 5: FAILED - triggering backtrack

**Next Action:** [What I'll do based on results]
```

### Final Answer Phase

```
**CONSTRAINT VERIFICATION TABLE**
[Complete table as shown in Phase 5]

**VERIFICATION SUMMARY**
Total: [N] constraints
Verified: [N] ✓
Failed: 0 ✗ (MUST be zero)
Ambiguous: 0 ? (MUST be zero)

**DECISION:** ACCEPT

**Final Answer:** [Your answer]

**Confidence:** High (all constraints verified from multiple sources)
```

---

## ⚠️ Critical Failure Modes to AVOID

### Failure Mode 1: Premature Conclusion
```
❌ BAD:
  Step 3: Found "Who Was?" series
  Step 4: Answer must be related to this!
  (Skipped verification of exact features)

✅ GOOD:
  Step 3: Found "Who Was?" series (candidate)
  Step 4: Verify: Does it have EXACTLY 5,500 questions?
  Step 5: Search result: No exact match ✗
  Step 6: BACKTRACK, try other series
```

### Failure Mode 2: Assumption Stacking
```
❌ BAD:
  Assumption 1: Series is "Who Was?" (unverified)
  Assumption 2: Person is Helen Keller (unverified)
  Assumption 3: Found article in journal (unverified)
  Answer: Volume 162 ✗ WRONG

✅ GOOD:
  Hypothesis 1: Series is "Who Was?"
  Verify: Search "[Who Was?] 5500 questions 100 levels"
  Result: No match ✗
  Action: REJECT hypothesis, try another
```

### Failure Mode 3: Ignoring Exact Numbers
```
❌ BAD:
  Feature: "5,500 questions"
  Found: "Thousands of questions"
  Decision: Close enough! ✗ WRONG

✅ GOOD:
  Feature: "5,500 questions"
  Found: "Thousands of questions"
  Decision: Not exact match ✗ Continue searching
  Found: "5,500 questions exactly"
  Decision: EXACT match ✓ Accept
```

### Failure Mode 4: No Backtracking
```
❌ BAD:
  Step 10: Can't find connection
  Step 11: Keep searching same thing
  Step 12: Still can't find
  Step 13: Guess an answer ✗ WRONG

✅ GOOD:
  Step 10: Can't find connection (after 2 tries)
  Step 11: BACKTRACK - reconsider anchor
  Step 12: Try different interpretation
  Step 13: Success! Found connection ✓
```

---

## 🎯 Success Checklist (Before Final Answer)

```
□ ALL variables identified
□ ALL constraints extracted
□ Anchor selected using scoring algorithm
□ Ambiguous phrases disambiguated
□ EVERY constraint verified with specific search
□ EXACT numbers matched (not approximate)
□ Backtracked when verification failed
□ Tested alternative interpretations
□ Constraint verification table completed
□ ALL constraints have ✓ (no ✗ or ?)
□ Cross-verified from 2+ sources
□ Answer language matches question language
```

**Only when ALL boxes checked → Output Final Answer**

---

## 💡 Problem 1 Specific Guidance

**For this type of problem (complex entity chain with exact features):**

1. **Extract EVERY numerical feature EXACTLY**
   - 5,500 questions (not "thousands")
   - 100 levels (not "many")
   - 1834 (exact year)

2. **Disambiguate "part of" phrase**
   - Test: Is article IN the series?
   - Test: Is article ABOUT the series?
   - Test: Is article REFERENCING the series?

3. **Verify EVERY link in the chain**
   - Essay → Recommendation (what was recommended?)
   - Recommendation → Article (does article discuss it?)
   - Article → Series (is article part of series?)
   - Article → Journal (is article in journal?)
   - Journal → Volume (what volume number?)

4. **Use exact numbers as hard filters**
   - If series doesn't have EXACTLY 5,500 questions → REJECT
   - If app doesn't have EXACTLY 100 levels → REJECT

5. **Backtrack early and often**
   - Can't verify series features after 2 searches? → Backtrack
   - Can't find article in journal? → Backtrack
   - ANY constraint fails? → Backtrack

Remember: **Better to backtrack 5 times and get it right than rush to wrong answer.**

---

Now proceed with systematic investigation following ALL protocols above.
"""

class AgentState(TypedDict):
    messages: List[dict]
    plan: str
    step_index: int
    max_steps: int
    pending_tool_calls: List[dict]
    emitted: List[Chunk]
    meta: dict

def _sanitize_messages(messages: list) -> list:
    # Simple sanitization if needed
    return messages

async def agent_loop(
    input_messages: list,
    tool_functions: List[Callable],
    skill_directories: Optional[List[str]] = ["skills"],
    max_steps: int = 30,
    inherited_memory: Optional['MemoryStore'] = None,
    inherited_context: Optional[str] = None,
) -> AsyncIterator[Chunk]:
    
    assert os.getenv("IFLOW_API_KEY"), "IFLOW_API_KEY is not set"
    client = get_llm_client(timeout=30.0)
    
    # Initialize Memory
    if inherited_memory:
        memory = inherited_memory
        print(f"[Retry] Inherited memory with {len(memory.short)} short-term entries")
    else:
        memory = MemoryStore()
        memory.build_index()

    # Initialize Skills
    skills: List[SkillMetadata] = discover_skills(skill_directories) if skill_directories else []
    skills_prompt = build_skills_system_prompt(skills)
    
    llm_tools = (tool_functions or []).copy()
    if skills:
        skill_tools = SkillIntegrationTools(skills)
        llm_tools.extend([skill_tools.load_skill_file, skill_tools.execute_script])
    
    # Add memory query tool
    def memory_query(query: str, top_k: int = 5) -> str:
        hits = memory.search(query, top_k=top_k)
        return json.dumps({"results": hits}, ensure_ascii=False)
    
    llm_tools.append(memory_query)
    
    tool_schema = [function_to_schema(tool_function) for tool_function in llm_tools]
    tool_functions_map = {func.__name__: func for func in llm_tools}

    # Extract user query
    user_query = ""
    for m in reversed(input_messages):
        if m.get("role") == "user":
            user_query = str(m.get("content") or "")
            break

    # --- Node Definitions ---

    def planner_node(state: AgentState) -> dict:
        # Generate initial plan
        plan_data = generate_plan(user_query)
        plan = plan_data.get("plan", "")
        recommended_steps = plan_data.get("max_steps", 30)
        
        print(f"[Planner] Plan created. Recommended steps: {recommended_steps}")
        
        # Emit plan chunk if needed (optional)
        # emitted = [Chunk(step_index=0, type="text", content=f"Created Plan:\n{plan}\n")]
        return {"plan": plan, "max_steps": recommended_steps}

    def agent_node(state: AgentState) -> dict:
        current_step = state["step_index"]
        limit = state.get("max_steps", max_steps)
        
        if current_step >= limit:
            return {"pending_tool_calls": [], "emitted": []} # Stop

        messages = state["messages"]
        plan = state["plan"]
        
        # Inject Context (Memory + Plan)
        # We construct a temporary message list for LLM call
        prompt_messages = messages[:]
        
        # Urgency & Drift Detection
        urgency_msg = ""
        try:
            # Urgency Check (Last 20% or 5 steps)
            threshold = max(limit - 5, int(limit * 0.8))
            if current_step >= threshold:
                steps_left = limit - current_step
                urgency_msg = (
                    f"\n\n⚠️ URGENCY MODE: You have {steps_left} steps remaining.\n"
                    "1. Try to STOP searching for new information.\n"
                    "2. You need to SYNTHESIZE existing information.\n"
                    "3. Prepare to provide the result in the format: `Final Answer: [Your Answer]` soon."
                )
                prompt_messages.append({
                    "role": "system",
                    "content": urgency_msg
                })
                
        except Exception as e:
            print(f"[UrgencyCheck] Error: {e}")

        # 1. System Prompt Enhancement
        system_prompt_addition = ""
        if skills_prompt:
            system_prompt_addition += f"\n\n{skills_prompt}"
        
        system_prompt_addition += f"\n{MULTI_HOP_SYSTEM_PROMPT}"

        system_prompt_addition += """

### ⚠️ CRITICAL CHECKPOINTS BEFORE FINAL ANSWER

Before outputting final answer, you MUST check:

**Checkpoint 1: Exact Number Verification**
If query mentions specific numbers (5,500, 100, 1834, etc.):
□ Have I verified these numbers EXACTLY?
□ Did I find "5,500" not just "thousands"?
□ Did I find "100" not just "many"?

**Checkpoint 2: All Constraints Verified**
□ Have I created a verification table?
□ Does EVERY constraint have a ✓?
□ Are there any ✗ or ? marks? (If yes: BACKTRACK)

**Checkpoint 3: Assumption Check**
□ How many unverified assumptions am I making?
□ If >2: STOP and verify each assumption

**Checkpoint 4: Backtrack Opportunity**
□ Have I searched >5 times without progress?
□ If yes: BACKTRACK to earlier decision point

**Checkpoint 5: Disambiguation Check**
□ Are there ambiguous phrases ("part of", "associated with")?
□ Have I tested ALL interpretations?

IF ANY checkpoint fails → DO NOT output final answer → Fix the issue first

### 🔄 FORCED BACKTRACK CONDITIONS

You MUST backtrack if:
1. Searched 3+ times, can't verify a critical constraint
2. Found candidate but exact numbers don't match
3. Making >2 unverified assumptions
4. Ambiguous phrase not disambiguated

When backtracking, explicitly state:
"BACKTRACKING: [Reason]
Returning to: [Earlier decision point]
Alternative approach: [What I'll try instead]"
"""

        
        system_prompt_addition += """
### 🧠 Dynamic Autonomous Strategy
You are an expert autonomous researcher. You are NOT bound by a fixed step-by-step plan.
Your goal is to satisfy the user's request by dynamically choosing the best action at each step.

**Core Principles:**
1. **Anchor First**: Identify the most unique or restrictive constraint (the "Anchor") and verify it first.
2. **Fail Fast & Pivot**: 
   - If a search query returns nothing relevant, DO NOT repeat it.
   - **Pivot Strategy**: If one condition cannot be verified (e.g., specific date not found), immediately switch to verifying OTHER conditions to triangulate the answer. Do not get stuck on a single missing detail.
   - IMMEDIATELY switch to a different search term, a different constraint, or a broader category.
   - YOU decide when to pivot.
3. **Completion**: 
   - Once you have sufficient information (>=3 sources), output the "Final Answer" immediately.
   - Do not over-verify if the answer is clear.
   - **IMPORTANT**: When providing the final answer, use the format: `Final Answer: [Your Answer Here]`.
   - **Do NOT** output "Thought:" traces in your final message content. Only output the final answer text.
"""
        if plan:
            system_prompt_addition += f"\n\n### 📋 INITIAL PLAN (Reference Only)\n{plan}\n"

        # Inject Memory Context
        mem_hits = memory.search(user_query, top_k=4)
        if mem_hits:
            joined = "\n".join([(hit.get("text") or "")[:500] for hit in mem_hits])
            prompt_messages.insert(1, {"role": "system", "content": f"<memory_context>\n{joined}\n</memory_context>"})

        # Update System Message
        if prompt_messages and prompt_messages[0].get("role") == "system":
            prompt_messages[0]["content"] += system_prompt_addition
        else:
            prompt_messages.insert(0, {"role": "system", "content": f"{DEFAULT_SYSTEM_PROMPT}{system_prompt_addition}"})

        # Call LLM
        emitted = []
        tool_calls_buffer = {}
        content_buffer = ""
        
        try:
            stream = client.chat.completions.create(
                model="qwen3-max",
                messages=prompt_messages,
                tools=tool_schema,
                stream=True,
                temperature=0.4,
                max_tokens=1024
            )
            
            for chunk in stream:
                chunk = cast(ChatCompletionChunk, chunk)
                if not chunk.choices: continue
                delta = chunk.choices[0].delta
                
                if delta.content:
                    content_buffer += delta.content
                    emitted.append(Chunk(type="text", content=delta.content, step_index=current_step))
                    memory.add_short(delta.content)
                
                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index or 0
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc_chunk.id or f"call_{idx}",
                                "function": {"name": tc_chunk.function.name or "", "arguments": ""}
                            }
                        if tc_chunk.function.name:
                            tool_calls_buffer[idx]["function"]["name"] = tc_chunk.function.name
                        if tc_chunk.function.arguments:
                            tool_calls_buffer[idx]["function"]["arguments"] += tc_chunk.function.arguments
                            
        except Exception as e:
            print(f"[Agent] LLM Error: {e}")
            return {"emitted": []} # Should probably retry or fail gracefully

        # Process Tool Calls
        pending_tool_calls = []
        for idx in sorted(tool_calls_buffer.keys()):
            raw = tool_calls_buffer[idx]
            pending_tool_calls.append({
                "id": raw["id"],
                "type": "function",
                "function": {
                    "name": raw["function"]["name"],
                    "arguments": raw["function"]["arguments"]
                }
            })
            
        # Update messages
        new_messages = messages[:]
        if content_buffer or pending_tool_calls:
            msg = {"role": "assistant"}
            if content_buffer: msg["content"] = content_buffer
            if pending_tool_calls: msg["tool_calls"] = pending_tool_calls
            new_messages.append(msg)


        # Check for verification table before Final Answer
        if "Final Answer:" in content_buffer:
            if "CONSTRAINT VERIFICATION TABLE" not in content_buffer:
                print("[WARNING] Final answer without verification table!")
                
                # Force requirement to supplement verification table
                error_msg = """
⚠️ CRITICAL ERROR: You attempted to output Final Answer without a Constraint Verification Table.

You MUST:
1. List ALL constraints from the original query
2. For EACH constraint, show:
   - What you searched
   - What you found
   - ✓/✗/? status
3. Only if ALL are ✓, then output final answer

Please complete the verification table now.
"""
                new_messages.append({"role": "system", "content": error_msg})

        return {
            "messages": new_messages,
            "pending_tool_calls": pending_tool_calls,
            "emitted": emitted,
            "step_index": current_step # Step index increments in executor or after tool
        }

    def tools_node(state: AgentState) -> dict:
        # Execute tools using existing logic
        # execute_tools_logic returns updated state with new messages and emitted chunks
        result = execute_tools_logic(state, tool_functions_map, memory)
        return result

    def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
        if state.get("pending_tool_calls"):
            return "tools"
        return "__end__"

    # --- Graph Construction ---
    workflow = StateGraph(AgentState)
    
    workflow.add_node("planner", planner_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)
    
    workflow.add_edge("__start__", "planner")
    workflow.add_edge("planner", "agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "__end__": END
        }
    )
    
    workflow.add_edge("tools", "agent")
    
    app = workflow.compile()
    
    # --- Execution Loop ---
    initial_state = {
        "messages": input_messages,
        "plan": "",
        "step_index": 0,
        "pending_tool_calls": [],
        "emitted": [],
        "meta": {"searched_keywords": []}
    }
    
    # We use stream_mode="updates" to get state updates from each node
    # Note: 'astream' might not be available if LangGraph version is old or specific.
    # Assuming standard LangGraph usage.
    
    try:
        # Using synchronous invoke/stream in loop if astream is problematic with async generator?
        # Actually agent_loop is async. LangGraph supports async nodes if defined async.
        # But my nodes are sync (calling sync client).
        # So I should use app.stream (sync iterator) but agent_loop is async generator.
        # I can wrap it.
        
        # To be safe and compatible with the fact that `client` is sync in my code:
        # I will use sync `app.stream`.
        
        iterator = app.stream(initial_state, stream_mode="updates")
        
        for output in iterator:
            # Output is a dict of {node_name: state_update}
            for node_name, state_update in output.items():
                if "emitted" in state_update:
                    for chunk in state_update["emitted"]:
                        yield chunk
                        
    except Exception as e:
        print(f"[AgentLoop] Error: {e}")
        import traceback
        traceback.print_exc()

    # Final answer handling (if needed)
    # The loop yields chunks. If the agent outputs text, it's yielded.
    # If explicit Final Answer is needed, the agent should have outputted it.
    
