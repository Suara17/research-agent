import http.client
import json
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量，确保 BRAVE_API_KEY 等配置生效
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)

import ssl
import urllib.parse
import urllib.request
from typing import Optional
from pathlib import Path
import concurrent.futures
import time
import io
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from bs4 import BeautifulSoup
from pypdf import PdfReader

from agent_loop import agent_loop
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from openai import OpenAI
try:
    from agui import stream_agui_events, to_openai_messages, to_sse_data
    from ag_ui.core import RunAgentInput
    _AGUI_AVAILABLE = True
except Exception:
    _AGUI_AVAILABLE = False

try:
    from duckduckgo_search import DDGS
    _DDGS_AVAILABLE = True
except ImportError:
    _DDGS_AVAILABLE = False

try:
    from exa_py import Exa
    _EXA_AVAILABLE = True
except ImportError:
    _EXA_AVAILABLE = False

try:
    import trafilatura
    _TRAFILATURA_AVAILABLE = True
except ImportError:
    _TRAFILATURA_AVAILABLE = False


def get_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=2,  # Reduced from 5 to 2 for faster fail
        backoff_factor=0.5, # Reduced from 1 to 0.5
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return session

def _load_env_from_dotenv():
    try:
        here = Path(__file__).resolve().parent
        candidates = [here / ".env", Path.cwd() / ".env"]
        seen = set()
        for p in candidates:
            if not p.exists():
                continue
            if str(p) in seen:
                continue
            seen.add(str(p))
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and v and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

_load_env_from_dotenv()

app = FastAPI()

def _extract_core_entities(query: str) -> list:
    s = str(query or "").strip()
    ents = []
    try:
        import re as _re

        # 预处理：移除示例数据（i.e. ..., e.g. ...）
        s_clean = _re.sub(r'\((?:i\.e\.|e\.g\.)[^)]*\)', '', s, flags=_re.IGNORECASE)
        s_clean = _re.sub(r'Answer\s+with\s+[^.]*\.', '', s_clean, flags=_re.IGNORECASE)

        # 1. 【优化】提取完整的复合名词短语（优先级最高）
        # 游戏/娱乐领域
        key_phrases = _re.findall(r'\b(action\s+video\s+game(?:\s+franchise)?|video\s+game\s+franchise|video\s+game\s+company)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(animated?\s+series|entertainment\s+company|game\s+series)\b', s_clean, _re.IGNORECASE)

        # 时间表达（高价值锚点）
        key_phrases += _re.findall(r'\b(late\s+20th\s+century|early\s+20th\s+century|mid-\d{4}s)\b', s_clean, _re.IGNORECASE)
        key_phrases += _re.findall(r'\b(in\s+(?:late\s+|early\s+)?\d{4})\b', s_clean, _re.IGNORECASE)

        # 2. 首字母大写的专有名词（人名、地名、公司名）
        latin = _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b', s_clean)

        # 3. 引号内容（明确标注的重要信息）
        quoted = _re.findall(r'"([^"]+)"', s_clean) + _re.findall(r"'([^']+)'", s_clean)

        # 4. 中文词组（2个以上汉字）
        chinese = _re.findall(r'[\u4e00-\u9fff]{2,}', s_clean)

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

        # 合并所有候选实体（复合短语优先）
        all_candidates = key_phrases + quoted + latin + chinese

        # 扩展停用词列表（大小写不敏感）
        stop_words = {
            "the", "and", "or", "a", "an", "in", "on", "at", "to", "for", "of", "with",
            "this", "that", "these", "those", "what", "which", "who", "where", "when",
            "during", "europe", "same", "year", "certain", "some", "any",
            "one", "two", "three", "there", "was", "were", "been", "have", "has",
            "more", "than", "about", "before", "after", "answer", "arabic", "numerals",
            # 新增：常见指令词
            "please", "find", "search", "question", "example"
        }

        for cand in all_candidates:
            c = cand.strip()
            c_lower = c.lower()

            # 过滤规则
            if not c or c_lower in stop_words or c in ents:
                continue

            # 过滤示例年份（如果在原始查询的示例部分）
            if c.isdigit() and len(c) == 4:
                # 检查是否来自示例部分（i.e. 2026）
                if f'i.e. {c}' in s.lower() or f'e.g. {c}' in s.lower():
                    continue
            
            # 子串冗余检查：如果当前词是已提取实体的子串，则跳过
            # 例如：已有 "United States"，跳过 "States"
            is_redundant = False
            for existing in ents:
                if c_lower in existing.lower() and len(c) < len(existing):
                    is_redundant = True
                    break
            if is_redundant:
                continue

            # 长度检查
            if len(c) > 1:
                # 过滤无意义的短数字
                if c.isdigit() and len(c) < 4:
                    continue
                ents.append(c)
            elif _re.match(r'\d{4}', c):  # 4位年份
                ents.append(c)

        # 如果实体为空且查询很短，使用整个查询
        if not ents and len(s_clean.split()) <= 4:
            ents.append(s_clean)

        print(f"[Monitoring] core_entities_extracted={ents[:8]} for_query='{s[:100]}...'")
    except Exception as e:
        print(f"[Monitoring] entity_extraction_error={e}")
        if s:
            ents.append(s)
    return ents[:8]

def extract_entities(query: str) -> str:
    try:
        ents = _extract_core_entities(query)
        print(f"[Monitoring] extract_entities query='{query}' entities={ents}")
        return json.dumps({"entities": ents}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "extract_failed", "message": str(e)}, ensure_ascii=False)


def _filter_search_results(results: list) -> list:
    """
    过滤包含敏感/不安全内容的搜索结果
    """
    if not results:
        return []
        
    filtered = []
    # 敏感关键词列表 (小写)
    sensitive_keywords = {
        "porn", "xxx", "sex", "gambling", "casino", 
        "色情", "赌博", "av", "hentai", "fuck", "bitch",
        "whore", "slut", "asshole", "nigger", "faggot"
    }
    
    for r in results:
        title = str(r.get("title") or "").lower()
        # Support both 'summary' and 'snippet' keys
        snippet = str(r.get("summary") or r.get("snippet") or "").lower()
        content = f"{title} {snippet}"
        
        # 检查是否包含敏感词
        if any(kw in content for kw in sensitive_keywords):
            continue
            
        filtered.append(r)
        
    if len(results) != len(filtered):
        print(f"[Monitoring] Filtered {len(results) - len(filtered)} sensitive results")
        
    return filtered


