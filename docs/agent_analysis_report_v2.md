# Agent 复杂推理能力深度分析报告 (v2.0)

## 1. 核心问题诊断

基于 `validation_results.jsonl` 的失败案例与代码库 (`core.py`, `reflection.py`, `skills/*`) 的对比分析，我们发现 Agent 的主要瓶颈不在于"能力缺失"（它有搜索、反思、验证工具），而在于 **"执行纪律松懈"** 和 **"认知捷径"**。

### A. 确认偏误 (Confirmation Bias) - "先入为主"
Agent 倾向于锁定第一个看似合理的"锚点"实体，然后通过"合理化"（Rationalization）来忽略不匹配的约束条件，而不是进行严谨的"证伪"。

*   **典型案例 (ID 9: 玉米 vs 小麦)**：
    *   **现象**：找到"副产品做味精" -> 锁定"玉米" -> 找到"玉米纠纷案例"。
    *   **忽略点**：完全无视"21世纪10年代末推出"（时间不符）和"播种季节与CNV相关"（生物学特征不符）这两个硬约束。
    *   **代码根源**：`core.py` 中的 `MULTI_HOP_SYSTEM_PROMPT` 虽然提到了 "Verify"，但没有强制性的 **Constraint Checklist (约束核对表)** 机制。Agent 在 Reasoning 过程中没有被强制要求逐一列出约束并打勾。

### B. 技能调用惰性 (Skill Utilization Inertia)
尽管我们有强大的 Skills (`multi-source-verify`, `smart-search`)，Agent 在实战中往往倾向于使用最基础的 `web_search`，或者忽略 Skill 的输出建议。

*   **证据**：
    *   `skills/multi-source-verify/run.py` 定义了非常完善的验证逻辑（查冲突、查权威来源、查竞争假设）。
    *   **失败点**：在 `validation_results.jsonl` 的 Trace 中，Agent 几乎从未主动调用 `multi-source-verify` 来验证中间结论（如"玉米"）。它把 Skill 当作"备用轮胎"，而不是"标准流程"。

### C. 反思机制流于形式 (Passive Reflection)
`reflection.py` 中的反思机制是"询问式"的，而非"强制执行式"的。

*   **代码分析** (`reflection.py`)：
    *   Prompt 模板：`"你的搜索结果是否包含你期望的信息？"`，`"你目前的搜索关键词是..."`。
    *   **问题**：这种反思依赖 Agent 的"自省"能力。如果 Agent 已经陷入了确认偏误（认为自己是对的），它会对反思问题回答 "Yes, I'm on track"，从而使反思失效。
    *   **改进方向**：反思不应是问答，而应是 **"对抗性测试"**。例如："请尝试证明你当前的结论是**错**的"，或者"列出当前结论不符合题目中哪一个细节"。

### D. 负向与长尾实体检索能力弱
*   **典型案例 (ID 5: PAD4 互作蛋白)**：
    *   **现象**：面对 "does NOT interact with..." 这类负向约束，Agent 束手无策。
    *   **原因**：`smart-search` 虽然支持负向查询，但 Agent 的 Planner 缺乏 **"列表枚举-逐个排除" (List & Filter)** 的显式策略。它试图直接搜索 "protein not interacting with..."，这在搜索引擎中通常无效。

---

## 2. 现有架构优势与不足

| 模块 | 优势 | 不足 |
| :--- | :--- | :--- |
| **Core Prompt** (`core.py`) | 包含了 CoT、Anchor Selection 等高级指导 | 缺乏强制性的输出格式约束（如 `<check>` 标签），导致 LLM 容易忽略指令。 |
| **Reflection** (`reflection.py`) | 动态触发，覆盖早中晚期 | 提示词过于温和（Open-ended），缺乏强制纠错的动作指令。 |
| **Smart Search** (`skills/smart-search`) | 支持多语言、HyDE、意图识别 | Agent 有时会忽略其生成的 `optimized_queries`，直接用简单关键词重搜。 |
| **Verify Skill** (`skills/multi-source-verify`) | 逻辑严密，包含反向验证 | **调用率极低**。Agent 没有被训练成"每一步都要验证"。 |

---

## 3. 改进建议 (无需改代码阶段)

虽然您要求暂时不改代码，但为了提升正确率，未来的代码调整应集中在以下方向：

1.  **强制约束检查 (Constraint-Check Enforcement)**：
    *   修改 `core.py` 的 System Prompt，要求 Agent 在输出 "Final Answer" 之前，必须输出一个 **Constraint Checklist表格**，列出题目所有条件及当前答案的匹配情况。不匹配则禁止输出答案。

2.  **激活 "List & Filter" 策略**：
    *   在 `planner.py` 或 Prompt 中，针对"负向约束"或"罕见实体"问题，强制生成 "List of candidates" 的步骤，而不是直接搜索答案。

3.  **提升验证 Skill 的优先级**：
    *   在 System Prompt 中，明确要求：当置信度高时，**必须**调用 `multi-source-verify` 进行最后确认，否则视为任务未完成。

4.  **对抗性反思**：
    *   修改 `reflection.py` 的 Prompt，让反思角色扮演"红方"（Red Teamer），专门攻击 Agent 的当前结论，迫使其自证清白。
