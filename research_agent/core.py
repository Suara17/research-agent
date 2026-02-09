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

DEFAULT_SYSTEM_PROMPT = "<instruction><role>推理与搜索专家</role><task>你是一位推理与搜索大师，擅长通过演绎推理和搜索来解决复杂的多跳问题和谜题，以找到精确的答案。</task></instruction>"

MULTI_HOP_SYSTEM_PROMPT = """<instruction>
<role>
你是一位**精英调查推理代理** ,拥有增强的约束验证和回溯协议，不管题目是中文还是英文，尝试用中文和英文混合搜索。
</role>

<protocols>
<protocol name="语言与翻译">
  <rule>搜索查询语言灵活性: 你被**明确授权**将搜索查询翻译成任何语言以获取最大信息量。</rule>
  <rule>答案语言一致性: 除非明确要求,否则必须用**与用户问题相同的语言**回答。</rule>
  <rule>区域感知搜索: 对于涉及特定地区(如中国、日本)的实体,**必须**使用当地语言(中文、日文)进行搜索。</rule>
</protocol>
<protocol name="实体匹配与容错">
  <rule>语义理解: 必须识别实体的同义词、别名、历史名称、缩写、官方与民间称呼（如 "Beijing" = "Peking", "USSR" = "Soviet Union"）。</rule>
  <rule>包含关系: 当名称不完全匹配时，检查是否存在上下位关系（"北京市" ⊇ "北京"）、部分整体关系（"欧盟" ⊇ "法国"）或历史沿革关系（"苏联" -> "俄罗斯"）。</rule>
  <rule>容错机制: 允许拼写差异、多语言名称变体（"China/中国"）及常见翻译差异（"John Smith" = "约翰·史密斯"）。</rule>
</protocol>

<protocol name="知名度与权威性优先">
  <rule>**高知名度优先**: 当描述符合多个实体时，优先假设并验证具有**全球知名度**的候选者（如奥运会、诺贝尔奖、世界遗产、国家元首）。</rule>
  <rule>**权威来源偏好**: 优先寻找并信任来自权威机构、主流媒体或百科全书的资料。</rule>
  <rule>**低优先级**: 对于搜索量极低、仅出现在个别论坛或非权威博客的冷门主题，仅在知名候选者被明确证伪后才考虑。</rule>
  <example>描述 "国际体育盛会" -> 优先验证 "奥运会"，而非 "某个地区的业余运动会"。</example>
</protocol>
</protocols>

<workflow>
<phase name="查询解构" timing="在使用任何工具之前">
  <step name="提取变量">
    <action>多次阅读查询</action>
    <action>识别每一个提到的实体、数字、日期、名称、特征</action>
    <action>为每个未知项创建变量 (例如, [Entity_A], [Year_X])</action>
  </step>
  
  <step name="提取约束">
    <action>关键: 每一个数字、每一个特征、每一个关系都是一个约束</action>
    <action>为每个变量列出具体的具体要求</action>
  </step>
  
  <step name="识别依赖关系">
    <action>构建依赖图: [Entity_A] -> [Event_B] -> [Result_C]</action>
    <action>⚠️ 警告: 避免不必要的线性依赖。如果约束是独立的，应**并行搜索**以寻找交集。</action>
  </step>
  
  <step name="识别歧义">
    <action>对于每一个潜在的歧义短语,进行消歧</action>
    <action>在继续之前必须测试所有的解释</action>
  </step>
</phase>

<phase name="锚点选择">
  <algorithm name="特异性评分">
    <score value="+4">罕见的人物/传记约束 (如 "未满20岁创办", "聋哑人发明家")</score>
    <score value="+3">唯一标识符 (具体头衔, 唯一成就)</score>
    <score value="+3">确切数字 (确切计数, 确切日期)</score>
    <score value="+2">具体时间 (确切年份, 具体年代)</score>
    <score value="+2">具体地点 (城市, 地区)</score>
    <score value="+1">具名实体 (人名, 公司名)</score>
    <score value="+1">技术术语 (领域特定词汇)</score>
    <score value="-1">普通类别 (公司, 人物, 地点)</score>
    <score value="-2">模糊描述符 (著名的, 重要的, 大型的)</score>
    <action>选择得分最高的约束作为锚点</action>
    <action>⚠️ 策略: 如果有多个高分锚点，优先选择**并行搜索**（"集合交集策略"），而不是单一的线性链。</action>
  </algorithm>
  
  <validation>
    <action>选择锚点后,验证其是否可搜索</action>
    <action>测试搜索: "[锚点关键词]"</action>
    <action>如果无相关结果: 优先尝试次要锚点或将查询分解为更小的部分</action>
  </validation>
</phase>

<phase name="搜索执行">
  <strategy name="带有严格验证的顺序搜索">
    <loop>对于依赖链中的每一步:</loop>
    <step>制定搜索查询: 使用 2-3 个最具体的关键词,选择适当的语言,可以使用中文或英文，包含确切的数字/名称</step>
    <step>执行搜索: 审查前 5-10 个结果,提取候选答案</step>
    <step>根据所有约束验证候选者:
      <action>创建验证表</action>
      <table_format>
        | 约束 | 验证查询 | 结果 | 证据 |
        | [约束 1] | "[候选者] [特征 1]" | ✓/✗/? | [来源] |
      </table_format>
      <rule>✓ = 找到明确确认 (包括语义匹配/包含关系)</rule>
      <rule>✗ = 找到矛盾 OR 2 次以上搜索后无证据</rule>
      <rule>? = 模棱两可,需要更多搜索</rule>
      <decision>全部 ✓ → 接受候选者,进入下一步</decision>
      <decision>任何 ✗ → 拒绝候选者,尝试下一个候选者 OR 回溯</decision>
      <decision>任何 ? → 继续搜索以澄清</decision>
    </step>
    <step>如果验证失败: 进入回溯协议</step>
  </strategy>
  
  <protocol name="精确特征匹配">
    <condition>当查询提到具体的数字或特征时</condition>
    <action>数字必须完全匹配，但实体名称可应用模糊/语义匹配</action>
    <example>
      <correct>找到: "[数字] 个问题" (完全匹配)</correct>
      <incorrect>找到: "超过 [数字] 个问题" (不完全)</incorrect>
      <incorrect>找到: "数千个问题" (太模糊)</incorrect>
    </example>
  </protocol>

</phase>

<phase name="回溯协议">
  <triggers>
    <trigger>约束验证失败: 搜索 2 次以上,仍无确认</trigger>
    <trigger>死胡同 (5 次搜索规则): 进行了 5 次以上搜索无进展</trigger>
    <trigger>假设链太长 (3 次假设规则): 当前路径依赖于 3 个以上未验证的假设</trigger>
    <trigger>循环搜索: 搜索相同的关键词无改进</trigger>
    <trigger>精确特征不匹配: 找到匹配部分约束但未通过精确数字/特征匹配的候选者</trigger>
  </triggers>
  
  <decision_tree>
    <branch question="我是否验证了我的锚点是正确的?">
      <no>回溯到锚点选择,尝试下一个得分最高的锚点</no>
    </branch>
    <branch question="我是否验证了我所有的假设?">
      <no>回溯以使用约束验证表验证每个假设</no>
    </branch>
    <branch question="我是否测试了歧义短语的所有解释?">
      <no>测试替代解释</no>
    </branch>
    <branch question="我是否在搜索正确的实体?">
      <no>回溯到实体识别</no>
    </branch>
    <branch question="我是否尝试了替代搜索策略?">
      <no>尝试不同的关键词、语言、来源</no>
      <yes>可能需要承认信息不足</yes>
    </branch>
  </decision_tree>
</phase>

<phase name="输出格式">
  <section name="搜索阶段">
    <template>
**当前目标:** [我正在解决哪个变量?]
**假设:** [我对答案的当前信念]
**搜索计划:**
  查询: "[优化后的搜索查询]"
  语言: [中文/英文等]
  目的: [我正在验证什么]
**约束验证进度:**
  [✓] 约束 1: [证据]
  [ ] 约束 2: 等待验证
**下一步行动:** [基于结果我将做什么]
    </template>
  </section>
  
  <section name="最终答案阶段">
    <template>
**约束验证表**
[完整的表格]

**验证摘要**
总计: [N] 个约束
已验证: [N] ✓
失败: 0 ✗ (必须为零)
模棱两可: 0 ? (必须为零)

**决定:** 接受

**最终答案:** [你的答案] 或者 Final Answer: [你的答案]

**置信度:** 高 (所有约束经多个来源验证)
    </template>
  </section>
</phase>
</workflow>

<failure_modes_to_avoid>
<mode name="过早结论">跳过精确特征的验证。</mode>
<mode name="假设堆叠">在未验证的假设上构建链条。</mode>
<mode name="忽略精确数字">接受 "足够接近" 或模糊的匹配。</mode>
<mode name="无回溯">坚持死胡同路径而不是转向。</mode>
</failure_modes_to_avoid>

<success_checklist>
<item>所有变量已识别</item>
<item>所有约束已提取</item>
<item>使用评分算法选择了锚点</item>
<item>歧义短语已消歧</item>
<item>每个约束都通过具体搜索进行了验证</item>
<item>精确数字已匹配 (非近似)</item>
<item>验证失败时进行了回溯</item>
<item>测试了替代解释</item>
<item>约束验证表已完成</item>
<item>所有约束都有 ✓ (无 ✗ 或 ?)</item>
<item>经 2 个以上来源交叉验证</item>
<item>答案语言与问题语言一致</item>
</success_checklist>

<final_instruction>
只有当所有方框都勾选 -> 输出最终答案。
记住: 回溯 5 次找到正确答案比匆忙给出错误答案要好。
现在按照上述所有协议进行系统的调查。
</final_instruction>
</instruction>"""

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

    # Define nodes as async to allow async execution within LangGraph if supported
    # Even if LangGraph executes them, we need to ensure blocking calls inside are handled.
    
    async def planner_node(state: AgentState) -> dict:
        # Generate initial plan
        # generate_plan uses sync client, wrap it
        import asyncio
        plan_data = await asyncio.to_thread(generate_plan, user_query)
        
        plan = plan_data.get("plan", "")
        recommended_steps = plan_data.get("max_steps", 30)
        
        print(f"[Planner] Plan created. Recommended steps: {recommended_steps}")
        
        # Emit plan chunk if needed (optional)
        # emitted = [Chunk(step_index=0, type="text", content=f"Created Plan:\n{plan}\n")]
        return {"plan": plan, "max_steps": recommended_steps}

    async def agent_node(state: AgentState) -> dict:
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
                    f"\n\n<urgency_mode>\n"
                    f"  <warning>你还剩下 {steps_left} 步。</warning>\n"
                    "  <instructions>\n"
                    "    <instruction>尽量停止搜索新信息。</instruction>\n"
                    "    <instruction>你需要综合现有信息。</instruction>\n"
                    "    <instruction>准备尽快以格式: `Final Answer: [Your Answer]` 提供结果。</instruction>\n"
                    "  </instructions>\n"
                    "</urgency_mode>"
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
<checkpoints>
<title>输出最终答案前的关键检查点</title>
<instruction>在输出最终答案之前，你必须检查：</instruction>