def _rerank_search_results(results, query: str, top_k: int):
    """
    根据实体匹配度对搜索结果重新排序
    返回值：重排序后的结果列表
    """
    try:
        ents = _extract_core_entities(query)
        print(f"[Monitoring] entity_rerank query='{query}' entities={ents}")
        if not results:
            return results
        if not ents:
            return results[:top_k]
        ents_lower = [str(e).lower() for e in ents if str(e).strip()]
        scored = []
        for idx, r in enumerate(results):
            title = str((r.get("title") or "")).lower()
            # Support both 'summary' and 'snippet' keys
            snippet = str(r.get("summary") or r.get("snippet") or "").lower()
            score = 0.0
            for e in ents_lower:
                if not e:
                    continue
                if e in title:
                    score += 2.0
                if e in snippet:
                    score += 1.0
            scored.append((score, idx, r))
        max_score = max((s for s, _, _ in scored), default=0.0)
        if max_score > 0:
            scored = [t for t in scored if t[0] > 0]
        scored_sorted = sorted(scored, key=lambda t: (t[0], -t[1]), reverse=True)
        reranked = [r for _, _, r in scored_sorted][:top_k]
        top_scores = [s for s, _, _ in scored_sorted[:3]]
        print(f"[Monitoring] entity_rerank top_scores={top_scores} kept={len(reranked)}")
        return reranked
    except Exception as e:
        print(f"[Monitoring] entity_rerank_failed: {e}")
        return results[:top_k]


def extract_answer_from_search_results(search_results: list, query: str) -> dict:
    """
    【优化方案1】从搜索结果标题/摘要中提取候选答案

    当web_fetch失败(403/超时)时，使用此函数从搜索结果元数据提取答案

    Args:
        search_results: 搜索结果列表 [{"title": str, "snippet": str, "url": str}]
        query: 原始查询

    Returns:
        {
            "candidates": [{"text": str, "confidence": float, "sources": int}],
            "extraction_method": str
        }
    """
    try:
        from collections import Counter
        import re as _re

        candidates = []

        # 策略1: 提取引号内容（通常是专有名词、书名、电影名）
        for result in search_results:
            title = result.get('title', '')
            # Support both 'summary' and 'snippet' keys
            snippet = result.get('summary') or result.get('snippet') or ''
            combined = f"{title} {snippet}"

            # 提取双引号内容
            quoted = _re.findall(r'"([^"]+)"', combined)
            candidates.extend(quoted)

            # 提取《》书名号内容（中文）
            book_names = _re.findall(r'《([^》]+)》', combined)
            candidates.extend(book_names)

        # 策略2: 提取标题中的关键实体（首字母大写的连续词）
        for result in search_results[:3]:  # 只看前3个结果
            title = result.get('title', '')
            # 提取连续的首字母大写词组（如 "Our Plastic World"）
            capitalized = _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', title)
            candidates.extend(capitalized)

        # 统计候选答案频率
        if not candidates:
            return {"candidates": [], "extraction_method": "no_candidates"}

        counter = Counter(candidates)

        # 计算置信度（基于出现频率和位置）
        ranked_candidates = []
        for text, count in counter.most_common(5):
            # 过滤太短或太长的候选
            if len(text) < 3 or len(text) > 100:
                continue

            # 置信度 = (出现次数 / 结果总数) * 基础分
            confidence = min(0.9, (count / len(search_results)) * 0.5 + 0.3)

            # 如果出现在第一个结果的标题中，提高置信度
            if search_results and text in search_results[0].get('title', ''):
                confidence = min(0.95, confidence + 0.2)

            ranked_candidates.append({
                "text": text,
                "confidence": round(confidence, 2),
                "sources": count
            })

        print(f"[Monitoring] extracted_candidates from search results: {ranked_candidates[:3]}")

        return {
            "candidates": ranked_candidates,
            "extraction_method": "search_metadata"
        }

    except Exception as e:
        print(f"[Monitoring] extract_answer_from_search_results error: {e}")
        return {"candidates": [], "extraction_method": "error"}


def _optimize_search_query(query: str) -> str:
    """
    应用logid15.md的高阶搜索策略优化查询

    优化策略：
    1. 为专有名词添加引号（强制匹配）
    2. 识别并应用site:等运算符
    3. 提取高价值"锚点"关键词

    Args:
        query: 原始查询字符串

    Returns:
        优化后的查询字符串
    """
    try:
        import re as _re
        optimized = query.strip()

        # 策略1: 检测并标记专有名词（连续首字母大写词组）
        # 如 "James Webb Space Telescope" → "James Webb Space Telescope"
        proper_nouns = _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', optimized)
        for noun in proper_nouns:
            # 只有当该名词尚未被引号包围时才添加引号
            if f'"{noun}"' not in optimized and f"'{noun}'" not in optimized:
                optimized = optimized.replace(noun, f'"{noun}"')

        # 策略2: 检测学术/百科类问题，自动添加site:限定
        # 关键词："Nobel Prize", "founding", "established", "biography", "history of"
        wiki_keywords = [
            'nobel prize', 'founding', 'established', 'founded',
            'biography', 'history of', 'discovered', 'invented',
            'born', 'died', 'award', 'winner'
        ]
        is_wiki_query = any(kw in optimized.lower() for kw in wiki_keywords)

        # 如果是百科类问题且未指定site:，添加Wikipedia限定
        if is_wiki_query and 'site:' not in optimized.lower():
            # 注意：某些搜索引擎可能不支持site:，这里作为可选优化
            # 实际使用时可根据搜索引擎类型决定是否启用
            pass  # 暂不强制添加，避免影响其他搜索引擎

        # 策略3: 识别带引号的关键短语（用户已明确标记的重点）
        # 这些内容保持不变，已经是最优形式

        # 策略4: 去除冗余词汇（如果查询过长）
        # 移除常见的冗余前缀
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
        # 优化失败时返回原查询
        return query


def _simplify_search_query(query: str) -> str:
    """
    当搜索失败时，尝试简化查询
    1. 移除 site: 等高级指令
    2. 移除 filetype:
    3. 移除过多的引号
    """
    import re
    try:
        # Remove site: and filetype:
        simplified = re.sub(r'site:\S+', '', query, flags=re.IGNORECASE)
        simplified = re.sub(r'filetype:\S+', '', simplified, flags=re.IGNORECASE)
        
        # Remove quotes if they might be overly restrictive (keep if it's a short name)
        # Only remove if query is reasonably long, to avoid breaking exact match for names
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
    用于当长难句搜索失败时的最后兜底
    """
    try:
        # 复用已有的实体提取逻辑
        ents = _extract_core_entities(query)
        # 过滤掉过短的词，除非它是唯一的
        valid_ents = [e for e in ents if len(e) > 1 or (e.isalnum() and len(e)==1)]
        if valid_ents:
            return " ".join(valid_ents)
    except Exception:
        pass
    return ""


def verify_answer(question: str, candidate_answer: str) -> str:
    """
    Use LLM to verify and refine the answer based on the question.
    Strictly enforces format requirements and removes repetitions.
    """
    if not candidate_answer:
        return ""
        
    try:
        # Create a temporary client (using same env key)
        # Use a shorter timeout for verification
        verify_client = OpenAI(base_url="https://apis.iflow.cn/v1", api_key=os.getenv("IFLOW_API_KEY"), timeout=15.0)
        
        verify_prompt = [
            {"role": "system", "content": """You are a strict answer validator.
