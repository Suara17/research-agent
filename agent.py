import os
import json
import asyncio
import sys
from typing import Optional, List

# 强制设置标准输出/输入编码为UTF-8，避免gbk编码错误
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from fastapi import FastAPI, HTTPException, status, Header
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
    verify_and_clean_answer,
)
from research_agent.answer_synthesis import (
    synthesize_best_answer,
    process_final_answer,
    verify_and_clean_answer,
)

try:
    from agui import stream_agui_events, to_openai_messages, to_sse_data
    from ag_ui.core import RunAgentInput

    _AGUI_AVAILABLE = True
except Exception as e:
    print(f"[Warning] AGUI not available: {e}")
    _AGUI_AVAILABLE = False
    RunAgentInput = None

app = FastAPI()


def verify_token(authorization: Optional[str] = Header(None)):
    """验证Bearer token"""
    expected_token = os.getenv("EAS_AUTH_TOKEN", "")

    # 如果没有配置token，则跳过验证
    if not expected_token:
        return True

    # 验证token
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format",
        )

    token = authorization[7:]  # 去掉 "Bearer " 前缀
    if token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization token",
        )

    return True


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
3. **首位/唯一类约束**: 遇到"first"、"首位"、"only"、"唯一"等约束时，必须通过额外搜索确认该实体确实满足"首位/唯一"条件，不能仅凭单次搜索结果就假设成立
4. **时间对齐约束**: 当问题涉及多个事件需同步到同一年时，必须明确列出各事件的年份并逐一验证它们确实相同，不能仅凭语义关联假设
5. **链式验证**: 当问题涉及A→B→C的链式推理时，每跳都必须独立验证，不能跳过中间环节直接给出最终答案
6. **领域术语精准**: 搜索专业领域问题时，需使用准确的领域术语+限定词，避免结果进入错误领域
7. **模糊消歧**: 当实体名称模糊（如数字艺名、通用词）时，必须通过额外信息（代表作、特征等）确认唯一性
8. **数值精确性**: 当问题要求精确数字/年份时，必须给出确切值而非近似值，使用额外搜索验证数值准确性
9. **深度优先**: 优先使用 web_fetch 读取全文，而非依赖搜索摘要
10. **善用 Skills**: 复杂任务使用专门的 Skills 提升准确性
11. **语言一致性(最高优先级)**: 
   - 答案语言必须与问题语言保持一致
   - 中文问题 -> 必须用中文回答，包括人名、公司名、地名等实体名称
   - 英文问题 -> 必须用英文回答
   - **实体翻译规则**: 
     - 公司/品牌名: 使用标准中文译名（如 "Mondadori" -> "蒙达多利出版社"）
     - 人名: 使用标准中文名/音译（如 "Arnoldo Mondadori" -> "阿诺尔多·蒙达多利"）
     - 如无标准译名，使用音译
   - **输出格式**: 最终答案必须直接是实体名称，不要包含任何解释

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
    verify_token()  # 验证token
    max_steps = 40  # 40步（约10分钟）
    
    # 整体超时设置：留20秒给答案综合
    TOTAL_TIMEOUT = 580  # 秒

    # Define a helper to run a single agent instance
    async def run_single_agent(agent_id: int):
        trace_chunks = []
        final_res = ""
        # Create a fresh copy of messages for each agent
        # req.to_messages() returns a new list each time, so it's safe
        messages = req.to_messages()

        # Add a system hint to differentiate them slightly (optional, but good for diversity)
        # For now, we rely on temperature randomness

        async def _run_agent_loop():
            async for chunk in agent_loop(
                messages,
                [
                    web_search,
                    web_fetch,
                    browse_page,
                    x_keyword_search,
                    search_pdf_attachment,
                    browse_pdf_attachment,
                    get_weather,
                ],
                max_steps=max_steps,
            ):
                if chunk.type == "text" and chunk.content:
                    trace_chunks.append(chunk.content)

            full_trace = "".join(trace_chunks)
            # 从 trace 中提取候选答案，避免 answer 字段空置导致兜底失败
            from research_agent.answer_synthesis import _extract_last_candidate
            extracted = _extract_last_candidate(full_trace)
            return {"id": agent_id, "trace": full_trace, "answer": extracted}

        try:
            # 使用 asyncio.wait_for 强制整体超时
            return await asyncio.wait_for(_run_agent_loop(), timeout=TOTAL_TIMEOUT)
        except asyncio.TimeoutError:
            print(f"[Agent {agent_id}] Total timeout ({TOTAL_TIMEOUT}s) exceeded, returning partial result")
            full_trace = "".join(trace_chunks)
            # 超时时同样从已有 trace 提取最佳候选答案
            from research_agent.answer_synthesis import _extract_last_candidate
            extracted = _extract_last_candidate(full_trace)
            print(f"[Agent {agent_id}] Extracted answer from partial trace: {extracted[:80] if extracted else '(empty)'}")
            return {"id": agent_id, "trace": full_trace, "answer": extracted}

    # Determine number of agents to run in parallel
    num_agents = int(
        os.getenv("NUM_AGENTS", "1")
    )  # Default to 1, can be overridden with env var
    if num_agents < 1:
        num_agents = 1
    elif num_agents > 5:  # Limit maximum to prevent resource exhaustion
        num_agents = 5

    print(
        f"[Multi-Agent] Starting {num_agents} parallel agents for query: {req.question[:50]}..."
    )

    # Helper to run async function in a new thread with new loop
    def run_in_new_thread(agent_id):
        import asyncio

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(run_single_agent(agent_id))
        finally:
            new_loop.close()

    import concurrent.futures

    loop = asyncio.get_running_loop()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_agents) as executor:
        futures = [
            loop.run_in_executor(executor, run_in_new_thread, i)
            for i in range(1, num_agents + 1)
        ]
        results = await asyncio.gather(*futures)

    print(
        f"[Multi-Agent] All {num_agents} agents finished. Synthesizing best answer..."
    )

    # Synthesize the final answer
    final_answer = synthesize_best_answer(
        req.question,
        results,
        original_question=req.question,
    )

    # 打印返回的JSON响应
    print(
        f"[Response] Returning: {json.dumps({'answer': final_answer}, ensure_ascii=False)}"
    )

    return QueryResponse(answer=final_answer)


@app.post("/stream")
async def stream(req: QueryRequest) -> StreamingResponse:
    verify_token()  # 验证token

    async def stream_response():
        async for chunk in agent_loop(
            req.to_messages(),
            [
                web_search,
                web_fetch,
                browse_page,
                x_keyword_search,
                search_pdf_attachment,
                browse_pdf_attachment,
                get_weather,
            ],
            max_steps=30,
        ):
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
        verify_token()  # 验证token
        messages = to_openai_messages(run_agent_input.messages)

        async def stream_response():
            async for event in stream_agui_events(
                chunks=agent_loop(
                    messages,
                    [
                        web_search,
                        web_fetch,
                        browse_page,
                        x_keyword_search,
                        search_pdf_attachment,
                        browse_pdf_attachment,
                        get_weather,
                    ],
                    max_steps=30,
                ),
                run_agent_input=run_agent_input,
            ):
                yield to_sse_data(event)

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
        )


if __name__ == "__main__":
    import uvicorn
    import socket

    def check_port(host, port):
        """检查端口是否可用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                s.close()
                return True
            except OSError:
                return False

    port = int(os.getenv("PORT", "8004"))  # 默认使用8004端口

    # 设置API超时时间为10分钟
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=600)
