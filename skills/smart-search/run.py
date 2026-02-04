#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Search Skill v2 - 针对复杂推理与谜语型问题的优化版
"""

import os
import json
import sys
import re
import requests
from openai import OpenAI

def _load_env():
    """加载 .env 文件"""
    try:
        # 尝试加载当前目录或上级目录的 .env
        paths = [
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
        ]
        for p in paths:
            if os.path.exists(p):
                # print(f"DEBUG: Loading env from {p}", file=sys.stderr)
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

def _call_llm_extract(query: str) -> list:
    """使用 LLM 辅助提取关键词（兜底保险）"""
    api_key = os.environ.get("IFLOW_API_KEY")
    if not api_key:
        print("DEBUG: No IFLOW_API_KEY found", file=sys.stderr)
        return []
    
    try:
        client = OpenAI(
            base_url="https://apis.iflow.cn/v1",
            api_key=api_key,
            timeout=10.0,
        )
        
        prompt = f"""你是一个搜索专家。请从以下查询中提取出最关键的搜索词、实体、时间点、约束条件。
要求：
1. 提取核心实体（人名、地名、组织名）。
2. 提取关键时间约束（如 "15th century", "mid-19th", "1990s"）。
3. 提取关键动作或属性（如 "hymn translator", "founded"）。
4. 保持原文语言（如果是英文专有名词，不要翻译）。
5. 只输出关键词，用空格分隔。