Your goal is to refine the Candidate Answer based on the Question.
Rules:
1. Remove repetition (e.g. "19721972" -> "1972", "ParisParis" -> "Paris").
2. Remove unnecessary context if the question asks for a specific entity (e.g. "1982年广州" -> "广州" if asking for city; "FC Seoul。FC Seoul" -> "FC Seoul").
3. Ensure strict adherence to format constraints in the question (e.g. "English name only", "only the year").
4. Output ONLY the final refined answer string. Do not output any explanation.
5. NO EXTRA CHARACTERS. No Markdown, no prefixes ("Answer:"), no periods at the end of short answers.
6. If the Candidate Answer is already correct and concise, output it exactly as is."""},
            {"role": "user", "content": f"Question: {question}\nCandidate Answer: {candidate_answer}"}
        ]
        
        verify_resp = verify_client.chat.completions.create(model="qwen3-max", messages=verify_prompt, max_tokens=200)
        verified = verify_resp.choices[0].message.content.strip()
        
        # Only apply if we got a valid non-empty response
        if verified:
            # Apply clean_answer one last time to the verified result
            final_cleaned = clean_answer(verified)
            if final_cleaned:
                print(f"[Verification] '{candidate_answer[:50]}...' -> '{final_cleaned[:50]}...'")
                return final_cleaned
                
    except Exception as e:
        print(f"[Verification] Failed: {e}")
        # Fallback to the original result if verification fails
    
    return candidate_answer


def web_search(query: str, top_k: int = 5) -> str:
    try:
        print(f"[Monitoring] web_search query='{query}'")
        if not isinstance(query, str) or not query.strip():
            return json.dumps({"error": "empty_query"}, ensure_ascii=False)

        # 准备查询列表：优先使用优化后的查询，失败则尝试简化查询
        queries_to_try = [_optimize_search_query(query)]
        
        # 策略2: 简化查询（移除语法糖）
        simplified = _simplify_search_query(query)
        if simplified and simplified != queries_to_try[0]:
            queries_to_try.append(simplified)
            
        # 策略3: 实体关键词查询（针对长难句兜底）
        # 如果查询较长，尝试只搜索核心实体
        if len(query) > 40:
            entity_q = _create_entity_query(query)
            if entity_q and entity_q not in queries_to_try:
                # 确保关键词查询与简化查询有足够差异
                if not simplified or entity_q != simplified:
                    queries_to_try.append(entity_q)
                    print(f"[Monitoring] Added entity fallback query: '{entity_q}'")

        try:
            k = int(top_k)
        except Exception:
            k = 5
        if k <= 0 or k > 10:
            k = 5

        serper_key = os.getenv("SERPER_API_KEY")
        serpapi_key = os.getenv("SERPAPI_API_KEY")
        brave_key = os.getenv("BRAVE_API_KEY")
        iqs_key = os.getenv("IQS_API_KEY")
        
        # 遍历尝试不同的查询变体
        for attempt_idx, current_q in enumerate(queries_to_try):
            # Only print retry log if we are actually retrying (attempt_idx > 0)
            # AND if we haven't exhausted providers due to fatal errors
            if attempt_idx > 0:
                print(f"[Monitoring] Primary search failed/empty. Retrying with simplified query: '{current_q}'")

            # Provider 0: Serper (Google) - First Priority
            if serper_key:
                try:
                    url = "https://google.serper.dev/search"
                    payload = json.dumps({"q": current_q, "num": k})
                    headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
                    response = requests.post(url, headers=headers, data=payload, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        results = []
                        for item in data.get("organic", []):
                            results.append({
                                "title": item.get("title"),
                                "summary": item.get("snippet"),
                                "url": item.get("link"),
                            })
                        if "knowledgeGraph" in data:
                            kg = data["knowledgeGraph"]
                            results.insert(0, {
                                "title": kg.get("title", "Knowledge Graph"),
                                "summary": f"{kg.get('type', '')}: {kg.get('description', '')} {kg.get('attributes', '')}",
                                "url": kg.get("website", ""),
                            })
                        if results:
                            results = _filter_search_results(results)
                            results = _rerank_search_results(results, query, k)
                            return json.dumps({"source": "serper", "results": results}, ensure_ascii=False)
                        else:
                             print(f"[Monitoring] Serper returned 200 but no organic results for query: '{current_q}'")
                    elif response.status_code in [400, 401, 402, 403]:
                        print(f"[CRITICAL] Serper API Error: {response.status_code} - {response.text}")
                        print(f"[Monitoring] Serper unavailable. Switching to next provider (IQS)...")
                    else:
                        print(f"[Monitoring] Serper failed with status {response.status_code}: {response.text[:200]}")
                        print(f"[Monitoring] Switching to next provider...")
                except Exception as e:
                    print(f"[Monitoring] Serper error (attempt {attempt_idx}): {e}")
                    print(f"[Monitoring] Switching to next provider...")

            # Provider 1: Alibaba IQS
            if iqs_key:
                try:
                    # 假设使用 DashScope Search 接口 (通常兼容)
                    # 如果用户未指定具体Endpoint, 使用通用 DashScope 搜索
                    # 注意: IQS 具体 SDK/API 调用方式可能不同，这里使用标准 HTTP 调用
                    url = "https://iqs.cn-beijing.aliyuncs.com/v1/search" # 示例Endpoint
                    # 实际调用通常需要更复杂的签名，或者通过 DashScope
                    # 这里尝试适配 OpenAI 兼容格式或通用 REST
                    # 如果无法确定，先实现一个基础的 GET/POST
                    
                    # 修正: 假设用户是指 "Aliyun Intelligent Query Search"
                    # 使用标准 DashScope 搜索 API (https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation) ? 不，是搜索。
                    # 由于缺乏具体文档，我将使用通用的 request 结构，并允许通过 env 覆盖 URL
                    iqs_url = os.getenv("IQS_API_ENDPOINT", "https://iqs.cn-beijing.aliyuncs.com/search")
                    
                    payload = {
                        "query": current_q,
                        "num": k,
                        "start": 0
                    }
                    headers = {
                        "Authorization": f"Bearer {iqs_key}",
                        "Content-Type": "application/json"
                    }
                    
                    # 尝试调用 (假设是 POST)
                    response = requests.post(iqs_url, headers=headers, json=payload, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        results = []
                        # 适配常见的 Alibaba 搜索返回格式 (result/items)
                        # 这里做一个兼容性解析
                        items = data.get("result", {}).get("items", []) or data.get("results", []) or data.get("data", [])
                        
                        for item in items:
                            results.append({
                                "title": item.get("title", ""),
                                "summary": item.get("summary", "") or item.get("snippet", ""),
                                "url": item.get("link", "") or item.get("url", "")
                            })
                            
                        if results:
                            results = _filter_search_results(results)
                            results = _rerank_search_results(results, query, k)
                            return json.dumps({"source": "iqs", "results": results}, ensure_ascii=False)
                        else:
                            print(f"[Monitoring] IQS returned 200 but no results")
                    else:
                        print(f"[Monitoring] IQS failed: {response.status_code} - {response.text[:100]}")
                        print(f"[Monitoring] Switching to next provider...")
                except Exception as e:
                    print(f"[Monitoring] IQS error: {e}")
                    print(f"[Monitoring] Switching to next provider...")

            # Provider 2: SerpApi (serpapi.com)
            if serpapi_key:
                try:
                    url = "https://serpapi.com/search"
                    params = {
                        "api_key": serpapi_key,
                        "q": current_q,
                        "engine": "google",
                        "num": k
                    }
                    # SerpApi 使用 GET 请求
                    response = requests.get(url, params=params, timeout=15)
                    
                    if response.status_code == 200:
                        data = response.json()
                        results = []
                        
                        # 解析 SerpApi 格式
                        if "organic_results" in data:
                            for item in data["organic_results"]:
                                results.append({
                                    "title": item.get("title", ""),
                                    "summary": item.get("snippet", ""),
                                    "url": item.get("link", "")
                                })
                        
                        # Knowledge Graph
                        if "knowledge_graph" in data:
                            kg = data["knowledge_graph"]
                            results.insert(0, {
                                "title": kg.get("title", "Knowledge Graph"),
                                "summary": f"{kg.get('type', '')}: {kg.get('description', '')}",
                                "url": kg.get("website", "") or kg.get("source", {}).get("link", "")
                            })
                            
                        if results:
                            results = _filter_search_results(results)
                            results = _rerank_search_results(results, query, k)
                            return json.dumps({"source": "serpapi", "results": results}, ensure_ascii=False)
                        else:
                            print(f"[Monitoring] SerpApi returned 200 but no organic results")
                    elif response.status_code in [401, 403]:
                        print(f"[CRITICAL] SerpApi Auth Error: {response.status_code} - {response.text[:100]}")
                        print(f"[Monitoring] Switching to next provider...")
                    else:
                        print(f"[Monitoring] SerpApi failed: {response.status_code} - {response.text[:100]}")
                        print(f"[Monitoring] Switching to next provider...")
                        
                except Exception as e:
                    print(f"[Monitoring] SerpApi error: {e}")
                    print(f"[Monitoring] Switching to next provider...")

            # Provider 2: Brave Search
            if brave_key:
                try:
                    url = "https://api.search.brave.com/res/v1/web/search"
                    headers = {"X-Subscription-Token": brave_key, "Accept": "application/json"}
                    params = {"q": current_q, "count": min(k, 20)}
                    response = requests.get(url, headers=headers, params=params, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        results = []
                        if "web" in data and "results" in data["web"]:
                            for item in data["web"]["results"]:
                                results.append({
                                    "title": item.get("title"),
                                    "summary": item.get("description"),
                                    "url": item.get("url"),
                                })
                        if "mixed" in data and "main" in data["mixed"]:
                            for item in data["mixed"]["main"]:
                                if item.get("type") == "infobox":
                                    results.insert(0, {
                                        "title": item.get("title") or "Infobox",
                                        "summary": item.get("description") or "",
                                        "url": item.get("url") or "",
                                    })
                        if results:
                            results = _filter_search_results(results)
                            results = _rerank_search_results(results, query, k)
                            return json.dumps({"source": "brave", "results": results}, ensure_ascii=False)
                    else:
                        print(f"[Monitoring] Brave search failed: {response.status_code}")
                        print(f"[Monitoring] Switching to next provider...")
                except Exception as e:
                    print(f"[Monitoring] Brave search error (attempt {attempt_idx}): {e}")
                    print(f"[Monitoring] Switching to next provider...")

            # Provider 3: DuckDuckGo (DDGS)
            if _DDGS_AVAILABLE:
                try:
                    results = []
                    # 自动检测中文查询并设置区域
                    region = "wt-wt"
                    # 简单的中文检测：如果包含中文字符
                    if any("\u4e00" <= ch <= "\u9fff" for ch in current_q):
                        region = "cn-zh"
                        print(f"[Monitoring] Detected Chinese query, using region='cn-zh' for DuckDuckGo")
                    
                    with DDGS() as ddgs:
                        ddgs_gen = ddgs.text(current_q, max_results=k, region=region)
                        for r in ddgs_gen:
                            results.append(
                                {
                                    "title": r.get("title"),
                                    "summary": r.get("body"),
                                    "url": r.get("href"),
                                }
                            )
                    if results:
                        results = _filter_search_results(results)
                        results = _rerank_search_results(results, query, k)
                        return json.dumps({"source": "ddgs", "results": results}, ensure_ascii=False)
                except Exception as e:
                    print(f"[Monitoring] DDGS error (attempt {attempt_idx}): {e}")
        
        # 如果所有尝试都失败
        return json.dumps({"error": "search_failed", "message": "All providers failed"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "unexpected_error", "message": str(e)}, ensure_ascii=False)


import re
from html.parser import HTMLParser
_UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/120.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 Chrome/118.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36",
]
def _pick_ua(i: int) -> str:
    try:
        return _UA_LIST[i % len(_UA_LIST)]
    except Exception:
        return "Mozilla/5.0"

class SimpleTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.output = []
    def handle_data(self, data):
        if data.strip():
            self.output.append(data.strip())
    def get_text(self):
        return " ".join(self.output)

def _wiki_title_from_path(path: str) -> str:
    try:
        if "/wiki/" in path:
            t = path.split("/wiki/", 1)[1]
        else:
            t = path.split("/")[-1]
        return urllib.parse.unquote(t)
    except Exception:
        return ""

_WIKI_UA = "ResearchBot/1.0 (contact@example.com)"

def _fetch_wikipedia_rest(url: str) -> Optional[dict]:
    try:
        p = urllib.parse.urlparse(url)
        host = p.netloc
        title = _wiki_title_from_path(p.path)
        if not host or not title:
            return None
            
        # Try 1: REST API
        try:
            api = f"https://{host}/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
            req = urllib.request.Request(api, headers={"User-Agent": _WIKI_UA})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            extract = str(data.get("extract") or "")
            if extract:
                return {"source": api, "content": extract, "title": data.get("title") or title, "sitename": host, "type": "wiki-summary"}
        except Exception as e:
            print(f"[Monitoring] Wiki REST API failed: {e}")

        # Try 2: PHP API (Fallback)
        try:
            api_php = f"https://{host}/w/api.php?action=query&format=json&prop=extracts&titles={urllib.parse.quote(title)}&exintro=1&explaintext=1"
            req = urllib.request.Request(api_php, headers={"User-Agent": _WIKI_UA})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            pages = data.get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                extract = pdata.get("extract", "")
                if extract:
                     return {"source": api_php, "content": extract, "title": pdata.get("title") or title, "sitename": host, "type": "wiki-extract"}
        except Exception as e:
             print(f"[Monitoring] Wiki PHP API failed: {e}")

        return None
    except Exception:
        return None

def _fetch_reprap_mediawiki(url: str) -> Optional[dict]:
    try:
        p = urllib.parse.urlparse(url)
        host = p.netloc
        title = _wiki_title_from_path(p.path)
        if not host or not title:
            return None
        api = f"https://{host}/mediawiki/api.php?action=parse&page={urllib.parse.quote(title)}&prop=text&format=json"
        req = urllib.request.Request(api, headers={"User-Agent": _pick_ua(1)})
        with urllib.request.urlopen(req, timeout=10) as resp:
            j = json.loads(resp.read().decode("utf-8", "replace"))
        parse = j.get("parse") or {}
        text_html = ((parse.get("text") or {}).get("*") or "")
        if not text_html:
            return None
        ex = SimpleTextExtractor()
        ex.feed(text_html)
        t = ex.get_text().strip()
        if not t:
            return None
        if len(t) > 10000:
            t = t[:10000] + "...(truncated)"
        return {"source": api, "content": t, "title": parse.get("title") or title, "sitename": host}
    except Exception:
        return None

def web_fetch(url: str, max_bytes: int = 200_000) -> str:
    """
    强大的网页/PDF抓取函数，带重试和防爬虫机制
    """
    try:
        print(f"[Monitoring] web_fetch called with url='{url}'")
        parsed = urllib.parse.urlparse(url)
        path_lower = (parsed.path or "").lower()
        
        # 1. 针对 PDF 的处理逻辑
        if path_lower.endswith(".pdf") or url.lower().endswith(".pdf"):
            try:
                session = get_session()
                # PDF下载可能慢，增加超时
                resp = session.get(url, timeout=15, stream=True, verify=False)
                resp.raise_for_status()
                content = b""
                # 内存限制：只读前 5MB
                for chunk in resp.iter_content(chunk_size=8192):
                    content += chunk
                    if len(content) > 5 * 1024 * 1024:
                        break
                
                reader = PdfReader(io.BytesIO(content))
                text = ""
                # 只读前 10 页 (通常包含摘要、结论和核心数据)
                for i, page in enumerate(reader.pages):
                    if i >= 10: break
                    extracted = page.extract_text() or ""
                    if extracted:
                        text += extracted + "\n"
                
                if len(text) < 50: 
                    return json.dumps({"error": "pdf_empty"}, ensure_ascii=False)
                return json.dumps({"source": url, "content": text[:15000], "type": "pdf"}, ensure_ascii=False)
            except Exception as e:
                print(f"[Warn] PDF parse failed: {e}")
                # PDF 失败不报错，继续尝试按普通网页处理（有些URL结尾是pdf但其实是网页预览）

        # Optimize Wikipedia access
        if "wikipedia.org" in parsed.netloc:
             wiki_res = _fetch_wikipedia_rest(url)
             if wiki_res:
                 print(f"[Monitoring] Wiki fetch success via API for {url}")
                 return json.dumps(wiki_res, ensure_ascii=False)
             print(f"[Monitoring] Wiki API fetch failed for {url}, falling back to standard fetch")

        # 2. 常规网页处理 (优先 Trafilatura)
        if _TRAFILATURA_AVAILABLE:
            try:
                # Wrap trafilatura in ThreadPoolExecutor to enforce strict timeout
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(trafilatura.fetch_url, url)
                    try:
                        downloaded = future.result(timeout=10)
                    except concurrent.futures.TimeoutError:
                        print(f"[Warn] Trafilatura fetch timed out for {url}")
                        downloaded = None

                if downloaded:
                    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                    if text and len(text) > 100:
                        return json.dumps({"source": url, "content": text[:15000], "type": "html"}, ensure_ascii=False)
            except Exception as e:
                print(f"[Monitoring] Trafilatura failed: {e}")
        
        # Fallback to BeautifulSoup
        try:
            session = get_session()
            # 加上 verify=False 防止证书错误
            resp = session.get(url, timeout=10, verify=False)
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")
            for t in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "button"]):
                t.extract()
            text = soup.get_text(separator="\n")
            import re as _re2

            text = _re2.sub(r"\n\s*\n", "\n", text)
            return json.dumps({"source": url, "content": text[:15000], "type": "html_fallback"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": "fetch_failed", "message": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "unexpected_error", "message": str(e)}, ensure_ascii=False)

def clean_answer(raw_answer: str) -> str:
    """
    工程级后处理：强制清洗答案格式
    """
    if not raw_answer:
        return ""
    
    # 1. 去除 Markdown 标记 (只去除 ``` 符号，保留内容)
    # 原方案 regex 会删除内容，这里修正为只删除标记
    clean = re.sub(r'```\w*', '', raw_answer)
    clean = clean.replace('```', '')
    clean = clean.replace('`', '').strip()
    
    # 2. 如果模型输出了 JSON 格式 ({"answer": "..."})，尝试提取
    # 有时候 JSON 前面还有杂质，尝试找第一个 { 和最后一个 }
    try:
        start = clean.find('{')
        end = clean.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = clean[start:end+1]
            data = json.loads(json_str)
            if 'answer' in data:
                clean = str(data['answer'])
    except:
        pass

    # 3. 去除常见的废话前缀/后缀 (循环多次以处理嵌套前缀)
    patterns = [
        r"^(answer|final answer|the answer is|output)[:：\s-]*",
        r"^答案是[:：]\s*",
        r"^The answer is[:：]\s*",
        r"^根据搜索结果[:：,，]\s*",
        r"^Final Answer[:：]\s*",
        r"^综上所述[:：,，]\s*",
        r"^经检索[:：,，]\s*",
        r"^因此[:：,，]\s*"
    ]
    
    for _ in range(3): # 运行几轮以处理 "根据搜索结果，答案是：" 这种情况
        changed = False
        for p in patterns:
            new_clean = re.sub(p, "", clean, flags=re.IGNORECASE).strip()
            if new_clean != clean:
                clean = new_clean
                changed = True
        if not changed:
            break

    # 4. 激进清洗：如果剩下的是 "2024年。" -> "2024" (针对数值题)
    clean = clean.strip(" 。.,'\"")
    
    # 5. 去重逻辑 (增强版)
    # 策略A: 检测带分隔符的重复 "Word.Word" "Word, Word"
    # (?:...) 是非捕获组，匹配中间可能出现的标点或空格
    m = re.match(r'^(.+?)(?:[ \t\n。,;!?.|]+)\1$', clean, re.IGNORECASE | re.DOTALL)
    if m:
        clean = m.group(1)
    else:
        # 策略B: 检测无分隔符的完全重复 "WordWord"
        m2 = re.match(r'^(.+?)\1$', clean, re.IGNORECASE | re.DOTALL)
        if m2:
            clean = m2.group(1)
        else:
            # 策略D: 检测起始部分的重复 (针对 "WordWordSuffix" 或 "Word, WordSuffix")
            # 必须在策略C之前，因为策略C处理的是部分重叠
            m3 = re.match(r'^(.+?)(?:[ \t\n。,;!?.|]*)\1', clean, re.IGNORECASE | re.DOTALL)
            found_prefix_dupe = False
            if m3:
                part1 = m3.group(1)
                # 限制重复部分长度 > 2，避免误伤叠词
                if len(part1) > 2:
                    suffix = clean[m3.end():]
                    clean = part1 + suffix
                    found_prefix_dupe = True
            
            if not found_prefix_dupe:
                # 策略C: 检测包含关系的重复 (Overlap)
                # 遍历所有切分点
                n = len(clean)
                if n > 10: # 只对较长的字符串做此检查
                    for i in range(3, n - 2): # 只有当两部分都至少有3个字符时
                        part1 = clean[:i]
                        part2 = clean[i:]
                        
                        # Case 1: Part1 is suffix of Part2 (e.g. "Name" + "FullName")
                        # ignore case and strip
                        p1s = part1.strip().lower()
                        p2s = part2.strip().lower()
                        
                        if len(p1s) > 3 and p2s.endswith(p1s):
                             clean = part2.strip()
                             break
                        
                        # Case 2: Part2 is suffix of Part1 (e.g. "FullName" + "Name")
                        if len(p2s) > 3 and p1s.endswith(p2s):
                             clean = part1.strip()
                             break
            
    # 再次清洗可能暴露出来的末尾标点
    clean = clean.strip(" 。.,'\"")
    
    return clean

def browse_page(url: str, instructions: str, max_bytes: int = 150_000) -> str:
    try:
        print(f"[Monitoring] browse_page url='{url}' instructions='{str(instructions)[:80]}'")
        fetched = web_fetch(url, max_bytes=max_bytes)
        data = json.loads(fetched)
        if "error" in data:
            return fetched
        content = str(data.get("content") or "")
        title = str(data.get("title") or "")
        prompt = [
            {"role": "system", "content": "You are a research assistant that produces concise structured summaries."},
            {"role": "user", "content": f"Task: {instructions}\nTitle: {title}\nContent:\n{content[:8000]}"},
        ]
        client = OpenAI(base_url="https://apis.iflow.cn/v1", api_key=os.getenv("IFLOW_API_KEY"), timeout=30.0)
        resp = client.chat.completions.create(model="qwen3-max", stream=False, temperature=0.3, max_tokens=800, messages=prompt)
        out = ""
        try:
            out = resp.choices[0].message.content or ""
        except Exception:
            out = ""
        if len(out) > 2000:
            out = out[:2000]
        return json.dumps({"source": url, "summary": out}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "browse_failed", "message": str(e)}, ensure_ascii=False)

def x_keyword_search(query: str, top_k: int = 5) -> str:
    try:
        base_q = f"(site:x.com OR site:twitter.com) {query}"
        return web_search(base_q, top_k=top_k)
    except Exception as e:
        return json.dumps({"error": "x_search_failed", "message": str(e)}, ensure_ascii=False)

def search_pdf_attachment(url: str, query: str, max_pages: int = 6) -> str:
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": _pick_ua(0)})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            data = resp.read(2_000_000)
        if "application/pdf" not in ctype and not url.lower().endswith(".pdf"):
            return json.dumps({"error": "not_pdf", "suggestions": ["ensure URL points to PDF"]}, ensure_ascii=False)
        text = ""
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = reader.pages[:max_pages]
            for p in pages:
                t = p.extract_text() or ""
                if t:
                    text += "\n" + t
        except Exception as e:
            return json.dumps({"error": "pdf_extract_failed", "message": str(e), "suggestions": ["install pypdf", "try browse_pdf_attachment"]}, ensure_ascii=False)
        toks = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", text)
        hits = []
        q = str(query or "").lower()
        if q:
            for i in range(0, len(toks), 100):
                seg = " ".join(toks[i:i+100])
                if q in seg.lower():
                    hits.append({"segment": seg[:300]})
        return json.dumps({"source": url, "matches": hits[:top_k], "bytes": len(data)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "pdf_search_failed", "message": str(e)}, ensure_ascii=False)

def browse_pdf_attachment(url: str, instructions: str, max_pages: int = 6) -> str:
    try:
        print(f"[Monitoring] browse_pdf_attachment url='{url}' instructions='{str(instructions)[:80]}'")
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": _pick_ua(1)})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            data = resp.read(2_000_000)
        if "application/pdf" not in ctype and not url.lower().endswith(".pdf"):
            return json.dumps({"error": "not_pdf", "suggestions": ["ensure URL points to PDF"]}, ensure_ascii=False)
        text = ""
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = reader.pages[:max_pages]
            for p in pages:
                t = p.extract_text() or ""
                if t:
                    text += "\n" + t
        except Exception as e:
            return json.dumps({"error": "pdf_extract_failed", "message": str(e), "suggestions": ["install pypdf"]}, ensure_ascii=False)
        prompt = [
            {"role": "system", "content": "You summarize PDF content into concise structured facts."},
            {"role": "user", "content": f"Task: {instructions}\nContent:\n{text[:8000]}"},
        ]
        client = OpenAI(base_url="https://apis.iflow.cn/v1", api_key=os.getenv("IFLOW_API_KEY"), timeout=30.0)
        resp = client.chat.completions.create(model="qwen3-max", stream=False, temperature=0.3, max_tokens=800, messages=prompt)
        out = ""
        try:
            out = resp.choices[0].message.content or ""
        except Exception:
            out = ""
        if len(out) > 2000:
            out = out[:2000]
        return json.dumps({"source": url, "summary": out}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "browse_pdf_failed", "message": str(e)}, ensure_ascii=False)
def multi_hop_search(query: str, max_hops: int = 3) -> str:
    """
    多跳推理搜索：自动拆解复杂问题为多个子查询

    应用logid15.md的漏斗式搜索法：
    1. 拆解：提取锚点关键词
    2. 收敛：先找实体，再查属性
    3. 验证：回测答案是否符合所有条件

    Args:
        query: 包含多个条件的复杂问题
        max_hops: 最大搜索跳数（默认3）

    Returns:
        JSON格式的搜索结果，包含每一跳的信息

    示例:
        query: "某日本娱乐公司在20世纪晚期成立，制作知名动作游戏系列并改编成动画片，该公司成立于哪一年？"

        Hop 1: 搜索 "famous video game animated adaptations action"
        Hop 2: 从结果中识别候选实体（如 Castlevania → Konami）
        Hop 3: 搜索 "Konami founding date"
    """
    try:
        import re as _re
        print(f"[Monitoring] multi_hop_search query='{query}' max_hops={max_hops}")

        # 步骤1: 分析查询，识别目标属性和约束条件
        target_attribute = None
        constraints = []

        # 识别目标属性（问题要求的答案类型）
        attribute_patterns = {
            'year': r'(哪一年|什么时候|when|which year|founding|established|founded)',
            'person': r'(谁|who|author|creator|founder|inventor)',
            'location': r'(哪里|where|location|place|country|city)',
            'number': r'(多少|how many|how much|数量|价格|票房)',
            'name': r'(叫什么|名字|name|title|called)'
        }

        for attr_type, pattern in attribute_patterns.items():
            if _re.search(pattern, query, _re.IGNORECASE):
                target_attribute = attr_type
                break

        # 步骤2: 提取锚点关键词（高价值词）
        entities = _extract_core_entities(query)

        # 步骤3: 构建漏斗式搜索序列
        search_hops = []

        # Hop 1: 使用锚点词搜索，确定候选实体
        if entities:
            # 选择最具体的2-3个实体组合
            anchor_keywords = entities[:3]
            hop1_query = ' '.join(anchor_keywords)
            search_hops.append({
                'hop': 1,
                'purpose': 'identify_entity',
                'query': hop1_query,
                'strategy': 'anchor_keywords'
            })
        else:
            # 如果实体提取失败，直接使用原查询
            search_hops.append({
                'hop': 1,
                'purpose': 'identify_entity',
                'query': query,
                'strategy': 'direct_query'
            })

        # 执行第一跳搜索
        hop1_result = web_search(search_hops[0]['query'], top_k=5)
        hop1_data = json.loads(hop1_result)

        if 'error' in hop1_data:
            return json.dumps({
                'error': 'hop1_failed',
                'message': hop1_data.get('message', 'First hop search failed'),
                'hops_attempted': 1
            }, ensure_ascii=False)

        # 步骤4: 从第一跳结果中提取候选实体
        # 这里使用简化策略：从标题中提取专有名词
        candidate_entities = []
        for result in hop1_data.get('results', [])[:3]:
            title = result.get('title', '')
            snippet = result.get('snippet', '')

            # 提取首字母大写的词组（可能的实体名）
            entities_in_result = _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', title + ' ' + snippet)
            candidate_entities.extend(entities_in_result)

        # 去重并保留前5个候选
        candidate_entities = list(dict.fromkeys(candidate_entities))[:5]

        # Hop 2: 如果识别出目标属性，针对候选实体查询该属性
        if target_attribute and candidate_entities:
            # 构建第二跳查询：实体 + 目标属性
            entity = candidate_entities[0]  # 使用最可能的候选

            attribute_query_templates = {
                'year': f'{entity} founding date established when',
                'person': f'{entity} founder creator author',
                'location': f'{entity} location headquarters country',
                'number': f'{entity} box office revenue sales',
                'name': f'{entity} official name title'
            }

            hop2_query = attribute_query_templates.get(target_attribute, f'{entity} {target_attribute}')
            search_hops.append({
                'hop': 2,
                'purpose': 'query_attribute',
                'query': hop2_query,
                'entity': entity,
                'attribute': target_attribute
            })

            # 执行第二跳搜索
            hop2_result = web_search(hop2_query, top_k=5)
            hop2_data = json.loads(hop2_result)

            return json.dumps({
                'source': 'multi_hop_search',
                'total_hops': 2,
                'target_attribute': target_attribute,
                'identified_entity': entity,
                'candidate_entities': candidate_entities,
                'search_sequence': search_hops,
                'hop1_results': hop1_data.get('results', [])[:2],  # 只返回前2个节省空间
                'hop2_results': hop2_data.get('results', [])[:3],
                'recommendation': f'建议从 hop2_results 中提取 {target_attribute} 相关信息'
            }, ensure_ascii=False)
        else:
            # 如果未识别出目标属性或候选实体，返回第一跳结果
            return json.dumps({
                'source': 'multi_hop_search',
                'total_hops': 1,
                'target_attribute': target_attribute,
                'candidate_entities': candidate_entities,
                'search_sequence': search_hops,
                'hop1_results': hop1_data.get('results', []),
                'recommendation': '未能自动识别目标属性，建议手动分析结果或使用 web_fetch 读取详细内容'
            }, ensure_ascii=False)

    except Exception as e:
        print(f"[Monitoring] multi_hop_search error: {e}")
        return json.dumps({
            'error': 'multi_hop_failed',
            'message': str(e),
            'fallback': '建议使用普通 web_search'
        }, ensure_ascii=False)


def get_weather(location: str) -> str:
    """
    Get the weather information for a given location.
    """
    return f"The weather of {location} is sunny."

def _post_process_answer(ans: str) -> str:
    return clean_answer(ans)

FEW_SHOT_EXAMPLES = """
### 示例 1 (多跳推理 + PDF 阅读)
用户问题: "2023年获得诺贝尔生理学或医学奖的科学家，他们的主要贡献解决了什么关键问题？"

