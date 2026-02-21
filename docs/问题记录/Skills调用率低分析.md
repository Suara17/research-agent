# Skills 调用率低问题分析

## 现状总结

根据代码分析，系统中定义了 7 个 Skills：
- smart-search
- multi-source-verify
- chain-of-verification
- deep-research
- get-current-time
- web-scraper
- create-plan

但在实际测试中，这些 Skills 被调用的频率很低。

---

## 问题根因分析

### 1. Skills 调用方式不直观（根本原因）

**当前调用方式**：
```
Tools 列表:
- web_search
- web_fetch
- load_skill_file (skill_name: str, file_path: str)
- execute_script (skill_name: str, args: dict)
```

**问题**：Agent 需要记住并主动调用 `execute_script(skill_name="smart-search", args={...})`

这种调用方式存在障碍：
- 工具名称 `execute_script` 不直接暴露 skill 功能
- Agent 需要知道准确的 skill 名称
- 传递参数格式复杂（需要构造 args dict）

---

### 2. 缺乏自动触发机制

**当前状态**：
- System Prompt 列出可用 Skills（软性建议）
- 没有强制触发规则
- Agent 可以完全忽略 Skills 自己推理

**证据**（`agent.py:164-168`）：
```python
### 可用 Skills
- **smart-search**: 智能多策略搜索...
- **multi-source-verify**: 多源验证...
### 思考模式
Action → Observation → Reflection → Action ... → Final Answer
```

这段只是告知 Agent"可以用"，但没有说"什么时候必须用"。

---

### 3. Skills 定义与 Agent 推理流程不匹配

以 `smart-search` 为例：

| Skill 设计意图 | Agent 实际行为 |
|----------------|----------------|
| 解决"直接搜整句搜不到"问题 | Agent 可能自己尝试不同搜索词 |
| 生成多个优化查询 | Agent 可能只用一个查询就继续 |
| 列表-筛选模式 | Agent 可能过早收敛到单一答案 |

**核心矛盾**：Skill 是为"Agent 不知道怎么做"的情况设计的，但 Agent 收到的问题通常认为自己知道怎么做。

---

### 4. 缺乏触发条件判断

**问题**：Agent 不知道何时应该调用 skill

```python
# 当前：Agent 需要自己判断
if "复杂问题" in query:  # 什么是复杂？
    execute_script(skill_name="smart-search", ...)
```

**应该**：系统自动判断或强制触发

---

### 5. 多源验证未被强制执行

`multi-source-verify` skill 的设计很好，但在实际流程中：

1. **没有强制要求**：只在 core.py 的 system prompt 中说"关键信息需≥2个独立来源确认"
2. **Agent 自行判断**：Agent 可能认为自己已经验证了
3. **缺乏验证表强制检查**：虽然有检查点，但因为过于复杂，Agent 可能跳过

---

## 解决方案

### 方案 1：直接暴露 Skills 作为独立工具（推荐）

**改动**：将每个 skill 直接暴露为可用工具，而非通过 `execute_script` 间接调用

```python
# 优化后的 tools 列表
llm_tools = [
    web_search,
    web_fetch,
    browse_page,
    smart_search,        # 直接作为工具
    multi_source_verify,  # 直接作为工具
    chain_of_verification,
    deep_research,
    get_weather,
]
```

**优点**：
- Agent 更容易发现和调用
- 工具名称直接反映功能
- 降低调用门槛

---

### 方案 2：添加自动触发规则

在 `agent_node` 中添加基于问题特征的自动调用：

```python
async def agent_node(state: AgentState) -> dict:
    # 自动触发检查
    if should_auto_use_skill(state):
        # 强制插入 skill 调用
        return {
            "pending_tool_calls": [{
                "function": {
                    "name": "execute_script",
                    "arguments": json.dumps({
                        "skill_name": "smart-search",
                        "args": {"query": user_query}
                    })
                }
            }]
        }

# 触发条件
def should_auto_use_skill(state):
    query = state.get("user_query", "")
    step = state.get("step_index", 0)
    
    # 条件1：首轮搜索前 + 问题超过20字
    if step == 0 and len(query) > 20:
        return True
    
    # 条件2：连续2次搜索无进展
    if state.get("search_no_progress_count", 0) >= 2:
        return True
    
    # 条件3：涉及关键数字/日期验证
    if contains_critical_facts(query):
        return True
```

---

### 方案 3：强制多源验证

**改动**：在 Final Answer 前必须调用 `multi-source-verify`

```python
# 在 agent_node 中
if "Final Answer:" in content_buffer:
    # 强制要求多源验证
    pending_tool_calls.append({
        "function": {
            "name": "multi-source-verify",
            "arguments": json.dumps({
                "answer": extracted_answer,
                "query": user_query
            })
        }
    })
```

---

### 方案 4：压缩 Skills 提示词并强化调用引导

**改动**：在 system prompt 中明确强制调用规则

```python
# 优化后的提示词
"""
### Skills 强制调用规则
1. **smart-search**: 满足以下任一条件时必须调用
   - 用户问题超过 20 个字
   - 问题包含"哪一年"、"谁是"、"列出"
   - 首次搜索失败后

2. **multi-source-verify**: 满足以下任一条件时必须调用
   - 答案包含人名/日期/数字
   - 准备输出 Final Answer 前

3. **chain-of-verification**: 满足以下任一条件时必须调用
   - 问题涉及 A→B→C 链式推理
   - 置信度 < 0.8
"""
```

---

## 推荐实施优先级

| 优先级 | 方案 | 预期效果 |
|--------|------|----------|
| P0 | 方案 4（强化调用引导） | 快速见效，改动小 |
| P0 | 方案 2（自动触发规则） | 强制使用，减少遗漏 |
| P1 | 方案 1（直接暴露工具） | 降低调用门槛 |
| P2 | 方案 3（强制多源验证） | 提升准确性 |

---

## 验证方式

添加日志追踪 skill 调用：

```python
# 在 executor.py 中
if func_name == "execute_script":
    skill_name = parsed_args.get("skill_name")
    print(f"[SkillCall] {skill_name} called at step {state['step_index']}")
```

监控指标：
- 每天 skill 调用次数
- 各 skill 调用频率分布
- 调用后答案质量提升比例
