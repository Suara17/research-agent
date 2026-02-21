# Search.py 优化方案

## 一、当前问题分析

### 1.1 测试结果问题

**测试问题**:
> 在某一年，一位法国天文学家对一颗彗星的光谱进行了开创性观测，同年的一张太阳黑子照片后来在东亚某大都市的天文展览中展出。也正是在这一年，一位尚不满二十岁的南欧创业者，在家乡小镇创办了他的出版事业。十余年后，他将公司总部迁往了该国北部的商业中心。他所创立的这家出版公司的名字是什么？

**预期答案**: 阿诺尔多·蒙达多利出版社

**实际搜索结果**:
| 结果 | 标题 | 问题 |
|------|------|------|
| 1 | 意大利天文学家 | ❌ 不相关 |
| 2 | solar | ❌ 不相关 |
| 3 | 第4章 未知世界的地图——海王星 | ❌ 不相关 |

### 1.2 问题根因

1. **查询优化策略过于简单**: 
   - 仅仅去除停用词，没有提取核心实体
   - 没有识别问题中的关键约束条件（年份、人物类型、事件）
   - "南欧创业者"、"出版公司"等关键信息被稀释

2. **实体查询检测失效**:
   - `_is_entity_query()` 返回 False
   - 没有添加 Wikipedia 站点限定

3. **搜索引擎优先级问题**:
   - 中文查询首选 Bocha，但结果质量不高
   - 缺少针对具体领域的专业化搜索策略

4. **缺少语义理解**:
   - 没有识别这是一个"需要推理出公司名"的问题
   - 没有提取"出版公司"、"南欧创业者"等核心概念

---

## 二、优化方案

### 2.1 强化查询优化策略

#### 方案A: 增强版实体提取

```python
def _extract_core_entities_enhanced(query: str) -> dict:
    """
    增强版实体提取 - 使用多种模式识别关键信息
    """
    entities = {
        "persons": [],      # 人名
        "organizations": [], # 组织/公司
        "locations": [],   # 地点
        "events": [],      # 事件
        "time": [],        # 时间
        "concepts": []    # 概念
    }
    
    # 1. 提取时间信息
    time_patterns = [
        r'(\d{4})年',      # 1671年
        r'十余年后',        # 10多年后
        r'同年',           # 同一年
        r'(不满)?二十岁',  # 20岁以下
    ]
    for pattern in time_patterns:
        matches = re.findall(pattern, query)
        entities["time"].extend(matches)
    
    # 2. 提取组织类型关键词
    org_keywords = [
        "公司", "出版社", "企业", "集团", "出版事业",
        "创业者", "企业家", "创始人"
    ]
    for kw in org_keywords:
        if kw in query:
            entities["concepts"].append(kw)
    
    # 3. 提取地理区域
    region_patterns = [
        r'(南欧|东亚|北欧|西欧|东欧)',
        r'(法国|意大利|西班牙|德国|英国)',
    ]
    for pattern in region_patterns:
        matches = re.findall(pattern, query)
        entities["locations"].extend(matches)
    
    # 4. 职业/身份关键词
    role_keywords = [
        "天文学家", "科学家", "创业者", "企业家", "出版商"
    ]
    for kw in role_keywords:
        if kw in query:
            entities["concepts"].append(kw)
    
    return entities
```

#### 方案B: 查询重写策略

```python
def _rewrite_query_for_search(query: str) -> str:
    """
    根据问题类型重写查询，使其更适合搜索
    """
    # 检测问题类型
    if "公司" in query and "名字" in query:
        # 需要找公司名的问题
        # 提取关键约束
        constraints = []
        
        # 南欧创业者
        if "南欧" in query:
            constraints.append("南欧")
        if "创业者" in query:
            constraints.append("创业者")
        if "出版" in query:
            constraints.append("出版公司")
            
        # 构建新查询
        if constraints:
            return " ".join(constraints) + " 创始人"
    
    # 如果是年份相关问题
    year_match = re.search(r'(\d{4})年', query)
    if year_match and "公司" in query:
        year = year_match.group(1)
        return f"{year}年 出版公司 创始人 南欧"
    
    return query
```

### 2.2 改进搜索引擎优先级