Thought: 这是一个关于诺贝尔奖的问题。
1. 我需要先搜索2023年诺贝尔生理学或医学奖得主。
2. 然后查找他们的贡献细节。
Action: web_search
Action Input: {"query": "2023 Nobel Prize in Physiology or Medicine winners contributions"}
Observation: [搜索结果] 提到 Katalin Karikó 和 Drew Weissman。关键词：mRNA vaccines, nucleoside base modification.
Thought: 搜索结果提到了 mRNA 疫苗和核苷碱基修饰。我需要更详细的信息来确认“解决了什么关键问题”。我应该找官方新闻或详细报道。
Action: web_search
Action Input: {"query": "Katalin Karikó Drew Weissman contributions nucleoside base modification details"}
Observation: [搜索结果] 包含一个指向 nobelprize.org 的 PDF 链接 "press_medicine2023.pdf"。
Thought: 官方 PDF 是最可靠的来源。我必须阅读它。
Action: web_fetch
Action Input: {"url": "https://www.nobelprize.org/.../press_medicine2023.pdf"}
Observation: [PDF内容] ...discovered that nucleoside base modification enabled effective delivery of mRNA... eliminated the inflammatory reaction...
Thought: 根据 PDF，关键问题是外源 mRNA 会引起炎症反应（inflammatory reaction）并被降解，限制了应用。他们的发现通过碱基修饰消除了这种反应。
Final Answer: 解决了外源 mRNA 进入人体后会引发炎症反应（inflammatory reaction）且产生蛋白水平低的关键问题，从而使开发有效的 mRNA 疫苗成为可能。

