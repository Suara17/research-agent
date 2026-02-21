# Agent 推理搜索优化方案

## 架构概览

```
agent.py (多Agent并行)
    ↓
core.py (LangGraph工作流)
    ├→ planner.py (生成搜索计划)
    ├→ agent_node (推理 + 工具调用)
    └→ executor.py (执行工具)
        ↓
search.py (多引擎搜索: SearXNG > Serper > Baidu > DDGS)
answer_synthesis.py (多Agent答案合并)
```

---

## 一、速度优化

### 1.1 合并 Planner 调用

**问题**：Planner 每轮都调用，增加延迟

**方案**：将 Planner 合并到 Agent 首轮内联执行

**改动位置**：`core.py` 的 `agent_node` 函数

```python
# 优化前：每轮都通过 planner_node 生成计划
workflow.add_node("planner", planner_node)
workflow.add_edge("planner", "agent")

# 优化后：首轮在 agent_node 内联生成计划
async def agent_node(state: AgentState) -> dict:
    if not state.get("plan"):
        # 首轮内联调用 planner
        plan_data = await asyncio.to_thread(generate_plan, user_query)
        state["plan"] = plan_data.get("plan", "")
```

**预期效果**：节省 1 次 LLM 调用 (~2秒/轮)

---

### 1.2 压缩系统提示词

**问题**：MULTI_HOP_SYSTEM_PROMPT 过长(~200行)，每轮都发送

**方案**：
1. 提取核心规则为简短指令（<500 tokens）
2. 将详细协议移到外部 skill 或知识库
3. 动态加载：只加载当前阶段需要的协议

**改动位置**：`core.py` 第 41-238 行

```python
# 压缩后的核心提示词示例
COMPRESSED_SYSTEM_PROMPT = """<核心规则>
1. 搜索语言：中文问题用中文搜索，英文问题用英文搜索
2. 锚点优先：先验证最独特/限制性最强的约束
3. 快速失败：搜索2次无进展立即换搜索词/引擎
4. 验证要求：数字必须精确匹配，不接受近似值
5. 回溯触发：5次搜索无进展 / 假设超过2个 / 约束验证失败
</核心规则>"""
```

**预期效果**：减少 ~300 tokens/step，降低延迟和成本

---

### 1.3 并行搜索策略

**问题**：搜索串行执行，SearXNG 失败才用备选

**方案**：同时发起多引擎搜索请求

**改动位置**：`search.py` 的 `web_search` 函数

```python
# 优化后：并行执行所有可用引擎
tasks = []
if searxng_base_url:
    tasks.append(lambda: _safe_search_searxng(optimized_q, top_k, searxng_base_url))
if serper_key:
    tasks.append(lambda: _safe_search_serper(optimized_q, top_k, serper_key))
if _DDGS_AVAILABLE:
    tasks.append(lambda: _safe_search_ddgs(optimized_q, top_k))

# 并行执行
futures = [_FETCH_EXECUTOR.submit(task) for task in tasks]
results = await asyncio.gather(*[asyncio.wrap_future(f) for f in futures])
```

**预期效果**：搜索时间从 max(各引擎) 变为 min(各引擎)

---

### 1.4 批量内容获取

**问题**：内容获取逐个进行

**方案**：搜索结果返回后，并行抓取 top 3 结果

**改动位置**：`search.py` 或 `executor.py`

```python
# 在 executor.py 中优化
async def fetch_multiple_urls(urls: list, max_workers: int = 3):
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, web_fetch, url) for url in urls]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

---

## 二、推理准确性优化

### 2.1 添加工具选择指导

**问题**：Agent 容易陷入搜索循环

**方案**：在提示词中明确"连续2次同类搜索无进展 → 换搜索词/换引擎"

**改动位置**：`core.py` 的 `agent_node`

```python
# 在 system_prompt_addition 中添加
"""
<工具使用策略>
- 搜索连续2次返回相似结果 → 立即换搜索词
- 搜索3次无关键信息 → 尝试不同搜索引擎
- 找到答案线索 → 立即用 web_fetch 抓取验证
</工具使用策略>
"""
```

---

### 2.2 实现 Self-Reflection

**问题**：缺乏主动方向转换

**方案**：每 5 步让 Agent 评估当前进展

**改动位置**：`core.py` 的 `agent_node`

```python
# 在 step_index % 5 == 0 时插入反思
if current_step > 0 and current_step % 5 == 0:
    reflection_prompt = """
    <自我反思>
    1. 过去5步有什么进展？
    2. 是否陷入死胡同？
    3. 是否需要换搜索策略？
    4. 还需要几步能给出答案？
    </自我反思>
    """
    prompt_messages.append({"role": "system", "content": reflection_prompt})