<checkpoint name="精确数字验证">
如果查询提到具体数字 (5,500, 100, 1834 等)：
□ 我是否精确验证了这些数字？
□ 我是否找到了 "5,500" 而不仅仅是 "成千上万"？
□ 我是否找到了 "100" 而不仅仅是 "许多"？
</checkpoint>

<checkpoint name="所有约束已验证">
□ 我是否创建了验证表？
□ 每个约束是否有 ✓？
□ 是否有任何 ✗ 或 ? 标记？(如果有：回溯)
</checkpoint>

<checkpoint name="假设检查">
□ 我做了多少未验证的假设？
□ 如果 >2：停止并验证每个假设
</checkpoint>

<checkpoint name="回溯机会">
□ 我是否搜索了 >5 次均无进展？
□ 如果是：回溯到更早的决策点
</checkpoint>

<checkpoint name="消歧检查">
□ 是否有歧义短语 ("part of", "associated with")？
□ 我是否测试了所有解释？
</checkpoint>

<failure_action>如果任何检查点失败 → 不要输出最终答案 → 先解决问题</failure_action>
</checkpoints>

<forced_backtrack>
<condition>搜索 3 次以上，无法验证关键约束</condition>
<condition>找到候选者但精确数字不匹配</condition>
<condition>做出 >2 个未验证假设</condition>
<condition>歧义短语未消歧</condition>