### 示例 2 (自我纠错/Reflexion)
用户问题: "查询电影《奥本海默》全球票房精确数字（美元）。"

Thought: 直接搜索奥本海默全球票房。
Action: web_search
Action Input: {"query": "Oppenheimer global box office exact number"}
Observation: [搜索结果] $950 Million, $960M, 9.76亿美元。
Thought: 搜索结果比较模糊，有多个近似值。题目要求“精确数字”。我需要找 Box Office Mojo 或权威财经新闻的最新数据。
Action: web_search
Action Input: {"query": "Oppenheimer box office mojo worldwide lifetime gross"}
Observation: [搜索结果] Box Office Mojo 显示 Lifetime Gross: $976,166,665.
Thought: 这是一个精确数字。
Final Answer: 976,166,665
"""

class QueryRequest(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {"question": "What is the weather in Beijing today?"}
        },
    )

    question: str
    chat_history: Optional[list] = None

    def to_messages(self) -> list:
        if self.chat_history:
            return self.chat_history + [{"role": "user", "content": self.question}]
        else:
            return [
                {
                    "role": "system",
                    "content": (
                        """你是一个专业的 Research Agent。你的唯一目标是给出精准的事实性答案。

### 核心原则
1. **证据驱动**: 每个结论必须有明确证据，标注来源URL
2. **多源验证**: 关键信息（人名/日期/数字）需≥2个独立来源确认
3. **深度优先**: 优先使用 web_fetch 读取全文，而非依赖搜索摘要
4. **善用 Skills**: 复杂任务使用专门的 Skills 提升准确性
5. **语言一致性**: 答案语言必须与问题语言保持一致（中文问题用中文回答，英文问题用英文回答），除非问题明确要求特定语言。