```

---

### 2.3 分级验证

**问题**：验证表检查过于严格导致卡住

**方案**：根据问题复杂度分级处理

| 复杂度 | 特征 | 验证要求 |
|--------|------|----------|
| 简单 | 单实体/单数字 | 直接输出答案 |
| 中等 | 2-3个实体/时间线 | 简单验证表 |
| 复杂 | 多跳/负向约束/交叉验证 | 完整验证表 |

**改动位置**：`core.py` 的 `agent_node`，根据 planner 返回的 complexity 选择验证级别

---

### 2.4 置信度评估

**问题**：没有置信度评估

**方案**：要求 Agent 输出 Final Answer 时附带置信度

```python
# 要求输出格式
"""
当准备输出 Final Answer 时，必须同时输出置信度：
Final Answer: [答案]
Confidence: 0.85

置信度标准：
- 0.9-1.0: 多源确认，数字精确匹配
- 0.7-0.9: 有验证，但来源有限
- 0.5-0.7: 单源或推断
- <0.5: 不应输出答案，继续搜索
"""

# 置信度低于阈值时自动触发多源验证
if confidence < 0.8:
    # 强制调用 multi-source-verify skill
    tool_calls.append({
        "function": {"name": "multi-source-verify", "arguments": json.dumps({"query": user_query})}
    })
```

---

## 三、搜索质量优化

### 3.1 查询优化结果缓存

**问题**：查询优化 LLM 调用频繁

**方案**：缓存相同查询的优化结果

**改动位置**：`search.py` 的 `_optimize_search_query`

```python
import functools

@functools.lru_cache(maxsize=500)
def _optimize_search_query_cached(query: str) -> str:
    return _optimize_search_query_impl(query)

# 缓存有效期5分钟
# 键：query (需要可哈希)
```

---

### 3.2 添加拼写纠错

**问题**：缺乏结果去重

**方案**：搜索前检测明显拼写错误

**改动位置**：`search.py`

```python
# 添加简单拼写检测
COMMON_SPELLING_ERRORS = {
    "googel": "google",
    "googlr": "google",
    "wikepedia": "wikipedia",
    # 可扩展
}

def _fix_spelling(query: str) -> str:
    words = query.split()
    fixed = [COMMON_SPELLING_ERRORS.get(w.lower(), w) for w in words]
    return " ".join(fixed)
```

---

## 四、资源与稳定性

### 4.1 改进多 Agent 合并策略

**问题**：多 Agent 合并逻辑简单

**方案**：比较证据完整度而非只选最长答案

**改动位置**：`answer_synthesis.py`

```python
def synthesize_best_answer(question: str, candidates: list) -> str:
    # 评估每个候选的证据完整度
    scored_candidates = []
    for c in candidates:
        trace = c.get("trace", "")
        # 检查是否有验证表
        has_verification = "CONSTRAINT VERIFICATION TABLE" in trace or "✓" in trace
        # 检查搜索次数
        search_count = trace.count("web_search")
        
        score = 0
        if has_verification:
            score += 2
        score += min(search_count / 10, 1)  # 搜索次数贡献
        
        scored_candidates.append((score, c))
    
    # 选择得分最高的
    best = max(scored_candidates, key=lambda x: x[0])
    return best[1].get("answer", "")
```

---

### 4.2 添加熔断机制

**问题**：LLM 调用无熔断

**方案**：单次请求失败后指数退避

**改动位置**：`core.py` 的 `agent_node`

```python
async def call_llm_with_retry(client, messages, tools, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await asyncio.to_thread(client.chat.completions.create, ...)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # 指数退避
            print(f"[LLM] Retry {attempt+1} after {wait_time}s")
            await asyncio.sleep(wait_time)
```

---

### 4.3 内存定期清理

**问题**：内存无清理

**方案**：每 N 步清理过期的短期记忆

**改动位置**：`core.py` 的 `agent_node`

```python
# 每20步清理短期记忆
if current_step > 0 and current_step % 20 == 0:
    memory.clear_short_term()
    print("[Memory] Short-term memory cleared")
```

---

## 五、快速见效改动清单

| 优先级 | 改动 | 预期效果 |
|--------|------|----------|
| P0 | 合并 Planner 调用 | 节省 ~2秒/轮 |
| P0 | 压缩系统提示词 | 减少 ~300 tokens/step |
| P1 | 并行搜索策略 | 搜索时间减半 |
| P1 | 添加工具使用策略指导 | 减少搜索循环 |
| P1 | 置信度评估 | 提升答案可靠性 |
| P2 | 查询缓存 | 减少 LLM 调用 |
| P2 | 批量内容获取 | 提升信息获取效率 |
| P2 | 多 Agent 合并优化 | 提升答案质量 |

---

## 六、验证方式

1. **基准测试**：使用 20 道多跳问题测试优化前后
2. **指标**：
   - 平均步数（越少越好）
   - 正确答案率（越高越好）
   - 平均耗时（越短越好）
3. **回归测试**：确保简单问题不受影响
