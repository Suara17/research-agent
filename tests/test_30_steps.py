#!/usr/bin/env python3
"""测试Agent是否能执行至少30步"""

import asyncio
from research_agent import (
    agent_loop,
    web_search,
    web_fetch,
    browse_page,
    x_keyword_search,
    search_pdf_attachment,
    browse_pdf_attachment,
    get_weather,
)


async def test_30_steps():
    query = "Which protein was identified as an interactor of PAD4 but has no evidence of interacting with ADF3, contributing to powdery mildew defense, or EHM targeting?"

    step_count = 0
    final_answer = None

    print(f"开始测试: {query}\n")

    tool_functions = [
        web_search,
        web_fetch,
        browse_page,
        x_keyword_search,
        search_pdf_attachment,
        browse_pdf_attachment,
        get_weather,
    ]

    messages = [{"role": "user", "content": query}]

    async for chunk in agent_loop(messages, tool_functions, max_steps=40):
        if chunk.type == "tool_call":
            step_count += 1
            print(f"[Step {step_count}] 工具调用: {chunk.tool_call.tool_name}")
        elif chunk.type == "text" and "Final Answer" in chunk.content:
            final_answer = chunk.content
            print(f"\n检测到最终答案在第 {step_count} 步")

    print(f"\n{'=' * 60}")
    print(f"测试结果:")
    print(f"  总步数: {step_count}")
    print(f"  目标步数: 30")
    print(f"  是否达标: {'✓ 是' if step_count >= 30 else '✗ 否'}")
    print(f"{'=' * 60}")

    if step_count < 30:
        print(f"\n⚠️ 警告: 仅执行了 {step_count} 步，未达到30步要求")
        return False
    else:
        print(f"\n✓ 成功: 执行了 {step_count} 步，达到30步要求")
        return True


if __name__ == "__main__":
    success = asyncio.run(test_30_steps())
    exit(0 if success else 1)
