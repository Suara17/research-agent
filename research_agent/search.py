import os
import json
import urllib.parse
import urllib.request
import requests
import concurrent.futures
import ssl
import re
import io
import time
from html.parser import HTMLParser
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pathlib import Path

# Third party imports (try/except)
try:
    from ddgs import DDGS
    _DDGS_AVAILABLE = True
except ImportError:
    _DDGS_AVAILABLE = False

try:
    import trafilatura
    _TRAFILATURA_AVAILABLE = True
except ImportError:
    _TRAFILATURA_AVAILABLE = False

try:
    from serpapi import GoogleSearch
    _SERPAPI_LIB_AVAILABLE = True
except ImportError:
    _SERPAPI_LIB_AVAILABLE = False

try:
    from baidusearch.baidusearch import search as baidu_search
    _BAIDU_AVAILABLE = True
except ImportError:
    _BAIDU_AVAILABLE = False

try:
    from googlesearch import search as google_search_scraper
    _GOOGLE_SCRAPER_AVAILABLE = True
except ImportError:
    _GOOGLE_SCRAPER_AVAILABLE = False

from .utils import get_session, get_llm_client, clean_answer
from .intelligent_fetcher import get_intelligent_fetcher

# --- Helpers ---

_KNOWN_TIMEOUT_DOMAINS = {
    "www.cia.gov",
    "www.state.gov",
}

def _fetch_with_jina(url: str, session) -> Optional[str]:
    """
    尝试使用 Jina Reader 获取网页内容的 Markdown
    """
    try:
        # Jina Reader URL 格式: https://r.jina.ai/<目标URL>
        jina_url = f"https://r.jina.ai/{url}"
        
        # Jina 建议的 Headers
        headers = {
            "X-Return-Format": "markdown"
        }
        
        # 15秒超时，避免阻塞太久
        resp = session.get(jina_url, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            text = resp.text
            # 简单验证内容有效性 (Jina 有时会返回错误提示 json)
            if "jina.ai" in text and "error" in text.lower() and len(text) < 200:
                print(f"[Jina] API returned error message: {text}")
                return None
                
            return text
        else:
            print(f"[Jina] Failed with status code: {resp.status_code}")
            return None
            
    except Exception as e:
        print(f"[Jina] Exception during fetch: {e}")
        return None

# URL去重缓存：归一化URL -> (内容, 时间戳)
_URL_FETCH_CACHE = {}
_URL_FETCH_LIMIT = 100  # 最多缓存100个URL

_UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/120.0",
]

def _normalize_url(url: str) -> str:
    """归一化URL：去除锚点和查询参数（可选），统一为小写"""
    parsed = urllib.parse.urlparse(url)
    # 只去除锚点，保留查询参数（因为查询参数可能改变内容）
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized.lower()

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

def _filter_search_results(results: list) -> list:
    if not results:
        return []
    filtered = []
    sensitive_keywords = {
        "porn", "xxx", "sex", "gambling", "casino", 
        "色情", "赌博", "av", "hentai", "fuck", "bitch",
        "whore", "slut", "asshole", "nigger", "faggot"
    }
    for r in results:
        title = str(r.get("title") or "").lower()
        snippet = str(r.get("summary") or r.get("snippet") or "").lower()
        content = f"{title} {snippet}"
        if any(kw in content for kw in sensitive_keywords):
            continue
        filtered.append(r)
    return filtered

def _rerank_search_results(results, query: str, top_k: int):
    # Deprecated: Reranking based on regex entity extraction is unreliable.
    # We trust the search engine's ranking and the LLM's ability to filter relevant results.
    if not results:
        return results
    return results[:top_k]