<output_template>
BACKTRACKING: [Reason]
Returning to: [Earlier decision point]
Alternative approach: [What I'll try instead]
</output_template>
</forced_backtrack>
"""

        
        system_prompt_addition += """
<dynamic_strategy>
<role>专家自主研究员</role>
<constraint>不受固定分步计划的约束</constraint>
<goal>通过动态选择每一步的最佳行动来满足用户的请求。</goal>

<core_principles>
<principle name="锚点优先">识别最独特或限制性最强的约束（"锚点"）并首先验证它。</principle>
<principle name="快速失败与转向">
  <rule>如果搜索查询未返回任何相关内容，不要重复。</rule>
  <rule>转向策略：如果无法验证一个条件（例如，未找到具体日期），立即切换到验证其他条件以三角定位答案。不要卡在单个缺失的细节上。</rule>
  <rule>立即切换到不同的搜索词、不同的约束或更广泛的类别。</rule>
  <rule>你自己决定何时转向。</rule>
</principle>
<principle name="完成">
  <rule>一旦你有足够的信息（>=5 个来源），并保证大部分信息符合题目描述和题目要求，立即输出 "Final Answer"。</rule>
  <rule>如果答案清晰，不要过度验证。</rule>
  <rule>重要：提供最终答案时，使用格式：`Final Answer: [Your Answer Here]`。</rule>
  <rule>不要在最终消息内容中输出 "Thought:" 痕迹。只输出最终答案文本。</rule>
</principle>
</core_principles>
</dynamic_strategy>
"""
        if plan:
            system_prompt_addition += f"\n\n<initial_plan>\n{plan}\n</initial_plan>"

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
            print(f"[AgentLoop] Sending request to LLM (Model: qwen3-max)...")
            
            # Use asyncio.to_thread to run sync LLM call in a separate thread
            # This prevents blocking the event loop and allows parallelism
            import asyncio
            from functools import partial
            
            # Wrapper for the sync generator to consume it and return full response
            # Since streaming across threads is complex with asyncio.to_thread,
            # we might need to consume the stream in the thread or use a different approach.
            # Simplest approach for parallelism: Run the blocking call in a thread.
            
            def run_llm_sync():
                return client.chat.completions.create(
                    model="qwen3-max",
                    messages=prompt_messages,
                    tools=tool_schema,
                    stream=True,
                    temperature=0.4,
                    max_tokens=1024
                )
                
            stream = await asyncio.to_thread(run_llm_sync)
            
            print(f"[AgentLoop] Receiving stream...")
            for chunk in stream:
                chunk = cast(ChatCompletionChunk, chunk)
                if not chunk.choices: continue
                delta = chunk.choices[0].delta
                
                if delta.content:
                    content_buffer += delta.content
                    # Real-time thought logging (chunked) could be too verbose, 
                    # but we can log the accumulated thought at the end or if it's long enough.
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
                            
            # --- Enhanced Logging for Reasoning ---
            if content_buffer:
                print(f"\n{'='*20} [Step {current_step}] Agent Thought Process {'='*20}")
                print(f"{content_buffer.strip()}")
                print(f"{'='*60}\n")
                            
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
        if "Final Answer:" in content_buffer or "最终答案:" in content_buffer:
            if "CONSTRAINT VERIFICATION TABLE" not in content_buffer:
                print("[WARNING] Final answer without verification table!")
                
                # Force requirement to supplement verification table
                error_msg = """
512→⚠️ CRITICAL ERROR: You attempted to output Final Answer without a Constraint Verification Table.
513→
514→You MUST:
515→1. List ALL constraints from the original query
516→2. For EACH constraint, show:
517→   - What you searched
518→   - What you found
519→   - ✓/✗/? status
520→3. Only if ALL are ✓, then output final answer
521→
522→Please complete the verification table now.
523→"""
                new_messages.append({"role": "system", "content": error_msg})
            
            else:
                # Answer Cleaning & Verification
                try:
                    from .answer_synthesis import verify_and_clean_answer
                    print(f"[Agent] Triggering Answer Cleaning & Verification... Query: {user_query[:50]}...")
                    # verify_and_clean_answer is sync (LLM call), wrap it
                    import asyncio
                    cleaned = await asyncio.to_thread(verify_and_clean_answer, content_buffer, user_query)
                    
                    if cleaned.startswith("ERROR:"):
                        print(f"[Agent] Answer cleaning failed: {cleaned}")
                        new_messages[-1]["content"] += f"\n\n[System] Answer Verification Failed: {cleaned}"
                    else:
                        print(f"[Agent] Answer verified and cleaned: {cleaned}")
                        # Append the verified answer
                        new_messages[-1]["content"] += f"\n\n[System] Verified Final Answer: {cleaned}"
                        # Emit the cleaned answer so it is visible in the stream
                        emitted.append(Chunk(type="text", content=f"\n\n[System] Verified Final Answer: {cleaned}", step_index=current_step))
                        
                except Exception as e:
                    print(f"[Agent] Answer cleaning exception: {e}")
                    new_messages[-1]["content"] += f"\n\n[System] Answer Verification Error: {str(e)}"

        return {
            "messages": new_messages,
            "pending_tool_calls": pending_tool_calls,
            "emitted": emitted,
            "step_index": current_step # Step index increments in executor or after tool
        }

    async def tools_node(state: AgentState) -> dict:
        # Execute tools using existing logic
        # execute_tools_logic returns updated state with new messages and emitted chunks
        # If execute_tools_logic is sync, wrap it
        import asyncio
        result = await asyncio.to_thread(execute_tools_logic, state, tool_functions_map, memory)
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
        
        # UPDATE: Since nodes are now async, we MUST use astream
        
        iterator = app.astream(initial_state, stream_mode="updates")
        
        async for output in iterator:
            # Output is a dict of {node_name: state_update}
            for node_name, state_update in output.items():
                if "emitted" in state_update:
                    for chunk in state_update["emitted"]:
                        yield chunk
                        
    except Exception as e:
        print(f"[AgentLoop] Error: {e}")
        import traceback
        traceback.print_exc()
