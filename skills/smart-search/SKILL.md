---
name: smart-search
description: 智能搜索构建器。利用 LLM 将自然语言问题转化为多个高精度的搜索引擎查询（Query）。支持意图识别、列表生成（防止过早收敛）、跨语言关键词提取和特定站点（Wiki/Edu）过滤。
---

# Smart Search Skill (v3 结构化版)

## 核心价值
本工具解决了 Agent "直接搜整句搜不到" 和 "搜到错误答案（过早收敛）" 的痛点。
它**不执行搜索**，而是**生成最好的搜索词**供你使用。

## 适用场景

1.  **列表-筛选模式 (List-then-Filter)** [最重要]
    * *问题*: "谁是蒙古国那个因亲属财产出丑闻的总理？"
    * *旧做法*: 直接搜整句 -> 搜出奥云额尔登（热门但错误）。
    * *新能力*: 工具会自动生成 `List of Prime Ministers of Mongolia`。
    * *Agent动作*: 你拿到这个 Query 后，去搜列表，然后一个个查，就能找到巴特包勒德。

2.  **谜语型/长难句 (Complex Riddle)**
    * *问题*: "一个20世纪90年代生效宪法并在2019年修宪的国家的元首..."
    * *新能力*: 提取结构化关键词 `Constitution 1990s effective` AND `2019 amendment` AND `Head of State`。

3.  **跨语言检索 (Cross-Lingual)**
    * *问题*: (中文) "...该实体的英文名称是什么？"
    * *新能力*: 自动翻译关键词并生成 `[Keywords] English Name` 或 `site:en.wikipedia.org` 查询。

## 使用指南 (Agent Prompt)

**何时调用？**
* 当用户问题超过 20 个字时。
* 当你尝试搜索一次但没有找到明确答案时。
* 当问题包含 "哪一年", "谁是", "列出" 等明确意图时。

**输入参数:**
* `query` (必填): 用户的原始自然语言问题，或者你推理出的中间问题。
* `entities` (选填): 你已经确认的实体（如 "蒙古国"），这能帮助工具生成更准的 Query。
* `excluded_entities` (选填): 需要排除的实体列表（如 ["Mongolia", "Batbold"]）。
* `feedback` (选填): 上一次搜索失败的原因或拒绝理由（如 "Failed to find family assets", "Answer rejected because..."）。

**如何处理输出 (`optimized_queries`)?**
工具会返回一个列表，通常包含 3-5 个 Query。
1.  **优先执行列表型 Query** (如包含 "List of...", "Timeline of...")。
2.  **其次执行精确关键词 Query**。
3.  **最后执行宽泛的 Wiki Query**。

## 示例

**输入**:
```json
{
  "query": "一位曾在海外知名学府深造的政府首脑，其政治生涯因亲属财产风波受挫...",
  "entities": ["政府首脑", "亲属财产"],
  "feedback": "Search for 'Mongolia' failed to verify family assets details. Try other countries."
}
```

**输出 (Example)**:
```json
{
  "status": "success",
  "optimized_queries": [
    "List of Heads of Government studied abroad scandal -Mongolia",
    "Prime Minister relatives assets scandal offshore -Mongolia",
    "Government leader corruption mining investigation -Mongolia",
    "site:wikipedia.org Head of Government scandal -Mongolia"
  ]
}
```
