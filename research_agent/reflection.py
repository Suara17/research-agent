"""
智能反思检查点模块 - 通用优化方案3
在关键步骤插入反思，避免概念误解和方向性错误
"""
import json
from typing import List, Dict, Optional
from .utils import get_llm_client


class ReflectionCheckpoint:
    """反思检查点"""

    def __init__(self, step_index: int, trigger_condition: str, prompt_template: str):
        self.step_index = step_index
        self.trigger_condition = trigger_condition
        self.prompt_template = prompt_template


class ReflectionManager:
    """反思管理器 - 在关键节点插入深度反思"""

    # 预定义的反思检查点模板（动态分布）
    CHECKPOINT_TEMPLATES = [
        # 早期概念验证 (约 25% 进度)
        {
            "phase": "early",
            "trigger_condition": "always",
            "prompt_template": """
🔍 **早期概念验证检查点** (步骤 {current_step}/{max_steps})

请回答以下问题来验证你的理解：

1. **问题类型识别**：这个问题要求的答案类型是什么？（人名/地名/年份/数字/组织名等）

2. **核心概念理解**：问题中是否有专业术语？你是否确认理解正确？
   - 例如："five-star accredited" 可能指什么？（博物馆评级？体育场评级？酒店评级？）
   - 如果不确定，列出可能的解释

3. **搜索方向检查**：你目前的搜索关键词是：{recent_keywords}
   - 这些关键词是否直接针对问题的核心要素？
   - 是否存在概念误解导致搜索方向错误？

4. **已获取信息盘点**：到目前为止，你已经找到哪些关键事实？还缺少什么？

⚠️ **强制要求**：如果发现概念理解有误，立即调整搜索策略。
"""
        },

        # 中期信息整合 (约 50% 进度)
        {
            "phase": "mid",
            "trigger_condition": "always",
            "prompt_template": """
🧩 **中期信息整合检查点** (步骤 {current_step}/{max_steps})

你已经进行了 {search_count} 次搜索。现在需要整合信息：

1. **实体关系梳理**：列出你识别到的所有关键实体及其关系
   - 例如：A位于B，C与D合作，E由F资助
   - 是否存在逻辑矛盾？（如：X在Y，但又要求X不在Y）

2. **信息缺口识别**：基于问题要求，你还缺少哪些关键信息？
   - 优先级排序：哪些是回答问题必须的？哪些是次要的？

3. **搜索效率评估**：
   - 最近5次搜索是否都在重复相似的查询？
   - 是否陷入"信息孤岛"（找到片段信息但未建立联系）？

4. **策略调整建议**：
   - 如果信息分散，是否需要搜索"X和Y的关系"？
   - 如果某个实体信息不足，是否需要直接搜索该实体的官方信息？

💡 **提示**：复杂问题通常需要将多个独立事实组合成完整推理链。
"""
        },

        # 后期答案验证 (约 75% 进度)
        {
            "phase": "late",
            "trigger_condition": "always",
            "prompt_template": """
✅ **后期答案验证检查点** (步骤 {current_step}/{max_steps})

你已经搜索了 {search_count} 次。如果你已有候选答案，请验证：

1. **完整性验证**：候选答案是否满足问题的所有约束条件？
   - 列出问题中的每个约束，逐一确认

2. **证据链验证**：你的推理过程是否基于确凿证据？
   - 列出支持答案的3个最强证据
   - 是否存在矛盾证据？

3. **答案类型匹配**：
   - 问题要求的答案格式是什么？（年份/全名/英文名/数字等）
   - 你的答案格式是否匹配？

4. **替代可能性排除**：是否还有其他候选答案？
   - 如果有，为什么选择当前答案而非其他？

如果答案仍不明确，建议：
- 搜索"候选答案 + 验证性关键词"来确认
- 使用multi-source-verify技能进行多源交叉验证
"""
        }
    ]

    def __init__(self):
        self.triggered_checkpoints = set()  # 记录已触发的步骤

    def should_trigger(self, current_step: int, max_steps: int, search_count: int) -> Optional[Dict]:
        """
        判断是否应该触发反思检查点 (动态均分策略)

        Args:
            current_step: 当前步骤
            max_steps: 最大步骤数
            search_count: 已执行的搜索次数

        Returns:
            如果应该触发，返回模板字典，否则返回None
        """
        # 计算三个动态检查点的位置
        # 确保至少间隔一定步数，避免在极短任务中频繁触发
        if max_steps < 10:
            return None
            
        checkpoints = [
            int(max_steps * 0.25),  # Early
            int(max_steps * 0.50),  # Mid
            int(max_steps * 0.75)   # Late
        ]
        
        # 找到当前步骤对应的检查点索引
        matched_index = -1
        for i, cp_step in enumerate(checkpoints):
            if current_step == cp_step:
                matched_index = i
                break
        
        if matched_index != -1:
            # 检查是否已触发过该步骤
            if current_step in self.triggered_checkpoints:
                return None
                
            template = self.CHECKPOINT_TEMPLATES[matched_index]
            
            # 检查触发条件
            if template["trigger_condition"] == "always":
                self.triggered_checkpoints.add(current_step)
                return template
            elif template["trigger_condition"] == "has_searches" and search_count > 0:
                self.triggered_checkpoints.add(current_step)
                return template

        return None

    def generate_reflection_prompt(
        self,
        checkpoint_template: Dict,
        context: Dict
    ) -> str:
        """
        生成反思提示

        Args:
            checkpoint_template: 检查点模板字典
            context: 上下文信息 (包含current_step, max_steps, search_count, recent_keywords等)

        Returns:
            格式化的反思提示
        """
        return checkpoint_template["prompt_template"].format(
            current_step=context.get("current_step", 0),
            max_steps=context.get("max_steps", 40),
            search_count=context.get("search_count", 0),
            recent_keywords=", ".join(context.get("recent_keywords", [])[-5:])
        )