查询：{query}
关键词："""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=100
        )
        
        # print(f"DEBUG: Raw response: {response}", file=sys.stderr)

        if not response or not response.choices:
             print(f"DEBUG: Response or choices is empty: {response}", file=sys.stderr)
             return []

        content = response.choices[0].message.content.strip()
        # 清理输出，防止包含 "关键词：" 前缀
        content = re.sub(r'^关键词[:：]\s*', '', content)
        print(f"DEBUG: LLM extracted: {content}", file=sys.stderr)
        return content.split()

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"DEBUG: LLM error: {e}", file=sys.stderr)
        pass
    return []

def _extract_keywords(text: str, top_n=10) -> list:
    """针对谜语型长句的关键词提取"""
    # 扩展的停用词表，过滤掉无意义的描述词
    stopwords = {
        'what', 'is', 'who', 'the', 'a', 'an', 'in', 'on', 'at', 'of', 'for', 'to', 'by', 'with',
        'and', 'or', 'but', 'so', 'question', 'answer', 'please', 'find', 'search',
        '请', '问', '是什么', '是谁', '哪个', '关于', '寻找', '回答', '描述', '一位', '一个',
        'person', 'people', 'man', 'woman', 'named', 'called', 'known', 'famous',
        'during', 'between', 'before', 'after', 'years', 'year', 'time',
        '的', '了', '和', '是', '在', '有', '而', '与', '这', '那', '这个', '那个',
        'there', 'this', 'that', 'give', 'including', 'his', 'her', 'its', 'their',
        'was', 'were', 'been', 'has', 'have', 'had', 'do', 'does', 'did',
        'major', 'end', 'well-known', 'originally'
    }
    
    # 清理引用标记 和标点
    text_clean = re.sub(r'[\'"]', '', text)
    text_clean = re.sub(r'[^\w\s\u4e00-\u9fff-]', ' ', text_clean)
    
    # 简单的中文分词策略：利用停用词作为切分点
    # (已移除危险的 replace 操作，改为 split 后过滤)
    
    words = text_clean.split()
    keywords = []
    seen = set()
    
    for w in words:
        w_lower = w.lower()
        if w_lower not in stopwords and len(w) > 1 and w_lower not in seen:
            # 过滤纯数字（除非是4位年份）
            if w.isdigit() and not (len(w) == 4 and (w.startswith('19') or w.startswith('20'))):
                continue
            seen.add(w_lower)
            keywords.append(w)
            
    return keywords[:top_n]

def _extract_entities_regex(text: str) -> list:
    """基于规则的实体提取（移植自 agent.py）"""
    s = str(text or "").strip()
    ents = []
    try:
        import re as _re
        
        # 预处理：移除示例数据
        s_clean = _re.sub(r'\((?:i\.e\.|e\.g\.)[^)]*\)', '', s, flags=_re.IGNORECASE)
        s_clean = _re.sub(r'Answer\s+with\s+[^.]*\.', '', s_clean, flags=_re.IGNORECASE)

        # 1. 提取完整的复合名词短语（优先级最高）
        # 游戏/娱乐领域
        key_phrases = _re.findall(r'\b(action\s+video\s+game(?:\s+franchise)?|video\s+game\s+franchise|video\s+game\s+company)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(animated?\s+series|entertainment\s+company|game\s+series)\b', s_clean, _re.IGNORECASE)
        
        # 时间表达
        key_phrases += _re.findall(r'\b(late\s+20th\s+century|early\s+20th\s+century|mid-\d{4}s)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(in\s+(?:late\s+|early\s+)?\d{4})\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b((?:mid|late|early)-?\d{1,2}th\s+century)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(end\s+of\s+the\s+\d{1,2}th\s+century)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(\d{1,2}th\s+century)\b', s_clean, _re.IGNORECASE)

        # 2. 首字母大写的专有名词
        latin = _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b', s_clean)

        # 3. 引号内容
        quoted = _re.findall(r'"([^"]+)"', s_clean) + _re.findall(r"'([^']+)'", s_clean)

        # 4. (已移除) 中文词组：交给 _extract_keywords 处理，避免提取过长短语
        # chinese = _re.findall(r'[\u4e00-\u9fff]{2,}', s_clean)
        chinese = []

        # 5. 领域特定术语
        # 科学术语
        key_phrases += _re.findall(r'\b(red dwarf\s+star|next-generation\s+\w+|space\s+telescope)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(exoplanet|super-earth|brown\s+dwarf|white\s+dwarf)\b', s_clean, _re.IGNORECASE)
        # 天文学术语
        key_phrases += _re.findall(r'\b(JWST|James\s+Webb|Hubble|Kepler|TESS)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(host\s+star|planetary\s+system|orbital\s+period)\b', s_clean, _re.IGNORECASE)
        # 学术领域
        key_phrases += _re.findall(r'\b(medieval\s+studies|academic\s+conference|higher\s+education)\b', s_clean, _re.IGNORECASE)
        # 媒体/出版领域
        key_phrases += _re.findall(r'\b(digital\s+news\s+platform|news\s+platform|online\s+publication)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(Southeast\s+Regional\s+Emmy|Emmy\s+Award)\b', s_clean, _re.IGNORECASE)
        # 数字 + 单位模式
        key_phrases += _re.findall(r'\b(\d+(?:\.\d+)?\s+(?:light-years|parsecs|AU))\b', s_clean, _re.IGNORECASE)
        
        # 合并所有候选实体
        all_candidates = key_phrases + quoted + latin + chinese
        
        # 扩展停用词列表（大小写不敏感）
        stop_words = {
        "the", "and", "or", "a", "an", "in", "on", "at", "to", "for", "of", "with",
        "this", "that", "these", "those", "what", "which", "who", "where", "when",
        "during", "europe", "same", "year", "certain", "some", "any",
        "one", "two", "three", "there", "was", "were", "been", "have", "has",
        "more", "than", "about", "before", "after", "answer", "arabic", "numerals",
        "please", "find", "search", "question", "example", "give", "describe",
        "how", "why", "whom", "whose", "major", "western"
    }

        # 过滤与去重
        seen = set()
        for cand in all_candidates:
            c = cand.strip()
            c_lower = c.lower()
            
            # 基础过滤
            if not c or c_lower in stop_words:
                continue
                
            # 过滤示例年份
            if c.isdigit() and len(c) == 4:
                if f'i.e. {c}' in s.lower() or f'e.g. {c}' in s.lower():
                    continue

            # 长度与数字过滤
            if len(c) > 1:
                if c.isdigit() and len(c) < 4:
                    continue
                if c_lower not in seen:
                    seen.add(c_lower)
                    ents.append(c)
            elif _re.match(r'\d{4}', c):  # 4位年份
                 if c_lower not in seen:
                    seen.add(c_lower)
                    ents.append(c)
                
    except Exception:
        pass
    return ents

def _detect_language(text: str) -> str:
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(re.sub(r'\s', '', text))
    if total_chars == 0: return 'en'
    return 'zh' if chinese_chars / total_chars > 0.3 else 'en'

def _auto_select_strategy(query: str, entities: list) -> str:
    query_lower = query.lower()
    
    # 1. 描述性/谜语类 (Riddle/Description) - 数据集中最常见
    # 特征：长句子，包含"一位"、"person who"、"author of"
    if len(query) > 40 and ("who" in query_lower or "what" in query_lower or "一位" in query or "author" in query_lower):
        return 'riddle'

    # 2. 时间/历史交叉类
    time_keywords = ['哪一年', 'when', 'year', 'date', '时间', 'timeline', 'born', 'died', 'founded', 'century']
    if any(kw in query_lower for kw in time_keywords):
        return 'timeline'

    # 3. 学术/定义
    academic_keywords = ['paper', 'thesis', 'dissertation', 'study', 'research', 'article', 'journal', '论文', '研究', '期刊', 'professor', 'scientist']
    if any(kw in query_lower for kw in academic_keywords):
        return 'academic'
        
    # 4. 娱乐/作品 (保留原有逻辑)
    ent_keywords = ['movie', 'film', 'series', 'show', 'game', 'actor', 'song', 'album', '电影', '电视剧', '游戏', '动画', '配音']
    if any(kw in query_lower for kw in ent_keywords):
        return 'entertainment'

    return 'general'

def main():
    try:
        _load_env()
        # 兼容两种参数传递方式
        args_file = os.environ.get("SKILL_ARGS_FILE")
        if args_file and os.path.exists(args_file):
            with open(args_file, 'r', encoding='utf-8') as f:
                args = json.load(f)
        else:
            args_json = os.environ.get("SKILL_ARGS", "{}")
            args = json.loads(args_json) if isinstance(args_json, str) else args_json

        # 修复：确保 args 是字典，处理被双重序列化的 JSON 字符串
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                pass
        
        if not isinstance(args, dict):
            print(json.dumps({"error": f"Invalid args format: {type(args)}", "args_repr": str(args)}))
            sys.exit(1)

        query = args.get("query", "")
        entities = args.get("entities", [])
        strategy = args.get("strategy", "auto")

        if not query:
            print(json.dumps({"error": "No query provided"}))
            sys.exit(1)

        # 预处理：清理 query 中的 source 标签
        query = re.sub(r'[\'"]', '', query).strip()

        if strategy == "auto":
            strategy = _auto_select_strategy(query, entities)

        optimized_queries = []
        lang = _detect_language(query)
        keywords = _extract_keywords(query)
        regex_entities = _extract_entities_regex(query)
        
        # 智能合并：优先使用 regex_entities (更精准)，然后用 keywords (更全面) 补充
        combined_keywords = []
        seen_k = set()
        
        # 1. 优先加入 entities (来自参数 - 最可信)
        for e in entities:
             if e.lower() not in seen_k:
                 seen_k.add(e.lower())
                 combined_keywords.append(e)
                 
        # 2. 加入正则提取的实体 (高准确率)
        for e in regex_entities:
             # 冗余检查：如果是已存在关键词的子串，跳过
             is_sub = False
             for exist in combined_keywords:
                 if e.lower() in exist.lower() and len(e) < len(exist):
                     is_sub = True
                     break
             
             if not is_sub and e.lower() not in seen_k:
                 seen_k.add(e.lower())
                 combined_keywords.append(e)

        # NEW: 2.5 LLM 辅助提取 (针对复杂查询的强力保险)
        llm_extracted_result = []
        # 扩大触发范围：只要是 riddles, timeline, academic 策略，或者查询长度超过 30 字符，都启用 LLM 提取
        # 用户特别强调了 "15th century" 这种约束容易丢失，所以 timeline 策略必须启用 LLM
        if strategy in ['riddle', 'timeline', 'academic'] or len(query) > 30:
             llm_keywords = _call_llm_extract(query)
             llm_extracted_result = llm_keywords # 用于结果展示
             # 将 LLM 关键词加入列表，保留顺序
             for k in llm_keywords:
                 k = k.strip('.,;"\'')
                 if len(k) > 1 and k.lower() not in seen_k:
                     seen_k.add(k.lower())
                     combined_keywords.append(k)
                 
        # 3. 加入分词提取的关键词 (作为兜底补充)
        for k in keywords:
             if k.lower() not in seen_k:
                 seen_k.add(k.lower())
                 combined_keywords.append(k)
                 
        # 基础组合：使用合并后的前8个词
        base_search = " ".join(combined_keywords[:8])

        # === 策略生成逻辑 ===

        if strategy == "riddle":
            # 谜语/长描述策略：核心是去噪 + 跨语言 + 强实体链接
            
            # 1. 纯关键词组合 (最宽泛)
            optimized_queries.append(f"{base_search}")
            
            # 2. 针对特定输出要求的处理 (非常关键)
            # 很多题目要求 English Name
            if "英文" in query or "english" in query.lower():
                optimized_queries.append(f"{base_search} English name")
            if "全称" in query or "full name" in query.lower():
                optimized_queries.append(f"{base_search} full name")
                
            # 3. 跨语言尝试
            if lang == 'zh':
                 optimized_queries.append(f"{base_search} wikipedia") # 强搜英文维基
            else:
                 optimized_queries.append(f"{base_search} 百度百科")

        elif strategy == "academic":
            # 学术增强：针对论文、期刊
            optimized_queries.append(f'"{base_search}" site:edu OR site:org')
            optimized_queries.append(f'"{base_search}" filetype:pdf')
            # 很多题目问的是论文标题，需要精确匹配
            if entities:
                optimized_queries.append(f'"{entities[0]}" research paper title')
            optimized_queries.append(f'{base_search} journal')

        elif strategy == "timeline":
            # 时间线增强：聚焦年份
            optimized_queries.append(f"{base_search} date year")
            optimized_queries.append(f"when was {base_search}")
            if entities:
                optimized_queries.append(f'"{entities[0]}" timeline')
                # 针对 "In the same year..." 这类问题
                optimized_queries.append(f'"{entities[0]}" history events')
                
        elif strategy == "entertainment":
            # 娱乐增强
            if lang == 'zh':
                optimized_queries.append(f'{base_search} site:douban.com')
                optimized_queries.append(f'{base_search} 百度百科')
            else:
                optimized_queries.append(f'{base_search} site:imdb.com OR site:wikipedia.org')
            
            if "cast" in query.lower() or "actor" in query.lower() or "扮演" in query:
                optimized_queries.append(f'{base_search} cast list')

        else: # General
            optimized_queries.append(query)
            optimized_queries.append(f"{base_search} wiki")
            optimized_queries.append(f"{base_search} overview")

        # 结果去重
        optimized_queries = list(dict.fromkeys(optimized_queries))

        result = {
            "status": "success",
            "strategy_used": strategy,
            "original_query": query,
            "extracted_keywords": keywords,
            "llm_keywords": llm_extracted_result,
            "optimized_queries": optimized_queries,
            "tips": f"检测到'{strategy}'类型问题。已自动生成跨语言或特定领域查询。"
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e), "status": "failed"}), file=sys.stdout)
        sys.exit(1)

if __name__ == "__main__":
    main()
