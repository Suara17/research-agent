import json
import re
from .utils import get_llm_client

def _extract_core_entities(query: str) -> list:
    s = str(query or "").strip()
    
    # 0. 预处理：如果是JSON，提取有意义的文本字段
    try:
        # Detect and skip binary/PDF content early
        if "%PDF-" in s or "stream" in s[:100]:
             return []

        if s.startswith('{') or s.startswith('['):
            data = json.loads(s)
            text_parts = []
            
            def extract_text_recursive(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in ["title", "summary", "snippet", "content", "description", "name"]:
                            extract_text_recursive(v)
                        elif k in ["results", "organic", "candidates"]: # 深入遍历列表
                            extract_text_recursive(v)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_text_recursive(item)
                elif isinstance(obj, str):
                    text_parts.append(obj)
            
            extract_text_recursive(data)
            if text_parts:
                s = " ".join(text_parts[:20]) # 限制长度，避免过长
    except:
        pass

    ents = []
    
    # 黑名单：常见的JSON元数据键名和无关词汇
    METADATA_BLACKLIST = {
        "source", "serper", "serpapi", "results", "title", "summary", "snippet", 
        "content", "url", "link", "description", "date", "type", "image", "images",
        "search", "query", "engine", "google", "bing", "baidu", "duckduckgo",
        "json", "html", "http", "https", "www", "com", "org", "net", "gov", "edu",
        "status", "code", "message", "error", "success", "fail", "true", "false", "null",
        "none", "undefined", "object", "array", "string", "number", "boolean",
        "items", "total", "page", "next", "prev", "previous", "first", "last",
        "can", "will", "should", "could", "would", "may", "might", "must",
        "what", "where", "when", "who", "why", "how", "which", "this", "that",
        "the", "and", "or", "of", "to", "in", "on", "at", "for", "with", "by"
    }

    try:
        s_clean = s
        # Remove very long words (likely garbage/base64)
        s_clean = re.sub(r'\S{50,}', '', s_clean)
        
        years = re.findall(r'\b(19\d{2}|20\d{2})\b', s_clean)
        ents.extend(years)
        countries = re.findall(r'\b(中国|美国|日本|韩国|蒙古|印度|巴西|南非|法国|德国|英国|俄罗斯|乌克兰|土耳其|伊朗|伊拉克|阿富汗|巴基斯坦|越南|泰国|新加坡|马来西亚|印度尼西亚|菲律宾|墨西哥|加拿大|澳大利亚|新西兰|意大利|西班牙|葡萄牙|希腊|波兰|捷克|匈牙利|罗马尼亚|保加利亚|塞尔维亚|克罗地亚|斯洛文尼亚|斯洛伐克|瑞典|挪威|芬兰|丹麦|冰岛|爱尔兰|荷兰|比利时|瑞士|奥地利|以色列|埃及|尼日利亚|肯尼亚|坦桑尼亚|埃塞俄比亚|加纳|摩洛哥|阿尔及利亚|突尼斯|利比亚|塞内加尔|喀麦隆|乌干达|津巴布韦|赞比亚|纳米比亚|博茨瓦纳|莫桑比克|安哥拉|吉尔吉斯斯坦|哈萨克斯坦|乌兹别克斯坦|塔吉克斯坦|土库曼斯坦|格鲁吉亚|亚美尼亚|阿塞拜疆|黎巴嫩|叙利亚|约旦|巴勒斯坦|沙特|阿联酋|卡塔尔|科威特|巴林|也门|阿曼|尼泊尔|不丹|斯里兰卡|孟加拉|老挝|柬埔寨|缅甸|朝鲜|台湾|香港|澳门|Mongolia|China|Japan|Korea|United States|USA|India|Brazil|South Africa|France|Germany|United Kingdom|Russia|Ukraine|Turkey|Iran|Iraq|Afghanistan|Pakistan|Vietnam|Thailand|Singapore|Malaysia|Indonesia|Philippines|Mexico|Canada|Australia|New Zealand|Italy|Spain|Portugal|Greece|Poland|Czech|Hungary|Romania|Bulgaria|Serbia|Croatia|Slovenia|Slovakia|Sweden|Norway|Finland|Denmark|Iceland|Ireland|Netherlands|Belgium|Switzerland|Austria|Israel|Egypt|Nigeria|Kenya|Tanzania|Ethiopia|Ghana|Morocco|Algeria|Tunisia|Libya|Senegal|Cameroon|Uganda|Zimbabwe|Zambia|Namibia|Botswana|Mozambique|Angola|Kyrgyzstan|Kazakhstan|Uzbekistan|Tajikistan|Turkmenistan|Georgia|Armenia|Azerbaijan|Lebanon|Syria|Jordan|Palestine|Saudi Arabia|UAE|Qatar|Kuwait|Bahrain|Yemen|Oman)\b', s_clean, re.IGNORECASE)
        ents.extend(countries)
        roles = re.findall(r'\b(总统|总理|首相|议员|部长|总统候选人|总理候选人|总统府|内阁|宪法|修宪|President|Prime Minister|Premier|Minister|Parliament|Congress|Constitution|Amendment)\b', s_clean, re.IGNORECASE)
        ents.extend(roles)
        quoted = re.findall(r'"([^"]+)"', s_clean) + re.findall(r"'([^']+)'", s_clean)
        ents.extend(quoted)
        # Improved Chinese Entity Extraction: Match longer sequences (2-20 chars) excluding "的" and punctuation
        cn_entities = re.findall(r'[^\x00-\x7f\s的，。！？；：“”‘’（）【】《》\u3000-\u303f]{2,20}', s_clean)
        ents.extend(cn_entities)
        en_entities = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2})\b', s_clean)
        ents.extend(en_entities)
        seen = set()
        unique_ents = []
        for e in ents:
            e1 = str(e).strip()
            if not e1:
                continue
            el = e1.lower()
            
            # 黑名单过滤
            if el in METADATA_BLACKLIST:
                continue
            
            # Length filter for garbage
            if len(e1) > 50:
                continue
                
            if el in seen:
                continue
            if e1.isdigit() and len(e1) < 4:
                continue
            seen.add(el)
            unique_ents.append(e1)
        print(f"[Monitoring] core_entities_extracted={unique_ents[:8]} for_query='{s[:100]}...'")
        return unique_ents[:8]
    except Exception as e:
        print(f"[Monitoring] entity_extraction_error={e}")
        return [s] if s else []

