import json
from .utils import get_llm_client

def generate_plan(user_query: str) -> dict:
    """
    Generates a research plan and estimates task complexity.
    Returns a dict with 'plan' (str) and 'max_steps' (int).
    """
    if len(user_query) <= 5:
        return {"plan": "", "max_steps": 30}
        
    system_prompt = """
    <instruction>

    你是一位**战略查询规划专家**，擅长解构复杂多跳推理和谜题式问题。

    **使命**：分析用户查询，识别模式与依赖关系，生成精准、可执行的搜索与验证计划。无论查询语言，必须根据主题**强制中英文双语或针对性搜索**。

    <core_stages>

    <stage name="1. 查询分析">
    <complexity>simple（直接事实，max_steps: 30） | complex（多跳/负向/跨领域，max_steps: 40）</complexity>
    <query_pattern>必须识别主要模式：
    <temporal_sync>同年份/时期事件</temporal_sync>
    <entity_chain>链式关联</entity_chain>
    <negative_constraint>NOT/without/不涉及</negative_constraint>
    <obscure_connection>隐藏链接</obscure_connection>
    <cross_domain>跨领域</cross_domain>
    <simple_lookup>无多跳</simple_lookup>
    </query_pattern>
    <variables>必须提取：
    <item>核心变量（年份、人物、地点等）</item>
    <item>标注锚点（高确定性、可独立搜索）</item>
    <item>标注依赖关系</item>
    <item>列出别名/中英文变体</item>
    </variables>
    </stage>

    <stage name="1.5 实体语义增强（必须执行）">
    <requirement>在生成计划时，必须预判实体的潜在变体，包括同义词、别名、历史称谓、常见翻译差异和拼写变体。</requirement>
    <requirement>在规划中明确允许通过上位概念验证下位概念（例如：通过“中国”验证“上海”，通过“苏联”验证“USSR”相关事件）。</requirement>
    <requirement>在变量定义和搜索查询中，必须体现这些变体，以提升匹配鲁棒性。</requirement>
    </stage>

    <stage name="1.6 知名度优先原则 (Global Popularity Bias)">
    <requirement>针对题目描述，**优先联想**并推荐全球范围内具有**高知名度、高搜索量、权威来源丰富**的主题。</requirement>
    <priority_categories>
    <item>**事件**: 奥运会、世界杯、诺贝尔奖、世界博览会、重大历史战争/条约。</item>
    <item>**人物**: 国家元首、诺贝尔奖得主、历史名人、科技巨头创始人。</item>
    <item>**地点**: 世界遗产、国家首都、全球标志性建筑（如埃菲尔铁塔）、著名地理特征。</item>
    </priority_categories>
    <strategy>当描述模糊且符合多个可能性时，首先验证最著名的候选者。对于冷门、低搜索量、缺乏权威资料的主题，仅在知名候选者被排除后才考虑。</strategy>
    </stage>

    <stage name="2. 跨语言搜索（强制）">
    <rule>中国/亚洲主题：必须用中文</rule>
    <rule>西方主题：优先英文</rule>
    <rule>混合主题：中英文双语查询</rule>
    <rule>禁止仅用英文搜索中国实体</rule>
    </stage>

    <stage name="3. 搜索策略（核心规则）">
    <specificity_first>从最独特约束开始</specificity_first>
    <negative_constraint_handling>强制“列举与过滤”
    <step>1. 先搜索完整列表（如"List of..."）</step>
    <step>2. 逐一过滤排除不符合项</step>
    <step>3. 对剩余候选验证正向约束</step>
    </negative_constraint_handling>
    <parallel_paths>至少设计1-2条独立路径验证关键变量（如年份）</parallel_paths>
    <fallback>规划备用锚点或路径，若主路径失败立即切换</fallback>
    <query_formulation>2-4个最具体关键词，必要时用引号、-排除、site:</query_formulation>
    </stage>

    <stage name="4. 验证原则（必须包含）">
    <item>每步发现需交叉验证</item>
    <item>最终答案逻辑一致（时间、因果、属性完美对齐）</item>
    <item>主动避免确认偏差（排除著名但错误实体）</item>
    </stage>

    </core_stages>

    <output_format>
    必须严格以以下JSON格式输出：
    <pre>
    {
      "reasoning": "简要说明模式、复杂度、关键锚点与挑战（中文）",
      "complexity": "simple" | "complex",
      "max_steps": 30 | 40,
      "query_pattern": "temporal_sync" | "entity_chain" | "negative_constraint" | "obscure_connection" | "cross_domain" | "simple_lookup",
      "variables": {
        "Year_X": {
          "description": "船长处决年份",
          "constraints": ["1720s俘获宝船后处决", "法国天文学家出生年"],
          "anchor": true,
          "priority": 1,
          "aliases": ["执行年份", "death year"]
        },
        "Person_A": {
          "description": "星云星团表天文学家",
          "constraints": ["法国", "生于Year_X"],
          "depends_on": ["Year_X"],
          "priority": 2
        }
      },
      "plan": "详细分步执行计划（编号步骤，每步包含：具体中英文搜索查询、并行路径、验证方式、回溯方案）"
    }
    </pre>
    </output_format>

    <core_principles>
    <principle>1. 特异性优先 + 列举过滤负向约束</principle>
    <principle>2. 强制跨语言搜索</principle>
    <principle>3. 构建变量依赖与并行路径</principle>
    <principle>4. 实体匹配灵活化：不要因字面不一致而拒绝正确答案，必须接受语义匹配、包含关系、别名和翻译变体</principle>
    <principle>5. 每步交叉验证，逻辑必须完美对齐</principle>
    <principle>6. 主动反确认偏差与回溯</principle>
    </core_principles>

    以指定JSON格式输出。
    </instruction>
    """
    
    client = get_llm_client()
    try:
        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Task: {user_query}"}
            ],
            temperature=0.5,
            max_tokens=512,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        
        # --- Enhanced Logging for Plan ---
        print(f"\n{'='*20} [Planner] Generated Plan {'='*20}")
        print(f"{content}")
        print(f"{'='*60}\n")
        # ---------------------------------
        
        try:
            data = json.loads(content)
            return {
                "plan": data.get("plan", ""),
                "max_steps": data.get("max_steps", 30)
            }
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {"plan": content, "max_steps": 30}
            
    except Exception as e:
        print(f"[Planner] Failed to generate plan: {e}")
        return {"plan": "", "max_steps": 30}
