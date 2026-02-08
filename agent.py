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
    get_weather,
    clean_answer,
    CandidatePool
)

try:
    from agui import stream_agui_events, to_openai_messages, to_sse_data
    from ag_ui.core import RunAgentInput
    _AGUI_AVAILABLE = True
except Exception:
    _AGUI_AVAILABLE = False

app = FastAPI()

FEW_SHOT_EXAMPLES = """
### 示例 1 (多跳推理: 分解与验证)
用户问题: "2023年获得诺贝尔生理学或医学奖的科学家，他们的主要贡献解决了什么关键问题？"

Thought: 这是一个复杂问题，我需要拆解：
1. 先查2023年得主是谁。
2. 再查他们的核心发现。
3. 最后确认该发现解决了什么具体障碍（"关键问题"）。

Action: web_search
Action Input: {"query": "2023 Nobel Prize in Physiology or Medicine winners"}
Observation: [搜索结果] Katalin Karikó 和 Drew Weissman。
Thought: 找到了得主。现在查他们的贡献细节，特别是关于 mRNA 的。
Action: web_search
Action Input: {"query": "Katalin Karikó Drew Weissman main discovery details"}
Observation: [搜索结果] 提到 "nucleoside base modifications" (核苷碱基修饰) 和 "enabled effective mRNA vaccines"。
Thought: 还需要更具体的信息：在他们发现之前，mRNA 疫苗面临什么问题？
Action: web_search
Action Input: {"query": "what problem did nucleoside base modifications solve for mRNA vaccines"}
Observation: [搜索结果] 外源 mRNA 会引起炎症反应 (inflammatory reaction) 并被降解。
Thought: 找到了。关键问题是“炎症反应”。
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
    max_steps = 30 # Simplified fixed max steps
    
    result = ""
    messages = req.to_messages()

    # Call agent_loop directly
    async for chunk in agent_loop(
        messages, 
        [web_search, web_fetch, browse_page, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, get_weather], 
        max_steps=max_steps
    ):
        if chunk.type == "text" and chunk.content:
            result += chunk.content

    if result:
        result = clean_answer(result)

    return QueryResponse(answer=result)


@app.post("/stream")
async def stream(req: QueryRequest) -> StreamingResponse:
    async def stream_response():
        async for chunk in agent_loop(req.to_messages(), [web_search, web_fetch, browse_page, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, multi_hop_search, get_weather], max_steps=30):
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
                chunks=agent_loop(messages, [web_search, web_fetch, browse_page, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, get_weather], max_steps=30),
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
