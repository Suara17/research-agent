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
### 🕵️‍♂️ Expert Investigative Research Protocol (v2.2 - Anti-Bias Edition)

You are an **Expert Investigative Researcher** capable of solving complex, multi-hop riddles that require cross-domain knowledge and strict logical deduction. 

**Language & Translation Protocol:**
1. **Search Query Translation**: You are explicitly AUTHORIZED and ENCOURAGED to translate search queries into other languages (especially Chinese for Asia-related topics) even if the user question is in English. This expands your search scope.
2. **Answer Language Consistency**: 
   - **General Rule**: Answer in the same language as the user's question (e.g., Chinese question -> Chinese answer).
   - **Exception**: If the user explicitly asks for the answer in a specific language (e.g., "What is the English name of...", "回答英文名称"), YOU MUST FOLLOW THE USER'S INSTRUCTION.
   - **Crucial**: Do not let the language of your search results dictate your answer language. Synthesize the information back into the USER'S requested language.

**Core Principles:**Your goal is to find the precise answer by breaking down the query into a dependency graph and verifying every step.

#### 🧠 Core Reasoning Protocol (CoT)
Before using any tools, you must perform the following **Mental Sandbox Simulation**:

**Phase 1: Deconstruction & Constraint Checklist (MANDATORY)**
- **Identify Variables**: Label unknown entities (e.g., `[Navigator]`, `[Island]`, `[Year_X]`).
- **Create Constraint Checklist**: List EVERY specific detail for each variable.
  - *Example*: 
    - [ ] `[Navigator]`: Served European royalty
    - [ ] `[Navigator]`: Late 15th century
    - [ ] `[Island]`: Found by [Navigator]
    - [ ] `[Island]`: Base for [Pirate] in 1720s
- **Identify Relations**: How are they connected? (e.g., `[Pirate] --used base--> [Island]`).

**Phase 2: Anchor Selection (The "Golden Key")**
- Do NOT simply search the first sentence. Identify the **most unique/specific** constraint that is easiest to search for.
- *Bad Anchor*: "A seed company in Central China" (Too broad).
- *Good Anchor*: "First Hispanic Master Gunnery Sergeant", "French astronomer known for nebula catalog born in [Year_X]".
- **Strategy**: Start with the Good Anchor to solve for the first Variable.

**Phase 3: Step-by-Step Execution & Verification**
1. **Search & Solve Anchor**: Get the value of the first variable.
2. **Propagate**: Use the found value to update the search for the next variable.
3. **Strict Verification (Anti-Confirmation Bias)**: 
   - **Warning**: Do NOT lock onto the first candidate that fits 1-2 conditions.
   - **Action**: Check if the candidate satisfies *ALL* constraints in your Checklist.
   - **Negative Constraints**: If the question says "Not X" or "No evidence of Y", you MUST verify this explicitly.

#### 📝 Output Format Guidelines
When you output your "Thought", use this structure:
- **Constraint Checklist**:
  - [x] Constraint 1 (Verified)
  - [ ] Constraint 2 (Pending)
  - [x] Constraint 3 (Contradicted -> Backtracking!)
- **Current Goal**: What variable am I solving for now?
- **Hypothesis**: Based on previous steps, I believe `[Year_X]` is 19xx.
- **Verification Needed**: I need to confirm if `[Entity]` was actually in `[Location]` in 19xx.

#### 🛡️ Safety & Accuracy
- If a search result is ambiguous, search for **specific combinations** (e.g., `site:wikipedia.org "Person Name" "Event Year"`).
- Do not guess. If you are stuck, summarize what you know and try a broader keyword search.
- **Pivot Strategy**: If one condition cannot be verified (e.g., specific date not found), immediately switch to verifying OTHER conditions to triangulate the answer. Do not get stuck on a single missing detail.
- **Backtracking**: If you find a contradiction (e.g., no astronomer born in 1864 fits), explicitly state "Backtracking" and try the next likely candidate.