class ConceptVerifier:
    """概念验证器 - 验证Agent对问题中关键概念的理解"""

    @staticmethod
    def verify_concept_understanding(question: str, agent_interpretation: str) -> Dict:
        """
        验证Agent对问题概念的理解是否正确

        Args:
            question: 原始问题
            agent_interpretation: Agent对问题的理解/搜索策略

        Returns:
            验证结果字典
        """
        try:
            client = get_llm_client(timeout=30.0)

            prompt = f"""你是一个概念验证专家。请分析Agent对问题的理解是否正确。

**原始问题**：
{question}

**Agent的理解/搜索策略**：
{agent_interpretation}

请分析：
1. Agent是否正确理解了问题中的专业术语？
2. Agent的搜索方向是否与问题目标一致？
3. 是否存在明显的概念误解？

输出JSON格式：
{{
  "is_correct": true/false,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"],
  "correct_interpretation": "正确的理解应该是..."
}}

**重要**：特别注意以下常见误解：
- "five-star"可能指酒店、餐厅、博物馆、体育场等不同评级体系
- "认证"/"accredited"在不同领域有不同含义
- 地理位置关系的传递性（A在B，B在C，但A可能"不在C"是矛盾的）
"""

            response = client.chat.completions.create(
                model="qwen3-max",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=512,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            print(f"[ConceptVerifier] 验证失败: {e}")
            return {"is_correct": True, "issues": [], "suggestions": []}


def should_inject_reflection(
    step_index: int,
    max_steps: int,
    searched_keywords: List[str],
    last_reflection_step: int
) -> bool:
    """
    判断是否应该注入反思

    通用策略：
    1. 在特定关键步骤强制反思 (5, 15, 25, 35)
    2. 避免过于频繁的反思 (至少间隔5步)

    Args:
        step_index: 当前步骤
        max_steps: 最大步骤
        searched_keywords: 已搜索的关键词列表
        last_reflection_step: 上次反思的步骤

    Returns:
        是否应该注入反思
    """
    # 检查间隔
    if step_index - last_reflection_step < 5:
        return False

    # 关键检查点
    key_checkpoints = [5, 15, 25, 35]
    if step_index in key_checkpoints:
        return True

    # 动态检查：如果搜索次数很多但仍在继续
    if step_index > 20 and len(searched_keywords) > 15:
        return True

    return False