def extract_answer_from_search_results(search_results: list, query: str) -> dict:
    try:
        from collections import Counter
        candidates = []
        if not search_results:
             return {"candidates": [], "extraction_method": "no_results"}
        for result in search_results:
            title = result.get('title', '')
            snippet = result.get('summary') or result.get('snippet') or ''
            combined = f"{title} {snippet}"
            quoted = re.findall(r'"([^"]+)"', combined)
            candidates.extend(quoted)
            book_names = re.findall(r'《([^》]+)》', combined)
            candidates.extend(book_names)
        for result in search_results[:3]:
            title = result.get('title', '')
            capitalized = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', title)
            candidates.extend(capitalized)
        if not candidates:
            return {"candidates": [], "extraction_method": "no_candidates"}
        counter = Counter(candidates)
        ranked_candidates = []
        for text, count in counter.most_common(5):
            if len(text) < 3 or len(text) > 100:
                continue
            confidence = min(0.9, (count / len(search_results)) * 0.5 + 0.3)
            if search_results and text in search_results[0].get('title', ''):
                confidence = min(0.95, confidence + 0.2)
            ranked_candidates.append({
                "text": text,
                "confidence": round(confidence, 2),
                "sources": count
            })
        return {
            "candidates": ranked_candidates,
            "extraction_method": "search_metadata"
        }
    except Exception as e:
        print(f"[Monitoring] extract_answer_from_search_results error: {e}")
        return {"candidates": [], "extraction_method": "error"}

def _optimize_search_query(query: str) -> str:
    """
    Use LLM to optimize search query for better results.
    Preserves advanced operators (site:, filetype:) if present.
    """
    try:
        # 1. If query contains advanced operators, trust the user/agent and return as is (just trim)
        if "site:" in query.lower() or "filetype:" in query.lower() or "intitle:" in query.lower():
            return query.strip()

        # 2. If query is short/simple, use regex optimization to save time
        if len(query) < 20 and not any(k in query.lower() for k in ["who", "what", "where", "when", "why", "how", "什么", "谁", "哪里", "怎么"]):
            return query.strip()
            
        # Add Length Limit Logic
        if len(query) > 300:
            query = query[:300]

        # 3. Use LLM for complex natural language queries
        client = get_llm_client()
        prompt = f"""<instruction>
<role>搜索引擎优化专家</role>
<task>将用户的自然语言查询转换为精确的搜索引擎查询。</task>
<rules>
  <rule>提取核心关键词。</rule>
  <rule>删除对话填充词 ("什么是", "搜索", "我需要找到")。</rule>
  <rule>对特定实体 (人名, 电影) 使用引号 ""。</rule>
  <rule>对于谜题或类别搜索, 使用 "List of..." 模式。</rule>
  <rule>保持简短有效。</rule>
</rules>
<input>{query}</input>
<output>仅返回查询字符串。</output>
</instruction>"""
        
        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[
                {"role": "system", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=64
        )
        
        if not response or not response.choices:
            print(f"[Monitoring] LLM returned empty response or choices")
            return query.strip()
            
        optimized = response.choices[0].message.content.strip().strip('"')

        
        # Fallback validation
        if not optimized or len(optimized) < 3:
            return query.strip()
            
        print(f"[Monitoring] LLM_query_optimization: '{query}' → '{optimized}'")
        return optimized

    except Exception as e:
        print(f"[Monitoring] query_optimization_error: {e}")
        return query.strip()

def _simplify_search_query(query: str) -> str:
    try:
        # DO NOT remove site: or filetype: operators!
        # simplified = re.sub(r'site:\S+', '', query, flags=re.IGNORECASE)
        # simplified = re.sub(r'filetype:\S+', '', simplified, flags=re.IGNORECASE)
        
        simplified = query
        if len(simplified) > 100: # Only truncate if extremely long
             simplified = simplified[:100]
             
        simplified = re.sub(r'\s+', ' ', simplified).strip()
        return simplified
    except Exception:
        return query

def _create_entity_query(query: str) -> str:
    # _extract_core_entities is removed. Return empty string.
    return ""

def _translate_query(query: str, target_lang: str = "English") -> str:
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": f"<instruction><task>为搜索引擎优化翻译搜索查询</task><target_lang>{target_lang}</target_lang><constraint>保持专有名词和关键术语准确</constraint><query>{query}</query></instruction>"}],
            max_tokens=128
        )
        return resp.choices[0].message.content.strip().strip('"')
    except Exception:
        return query

def expand_query_language(query: str) -> list:
    queries = []
    if any("\u4e00" <= ch <= "\u9fff" for ch in query):
        en_q = _translate_query(query, "English")
        if en_q and en_q.lower() != query.lower():
            queries.append(en_q)
    return queries

