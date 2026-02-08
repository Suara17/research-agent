#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Search Skill v3 - 结构化意图分析与列表生成增强版
"""

import os
import json
import sys
import re
import io

# [Fix] Force UTF-8 encoding for stdout/stderr to prevent UnicodeEncodeError on Windows
# especially when printing foreign characters (e.g., Mongolian, Cyrillic)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from openai import OpenAI

def _load_env():
    """加载 .env 文件"""
    try:
        paths = [
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
        ]
        for p in paths:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        if k not in os.environ:
                            os.environ[k.strip()] = v.strip().strip("'").strip('"')
    except Exception:
        pass

def _get_client():
    """Get LLM client"""
    # Add project root to sys.path to ensure we can import research_agent
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    from research_agent.utils import get_llm_client
    return get_llm_client(timeout=15.0)

def _analyze_query_with_llm(query: str, original_entities: list, excluded_entities: list = [], feedback: str = "") -> dict:
    """
    使用 LLM 进行结构化查询分析
    返回: {
        "intent": "person_search" | "fact_check" | "list_generation" | "riddle",
        "keywords_en": ["keyword1", "keyword2"],
        "keywords_native": ["关键词1", "关键词2"],
        "search_queries": ["query1", "query2"]
    }
    """
    client = _get_client()
    if not client:
        return None

    # 🔥 优化后的 Prompt：分层搜索 + HyDE (Hypothetical Document Embeddings) + 权威来源
    prompt = f"""You are a Search Engine Optimization Expert with expertise in hierarchical verification strategies.
Analyze the user query and generate TARGETED search queries.

User Query: "{query}"
Known Entities: {json.dumps(original_entities, ensure_ascii=False)}
Excluded Entities: {json.dumps(excluded_entities, ensure_ascii=False)} (MUST be excluded)
Previous Feedback/Failure Context: "{feedback}"

Analysis Tasks:
1. **Identify Intent**: Is it a specific person search, fact check, or **RIDDLE/VAGUE** description?

2. **Riddle & Category Strategy (CRITICAL)**:
   - If the query mentions a generic **CATEGORY** (e.g. "a unit of power", "a chemical element") instead of a specific name, you MUST generate a query to **LIST** that category.
   - Example: Query "Writer named same as power unit" -> Query "List of power units", "List of writers with names matching power units".
   - **DO NOT** just guess one instance (e.g. do not just search "Watt" unless explicitly asked).

3. **HyDE Strategy (Hypothetical Document Embeddings)**:
   - If the query is a **RIDDLE** or uses **VAGUE** descriptions (e.g. "A department...", "A major country...", "An event in 1990s"), you MUST imagine what the **Official News Headline** or **Report Title** would be.
   - Example: Query "A wealth management department investigated..." -> HyDE: "FINRA investigates wealth management division 2025" or "SEC charges bank wealth unit".
   - **Action**: Generate 1-2 hypothetical titles to search.

4. **Structured Query Generation (3 Categories)**:
   - **A. Broad/Context Queries**: Search for lists, overviews, or broad events (e.g. "List of ...", "... scandal overview").
   - **B. Precise/Authoritative Queries**: Use `site:.gov`, `site:.edu`, `site:reuters.com` with specific hard constraints (Year, Location).
   - **C. Negative/Exclusion Queries**: If 'Excluded Entities' are provided or Feedback mentions a wrong path, explicitly exclude them (e.g. "-Bitcoin").

4. **Cross-Lingual (MANDATORY)**:
   - If the entity or topic is associated with a specific country (e.g. "Tencent" -> China, "Nintendo" -> Japan, "Volkswagen" -> Germany), you **MUST** generate queries in that country's NATIVE language.
   - Example: "Tencent game" -> Generate "腾讯 游戏" (Chinese).
   - Example: "Anime about..." -> Generate "动漫 ..." (Japanese).
   - **Do not rely on English only for local entities.**

