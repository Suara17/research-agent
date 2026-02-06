import os
import json
from typing import Optional, List
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

# Import from package
from research_agent import config
from research_agent import (
    agent_loop,
    web_search,
    web_fetch,
    browse_page,
    x_keyword_search,
    search_pdf_attachment,
    browse_pdf_attachment,
    multi_hop_search,
    get_weather,
    extract_entities,
    check_answer_type,
    verify_answer,
    force_fix_answer,
    clean_answer,
    CandidatePool
)
from research_agent.complexity import calculate_max_steps

try:
    from agui import stream_agui_events, to_openai_messages, to_sse_data
    from ag_ui.core import RunAgentInput
    _AGUI_AVAILABLE = True
except Exception:
    _AGUI_AVAILABLE = False

app = FastAPI()

FEW_SHOT_EXAMPLES = """
### 示例 1 (多跳推理 + PDF 阅读)
用户问题: "2023年获得诺贝尔生理学或医学奖的科学家，他们的主要贡献解决了什么关键问题？"

Thought: 这是一个关于诺贝尔奖的问题。
1. 我需要先搜索2023年诺贝尔生理学或医学奖得主。
2. 然后查找他们的贡献细节。
Action: web_search
Action Input: {"query": "2023 Nobel Prize in Physiology or Medicine winners contributions"}
Observation: [搜索结果] 提到 Katalin Karikó 和 Drew Weissman。关键词：mRNA vaccines, nucleoside base modification.
Thought: 搜索结果提到了 mRNA 疫苗和核苷碱基修饰。我需要更详细的信息来确认“解决了什么关键问题”。我应该找官方新闻或详细报道。
Action: web_search
Action Input: {"query": "Katalin Karikó Drew Weissman contributions nucleoside base modification details"}
Observation: [搜索结果] 包含一个指向 nobelprize.org 的 PDF 链接 "press_medicine2023.pdf"。
Thought: 官方 PDF 是最可靠的来源。我必须阅读它。
Action: web_fetch
Action Input: {"url": "https://www.nobelprize.org/.../press_medicine2023.pdf"}
Observation: [PDF内容] ...discovered that nucleoside base modification enabled effective delivery of mRNA... eliminated the inflammatory reaction...
Thought: 根据 PDF，关键问题是外源 mRNA 会引起炎症反应（inflammatory reaction）并被降解，限制了应用。他们的发现通过碱基修饰消除了这种反应。
Final Answer: 解决了外源 mRNA 进入人体后会引发炎症反应（inflammatory reaction）且产生蛋白水平低的关键问题，从而使开发有效的 mRNA 疫苗成为可能。

### 示例 2 (自我纠错/Reflexion)
用户问题: "查询电影《奥本海默》全球票房精确数字（美元）。"

Thought: 直接搜索奥本海默全球票房。
Action: web_search
Action Input: {"query": "Oppenheimer global box office exact number"}
Observation: [搜索结果] $950 Million, $960M, 9.76亿美元。
Thought: 搜索结果比较模糊，有多个近似值。题目要求“精确数字”。我需要找 Box Office Mojo 或权威财经新闻的最新数据。
Action: web_search
Action Input: {"query": "Oppenheimer box office mojo worldwide lifetime gross"}
Observation: [搜索结果] Box Office Mojo 显示 Lifetime Gross: $976,166,665.
Thought: 这是一个精确数字。
Final Answer: 976,166,665
"""

class QueryRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {"question": "What is the weather in Beijing today?"}
        },
    )

    question: str
    chat_history: Optional[list] = None

    def to_messages(self) -> list:
        if self.chat_history:
            return self.chat_history + [{"role": "user", "content": self.question}]
        else:
            return [
                {
                    "role": "system",
                    "content": (
                        """你是一个专业的 Research Agent。你的唯一目标是给出精准的事实性答案。

### 核心原则
1. **证据驱动**: 每个结论必须有明确证据，标注来源URL
2. **多源验证**: 关键信息（人名/日期/数字）需≥2个独立来源确认
3. **深度优先**: 优先使用 web_fetch 读取全文，而非依赖搜索摘要
4. **善用 Skills**: 复杂任务使用专门的 Skills 提升准确性
5. **语言一致性**: 答案语言必须与问题语言保持一致（中文问题用中文回答，英文问题用英文回答），除非问题明确要求特定语言。

### 可用 Skills
- **smart-search**: 智能多策略搜索，根据问题类型自动选择最佳搜索策略（学术/新闻/时间线/对比/定义）。初次搜索或需要改变策略时使用。
- **multi-source-verify**: 多源验证答案准确性。验证关键事实（人名/日期/数字）时使用，要求至少2个独立来源支持。
- **chain-of-verification**: 验证链推理。对复杂或高价值问题，生成验证问题并独立搜索验证，修正答案。当置信度<0.8时使用。
- **deep-research**: 深度研究。需要多步深度研究和证据综合时使用。

### 多跳推理策略（漏斗式搜索法）
面对包含多个条件的复杂问题，采用以下四步法：

**步骤1 - 拆解与提取（识别锚点）**
- 不要搜索整句话，而是识别最具体的"锚点"关键词
- 低价值词示例（太宽泛）："日本公司"、"20世纪"、"知名游戏"
- 高价值词示例（锚点）："改编动画片"、"动作游戏系列"、具体作品名

**步骤2 - 逐步收敛（漏斗搜索）**
- 第一步：确定实体（利用"交集"逻辑找唯一解）
  - 搜索高价值锚点词组合
  - 从结果中筛选符合约束条件的候选项
- 第二步：查询属性（针对锁定实体精准查询）
  - 一旦锁定目标实体，再查具体属性

**步骤3 - 高阶搜索指令**
- 强制匹配（引号）："animated series"
- 站内搜索（site:）：site:wikipedia.org
- 排除干扰（减号）：-Nintendo

**步骤4 - 验证与三角测量**
- 对推理出的答案进行"回测"，确保符合所有描述条件

### 黄金法则
1. **搜索摘要常错误**: 必须使用 web_fetch 读取全文验证，不能只看摘要
2. **PDF优先**: 学术/历史/法律问题答案常在PDF中，优先使用 browse_pdf_attachment
3. **拆分复杂问题**: 复杂问题拆分为子问题，逐步验证。多跳问题必须使用漏斗搜索法
4. **死循环检测**: 连续2次相似搜索无进展→立即改变策略
5. **仅输出答案**: 严格只输出答案文本
6. **日期/数字精确**: 务必精确匹配
7. **必须回答**: 禁止输出"无法确定"

### Skills 使用建议
- 初次搜索某个主题 → 使用 **smart-search**
- 找到候选答案后 → 使用 **multi-source-verify** 验证
- 复杂问题或置信度中等 → 使用 **chain-of-verification**
- 需要多步深度研究 → 使用 **deep-research**

### 思考模式
Action → Observation → Reflection → Action ... → Final Answer

"""
                        f"{FEW_SHOT_EXAMPLES}"
                    ),
                },
                {"role": "user", "content": self.question},
            ]


class QueryResponse(BaseModel):
    answer: str


