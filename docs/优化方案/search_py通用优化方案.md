# Search.py 通用优化方案

## 一、问题分析

### 1.1 Question.jsonl 概览

| 统计项 | 数值 |
|--------|------|
| 总问题数 | 100 |
| 中文问题 | ~40 |
| 英文问题 | ~60 |

### 1.2 问题类型分布

| 问题类型 | 示例 | 占比 |
|----------|------|------|
| 实体查询（谁/什么） | "这家公司叫什么？" | ~60% |
| 时间查询（哪一年） | "这是哪一年发生的？" | ~15% |
| 数量查询（多少） | "有多少人？" | ~5% |
| 地点查询（在哪里） | "在哪个城市？" | ~10% |
| 其他复合问题 | 多约束推理题 | ~10% |

### 1.3 问题结构特征

```
问题结构模式分析：

【模式1】多约束推理型 (70%)
├── 时间约束：某年、同年、十余年后
├── 地点约束：东亚、欧洲、南欧
├── 人物约束：创业者、天文学家
├── 事件约束：创办、迁移、死亡
└── 目标约束：公司名、人名、地名

【模式2】单一实体型 (20%)
├── 直接问：xxx是谁？
├── 书名号：《xxx》
└── 引号："xxx"

【模式3】技术细节型 (10%)
├── 专业术语
├── 学术论文
└── 科学概念
```

### 1.4 当前问题根因分析

| 问题 | 原因 | 影响 |
|------|------|------|
| 查询优化过于机械 | 只去除停用词 | 关键约束被稀释 |
| 实体检测失效 | 复杂问句不匹配模式 | 无Wikipedia限定 |
| 搜索引擎选择不当 | 中文首选Bocha | 结果质量不稳 |
| 无结果后处理 | 依赖引擎排序 | 相关性低 |

---

## 二、通用优化方案

### 2.1 核心策略：问题类型分类器

```python
def classify_query_type(query: str) -> dict:
    """
    分类查询类型，返回优化策略
    """
    query_type = {
        "type": "unknown",           # entity/time/number/location/compound
        "is_chinese": False,
        "has_time_constraint": False,
        "has_location_constraint": False,
        "has_person_constraint": False,
        "has_org_constraint": False,
        "target_type": "unknown",    # person/company/place/year/number
        "search_strategy": "default"
    }
    
    # 检测语言
    query_type["is_chinese"] = any("\u4e00" <= ch <= "\u9fff" for ch in query[:50])
    
    # 检测时间约束
    time_patterns = [r"\d{4}年", r"同年", r"十余年后", r"世纪初", r"年代"]
    query_type["has_time_constraint"] = any(re.search(p, query) for p in time_patterns)
    
    # 检测地点约束
    location_patterns = [r"东亚|南欧|北欧|西欧|欧洲|亚洲|北美", r"国家|城市|首都"]
    query_type["has_location_constraint"] = any(re.search(p, query) for p in location_patterns)
    
    # 检测组织/公司约束
    org_patterns = [r"公司|出版社|企业|集团|机构|组织"]
    query_type["has_org_constraint"] = any(re.search(p, query) for p in org_patterns)
    
    # 检测人物约束
    person_patterns = [r"创业者|企业家|天文学家|科学家|政治家|艺术家"]
    query_type["has_person_constraint"] = any(re.search(p, query) for p in person_patterns)
    
    # 判断目标类型
    if any(kw in query for kw in ["公司", "出版社", "企业", "机构", "组织"]):
        query_type["target_type"] = "company"
    elif any(kw in query for kw in ["谁", "人名", "人物", "作者", "创始人"]):
        query_type["target_type"] = "person"
    elif any(kw in query for kw in ["哪一年", "年份", "年", "时间"]):
        query_type["target_type"] = "year"
    elif any(kw in query for kw in ["哪里", "城市", "地点", "位置"]):
        query_type["target_type"] = "location"
    elif query.endswith("?"):
        # 问句可能是实体查询
        query_type["target_type"] = "entity"
    
    # 判断问题类型
    if query_type["has_time_constraint"] or query_type["target_type"] == "year":
        query_type["type"] = "time"
    elif query_type["has_org_constraint"] or query_type["target_type"] == "company":
        query_type["type"] = "organization"
    elif query_type["has_person_constraint"] or query_type["target_type"] == "person":
        query_type["type"] = "person"
    
    # 选择搜索策略
    if query_type["type"] == "organization" or query_type["target_type"] == "company":
        query_type["search_strategy"] = "company_focused"
    elif query_type["type"] == "person":
        query_type["search_strategy"] = "person_focused"
    elif query_type["type"] == "time":
        query_type["search_strategy"] = "time_focused"
    else:
        query_type["search_strategy"] = "general"
    
    return query_type
```