def _extract_search_slots(query: str) -> dict:
    try:
        client = get_llm_client()
        prompt = [
            {"role": "system", "content": """<instruction>
<task>从查询中提取搜索槽位。</task>
<output_format>json_object</output_format>
<keys>
  <key name="type">"Person" | "Organization" | "Event" | "Object" | "Other"</key>
  <key name="hard_constraints">严格条件列表 (年份, 地点, 角色, 具体事件)</key>
  <key name="soft_constraints">描述性条件列表 (丑闻, 教育, 家庭)</key>
  <key name="anchors">用于搜索的唯一关键词列表 (名称, 具体术语)</key>
  <key name="target_country">国家名称 (英文) 如果适用, 否则 null</key>
</keys>
</instruction>"""},
            {"role": "user", "content": f"<input><query>{query}</query></input>"}
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
            
        try:
            api = f"https://{host}/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
            req = urllib.request.Request(api, headers={"User-Agent": _WIKI_UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            extract = str(data.get("extract") or "")
            if extract:
                return {"source": api, "content": extract, "title": data.get("title") or title, "sitename": host, "type": "wiki-summary"}
        except Exception as e:
            print(f"[Monitoring] Wiki REST API failed: {e}")

        try:
            api_php = f"https://{host}/w/api.php?action=query&format=json&prop=extracts&titles={urllib.parse.quote(title)}&exintro=1&explaintext=1"
            req = urllib.request.Request(api_php, headers={"User-Agent": _WIKI_UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
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

# --- Main Functions ---

def web_search(query: str, top_k: int = 5) -> str:
    try:
        print(f"[Monitoring] web_search query='{query}'")
        if not isinstance(query, str) or not query.strip():
            return json.dumps({"error": "empty_query"}, ensure_ascii=False)

        # Entity Quantity Detection and Limit
        quoted_entities = re.findall(r'"[^"]+"', query)
        if len(quoted_entities) > 6:
            print(f"[Monitoring] Query contains {len(quoted_entities)} entities (limit 6). Truncating...")
            matches = list(re.finditer(r'"[^"]+"', query))
            if len(matches) > 6:
                # Keep first 6 entities
                cutoff = matches[5].end()
                query = query[:cutoff]

        optimized = _optimize_search_query(query)
        queries_to_try = [optimized]
        
        lang_expanded = expand_query_language(optimized)
        for eq in lang_expanded:
            if eq not in queries_to_try:
                queries_to_try.append(eq)
                print(f"[Monitoring] Added cross-lingual query: '{eq}'")

        simplified = _simplify_search_query(query)
        if simplified and simplified != queries_to_try[0]:
            queries_to_try.append(simplified)
            
        if len(query) > 40:
            entity_q = _create_entity_query(query)
            if entity_q and entity_q not in queries_to_try:
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
        bocha_key = os.getenv("BOCHA_API_KEY")
        
        for attempt_idx, current_q in enumerate(queries_to_try):
            if attempt_idx > 0:
                print(f"[Monitoring] Primary search failed/empty. Retrying with simplified query: '{current_q}'")

            print(f"\n[Search] Executing Search: '{current_q}' (Original: '{query}')")

            is_chinese_query = any("\u4e00" <= ch <= "\u9fff" for ch in current_q)

            if is_chinese_query and _BAIDU_AVAILABLE:
                try:
                    results = []
                    # baidusearch usually returns a list of dicts
                    baidu_gen = baidu_search(current_q, num_results=k)
                    for r in baidu_gen:
                        results.append({
                            "title": r.get("title"),
                            "summary": r.get("abstract"),
                            "url": r.get("url"),
                        })
                    if results:
                        results = _filter_search_results(results)
                        results = _rerank_search_results(results, query, k)
                        return json.dumps({"source": "baidu", "results": results}, ensure_ascii=False)
                except Exception as e:
                    print(f"[Monitoring] Baidu error: {e}")

            if serper_key:
                try:
                    url = "https://google.serper.dev/search"
                    payload_dict = {
                        "q": current_q,
                        "num": k,
                        "gl": "cn" if is_chinese_query else "us",
                        "hl": "zh-cn" if is_chinese_query else "en"
                    }
                    payload = json.dumps(payload_dict)
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
                except Exception as e:
                    print(f"[Monitoring] Serper error (attempt {attempt_idx}): {e}")

            if serpapi_key:
                try:
                    if _SERPAPI_LIB_AVAILABLE:
                        params = {
                            "api_key": serpapi_key,
                            "q": current_q,
                            "engine": "google",
                            "num": k,
                            "google_domain": "google.com.hk" if is_chinese_query else "google.com",
                            "gl": "cn" if is_chinese_query else "us",
                            "hl": "zh-cn" if is_chinese_query else "en"
                        }
                        search = GoogleSearch(params)
                        results = []
                        data = search.get_dict()
                        if "organic_results" in data:
                            for item in data["organic_results"]:
                                results.append({
                                    "title": item.get("title", ""),
                                    "summary": item.get("snippet", ""),
                                    "url": item.get("link", "")
                                })
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
                            
                            # --- Enhanced Logging ---
                            print(f"[Search] Found {len(results)} results via SerpApi.")
                            for i, res in enumerate(results[:3]): # Log top 3
                                print(f"  [{i+1}] {res['title']} ({res['url']})\n      {res['summary'][:100]}...")
                            # ------------------------

                            return json.dumps({"source": "serpapi-lib", "results": results}, ensure_ascii=False)
                    else:
                        url = "https://serpapi.com/search"
                        params = {
                            "api_key": serpapi_key,
                            "q": current_q,
                            "engine": "google",
                            "num": k
                        }
                        response = requests.get(url, params=params, timeout=15)
                        
                        if response.status_code == 200:
                            data = response.json()
                            results = []
                            if "organic_results" in data:
                                for item in data["organic_results"]:
                                    results.append({
                                        "title": item.get("title", ""),
                                        "summary": item.get("snippet", ""),
                                        "url": item.get("link", "")
                                    })
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
                except Exception as e:
                    print(f"[Monitoring] SerpApi error: {e}")

            if _GOOGLE_SCRAPER_AVAILABLE:
                try:
                    # Fallback to google-search-scraper if API keys are missing or failed
                    # Note: This might be rate-limited
                    results = []
                    # google_search_scraper yields urls, we might need to fetch them or just return links?
                    # actually the library 'googlesearch-python' yields strings (URLs) usually.
                    # Wait, the prompt said "googlesearch-python>=1.3.0".
                    # The import is "from googlesearch import search as google_search_scraper"
                    # Standard usage: search("query", advanced=True) returns objects with title/description in recent versions?
                    # Let's assume standard usage for safety: search(query, num_results=k, advanced=True)
                    
                    # Check if 'advanced' parameter is supported (it is in googlesearch-python)
                    # If it's the old 'google' library, it only returns URLs.
                    # The requirement said 'googlesearch-python', so it supports advanced=True.
                    
                    g_results = google_search_scraper(current_q, num_results=k, advanced=True)
                    for r in g_results:
                        results.append({
                            "title": r.title,
                            "summary": r.description,
                            "url": r.url
                        })
                    
                    if results:
                        results = _filter_search_results(results)
                        results = _rerank_search_results(results, query, k)
                        return json.dumps({"source": "google-scraper", "results": results}, ensure_ascii=False)
                except Exception as e:
                    print(f"[Monitoring] Google Scraper error: {e}")

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
                except Exception as e:
                    print(f"[Monitoring] Brave search error (attempt {attempt_idx}): {e}")

            if _DDGS_AVAILABLE:
                try:
                    results = []
                    region = "wt-wt"
                    if any("\u4e00" <= ch <= "\u9fff" for ch in current_q):
                        region = "cn-zh"
                    
                    backends_to_try = ["auto", "html", "lite"]
                    
                    with DDGS() as ddgs:
                        for backend in backends_to_try:
                            try:
                                ddgs_gen = ddgs.text(current_q, max_results=k, region=region, backend=backend)
                                current_results = []
                                for r in ddgs_gen:
                                    current_results.append({
                                        "title": r.get("title"),
                                        "summary": r.get("body"),
                                        "url": r.get("href"),
                                    })
                                
                                if current_results:
                                    results = current_results
                                    break 
                            except Exception:
                                continue

                    if results:
                        results = _filter_search_results(results)
                        results = _rerank_search_results(results, query, k)
                        return json.dumps({"source": "ddgs", "results": results}, ensure_ascii=False)
                        
                except Exception as e:
                    print(f"[Monitoring] DDGS error (attempt {attempt_idx}): {e}")
        
        return json.dumps({"error": "search_failed", "message": "All providers failed"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "unexpected_error", "message": str(e)}, ensure_ascii=False)

def web_fetch(url: str, max_bytes: int = 200_000) -> str:
    try:
        print(f"[Monitoring] web_fetch called with url='{url}'")

        # URL去重检测
        normalized_url = _normalize_url(url)
        if normalized_url in _URL_FETCH_CACHE:
            cached_content, cached_time = _URL_FETCH_CACHE[normalized_url]
            # 缓存有效期：5分钟内直接返回
            if time.time() - cached_time < 300:
                print(f"[WebFetch] URL already fetched recently (cached). Skipping duplicate fetch: {url}")
                return cached_content
            else:
                print(f"[WebFetch] Cache expired for {url}, re-fetching...")

        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc

        # 使用智能请求器检查域名状态
        intelligent_fetcher = get_intelligent_fetcher()
        should_fetch, skip_reason = intelligent_fetcher.should_attempt_fetch(url)

        if not should_fetch:
            print(f"[WebFetch] {skip_reason}. Using snippet fallback.")
            raise TimeoutError(skip_reason)

        # 兼容旧的黑名单机制
        if domain in _KNOWN_TIMEOUT_DOMAINS:
            print(f"[WebFetch] Domain {domain} in legacy blacklist. Skip fetch, try snippet fallback.")
            raise TimeoutError(f"Domain {domain} known to timeout")

        path_lower = (parsed.path or "").lower()
        
        # === Jina Reader 优先策略 ===
        # 排除 Wikipedia (API已经很稳定) 和 PDF
        if "wikipedia.org" not in parsed.netloc and not url.lower().endswith(".pdf"):
            try:
                session = get_session()
                jina_content = _fetch_with_jina(url, session)
                
                if jina_content:
                    print(f"[WebFetch] Jina Reader success for {url}")
                    # 缓存成功的fetch结果
                    try:
                        result = json.dumps({
                            "source": url, 
                            "content": jina_content[:15000], 
                            "type": "jina_markdown"
                        }, ensure_ascii=False)
                        _URL_FETCH_CACHE[normalized_url] = (result, time.time())
                        if len(_URL_FETCH_CACHE) > _URL_FETCH_LIMIT:
                            oldest_key = min(_URL_FETCH_CACHE.keys(), key=lambda k: _URL_FETCH_CACHE[k][1])
                            del _URL_FETCH_CACHE[oldest_key]
                    except Exception:
                        pass

                    return json.dumps({
                        "source": url, 
                        "content": jina_content[:15000], 
                        "type": "jina_markdown"
                    }, ensure_ascii=False)
                else:
                    print(f"[WebFetch] Jina Reader failed/skipped, falling back to standard fetch...")
            except Exception as e_jina:
                print(f"[WebFetch] Jina Error: {e_jina}, falling back...")
        # ===========================

        if path_lower.endswith(".pdf") or url.lower().endswith(".pdf"):
            try:
                content = None
                def _download_pdf(u):
                    session = get_session()
                    r = session.get(u, timeout=15, stream=True, verify=False)
                    r.raise_for_status()
                    buf = b""
                    for chunk in r.iter_content(chunk_size=8192):
                        buf += chunk
                        if len(buf) > 5 * 1024 * 1024:
                            break
                    return buf

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_download_pdf, url)
                    try:
                         content = future.result(timeout=20)
                    except concurrent.futures.TimeoutError:
                         print(f"[Warn] PDF download timed out for {url}")
                         raise TimeoutError("PDF download timed out")
                    except Exception as e:
                         print(f"[Warn] PDF download error: {e}")
                         raise e

                if not content:
                     return json.dumps({"error": "pdf_empty"}, ensure_ascii=False)

                try:
                    reader = PdfReader(io.BytesIO(content), strict=False)
                    text = ""
                    for i, page in enumerate(reader.pages):
                        if i >= 10: break
                        try:
                            extracted = page.extract_text() or ""
                            if extracted:
                                text += extracted + "\n"
                        except Exception:
                            continue
                    
                    if len(text) < 50: 
                        return json.dumps({"error": "pdf_text_empty", "message": "Parsed PDF but found little text (scanned?)"}, ensure_ascii=False)
                    return json.dumps({"source": url, "content": text[:15000], "type": "pdf"}, ensure_ascii=False)
                except Exception as e:
                     print(f"[Warn] PDF parse error: {e}")
                     return json.dumps({"error": "pdf_parse_error", "message": str(e)}, ensure_ascii=False)

            except Exception as e:
                print(f"[Warn] PDF processing failed: {e}. Attempting Snippet Fallback.")
                try:
                    fallback_res = web_search(url, top_k=1)
                    fallback_data = json.loads(fallback_res)
                    if "results" in fallback_data and fallback_data["results"]:
                        first = fallback_data["results"][0]
                        snippet = first.get("summary") or first.get("snippet") or ""
                        title = first.get("title") or ""
                        if snippet:
                             return json.dumps({
                                "source": url,
                                "content": f"Title: {title}\nSnippet: {snippet}\n\n[System Note]: PDF download failed. This is the search snippet.",
                                "type": "snippet_fallback"
                            }, ensure_ascii=False)
                except Exception as e_fallback:
                    print(f"[Warn] PDF Fallback failed: {e_fallback}")
                
                # If fallback failed, just return error
                return json.dumps({"error": "pdf_failed", "message": str(e)}, ensure_ascii=False)

        if "wikipedia.org" in parsed.netloc:
             wiki_res = _fetch_wikipedia_rest(url)
             if wiki_res:
                 print(f"[Monitoring] Wiki fetch success via API for {url}")
                 return json.dumps(wiki_res, ensure_ascii=False)
             print(f"[Monitoring] Wiki API fetch failed for {url}, attempting Snippet Fallback immediately")
             try:
                fallback_res = web_search(url, top_k=1)
                fallback_data = json.loads(fallback_res)
                if "results" in fallback_data and fallback_data["results"]:
                    first = fallback_data["results"][0]
                    snippet = first.get("summary") or first.get("snippet") or ""
                    title = first.get("title") or ""
                    if snippet:
                        return json.dumps({
                            "source": url,
                            "content": f"Title: {title}\nSnippet: {snippet}\n\n[System Note]: Wiki API failed. This is the search snippet.",
                            "type": "snippet_fallback"
                        }, ensure_ascii=False)
             except Exception as e_wiki:
                 print(f"[Monitoring] Wiki Snippet Fallback failed: {e_wiki}")
             print(f"[Monitoring] Wiki Snippet Fallback failed or empty, continuing to standard fetch...")

        if _TRAFILATURA_AVAILABLE:
            try:
                # 使用智能请求器获取自适应超时
                timeout = intelligent_fetcher.domain_status.get_recommended_timeout(domain, 0)

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(trafilatura.fetch_url, url)
                    try:
                        downloaded = future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError:
                        print(f"[Warn] Trafilatura fetch timed out for {url} after {timeout}s")
                        downloaded = None

                if downloaded:
                    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                    if text and len(text) > 100:
                        # 成功时标记域名为可达
                        intelligent_fetcher.domain_status.mark_reachable(domain)
                        return json.dumps({"source": url, "content": text[:15000], "type": "html"}, ensure_ascii=False)
            except Exception as e:
                print(f"[Monitoring] Trafilatura failed: {e}")
        
        # 使用智能请求器进行HTTP请求
        try:
            session = get_session()
            # 使用智能请求器的自适应重试策略
            resp, error_msg = intelligent_fetcher.fetch_with_retry(
                url,
                session,
                max_retries=1,  # 只重试1次，而非原来的隐式3次
                verify_ssl=False
            )

            if resp is None:
                # 请求失败，抛出异常进入fallback逻辑
                raise Exception(error_msg or "Fetch failed")

            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")
            for t in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "button"]):
                t.extract()
            text = soup.get_text(separator="\n")
            import re as _re2
            text = _re2.sub(r"\n\s*\n", "\n", text)
            return json.dumps({"source": url, "content": text[:15000], "type": "html_fallback"}, ensure_ascii=False)
        except Exception as e:
            # 不再手动管理黑名单，由智能请求器自动处理
            print(f"[Monitoring] Fetch failed ({e}), attempting Snippet Fallback for {url}...")
            
            # Helper to extract text from URL
            def _extract_text_from_url(u: str) -> str:
                from urllib.parse import urlparse, unquote
                try:
                    parsed = urlparse(u)
                    path = unquote(parsed.path)
                    # Replace separators
                    text = path.replace("-", " ").replace("_", " ").replace("/", " ")
                    # Simple filter
                    words = [w for w in text.split() if len(w) > 2 and not w.isdigit()]
                    return " ".join(words)
                except:
                    return ""

            url_text = _extract_text_from_url(url)
            fallback_content = ""
            fallback_title = ""

            try:
                fallback_res = web_search(url, top_k=1)
                fallback_data = json.loads(fallback_res)
                if "results" in fallback_data and fallback_data["results"]:
                    first = fallback_data["results"][0]
                    snippet = first.get("summary") or first.get("snippet") or ""
                    title = first.get("title") or ""
                    if snippet:
                        fallback_content = f"Title: {title}\nSnippet: {snippet}"
                        fallback_title = title
            except Exception as e2:
                print(f"[Monitoring] Snippet Fallback failed: {e2}")
            
            # Combine results
            final_content = ""
            if fallback_content:
                final_content = f"{fallback_content}\n\n[System Note]: Full content fetch failed. Above is the search snippet."
            
            # Append URL semantic text if available
            if url_text and len(url_text) > 10:
                 final_content += f"\n\n[System Note]: Extracted keywords from URL path (HIGH VALUE):\n{url_text}"

            if final_content:
                return json.dumps({
                    "source": url,
                    "content": final_content,
                    "type": "snippet_fallback"
                }, ensure_ascii=False)
            
            return json.dumps({"error": "fetch_failed", "message": str(e)}, ensure_ascii=False)
    except Exception as e:
        result = json.dumps({"error": "unexpected_error", "message": str(e)}, ensure_ascii=False)
        return result
    finally:
        # 缓存成功的fetch结果（仅在没有异常时）
        try:
            if 'result' not in locals():
                # 获取最后一次成功返回的内容
                import inspect
                frame = inspect.currentframe()
                if frame and frame.f_locals.get('text'):
                    result = json.dumps({"source": url, "content": frame.f_locals['text'][:15000]}, ensure_ascii=False)
                    normalized_url = _normalize_url(url)
                    _URL_FETCH_CACHE[normalized_url] = (result, time.time())
                    # 限制缓存大小
                    if len(_URL_FETCH_CACHE) > _URL_FETCH_LIMIT:
                        # 删除最旧的条目
                        oldest_key = min(_URL_FETCH_CACHE.keys(), key=lambda k: _URL_FETCH_CACHE[k][1])
                        del _URL_FETCH_CACHE[oldest_key]
        except Exception:
            pass

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
            {"role": "system", "content": "<instruction><role>研究助理</role><task>生成简洁的结构化摘要。</task></instruction>"},
            {"role": "user", "content": f"<input><task>{instructions}</task><title>{title}</title><content>{content[:8000]}</content></input>"},
        ]
        client = get_llm_client(timeout=30.0)
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
        return json.dumps({"source": url, "matches": hits[:5], "bytes": len(data)}, ensure_ascii=False)
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
            {"role": "system", "content": "<instruction><role>Research Assistant</role><task>Summarize PDF content into concise structured facts.</task></instruction>"},
            {"role": "user", "content": f"<input><task>{instructions}</task><content>{text[:8000]}</content></input>"},
        ]
        client = get_llm_client(timeout=30.0)
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


def get_weather(location: str) -> str:
    return f"The weather of {location} is sunny."