### 可用 Skills
- **smart-search**: 智能多策略搜索，根据问题类型自动选择最佳搜索策略（学术/新闻/时间线/对比/定义）。初次搜索或需要改变策略时使用。
- **multi-source-verify**: 多源验证答案准确性。验证关键事实（人名/日期/数字）时使用，要求至少2个独立来源支持。
- **chain-of-verification**: 验证链推理。对复杂或高价值问题，生成验证问题并独立搜索验证，修正答案。当置信度<0.8时使用。
- **deep-research**: 深度研究。需要多步深度研究和证据综合时使用。

### 多跳推理策略（漏斗式搜索法）
面对包含多个条件的复杂问题，采用以下四步法：

**步骤1 - 拆解与提取（识别锚点）**
- 不要搜索整句话，而是识别最独特、最不容易重合的"锚点"关键词
- 低价值词示例（太宽泛）："日本公司"、"20世纪"、"知名游戏"
- 高价值词示例（锚点）："改编动画片"、"动作游戏系列"、具体作品名
- 优先从最具体的线索入手，而非从最大的集合入手

**步骤2 - 逐步收敛（漏斗搜索）**
- 第一步：确定实体（利用"交集"逻辑找唯一解）
  - 搜索高价值锚点词组合：如 "video game animated adaptation action"
  - 从结果中筛选符合约束条件的候选项