### 2.2 策略1：智能查询重写

```python
def smart_query_rewrite(query: str, query_type: dict) -> str:
    """
    根据问题类型智能重写查询
    """
    if query_type["search_strategy"] == "company_focused":
        # 公司/组织类问题 - 提取关键约束
        keywords = []
        
        # 提取地点约束
        locations = re.findall(r"(东亚|南欧|北欧|西欧|日本|意大利|法国|德国|英国|美国|西班牙)", query)
        keywords.extend(locations)
        
        # 提取组织类型
        if "出版" in query:
            keywords.append("出版社")
        if "科技" in query:
            keywords.append("科技公司")
        
        # 提取时间约束
        year_match = re.search(r"(\d{4})年", query)
        if year_match:
            keywords.append(f"{year_match.group(1)}年")
        
        # 提取人物角色
        if "创业者" in query or "创始人" in query:
            keywords.append("创始人")
        
        if keywords:
            return " ".join(keywords)
    
    elif query_type["search_strategy"] == "person_focused":
        # 人物类问题 - 提取职业/身份约束
        keywords = []
        
        # 提取职业
        roles = re.findall(r"(天文学家|科学家|政治家|艺术家|作家|企业家)", query)
        keywords.extend(roles)
        
        # 提取国籍/地区
        nationalities = re.findall(r"(法国|意大利|德国|英国|美国|欧洲|亚洲)", query)
        keywords.extend(nationalities)
        
        if keywords:
            return " ".join(keywords)
    
    elif query_type["search_strategy"] == "time_focused":
        # 时间类问题 - 提取事件+年份
        keywords = []
        
        # 提取年份
        years = re.findall(r"\d{4}年", query)
        keywords.extend(years)
        
        # 提取事件
        events = re.findall(r"([^，,。]+)发生|([^，,。]+)成立|([^，,。]+)创办", query)
        for event in events:
            keywords.extend([e for e in event if e])
        
        if keywords:
            return " ".join(keywords)
    
    # 默认：使用原始优化
    return _optimize_search_query(query)
```

### 2.3 策略2：动态搜索引擎选择

```python
def select_best_search_engine(query: str, query_type: dict) -> str:
    """
    根据问题类型选择最佳搜索引擎
    """
    # 英文问题 + 实体查询 -> Serper (Google)
    if not query_type["is_chinese"] and query_type["target_type"] != "year":
        return "serper"
    
    # 公司/组织类问题 -> Serper (通常Google对这类查询效果更好)
    if query_type["search_strategy"] == "company_focused":
        return "serper"
    
    # 时间类问题 -> SearXNG (支持精确时间过滤)
    if query_type["search_strategy"] == "time_focused":
        return "searxng"
    
    # 人物类问题 -> Wikipedia优先
    if query_type["search_strategy"] == "person_focused":
        return "searxng_wiki"
    
    # 中文普通问题 -> Bocha
    if query_type["is_chinese"]:
        return "bocha"
    
    # 默认 -> Serper
    return "serper"
```

### 2.4 策略3：多阶段搜索策略

```python
def multi_stage_search(query: str, query_type: dict, top_k: int) -> list:
    """
    多阶段搜索：先精确后泛化
    """
    results = []
    
    # 阶段1：精确搜索
    exact_query = smart_query_rewrite(query, query_type)
    if exact_query and exact_query != query:
        exact_results = _execute_search(exact_query, top_k, query_type)
        results.extend(exact_results)
    
    # 阶段2：如果结果不足，尝试原始查询
    if len(results) < top_k:
        fallback_results = _execute_search(query, top_k, query_type)
        results.extend(fallback_results)
    
    # 阶段3：Wikipedia补充（针对人物/组织）
    if query_type["target_type"] in ["person", "company"]:
        wiki_results = _search_wikipedia_fallback(query, 2)
        results.extend(wiki_results)
    
    # 去重和排序
    return _deduplicate_and_rank(results, top_k)
```

### 2.5 策略4：结果相关性重排