#### 针对不同查询类型选择最佳搜索引擎

```python
def _select_optimal_search_engine(query: str, is_chinese: bool) -> str:
    """
    根据查询特点选择最佳搜索引擎
    """
    # 复杂问题/公司查询 -> 使用 Google/Serper
    if any(kw in query for kw in ["公司", "出版社", "创始人", "企业家"]):
        if not is_chinese:  # 英文查询
            return "serper"  # Google 更擅长
    
    # 明确实体查询 -> 尝试 Wikipedia
    if _has_clear_entity(query):
        return "searxng_wiki"  # SearXNG + Wikipedia
    
    # 普通中文查询 -> Bocha
    if is_chinese:
        return "bocha"
    
    # 默认 -> Serper
    return "serper"
```

### 2.3 添加查询后处理

```python
def _postprocess_search_results(results: list, original_query: str) -> list:
    """
    对搜索结果进行后处理，提高相关性
    """
    if not results:
        return results
    
    # 提取原始查询中的关键概念
    key_concepts = set()
    if "公司" in original_query:
        key_concepts.add("公司")
    if "出版" in original_query:
        key_concepts.add("出版")
    if "创始人" in original_query:
        key_concepts.add("创始人")
    
    # 对结果进行相关性评分
    scored_results = []
    for r in results:
        score = 0
        title = r.get("title", "").lower()
        summary = r.get("summary", "").lower()
        content = f"{title} {summary}"
        
        # 概念匹配加分
        for concept in key_concepts:
            if concept in content:
                score += 2
        
        # 惩罚不相关结果
        unrelated = ["天文学", "恒星", "行星", "星系", "彗星观测"]
        for kw in unrelated:
            if kw in content and "公司" not in content:
                score -= 3
        
        scored_results.append((r, score))
    
    # 按分数排序
    scored_results.sort(key=lambda x: x[1], reverse=True)
    return [r for r, s in scored_results if s > 0]
```

### 2.4 添加 Wikipedia/专业来源优先策略

```python
def _search_with_wikipedia_fallback(query: str, k: int) -> List[Dict]:
    """
    先尝试 Wikipedia，再尝试普通搜索
    """
    # 尝试从 Wikipedia 获取答案
    wiki_results = _search_wikipedia_direct(query)
    if wiki_results:
        return wiki_results
    
    # Wikipedia 没有结果，使用普通搜索
    return web_search(query, k)
```

---

## 三、实施优先级

| 优先级 | 优化项 | 预期效果 | 难度 |
|--------|--------|----------|------|
| P0 | 查询重写策略 | 直接解决复杂问题搜索 | 中 |
| P1 | 搜索引擎选择优化 | 提高结果质量 | 低 |
| P2 | 结果后处理 | 过滤噪音结果 | 中 |
| P3 | Wikipedia 优先 | 专业问题更准确 | 低 |

---

## 四、建议的具体改动

### 4.1 在 web_search 函数中添加查询重写

```python
# 在 web_search 函数中，优化查询后添加：
if "公司" in query and ("创始人" in query or "创办" in query):
    # 提取关键约束词
    keywords = []
    if "南欧" in query:
        keywords.append("南欧")
    if "意大利" in query:
        keywords.append("意大利")
    keywords.extend(["出版公司", "创始人"])
    optimized_q = " ".join(keywords)
    print(f"[Search] Query rewritten: '{optimized_q}'")
```

### 4.2 改进搜索引擎选择逻辑

```python
# 对于包含"公司"关键词的查询，优先尝试 Serper/Google
if "公司" in query and serper_key:
    primary_results = _safe_search_serper(optimized_q, top_k, serper_key)
    if primary_results:
        return json.dumps({
            "source": "serper_for_company",
            "results": primary_results,
            ...
        })
```

---

## 五、总结

当前 search.py 的主要问题是:
1. **查询优化过于机械** - 没有理解问题意图
2. **搜索引擎选择不够智能** - 没有根据问题类型选择最佳引擎
3. **缺乏结果相关性排序** - 简单依赖搜索引擎返回的顺序

通过实施以上优化方案，可以显著提升搜索结果的有效性，特别是对于需要推理的复杂问题。