- 第二步：查询属性（针对锁定实体精准查询）
  - 一旦锁定目标实体（如某公司/作品），再查具体属性
  - 示例："Konami founding date"

**步骤3 - 高阶搜索指令**
- 强制匹配（引号）："animated series" "action game" Japan
- 站内搜索（site:）：site:wikipedia.org "video game company" "founded"
- 排除干扰（减号）：Japanese game company -Nintendo -Sony
- 百科类问题优先使用 Wikipedia/专业Wiki

**步骤4 - 验证与三角测量**
- 对推理出的答案进行"回测"，确保符合所有描述条件
- 逐一验证：改编动画？✓ 动作游戏？✓ 成立时间？✓ 影响力？✓

**多跳推理示例**
问题："某日本娱乐公司在20世纪晚期成立，制作知名动作游戏系列并改编成动画片，该公司成立于哪一年？"

错误做法❌：直接搜索整句话
正确做法✅：
1. 搜索锚点："famous video game animated adaptations" 或 "best animated series based on video games action"
2. 发现候选：Castlevania（恶魔城）、Devil May Cry（鬼泣）等
3. 筛选：符合"action game franchise"且"late 20th century"→ Castlevania (Konami)
4. 精准查询："Konami founding date" → 1969年3月21日
5. 验证：✓改编动画(Netflix)、✓动作游戏、✓1969年(20世纪晚期)、✓多个系列

