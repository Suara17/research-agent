---
name: smart-search
description: 高级推理搜索工具。专为复杂谜语、实体链接、跨语言检索和多跳推理问题设计。能够自动提取关键词、生成多语言查询并针对特定领域（学术/时间线/娱乐）进行优化。
---

# Smart Search Skill (高级版)

## 核心能力
本技能不只是简单的搜索，而是针对**复杂描述性问题**（如 "一个出生在...的作家..."）的**解题器**。它会自动将自然语言描述转化为搜索引擎能理解的结构化查询。

## 适用场景 (Benchmark Analysis)

1.  **谜语型实体搜索 (Riddle/Entity Linking)**
    * *用户问*: "一位欧洲学者的某项开源硬件项目，灵感源于元胞自动机..."
    * *技能解*: 自动提取 "European scholar", "open source hardware", "cellular automaton"，并生成组合查询。
2.  **跨语言/特定格式检索 (Cross-Lingual)**
    * *用户问*: (中文描述) "...请回答该实体的英文名称。"
    * *技能解*: 强制搜索英文源 (site:en.wikipedia.org)，寻找 English name。
3.  **时间锚定 (Timeline Anchoring)**
    * *用户问*: "事件发生的那一年，某软件巨头..."
    * *技能解*: 生成针对年份和历史事件的精确查询。

## 策略说明

本技能会自动识别以下策略，无需人工干预：

| 策略代码 | 触发场景 | 优化逻辑 |
| :--- | :--- | :--- |
| **riddle** | 长难句、多属性描述、"Who is..." | 提取核心名词，去除停用词，强制使用 Wikipedia/百度百科源。 |
| **timeline** | 询问年份、"In the same year" | 增加 "date", "year", "timeline" 关键词，侧重历史记录。 |
| **academic** | 论文、期刊、研究、学者 | 锁定 .edu/.org 域名，增加 "paper", "dissertation" 等后缀。 |
| **entertainment** | 影视、游戏、动漫、配音 | 锁定 IMDb, 豆瓣, Fandom 等垂直数据库。 |

## 最佳实践 (Agent 指南)

当处理复杂问题时，请遵循以下 **"搜索-观察-推理"** 循环：

1.  **初次搜索**: 直接使用 `smart-search`，传入用户的原始长问题和已知的实体。
    * *Input*: `query="一位欧洲学者的..."`, `entities=["开源硬件"]`
2.  **观察结果**: 工具会返回 3-5 个优化后的 Query（包含关键词组合）。
    * *系统行为*: 工具会自动尝试 "Keywords English name" 或 "Keywords wiki"。
3.  **二次验证**: 如果初次搜索找到了候选人（例如 "Adrian Bowyer"），但需要确认细节（如"2010年中期交易情况"），请再次调用本工具，但这次将候选人作为实体传入。
    * *Input*: `query="Adrian Bowyer business entity 2010s"`, `entities=["Adrian Bowyer"]`

## 参数说明

* `query` (必填): 用户的原始问题或需要查证的描述。**注意：即使问题很长，也请完整传入，工具内置了关键词提取算法。**
* `entities` (选填): 你已经识别出的明确实体列表（如人名、地名、书名）。这有助于提高搜索精度。

## 示例

**输入**:
```json
{
  "query": "一位在16世纪统治着一个庞大帝国的君主，曾因一种慢性关节疾病而尝试过...",
  "entities": ["16世纪", "帝国"]
}

```

**工具内部逻辑**:

1. 检测到长描述 -> 激活 **riddle** 策略。
2. 提取关键词 -> "16th century monarch", "chronic joint disease", "empire"。
3. 生成 Query:
* `16th century monarch chronic joint disease empire`
* `"16世纪" "帝国" 关节疾病`
* `monarch joint disease history wiki`



**输出**:
返回优化后的查询列表，供 Agent 调用底层 Web Search。

```

### 总结

这份优化的核心在于**“承认搜索引擎的局限性”**。搜索引擎不理解复杂的语法逻辑，只看重关键词共现。
1.  **`run.py`** 变成了一个“翻译器”，把人类的复杂谜语翻译成搜索引擎喜欢的“关键词沙拉（Keyword Salad）”。
2.  **`SKILL.md`** 明确了 Agent 在面对长问题时，不要试图自己概括（容易丢失细节），而是把原话交给工具，让工具里的正则和逻辑去处理。