def extract_entities(query: str) -> str:
    try:
        ents = _extract_core_entities(query)
        print(f"[Monitoring] extract_entities query='{query}' entities={ents}")
        return json.dumps({"entities": ents}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "extract_failed", "message": str(e)}, ensure_ascii=False)

def _optimize_search_query(query: str) -> str:
    """
    应用高阶搜索策略优化查询
    """
    try:
        optimized = query.strip()

        # 策略1: 检测并标记专有名词
        proper_nouns = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', optimized)
        for noun in proper_nouns:
            if f'"{noun}"' not in optimized and f"'{noun}'" not in optimized:
                optimized = optimized.replace(noun, f'"{noun}"')

        # 策略2: 检测学术/百科类问题
        wiki_keywords = [
            'nobel prize', 'founding', 'established', 'founded',
            'biography', 'history of', 'discovered', 'invented',
            'born', 'died', 'award', 'winner'
        ]
        is_wiki_query = any(kw in optimized.lower() for kw in wiki_keywords)
        # (Pass implementation as in original)

        # 策略4: 去除冗余词汇
        redundant_prefixes = [
            'please search for', 'find information about',
            'look up', 'search', 'find', 'what is', 'who is'
        ]
        for prefix in redundant_prefixes:
            if optimized.lower().startswith(prefix):
                optimized = optimized[len(prefix):].strip()

        print(f"[Monitoring] query_optimization: '{query}' → '{optimized}'")
        return optimized

    except Exception as e:
        print(f"[Monitoring] query_optimization_error: {e}")
        return query

def _simplify_search_query(query: str) -> str:
    """
    当搜索失败时，尝试简化查询
    """
    try:
        # Remove site: and filetype:
        simplified = re.sub(r'site:\S+', '', query, flags=re.IGNORECASE)
        simplified = re.sub(r'filetype:\S+', '', simplified, flags=re.IGNORECASE)
        
        # Remove quotes if they might be overly restrictive
        if len(simplified) > 30:
            simplified = simplified.replace('"', '').replace("'", "")
            
        # Collapse spaces
        simplified = re.sub(r'\s+', ' ', simplified).strip()
        return simplified
    except Exception:
        return query

def _create_entity_query(query: str) -> str:
    """
    基于核心实体提取生成关键词查询
    """
    try:
        ents = _extract_core_entities(query)
        valid_ents = [e for e in ents if len(e) > 1 or (e.isalnum() and len(e)==1)]
        if valid_ents:
            return " ".join(valid_ents)
    except Exception:
        pass
    return ""

def _translate_query(query: str, target_lang: str = "English") -> str:
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": f"Translate this search query to {target_lang} for search engine optimization. Keep proper nouns and key terms accurate: {query}"}],
            max_tokens=128
        )
        return resp.choices[0].message.content.strip().strip('"')
    except Exception:
        return query

def expand_query_language(query: str) -> list:
    queries = []
    # Simple heuristic: if query has Chinese and looks like international topic
    if any("\u4e00" <= ch <= "\u9fff" for ch in query):
        # Always translate to English for international coverage
        en_q = _translate_query(query, "English")
        if en_q and en_q.lower() != query.lower():
            queries.append(en_q)
    return queries

def _extract_search_slots(query: str) -> dict:
    try:
        client = get_llm_client()
        prompt = [
            {"role": "system", "content": """Extract search slots from the query.
Output JSON with keys:
- type: "Person", "Organization", "Event", "Object" or "Other"
- hard_constraints: list of strict conditions (year, location, role, specific event)
- soft_constraints: list of descriptive conditions (scandals, education, family)
- anchors: list of unique keywords for search (names, specific terms)
- target_country: country name if applicable (in English), else null
"""},
            {"role": "user", "content": query}
        ]
        resp = client.chat.completions.create(
            model="qwen3-max", 
            messages=prompt, 
            max_tokens=256, 
            response_format={"type": "json_object"}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[Monitoring] Slot extraction failed: {e}")
        return {}