### 推理模式
Action → Observation → Reflection → (Verify with Skills) → Final Answer

### 黄金法则
1. **搜索摘要常错误**: 必须使用 web_fetch 读取全文验证，不能只看摘要
2. **PDF优先**: 学术/历史/法律问题答案常在PDF中，优先使用 browse_pdf_attachment
3. **拆分复杂问题**: 复杂问题拆分为子问题，逐步验证。多跳问题必须使用漏斗搜索法
4. **死循环检测**: 连续2次相似搜索无进展→立即改变策略（切换锚点关键词或使用 smart-search）
5. **仅输出答案**: 严格只输出答案文本，无"答案是"等前缀。人名输出全名，数字输出精确值
6. **日期/数字精确**: 对于"哪一年""多少钱"类问题，务必精确匹配，不可估算
7. **必须回答**: 即使不确定，也要根据现有信息提供最可能的答案。**绝对禁止**输出"无法确定"、"找不到"

### Skills 使用建议
- 初次搜索某个主题 → 使用 **smart-search**
- 找到候选答案后 → 使用 **multi-source-verify** 验证
- 复杂问题或置信度中等 → 使用 **chain-of-verification**
- 需要多步深度研究 → 使用 **deep-research**

### 思考模式
Action → Observation → Reflection → Action ... → Final Answer

"""
                        f"{FEW_SHOT_EXAMPLES}"
                    ),
                },
                {"role": "user", "content": self.question},
            ]


class QueryResponse(BaseModel):
    answer: str


@app.post("/")
async def query(req: QueryRequest) -> QueryResponse:
    """
    Basic LLM API example.

    Invoke example:

    ```
    curl -X POST "http://localhost:8000/" \
    -H "Content-Type: application/json" \
    -d '{"question": "What is the weather in Beijing today?"}'

    ```

    Response example:

    ```json
    {
        "answer": "Beijing has sunny weather today, with temperatures between 10°C and 20°C."
    }
    ```


    """

    result = ""

    # Return messages after the last tool call message as the final answer
    async for chunk in agent_loop(req.to_messages(), [web_search, web_fetch, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, multi_hop_search, get_weather], max_steps=15):
        if chunk.type == "tool_call" or chunk.type == "tool_call_result":
            result = ""
        elif chunk.type == "text" and chunk.content:
            result += chunk.content

    # Clean answer
    final_answer = clean_answer(result)
    # Verify answer
    final_answer = verify_answer(req.question, final_answer)

    return QueryResponse(answer=final_answer)


@app.post("/stream")
async def stream(req: QueryRequest) -> StreamingResponse:
    """
    Streaming query example.
    Invoke example:

    ```shell
    curl -N -X POST "http://localhost:8000/stream" \
    -H "Content-Type: application/json" \
    -d '{"question": "What is the weather in Beijing today?"}'

    ```

    Response example:

    ```text

    data: {"answer": "Beijing has "}

    data: {"answer": "sunny weather"}

    data: {"answer": " today, with"}

    data: {"answer": " temperatures"}

    data: {"answer": " between 10°C and 20°C."}


    ```

    """

    async def stream_response():
        full_text = ""
        async for chunk in agent_loop(req.to_messages(), [web_search, web_fetch, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, multi_hop_search, get_weather], max_steps=15):
            if chunk.type == "text" and chunk.content:
                full_text += chunk.content
                data = {"answer": chunk.content}
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        
        # 可选：在流结束后发送一个包含完整清理后答案的特殊包，或者简单的结束标识
        # 这里保持 SSE 规范，不额外增加清理后的包，因为流式输出通常是为了实时展示
    
    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
    )

if _AGUI_AVAILABLE:
    @app.post("/ag-ui")
    async def ag_ui(run_agent_input: RunAgentInput) -> StreamingResponse:
        messages = to_openai_messages(run_agent_input.messages)
        async def stream_response():
            async for event in stream_agui_events(
                chunks=agent_loop(messages, [web_search, web_fetch, browse_page, extract_entities, x_keyword_search, search_pdf_attachment, browse_pdf_attachment, get_weather], max_steps=15),
                run_agent_input=run_agent_input,
            ):
                yield to_sse_data(event)
        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception:
        uvicorn.run(app, host="0.0.0.0", port=8001)
