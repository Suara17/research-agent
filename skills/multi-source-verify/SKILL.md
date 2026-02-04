---
name: multi-source-verify
description: 多源验证答案准确性。当需要确认关键事实（人名、日期、数字）时使用，要求至少2个独立来源支持。
---

# 多源验证技能 (Multi-Source Verification)

## 使用场景

- 需要验证关键事实的准确性（人名、日期、金额、数量）
- 初步答案置信度不足时
- 发现信息源之间存在冲突时
- 用户明确要求"验证"或"确认"时

## 核心原则

1. **至少2个独立来源** - 关键信息必须有≥2个不同域名的来源确认
2. **来源质量评估** - 优先级：.edu/.gov > 权威媒体 > 百科 > 博客/社交媒体
3. **一致性检查** - 不同来源的信息必须一致，如有冲突需解决
4. **证据链记录** - 每个结论标注来源URL

## 工作流程

### 第一步：提取候选答案的关键实体

```
[分析] 候选答案: "Adrian Bowyer 在 2005 年发明了 RepRap 3D打印机"
[提取] 关键实体:
  - 人名: Adrian Bowyer
  - 时间: 2005
  - 发明物: RepRap 3D打印机
```

### 第二步：多角度搜索验证

对每个关键实体进行验证搜索：

```
[搜索1] multi_strategy_search(
    question="Adrian Bowyer RepRap inventor",
    strategy="academic"
)
目标: 确认发明人身份

[搜索2] multi_strategy_search(
    question="RepRap 3D printer history timeline",
    strategy="timeline"
)
目标: 确认发明时间

[搜索3] web_search("RepRap project founded site:edu OR site:org")
目标: 获取权威学术来源
```

### 第三步：深度阅读权威来源

```
[行动] 从搜索结果中选择Top 3权威来源：
  1. Wikipedia: https://en.wikipedia.org/wiki/RepRap_project
  2. 官方网站: https://reprap.org/wiki/About
  3. 学术论文: https://xxx.edu/papers/reprap.pdf

[行动] 对每个来源使用 web_fetch 获取全文

[证据提取]
来源1 (Wikipedia, 可信度0.8):
  - "The RepRap project was founded in 2005 by Adrian Bowyer"
  - 支持实体: ✓ Adrian Bowyer, ✓ 2005

来源2 (RepRap官网, 可信度0.85):
  - "Dr. Adrian Bowyer, a Senior Lecturer at the University of Bath, started the RepRap Project in 2005"
  - 支持实体: ✓ Adrian Bowyer, ✓ 2005
  - 额外信息: University of Bath

来源3 (学术论文, 可信度0.95):
  - "RepRap (Replicating Rapid Prototyper) was initiated by Adrian Bowyer in 2005"
  - 支持实体: ✓ Adrian Bowyer, ✓ 2005
```

### 第四步：一致性检查

```
[验证结果]
✓ 人名 "Adrian Bowyer": 3/3 来源一致
✓ 时间 "2005": 3/3 来源一致
✓ 发明物 "RepRap": 3/3 来源一致

[置信度计算]
- 来源数量: 3 (≥2, 通过)
- 平均可信度: (0.8 + 0.85 + 0.95) / 3 = 0.87
- 一致性: 100% (无冲突)

最终置信度: 0.87 (高)
```

### 第五步：输出验证结论

```
[验证通过]
答案: Adrian Bowyer 在 2005 年发明了 RepRap 3D打印机
置信度: 0.87
支持证据:
  1. Wikipedia - https://en.wikipedia.org/wiki/RepRap_project
  2. RepRap官网 - https://reprap.org/wiki/About
  3. 学术论文 - https://xxx.edu/papers/reprap.pdf
```

## 处理冲突信息

如果发现来源之间存在冲突：

```
[冲突检测]
来源A: "发明于2004年"
来源B: "发明于2005年"
来源C: "发明于2005年"

[解决策略]
1. 统计多数: 2/3 支持 2005
2. 评估可信度:
   - 来源A (博客, 0.4)
   - 来源B (Wikipedia, 0.8)
   - 来源C (官网, 0.85)
3. 加权投票: 0.8 + 0.85 > 0.4

[结论] 采用 "2005", 忽略低可信度的 "2004"

[继续验证] 搜索第4个来源确认
```

## 验证失败处理

如果无法获得≥2个来源支持：

```
[验证失败]
原因: 仅找到1个来源支持 "XXX"

[行动]
1. 改变搜索策略:
   - 切换语言 (中文→英文)
   - 使用同义词
   - 搜索相关实体

2. 降低验证标准 (谨慎):
   - 如果唯一来源是 .edu/.gov (可信度≥0.9)
   - 且无其他冲突信息
   - 可以接受单一来源

3. 诚实告知:
   如果反复尝试仍无法验证，输出:
   "基于现有证据，最可能的答案是XXX (仅1个来源支持，置信度中等)"
```

## 数字类答案特殊处理

对于年份、金额、数量等数字答案：