@app.post("/")
async def query(req: QueryRequest) -> QueryResponse:
    MAX_RETRIES = 2
    final_answer = ""
    rejection_history = []
    candidate_pool = CandidatePool()

    # 🔥 动态计算最大步数（方案2）
    max_steps = calculate_max_steps(req.question, base_steps=20)
    print(f"[Monitoring] Dynamic max_steps calculated: {max_steps} for question: {req.question[:50]}...")

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            print(f"[Monitoring] Query Retry {attempt}/{MAX_RETRIES} for question: {req.question[:50]}...")

        result = ""
        agent_state = None

        messages = req.to_messages()
        if rejection_history:
            hint_text = "\n\n".join(rejection_history)
            rejected_names = candidate_pool.get_rejected_names()

            messages.append({
                "role": "system",
                "content": f"SYSTEM REMINDER: You previously attempted to answer this question but were REJECTED by verification.\n\nPREVIOUS REJECTIONS:\n{hint_text}\n\nREJECTED CANDIDATES (DO NOT REPEAT):\n{rejected_names}\n\nCRITICAL INSTRUCTION:\n1. You MUST change your search strategy completely\n2. Explore DIFFERENT countries/persons (NOT {rejected_names})\n3. If you believe the rejected candidate is actually correct, provide EXPLICIT evidence for ALL missing constraints\n4. Consider using excluded_entities parameter in smart-search to force diversification"
            })

        async for chunk in agent_loop(messages, [web_search, web_fetch, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, multi_hop_search, get_weather], max_steps=max_steps):
            if chunk.type == "tool_call" or chunk.type == "tool_call_result":
                result = ""
            elif chunk.type == "text" and chunk.content:
                result += chunk.content
            elif chunk.type == "final_state":
                try:
                    state_data = json.loads(chunk.content)
                    agent_state = state_data.get("state", {})
                    candidates = (agent_state.get("meta") or {}).get("candidates", [])
                    for cand in candidates:
                        candidate_pool.add_candidate(
                            answer=cand.get("text", ""),
                            confidence=cand.get("confidence", 0.0),
                            sources=[f"source_{i}" for i in range(cand.get("sources", 1))]
                        )
                    print(f"[CandidatePool] Extracted {len(candidates)} candidates from agent_loop")
                except Exception as e:
                    print(f"[CandidatePool] Failed to extract candidates: {e}")

        if result:
            result = clean_answer(result)
            result = check_answer_type(req.question, result)

        if result:
            original = result
            verified = verify_answer(req.question, result)

            if "[REJECTED]" in verified:
                 print(f"[Monitoring] Answer rejected by verification (Attempt {attempt}): {verified}")

                 candidate_pool.reject(original, verified)
                 next_candidate = candidate_pool.get_next_best()

                 if next_candidate and next_candidate != original:
                     print(f"[CandidatePool] Switching to next candidate: '{next_candidate}'")
                     result = next_candidate
                     verified = verify_answer(req.question, result)

                     retry_count = 0
                     while "[REJECTED]" in verified and retry_count < 3:
                         candidate_pool.reject(result, verified)
                         next_candidate = candidate_pool.get_next_best()
                         if not next_candidate or next_candidate == result:
                             break
                         print(f"[CandidatePool] Candidate rejected, trying next: '{next_candidate}'")
                         result = next_candidate
                         verified = verify_answer(req.question, result)
                         retry_count += 1

                     if "[REJECTED]" not in verified:
                         result = verified
                         final_answer = clean_answer(result)
                         if final_answer:
                             print(f"[CandidatePool] Found valid candidate from pool: '{final_answer[:50]}...'")
                             break

                 rejection_history.append(f"Attempt {attempt+1}: {verified}")

                 if attempt == MAX_RETRIES:
                     print(f"[Monitoring] Max retries reached. Forcing fix for rejected candidate...")
                     fixed_ans = await force_fix_answer(req.question, original, verified)
                     if fixed_ans:
                         result = fixed_ans
                         final_answer = fixed_ans
                         break

                 result = ""
            else:
                 if verified != original:
                     print(f"[Monitoring] Verified answer: '{original[:50]}...' -> '{verified[:50]}...'")
                 result = verified

        if result:
            final_answer = clean_answer(result)
            if final_answer:
                break

    return QueryResponse(answer=final_answer)


@app.post("/stream")
async def stream(req: QueryRequest) -> StreamingResponse:
    async def stream_response():
        async for chunk in agent_loop(req.to_messages(), [web_search, web_fetch, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, multi_hop_search, get_weather], max_steps=15):
            if chunk.type == "text" and chunk.content:
                data = {"answer": chunk.content}
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
    )

if _AGUI_AVAILABLE:
    @app.post("/ag-ui")
    async def ag_ui(run_agent_input: RunAgentInput) -> StreamingResponse:
        messages = to_openai_messages(run_agent_input.messages)
        async def stream_response():
            async for event in stream_agui_events(
                chunks=agent_loop(messages, [web_search, web_fetch, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, multi_hop_search, get_weather], max_steps=30),
                run_agent_input=run_agent_input,
            ):
                yield to_sse_data(event)
        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception:
        uvicorn.run(app, host="0.0.0.0", port=8001)