Output JSON format ONLY:
{{
    "intent": "string",
    "extracted_keywords": ["str"],
    "generated_queries": [
        "HyDE: Hypothetical Headline 1",
        "Broad: List of ...",
        "Precise: ... site:...",
        "Native: [Chinese/Japanese/etc] query...",
        "Negative: ... -excluded"
    ]
}}
"""
    try:
        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
            max_tokens=512
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"DEBUG: LLM Analysis failed: {e}", file=sys.stderr)
        return None

def _fallback_keyword_extraction(text: str) -> list:
    """正则兜底提取逻辑 (原 _extract_keywords 的简化版)"""
    stopwords = {'what', 'who', 'find', 'search', 'question', 'answer', 'the', 'a', 'in', 'of', 'and'}
    words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]+', text)
    return [w for w in words if w.lower() not in stopwords and not (w.isdigit() and len(w)<4)]

def main():
    try:
        _load_env()
        # 参数解析逻辑保持不变
        args_file = os.environ.get("SKILL_ARGS_FILE")
        if args_file and os.path.exists(args_file):
            with open(args_file, 'r', encoding='utf-8') as f:
                args = json.load(f)
        else:
            args_json = os.environ.get("SKILL_ARGS", "{}")
            args = json.loads(args_json) if isinstance(args_json, str) else args_json

        if isinstance(args, str):
            try: args = json.loads(args)
            except: pass
        
        query = args.get("query", "")
        entities = args.get("entities", [])
        excluded = args.get("excluded_entities", [])
        feedback = args.get("feedback", "")
        strategy = args.get("strategy", "auto")

        if not query:
            print(json.dumps({"error": "No query provided"}))
            sys.exit(1)

        # 1. 尝试 LLM 结构化分析 (优先)
        llm_result = _analyze_query_with_llm(query, entities, excluded, feedback)
        
        final_queries = []
        keywords = []
        
        if llm_result:
            # 使用 LLM 生成的高质量查询
            final_queries = llm_result.get("generated_queries", [])
            keywords = llm_result.get("extracted_keywords", [])
            
            # 策略补丁：如果 LLM 没有生成 wiki 查询，手动补一个
            has_site = any("site:" in q for q in final_queries)
            if not has_site:
                base_kw = " ".join(keywords[:5])
                extra_q = f'{base_kw} site:wikipedia.org OR site:baike.baidu.com'
                if excluded:
                    extra_q += " " + " ".join([f"-{e}" for e in excluded])
                final_queries.append(extra_q)
                
        else:
            # 2. 降级回退：基于规则的生成 (原逻辑的精简版)
            keywords = _fallback_keyword_extraction(query)
            base_search = " ".join(keywords[:8])
            
            # 构造排除后缀
            neg_suffix = ""
            if excluded:
                 neg_suffix = " " + " ".join([f"-{e}" for e in excluded])
            
            final_queries.append(base_search + neg_suffix) # 基础查询
            final_queries.append(f"{base_search} wikipedia{neg_suffix}") # 百科查询
            
            # 简单的规则补充
            if "who" in query.lower() or "list" in query.lower():
                final_queries.append(f"List of {base_search}{neg_suffix}")
            if any(k in query.lower() for k in ['year', 'when', 'date']):
                final_queries.append(f"{base_search} timeline{neg_suffix}")

        # 3. 结果去重与清洗
        unique_queries = []
        seen = set()
        for q in final_queries:
            q_clean = re.sub(r'\s+', ' ', q).strip()
            if q_clean and q_clean.lower() not in seen:
                seen.add(q_clean.lower())
                unique_queries.append(q_clean)

        result = {
            "status": "success",
            "strategy_used": llm_result.get("intent", "fallback") if llm_result else "regex_fallback",
            "original_query": query,
            "optimized_queries": unique_queries[:5], # 限制返回数量
            "tips": "已利用 LLM 分析意图并生成结构化查询。" if llm_result else "LLM 分析超时，使用基础关键词查询。"
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e), "status": "failed"}), file=sys.stdout)
        sys.exit(1)

if __name__ == "__main__":
    main()