```python
def rerank_results(results: list, query: str, query_type: dict) -> list:
    """
    基于问题类型对结果进行相关性重排
    """
    if not results:
        return results
    
    # 提取关键概念
    key_concepts = set()
    
    # 根据目标类型添加概念
    if query_type["target_type"] == "company":
        key_concepts.update(["公司", "出版社", "集团", "企业", "corporation", "company"])
    elif query_type["target_type"] == "person":
        key_concepts.update(["人", "作者", "创始人", "person", "founder"])
    elif query_type["target_type"] == "year":
        key_concepts.update(["年", "年份", "year"])
    
    # 根据搜索策略添加概念
    for strategy, concepts in {
        "company_focused": ["创办", "创始人", "总部"],
        "person_focused": ["出生于", "逝世", "著名"],
        "time_focused": ["发生", "成立", "创建"]
    }.items():
        if query_type["search_strategy"] == strategy:
            key_concepts.update(concepts)
    
    # 评分
    scored = []
    for r in results:
        score = 0
        content = (r.get("title", "") + " " + r.get("summary", "")).lower()
        
        # 正向匹配
        for concept in key_concepts:
            if concept.lower() in content:
                score += 1
        
        # 惩罚不相关（根据问题类型）
        if query_type["target_type"] == "company":
            # 惩罚天文学、科学等不相关领域
            if any(kw in content for kw in ["天文学", "恒星", "行星", "astronomy"]):
                if "公司" not in content and "corporation" not in content:
                    score -= 2
        
        scored.append((r, score))
    
    # 排序并返回
    scored.sort(key=lambda x: x[1], reverse=True)
    return [r for r, s in scored if s >= 0]
```

---

## 三、实施架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Query Analysis Layer                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ Language    │  │ Type        │  │ Constraint  │       │
│  │ Detection   │→ │ Classification│→│ Extraction │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Query Rewrite Layer                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ Company     │  │ Person      │  │ Time        │       │
│  │ Rewriter    │  │ Rewriter    │  │ Rewriter    │       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Search Engine Layer                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
│  │ Serper  │  │ Bocha   │  │SearXNG │  │Wiki API │     │
│  │ (Google)│  │ (中文)  │  │ (混合)  │  │ (百科)  │     │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   Result Process Layer                      │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ Deduplicate │  │ Re-rank     │  │ Filter     │       │
│  │ & Merge     │  │ by Type     │  │ Low Quality│       │
│  └─────────────┘  └─────────────┘  └─────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、优先级实施计划

| 阶段 | 优先级 | 优化项 | 预期效果 |
|------|--------|--------|----------|
| Phase 1 | P0 | 问题类型分类器 | 理解问题意图 |
| Phase 1 | P0 | 智能查询重写 | 提取关键约束 |
| Phase 2 | P1 | 动态搜索引擎选择 | 匹配最佳引擎 |
| Phase 2 | P1 | 多阶段搜索 | 提高召回率 |
| Phase 3 | P2 | 结果相关性重排 | 提升准确率 |

---

## 五、代码改动要点

### 5.1 新增函数

```python
# research_agent/search.py 新增

def _classify_query_type(query: str) -> dict:
    """问题类型分类"""
    pass

def _smart_query_rewrite(query: str, query_type: dict) -> str:
    """智能查询重写"""
    pass

def _select_best_search_engine(query: str, query_type: dict) -> str:
    """选择最佳搜索引擎"""
    pass

def _multi_stage_search(query: str, query_type: dict, top_k: int) -> list:
    """多阶段搜索"""
    pass

def _rerank_by_query_type(results: list, query: str, query_type: dict) -> list:
    """按问题类型重排"""
    pass
```

### 5.2 修改 web_search 函数

```python
def web_search(query: str, top_k: int = 5) -> str:
    # 1. 分类问题类型
    query_type = _classify_query_type(query)
    
    # 2. 智能重写查询
    optimized_q = _smart_query_rewrite(query, query_type)
    
    # 3. 选择最佳搜索引擎
    engine = _select_best_search_engine(query, query_type)
    
    # 4. 执行多阶段搜索
    results = _multi_stage_search(optimized_q, query_type, top_k)
    
    # 5. 结果重排
    results = _rerank_by_query_type(results, query, query_type)
    
    return json.dumps({"results": results, ...})
```

---

## 六、测试验证

### 6.1 测试问题分类

```python
test_queries = [
    # 公司类
    "一家在21世纪20年代初收购了某重工集团子公司的日本企业...",
    # 人物类
    "一位物理学家任教于华东地区的一所大学...",
    # 时间类
    "在哪一年发生了什么事件...",
    # 实体类
    "What is the name of..."
]
```

### 6.2 评估指标

| 指标 | 目标 |
|------|------|
| 问题类型分类准确率 | > 85% |
| 查询重写有效性 | 相关结果增加 30% |
| 搜索结果相关性 | 前5结果相关率 > 60% |
| 端到端准确率 | 验证集准确率提升 20% |
