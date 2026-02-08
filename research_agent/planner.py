import json
from .utils import get_llm_client

def generate_plan(user_query: str) -> dict:
    """
    Generates a research plan and estimates task complexity.
    Returns a dict with 'plan' (str) and 'max_steps' (int).
    """
    if len(user_query) <= 5:
        return {"plan": "", "max_steps": 20}
        
    system_prompt = """You are a strategic planner. 
Your goal is to analyze the user's request and create a execution plan.

1. **Analyze Complexity**:
   - **Simple**: Direct fact lookup, single entity, or simple definition. (Recommend 20 steps)
   - **Complex**: Multi-hop reasoning, comparing multiple entities, obscure details, or cross-referencing required. (Recommend 30 steps)

2. **Create Plan (Dependency Graph Approach)**:
   - **Identify Variables**: Label unknown entities (e.g., [Year_X], [Person_A]).
   - **Select Anchor**: Choose the most unique constraint to solve first.
   - **Sequence**: Ensure dependencies are respected (e.g., "Find Year_X first, then use Year_X to find Person_A").

3. **The "List & Filter" Strategy (For Negative/Rare Constraints)**:
   - **Trigger**: When the query asks for an entity that is [Category] but does **NOT** have [Feature X], or implies a "rare/specific" case.
   - **Bad Plan**: "Search for [Category] not having [Feature X]." (Will fail).
   - **Mandatory Plan**: 
     1. **Enumerate**: Search for a comprehensive "List of [Category]" or "Table of [Category]".
     2. **Select Candidates**: Identify 3-5 potential candidates (avoiding just the most famous ones).
     3. **Verify**: Check each candidate individually: "Does [Candidate A] have [Feature X]?"
     4. **Conclude**: Select the one where the check is FALSE.

Output a JSON object with the following keys:
- "reasoning": Brief explanation of complexity analysis and variable mapping.
- "complexity": "simple" or "complex".
- "max_steps": 20 or 30.
- "plan": The step-by-step plan string (e.g., "1. Solve [Year_X] by searching '...'. 2. Use [Year_X] to search for [Person_A]...").
"""
    
    client = get_llm_client()
    try:
        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Task: {user_query}"}
            ],
            temperature=0.5,
            max_tokens=512,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        try:
            data = json.loads(content)
            return {
                "plan": data.get("plan", ""),
                "max_steps": data.get("max_steps", 30)
            }
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {"plan": content, "max_steps": 30}
            
    except Exception as e:
        print(f"[Planner] Failed to generate plan: {e}")
        return {"plan": "", "max_steps": 30}
