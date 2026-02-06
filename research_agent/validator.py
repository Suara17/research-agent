import os
import json
from openai import OpenAI
from .utils import get_llm_client

def validate_plan(plan: str, rejection_context: str = "") -> dict:
    try:
        # Use a new client with longer timeout
        client = OpenAI(
            base_url="https://apis.iflow.cn/v1",
            api_key=os.getenv("IFLOW_API_KEY"),
            timeout=60.0,
            max_retries=2
        )

        validator_prompt = [{
            "role": "system",
            "content": """You are a Plan Validator. Your goal is to catch FATAL logic errors, but allow reasonable exploration plans.

**Validation Philosophy (RELAXED MODE)**:
- **Do NOT be overly pedantic**. Research plans often start with hypotheses that need to be verified.
- **Allow "Hypothetical Steps"**: It is OK for a plan to say "If X is found, do Y".
- **Allow "Broad Search"**: It is OK to search for a broad topic first.
- **Focus on FATAL errors only**: Only reject the plan if it is physically impossible, strictly self-contradictory, or completely off-topic.

**Fatal Errors to Catch**:
1. **Direct Contradiction**: Step 2 says "Focus on Mongolia", Step 3 says "Exclude Mongolia" (without reason).
2. **Infinite Loop Risk**: Planning to search the same query 10 times.
3. **Missing Core Constraints**: The user asked for "1990s" but the plan searches for "2020s".

**Non-Errors (Do NOT Reject)**:
- Ambiguity in entity relationships (the agent will figure it out).
- Searching for things that might not exist (that's why we search).
- Minor inefficiencies.

**Output Format** (JSON):
{
  "is_valid": true/false,
  "issues": ["Critical Issue 1"],
  "suggestions": ["Suggestion 1"],
  "fixed_plan": "Fixed plan text (only if invalid)"
}
"""
        }, {
            "role": "user",
            "content": f"""请验证以下研究计划的逻辑一致性:

**Plan**:
{plan}

**拒绝反馈上下文** (如果是重试):
{rejection_context if rejection_context else "无(首次尝试)"}

请检查Plan是否有矛盾、遗漏或不合理之处。"""
        }]

        resp = client.chat.completions.create(
            model="qwen3-max",
            messages=validator_prompt,
            response_format={"type": "json_object"},
            max_tokens=1024,
            temperature=0.3
        )

        try:
            content = resp.choices[0].message.content
            # 清理可能的Markdown代码块标记
            content = content.replace('```json', '').replace('```', '').strip()
            result = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[PlanValidator] JSON解析失败: {e}")
            print(f"[PlanValidator] 原始内容: {content[:200] if content else 'Empty'}...")
            # 返回默认通过，避免阻塞流程
            return {
                "is_valid": True,
                "issues": ["Plan验证JSON解析失败，已跳过验证"],
                "validation_skipped": True,
                "fixed_plan": plan
            }

        if not result.get("is_valid", True):
            print(f"[PlanValidator] ⚠️ Plan有 {len(result.get('issues', []))} 个问题:")
            for issue in result.get("issues", []):
                print(f"  - {issue}")
            if result.get("suggestions"):
                print(f"[PlanValidator] 💡 建议:")
                for sug in result.get("suggestions", []):
                    print(f"  - {sug}")
        else:
            print(f"[PlanValidator] ✅ Plan验证通过")

        return result

    except Exception as e:
        error_msg = str(e)
        print(f"[PlanValidator] 验证失败: {e}")
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            print("[PlanValidator] ⚠️ API请求超时，将使用原计划但标记为未验证")
            return {
                "is_valid": False,
                "issues": ["API验证超时，计划未经过逻辑验证，请谨慎执行"],
                "suggestions": ["建议：手动检查计划的逻辑一致性"],
                "fixed_plan": plan,
                "validation_skipped": True
            }
        else:
            print(f"[PlanValidator] ❌ 验证过程出现异常: {error_msg}")
            return {
                "is_valid": False,
                "issues": [f"验证失败：{error_msg}"],
                "suggestions": ["建议：检查API配置或网络连接"],
                "fixed_plan": plan,
                "validation_skipped": True
            }