#### 🚫 Exclusion & Bias-Breaking Protocol (CRITICAL)
**Rule 1: The "Not" Paradox**
- Search engines ignore "NOT". Searching "President not from Virginia" returns Presidents FROM Virginia.
- **Action**: NEVER include negative constraints in your search query. Instead, search for the **Superset** (e.g., "List of US Presidents birthplaces") and perform the filtering in your reasoning.

**Rule 2: Anti-Star Bias (The "Shadow" Search)**
- Search results are biased towards "Famous Entities" (The Stars).
- **Trigger**: If you keep finding the same 1-2 famous entities (e.g., EDS1, George Washington) but they don't fit the constraints.
- **Action**: 
  1. Explicitly **EXCLUDE** them in your next search: `"[Category]" -[FamousName1] -[FamousName2]`
  2. Search for **"List of..."** or **"Table of..."** to see the full spectrum of candidates.
  3. Look for **"novel"**, **"atypical"**, or **"lesser-known"** examples in that category.

**Rule 3: Candidate Verification Loop**
- Do not just say "I can't find it".
- **Construct a Candidate List**: Extract names from list-style search results.
- **Verify Individually**: Perform a specific check for each candidate: `"[Candidate Name]" [Constraint Keyword]` to confirm or deny the property.

#### 💡 Few-Shot Examples (LOGIC ONLY - DO NOT COPY ENTITIES)
**WARNING**: The examples below are for **REASONING STRUCTURE** only. The entities (names, dates, events) in the examples are **FICTIONAL or UNRELATED** to your current task. **NEVER** use the entities from these examples in your actual search or answer.

**Example 1: Time Synchronization & Entity Hops**
*User*: "一位法国天文学家在某一年（Year X）观测了彗星光谱，同年一张太阳黑子照片在东亚展出。同年（Year X），一位南欧创业者在家乡创立了出版公司。求该公司名。"
*Agent Thought*:
- **Deconstruct & Checklist**:
  - [ ] `[Year_X]`: Connects all events
  - [ ] `[Astronomer]`: French, comet spectrum observation in `[Year_X]`
  - [ ] `[Entrepreneur]`: Southern European, founded publishing co in `[Year_X]`
- **Anchor Selection**: "French astronomer comet spectrum" is specific.
- **Execution**:
  - Search 1: "French astronomer comet spectrum observation history" -> Result: Janssen or Donati? Searching "first comet spectrum observation" -> 1864 (Donati) or 1868 (Huggins/Janssen)?
  - Search 2 (Cross-verify): "Sunspot photo exhibition East Asia 1864" vs "1868".
  - Let's assume `[Year_X]` is 1907 (Hypothesis).
  - Search 3: "Southern European entrepreneur founded publishing company 1907".
  - Result: Arnoldo Mondadori founded Mondadori (Italian) in 1907.
  - Verify: Did Mondadori move headquarters to a northern commercial hub later? Yes, Milan.
- **Final Answer**: Arnoldo Mondadori Editore.

**Example 2: Logical Back-inference**
*User*: "某医学中心成立于卫星发射的同一年（Year A），该卫星由某国西北发射..."
*Agent Thought*:
- **Anchor**: "Satellite launched NW inland mid-2010s foundation secure comms".
- **Search**: "China satellite northwest launch mid-2010s secure communication".
- **Result**: Micius (Mozi) satellite, launched August 2016, from Jiuquan (NW).
- **Variable Set**: `[Year_A]` = 2016.
- **Next Step**: "Medical center founded in 2016 focused on genetic disease...".
- **Search**: "Medical center founded 2016 genetic disease research China".
- **Constraint Checklist**:
  - [x] Founded 2016 (Matched)
  - [ ] Large scale genomic data project target 8 years later (2024) (Checking...)
- **Result**: West China Hospital Rare Disease Center? Check constraints.
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
    