```
[验证流程]
1. 从多个来源提取所有数字
2. 统计数字出现频率
3. 要求≥2个来源报告相同数字

[示例]
问题: "人类基因组计划花费了多少钱?"

来源1: "$2.7 billion"
来源2: "approximately 2.7 billion dollars"
来源3: "$300 million initially, later expanded to $2.7B"

[统计]
$2.7 billion: 3次出现 ✓
$300 million: 1次出现 (初始预算，不是总花费)

[结论] 27亿美元 (3个来源一致)
```

## 检查清单

在验证完成前，确认：

- [ ] 至少2个独立来源（不同域名）
- [ ] 所有来源可信度 > 0.4
- [ ] 平均可信度 ≥ 0.6
- [ ] 关键实体在所有来源中一致
- [ ] 无未解决的冲突信息
- [ ] 记录了所有证据来源URL

## 输出格式

```
### 验证结果

**答案**: [最终验证的答案]

**置信度**: [0.0-1.0分数]

**支持证据**:
1. [来源名称] - [URL] (可信度: X.X)
   提取内容: "引用原文片段"

2. [来源名称] - [URL] (可信度: X.X)
   提取内容: "引用原文片段"

**验证状态**: ✓ 通过 / ⚠️ 部分通过 / ✗ 失败
```

## 常见错误

❌ **错误1**: 仅搜索不读取
```
web_search("RepRap inventor")
→ 看到摘要 "Adrian Bowyer"
→ 直接输出答案 ✗
```

✅ **正确做法**:
```
web_search("RepRap inventor")
→ 获取3个候选URL
→ web_fetch(每个URL)
→ 提取并对比信息
→ 验证一致性后输出 ✓
```

❌ **错误2**: 只验证一个实体
```
问题: "谁在哪一年发明了XXX?"
→ 只验证"谁" (人名)
→ 忽略"哪一年" ✗
```

✅ **正确做法**:
```
→ 验证人名 (2个来源)
→ 验证年份 (2个来源)
→ 验证发明物 (2个来源) ✓
```

## 高级技巧

### 技巧1: 交叉验证链

```
[策略] 不仅验证答案，还验证答案的上下文

问题: "谁发明了RepRap?"
答案候选: "Adrian Bowyer"

[验证链]
1. 验证 Adrian Bowyer 是发明人 ✓
2. 验证 Adrian Bowyer 的职业 (应该是工程师/教授)
3. 验证 Adrian Bowyer 的所在机构 (University of Bath)
4. 验证 RepRap 项目启动时间与 Bowyer 的职业时间线一致

如果任何一环断裂 → 重新审视答案
```

### 技巧2: 时间一致性检查

```
[检查] 事件的时间顺序是否合理

示例:
- 发明人出生: 1952年
- 发明时间: 2005年
- 发明人年龄: 2005 - 1952 = 53岁 ✓ 合理

如果计算出发明人当时只有5岁 → 必然错误
```

### 技巧3: 反向验证

```
[策略] 不仅验证答案正确，还要验证其他候选答案错误

问题: "谁发明了RepRap?"
答案候选: "Adrian Bowyer"

[反向搜索]
web_search("RepRap inventor NOT Bowyer")
→ 检查是否有其他声称的发明人
→ 如果有，分析为何不是正确答案
→ 增强对 Bowyer 答案的信心
```

## 完整示例

```
用户问题: "2023年诺贝尔物理学奖得主的主要贡献是什么?"

[Step 1: 分析]
关键实体:
- 年份: 2023
- 奖项: 诺贝尔物理学奖
- 需要信息: 得主 + 贡献

[Step 2: 多角度搜索]
搜索1: multi_strategy_search("2023 Nobel Prize Physics", strategy="news")
搜索2: web_search("2023 Nobel Prize Physics site:nobelprize.org")
搜索3: multi_strategy_search("2023诺贝尔物理学奖", strategy="news")

[Step 3: 提取候选来源]
1. https://www.nobelprize.org/prizes/physics/2023/ (可信度: 0.95)
2. https://www.nature.com/articles/d41586-023-03046-0 (可信度: 0.90)
3. https://www.bbc.com/news/science-environment-67000000 (可信度: 0.85)

[Step 4: 深度阅读]
web_fetch("https://www.nobelprize.org/prizes/physics/2023/")
提取:
- 得主: Pierre Agostini, Ferenc Krausz, Anne L'Huillier
- 贡献: "for experimental methods that generate attosecond pulses of light"

web_fetch("https://www.nature.com/articles/d41586-023-03046-0")
提取:
- 贡献: "attosecond physics" "studying electron dynamics"

web_fetch(BBC链接)
提取:
- 贡献: "attosecond pulses of light" "electron movements"

[Step 5: 一致性检查]
核心关键词统计:
- "attosecond": 3/3 ✓
- "electron dynamics/movements": 2/3 ✓
- "pulses of light": 3/3 ✓

[Step 6: 验证结论]
答案: 产生用于研究物质中电子动力学的阿秒光脉冲的实验方法

置信度: 0.90

支持证据:
1. 诺贝尔官网 (0.95) - 官方表述
2. Nature期刊 (0.90) - 学术解读
3. BBC新闻 (0.85) - 科普表述

验证状态: ✓ 通过 (3个独立来源一致)
```

## 记住

> **质量 > 速度**
> 宁可多花2-3步验证，也不要输出未经确认的答案。
> 多源验证是确保准确性的最可靠方法。
