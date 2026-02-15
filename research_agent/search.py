import os
import json
import urllib.parse
import urllib.request
from urllib.parse import urlparse
from curl_cffi import requests
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import ssl
import re
import io
import time
import asyncio
from html.parser import HTMLParser
from typing import Optional, List, Dict, Any, Union
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
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

    _CRAWL4AI_AVAILABLE = True
except ImportError:
    _CRAWL4AI_AVAILABLE = False

try:
    from DrissionPage import ChromiumPage, ChromiumOptions, SessionPage

    _DRISSION_AVAILABLE = True
except ImportError:
    _DRISSION_AVAILABLE = False

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

# Global ThreadPool for fetching to avoid recreation overhead
_FETCH_EXECUTOR = ThreadPoolExecutor(max_workers=20)

# Global Session for connection reuse
_GLOBAL_SESSION = requests.Session(impersonate="chrome124")
_GLOBAL_SESSION.headers.update(
    {
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    }
)

# --- Helpers ---

_KNOWN_TIMEOUT_DOMAINS = {
    "www.cia.gov",
    "www.state.gov",
}


def _fetch_with_curl_cffi(url: str) -> Optional[str]:
    """
    Level 2: curl_cffi (Impersonate Browser, No JS)
    """
    try:
        # Impersonate Chrome to bypass basic WAF/403
        r = requests.get(url, impersonate="chrome120", timeout=10)
        if r.status_code == 200:
            # Use Trafilatura to extract content from HTML
            if _TRAFILATURA_AVAILABLE:
                text = trafilatura.extract(r.text, include_tables=True)
                if text and len(text) > 100:
                    return text

            # Fallback to simple extraction
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["script", "style"]):
                t.extract()
            return soup.get_text()[:15000]
    except Exception as e:
        print(f"[curl_cffi] Failed: {e}")
    return None


def _fetch_with_drission_session(url: str) -> Optional[str]:
    """
    Level 3: DrissionPage SessionPage (Optimized Requests, No JS)
    """
    if not _DRISSION_AVAILABLE:
        return None
    try:
        page = SessionPage()
        page.get(url, timeout=10)

        # Try extracting body text directly
        text = page.ele("tag:body").text
        if text and len(text) > 100:
            return text

        # Fallback: get html and use trafilatura
        html = page.html
        if _TRAFILATURA_AVAILABLE and html:
            t = trafilatura.extract(html, include_tables=True)
            if t:
                return t

        return None
    except Exception as e:
        print(f"[DrissionSession] Failed: {e}")
    return None


def _fetch_with_crawl4ai(url: str) -> Optional[str]:
    """
    Use Crawl4AI to fetch page content (Markdown).
    Mode: Headless, No Images, Pure Algorithm.
    """
    if not _CRAWL4AI_AVAILABLE:
        return None
    try:

        async def _run_crawl():
            # Configure for speed and low resource usage
            browser_conf = BrowserConfig(
                headless=True,
                verbose=False,
                java_script_enabled=True,
                text_mode=False,  # We need JS for some sites
                light_mode=True,  # Disable some heavy features
            )
            run_conf = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                word_count_threshold=10,
                exclude_external_links=True,
                exclude_social_media_links=True,
                # remove_overlay_elements=True,
            )

            async with AsyncWebCrawler(config=browser_conf) as crawler:
                result = await crawler.arun(url=url, config=run_conf)
                return result.markdown

        # Create a new event loop for this thread if needed
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(_run_crawl())
    except Exception as e:
        print(f"[Crawl4AI] Failed: {e}")
        return None


def _fetch_with_drission(url: str) -> Optional[str]:
    """
    Use DrissionPage for anti-detection fetching.
    Strictly Headless & No Images.
    """
    if not _DRISSION_AVAILABLE:
        return None
    page = None
    try:
        # Use a headless config with optimizations
        co = ChromiumOptions()
        co.headless(True)
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-gpu")
        co.set_argument("--blink-settings=imagesEnabled=false")  # Disable images
        co.set_argument("--mute-audio")
        co.incognito(True)  # Incognito mode

        # Initialize ChromiumPage
        page = ChromiumPage(addr_or_opts=co)

        # Set timeout
        page.get(url, timeout=15)

        # Wait slightly for JS to settle (optional, but good for heavy sites)
        # page.wait.load_start()

        # Get text content
        # Try to get body text, if empty fallback to html and parse?
        # DrissionPage .text property on element returns visible text
        body_ele = page.ele("tag:body")
        if body_ele:
            text = body_ele.text
            return text
        return None
    except Exception as e:
        print(f"[DrissionPage] Failed: {e}")
        return None
    finally:
        if page:
            try:
                page.quit()
            except:
                pass


def _fetch_with_jina(url: str, session) -> Optional[str]:
    """
    尝试使用 Jina Reader 获取网页内容的 Markdown
    """
    try:
        # Jina Reader URL 格式: https://r.jina.ai/<目标URL>
        jina_url = f"https://r.jina.ai/{url}"

        # Jina 建议的 Headers
        headers = {"X-Return-Format": "markdown"}

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
        "porn",
        "xxx",
        "sex",
        "gambling",
        "casino",
        "色情",
        "赌博",
        "av",
        "hentai",
        "fuck",
        "bitch",
        "whore",
        "slut",
        "asshole",
        "nigger",
        "faggot",
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
            title = result.get("title", "")
            snippet = result.get("summary") or result.get("snippet") or ""
            combined = f"{title} {snippet}"
            quoted = re.findall(r'"([^"]+)"', combined)
            candidates.extend(quoted)
            book_names = re.findall(r"《([^》]+)》", combined)
            candidates.extend(book_names)
        for result in search_results[:3]:
            title = result.get("title", "")
            capitalized = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", title)
            candidates.extend(capitalized)
        if not candidates:
            return {"candidates": [], "extraction_method": "no_candidates"}
        counter = Counter(candidates)
        ranked_candidates = []
        for text, count in counter.most_common(5):
            if len(text) < 3 or len(text) > 100:
                continue
            confidence = min(0.9, (count / len(search_results)) * 0.5 + 0.3)
            if search_results and text in search_results[0].get("title", ""):
                confidence = min(0.95, confidence + 0.2)
            ranked_candidates.append(
                {"text": text, "confidence": round(confidence, 2), "sources": count}
            )
        return {"candidates": ranked_candidates, "extraction_method": "search_metadata"}
    except Exception as e:
        print(f"[Monitoring] extract_answer_from_search_results error: {e}")
        return {"candidates": [], "extraction_method": "error"}


def _optimize_search_query(query: str) -> str:
    """
    混合优化策略：
    1. 短查询（<40字符）：直接返回，靠搜索引擎自己处理（0延迟）。
    2. 简单清洗：用正则去掉常见的废话（"请问"、"搜索"等）。
    3. 长难句：才调用 LLM 进行重写。
    """
    try:
        # 0. 保护性截断（防止超长 token 攻击）
        if len(query) > 300:
            query = query[:300]

        # 1. 快速通道：如果查询很短，或者是高级指令（site:），直接放行
        # 大多数用户搜索都在 10-30 个字之间，这里能节省 90% 的 LLM 调用
        if len(query) < 40 and "site:" not in query and "filetype:" not in query:
            return query.strip()

        # 2. 中等长度：本地正则清洗（0延迟）
        # 去除常见的中文口语废话
        clean_pattern = (
            r"(请帮我|查找|搜索|关于|我想知道|有没有|what is|how to|find me)"
        )
        cleaned_query = re.sub(clean_pattern, "", query, flags=re.IGNORECASE).strip()

        # 如果清洗后长度适中，直接用清洗后的（避免 LLM）
        if len(cleaned_query) < 60:
            return cleaned_query

        # 3. 只有真正的“长难句”才调用 LLM
        print(
            f"[Monitoring] Query too complex, invoking LLM optimization: {query[:20]}..."
        )

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
            max_tokens=64,
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
        if len(simplified) > 100:  # Only truncate if extremely long
            simplified = simplified[:100]

        simplified = re.sub(r"\s+", " ", simplified).strip()
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
            messages=[
                {
                    "role": "user",
                    "content": f"<instruction><task>为搜索引擎优化翻译搜索查询</task><target_lang>{target_lang}</target_lang><constraint>保持专有名词和关键术语准确</constraint><query>{query}</query></instruction>",
                }
            ],
            max_tokens=128,
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
            {
                "role": "system",
                "content": """<instruction>
<task>从查询中提取搜索槽位。</task>
<output_format>json_object</output_format>
<keys>
  <key name="type">"Person" | "Organization" | "Event" | "Object" | "Other"</key>
  <key name="hard_constraints">严格条件列表 (年份, 地点, 角色, 具体事件)</key>
  <key name="soft_constraints">描述性条件列表 (丑闻, 教育, 家庭)</key>
  <key name="anchors">用于搜索的唯一关键词列表 (名称, 具体术语)</key>
  <key name="target_country">国家名称 (英文) 如果适用, 否则 null</key>
</keys>
</instruction>""",
            },
            {"role": "user", "content": f"<input><query>{query}</query></input>"},
        ]
        resp = client.chat.completions.create(
            model="qwen3-max",
            messages=prompt,
            max_tokens=256,
            response_format={"type": "json_object"},
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
                return {
                    "source": api,
                    "content": extract,
                    "title": data.get("title") or title,
                    "sitename": host,
                    "type": "wiki-summary",
                }
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
                    return {
                        "source": api_php,
                        "content": extract,
                        "title": pdata.get("title") or title,
                        "sitename": host,
                        "type": "wiki-extract",
                    }
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
        text_html = (parse.get("text") or {}).get("*") or ""
        if not text_html:
            return None
        ex = SimpleTextExtractor()
        ex.feed(text_html)
        t = ex.get_text().strip()
        if not t:
            return None
        if len(t) > 10000:
            t = t[:10000] + "...(truncated)"
        return {
            "source": api,
            "content": t,
            "title": parse.get("title") or title,
            "sitename": host,
        }
    except Exception:
        return None


# --- Parallel Search Helpers ---


def _safe_search_baidu(query: str, k: int) -> List[Dict]:
    """封装百度搜索，带异常处理"""
    if not _BAIDU_AVAILABLE:
        return []
    try:
        results = []
        # baidusearch returns a generator
        # Note: baidusearch library uses requests internally, difficult to patch global session easily without monkey patch
        # But we can limit results for speed
        raw_results = baidu_search(query, num_results=k)
        for i, r in enumerate(raw_results):
            if i >= k:
                break
            results.append(
                {
                    "title": r.get("title", ""),
                    "summary": r.get("abstract", ""),
                    "url": r.get("url", ""),
                    "source": "baidu",
                    "score": 1.0 - (i * 0.1),  # Simple decay
                }
            )
        return _filter_search_results(results)
    except Exception as e:
        print(f"[Search] Baidu failed: {e}")
        return []


def _safe_search_serper(
    query: str, k: int, api_keys: Union[str, List[str]]
) -> List[Dict]:
    """封装 Serper 搜索，支持多 Key 轮询"""

    # Ensure api_keys is a list
    if isinstance(api_keys, str):
        keys = [k.strip() for k in api_keys.split(",") if k.strip()]
    else:
        keys = api_keys

    if not keys:
        return []

    url = "https://google.serper.dev/search"
    is_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in query)
    payload = json.dumps(
        {
            "q": query,
            "num": k,
            "gl": "cn" if is_chinese else "us",
            "hl": "zh-cn" if is_chinese else "en",
        }
    )

    # Try keys in rotation
    for i, key in enumerate(keys):
        try:
            headers = {"X-API-KEY": key, "Content-Type": "application/json"}
            # Use Global Session for reuse
            resp = _GLOBAL_SESSION.post(url, headers=headers, data=payload, timeout=4)

            if resp.status_code == 200:
                data = resp.json()
                results = []

                # Handle Knowledge Graph
                if "knowledgeGraph" in data:
                    kg = data["knowledgeGraph"]
                    results.append(
                        {
                            "title": kg.get("title", "Knowledge Graph"),
                            "summary": f"{kg.get('type', '')}: {kg.get('description', '')} {kg.get('attributes', '')}",
                            "url": kg.get("website", ""),
                            "source": "serper_kg",
                            "score": 1.1,
                        }
                    )

                for item in data.get("organic", []):
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "summary": item.get("snippet", ""),
                            "url": item.get("link", ""),
                            "source": "serper",
                            "score": 1.0 - (item.get("position", 0) * 0.1),
                        }
                    )
                return _filter_search_results(results)

            elif resp.status_code in [401, 403, 429]:
                print(
                    f"[Search] Serper Key #{i} failed ({resp.status_code}). Rotating to next key..."
                )
                continue  # Try next key
            else:
                print(f"[Search] Serper error: {resp.status_code} - {resp.text}")

        except Exception as e:
            print(f"[Search] Serper attempt failed: {e}")
            continue

    return []


def _safe_search_searxng(query: str, k: int, base_url: str) -> List[Dict]:
    """封装 SearXNG 搜索"""
    try:
        searxng_url = f"{base_url.rstrip('/')}/search"
        is_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in query)
        params = {
            "q": query,
            "format": "json",
            "language": "zh-CN" if is_chinese else "en-US",
        }

        # 添加适当的HTTP头来绕过SearXNG的bot detection
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        }

        # Use Global Session with custom headers
        resp = _GLOBAL_SESSION.get(
            searxng_url, params=params, headers=headers, timeout=15
        )  # 增加超时时间
        if resp.status_code == 200:
            data = resp.json()
            raw_results = []

            # Infoboxes
            for infobox in data.get("infoboxes", []):
                raw_results.append(
                    {
                        "title": infobox.get("infobox", "Infobox"),
                        "summary": infobox.get("content", ""),
                        "url": infobox.get("urls", [{}])[0].get("url", "")
                        if infobox.get("urls")
                        else "",
                        "source": "searxng_infobox",
                        "engine": "searxng_infobox",
                        "score": 1.1,
                    }
                )

            for i, item in enumerate(data.get("results", [])):
                if not item.get("url") or not item.get("title"):
                    continue
                raw_results.append(
                    {
                        "title": item.get("title"),
                        "summary": item.get("content") or item.get("snippet") or "",
                        "url": item.get("url"),
                        "source": item.get("engine", "searxng"),
                        "engine": item.get("engine", "searxng"),
                        "score": 0.95 - (i * 0.1),  # Slightly lower base than Google
                    }
                )

            # 使用评分系统对结果进行筛选和排序
            filtered_results = _filter_searxng_results(raw_results, query, k)
            return _filter_search_results(filtered_results)
        return []
    except Exception as e:
        print(f"[Search] SearXNG failed: {e}")
        return []


def _calculate_result_score(result: Dict[str, Any], query: str) -> float:
    """
    为搜索结果计算评分，分数越高越相关
    """
    score = 0.0

    # 1. 标题相关性评分
    title = result.get("title", "").lower()
    query_lower = query.lower()

    if query_lower in title:
        score += 3.0  # 完全匹配标题
    elif any(word in title for word in query_lower.split()):
        score += 1.5  # 部分匹配标题

    # 2. 内容相关性评分
    content = result.get("summary", result.get("content", "")).lower()
    if query_lower in content:
        score += 2.0  # 完全匹配内容
    elif any(word in content for word in query_lower.split()):
        score += 1.0  # 部分匹配内容

    # 3. 引擎可信度评分
    engine = result.get("engine", result.get("source", "unknown")).lower()
    trusted_engines = {
        "wikipedia": 2.0,
        "wikidata": 2.0,
        "wikinews": 2.0,
        "google": 1.8,
        "bing": 1.7,
        "duckduckgo": 1.6,
        "brave": 1.5,
        "startpage": 1.5,
        "arxiv": 1.8,
        "pubmed": 1.8,  # 学术引擎
        "github": 1.5,
        "stackoverflow": 1.6,
        "askubuntu": 1.6,
        "superuser": 1.6,  # 技术引擎
    }
    score += trusted_engines.get(engine, 0.5)

    # 4. URL类型评分
    url = result.get("url", "")
    if url:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # 高可信度域名
        if any(
            trusted_domain in domain
            for trusted_domain in [
                "wikipedia.org",
                "wikidata.org",
                "arxiv.org",
                "edu",
                "gov",
                "org",
                "stackexchange.com",
                "github.com",
            ]
        ):
            score += 1.0

        # 低质量域名惩罚
        if any(
            low_quality in domain
            for low_quality in ["ads.", "advertisement", "click", "redirect"]
        ):
            score -= 2.0

    # 5. 内度评分
    content_length = len(content)
    if 50 <= content_length <= 1000:  # 适中长度的内容更有价值
        score += 0.5
    elif content_length < 20:  # 内度过短可能信息不足
        score -= 0.5
    elif content_length > 2000:  # 内度过长可能包含无关信息
        score -= 0.3

    # 6. 原始分数加权
    original_score = result.get("score", 0.5)
    score += original_score * 0.5  # 原始分数权重较低，主要依赖我们的评分

    return score


def _filter_searxng_results(
    results: List[Dict[str, Any]], query: str, top_k: int
) -> List[Dict[str, Any]]:
    """
    使用评分系统筛选和排序SearXNG结果
    """
    if not results:
        return []

    # 为每个结果打分
    scored_results = []
    for result in results:
        score = _calculate_result_score(result, query)
        scored_results.append((result, score))

    # 按分数降序排序
    scored_results.sort(key=lambda x: x[1], reverse=True)

    # 返回前top_k个结果
    filtered_results = [item[0] for item in scored_results[:top_k]]

    return filtered_results


def _safe_search_ddgs(query: str, k: int) -> List[Dict]:
    """封装 DuckDuckGo"""
    if not _DDGS_AVAILABLE:
        return []
    try:
        results = []
        is_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in query)
        region = "cn-zh" if is_chinese else "wt-wt"

        with DDGS() as ddgs:
            # backend='html' is often more stable for scraping
            ddgs_gen = ddgs.text(query, max_results=k, region=region, backend="html")
            for i, r in enumerate(ddgs_gen):
                results.append(
                    {
                        "title": r.get("title"),
                        "summary": r.get("body"),
                        "url": r.get("href"),
                        "source": "ddgs",
                        "score": 0.9 - (i * 0.1),
                    }
                )
        return _filter_search_results(results)
    except Exception as e:
        print(f"[Search] DDGS failed: {e}")
        return []


def _deduplicate_and_rank(all_results: List[Dict], top_k: int) -> List[Dict]:
    """
    结果去重与重排序
    """
    unique_map = {}
    for res in all_results:
        url = res.get("url")
        if not url:
            continue
        norm_url = _normalize_url(url)

        if norm_url in unique_map:
            existing = unique_map[norm_url]
            # Merge logic: keep longer summary, combine sources
            existing_summary = str(existing.get("summary", ""))
            new_summary = str(res.get("summary", ""))

            if len(new_summary) > len(existing_summary):
                existing["summary"] = new_summary
                existing["title"] = res.get("title") or existing["title"]

            # Boost score if found by multiple providers
            existing["score"] = max(existing.get("score", 0), res.get("score", 0)) + 0.2
            existing["source"] = f"{existing['source']}+{res['source']}"
        else:
            unique_map[norm_url] = res

    final_list = list(unique_map.values())
    # Sort by score
    final_list.sort(key=lambda x: x.get("score", 0), reverse=True)

    return final_list[:top_k]


# --- Main Functions ---


def web_search(query: str, top_k: int = 5) -> str:
    try:
        print(f"[Monitoring] Parallel web_search query='{query}'")
        if not isinstance(query, str) or not query.strip():
            return json.dumps({"error": "empty_query"}, ensure_ascii=False)

        # Entity Quantity Detection and Limit
        quoted_entities = re.findall(r'"[^"]+"', query)
        if len(quoted_entities) > 6:
            matches = list(re.finditer(r'"[^"]+"', query))
            if len(matches) > 6:
                cutoff = matches[5].end()
                query = query[:cutoff]

        # 1. Optimize Query
        optimized_q = _optimize_search_query(query)
        is_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in optimized_q)

        # 2. Define Tasks with Priority Order (SearXNG first)
        searxng_base_url = os.getenv("SEARXNG_BASE_URL")
        serper_key = os.getenv("SERPER_API_KEY")

        # Check if SearXNG is available first
        if searxng_base_url:
            print(f"[Search] Trying SearXNG first (priority provider)")
            try:
                searxng_results = _safe_search_searxng(
                    optimized_q, top_k, searxng_base_url
                )
                if searxng_results:
                    print(
                        f"[Search] Got {len(searxng_results)} results from SearXNG, using as primary source"
                    )

                    # Enhance SearXNG results with detailed content if enabled
                    should_enhance_content = (
                        os.getenv("ENHANCE_SEARCH_CONTENT", "false").lower() == "true"
                    )
                    if should_enhance_content and searxng_results:
                        print(
                            f"[Monitoring] Enhancing SearXNG search results with detailed content..."
                        )
                        try:
                            from .content_enhancer import (
                                sync_enhance_search_results_with_content,
                            )

                            searxng_results = sync_enhance_search_results_with_content(
                                searxng_results, optimized_q
                            )
                        except ImportError:
                            print(
                                "[Monitoring] Content enhancer not available, skipping enhancement"
                            )
                        except Exception as e:
                            print(f"[Monitoring] Content enhancement failed: {e}")

                    return json.dumps(
                        {
                            "source": "searxng_primary",
                            "results": searxng_results,
                            "providers_used": 1,
                            "primary_provider": "searxng",
                        },
                        ensure_ascii=False,
                    )
            except Exception as e:
                print(f"[Search] SearXNG failed as primary source: {e}")

        # If SearXNG is not available or failed, proceed with other providers
        tasks = []

        # Task: Serper
        if serper_key:
            tasks.append(lambda: _safe_search_serper(optimized_q, top_k, serper_key))

        # Task: Baidu (If Chinese or no SearXNG/Serper)
        # Always try Baidu for Chinese queries to get local context
        if _BAIDU_AVAILABLE and is_chinese:
            tasks.append(lambda: _safe_search_baidu(optimized_q, top_k))
        elif _BAIDU_AVAILABLE and not serper_key and not searxng_base_url:
            tasks.append(lambda: _safe_search_baidu(optimized_q, top_k))

        # Task: DuckDuckGo (Supplemental)
        if _DDGS_AVAILABLE:
            tasks.append(lambda: _safe_search_ddgs(optimized_q, top_k))

        # 3. Parallel Execution
        all_results = []
        # Use Global ThreadPool
        futures = []
        for task in tasks:
            futures.append(_FETCH_EXECUTOR.submit(task))

        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    all_results.extend(res)
            except Exception as e:
                print(f"[Search] Worker exception: {e}")

        # 4. Result Integration
        if not all_results:
            return json.dumps(
                {"error": "search_failed", "message": "All providers failed"},
                ensure_ascii=False,
            )

        final_results = _deduplicate_and_rank(all_results, top_k)

        # 5. Enhance results with detailed content (optional, can be toggled)
        should_enhance_content = (
            os.getenv("ENHANCE_SEARCH_CONTENT", "false").lower() == "true"
        )
        if should_enhance_content and final_results:
            print(f"[Monitoring] Enhancing search results with detailed content...")
            try:
                from .content_enhancer import sync_enhance_search_results_with_content

                final_results = sync_enhance_search_results_with_content(
                    final_results, optimized_q
                )
            except ImportError:
                print(
                    "[Monitoring] Content enhancer not available, skipping enhancement"
                )
            except Exception as e:
                print(f"[Monitoring] Content enhancement failed: {e}")

        return json.dumps(
            {
                "source": "mixed_fallback",
                "results": final_results,
                "providers_used": len(tasks),
                "primary_provider": "searxng_unavailable",
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return json.dumps(
            {"error": "unexpected_error", "message": str(e)}, ensure_ascii=False
        )


# 导入优化的内容增强功能
try:
    from ..content_enhancer import (
        extract_content_from_html,
        summarize_content,
        extract_key_sentences,
        extract_top_content,
        sync_enhance_search_results_with_content,
    )
except ImportError:
    # 如果无法导入外部模块，则使用本地定义的函数
    from bs4 import BeautifulSoup

    def extract_content_from_html(html: str, url: str) -> str:
        """
        从HTML中提取主要内容
        """
        soup = BeautifulSoup(html, "html.parser")

        # 移除不必要的标签
        for tag in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "aside",
                "广告",
                "advertisement",
            ]
        ):
            tag.decompose()

        # 尝试获取特定区域的内容
        content_selectors = [
            "article",
            ".content",
            "#content",
            ".post",
            ".article",
            ".main-content",
            '[role="main"]',
            ".entry-content",
            ".post-content",
        ]

        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                return content_elem.get_text(strip=True, separator="\n")

        # 如果没有找到特定区域，返回body内容
        body = soup.find("body")
        if body:
            return body.get_text(strip=True, separator="\n")

        # 否则返回整个文档的文本
        return soup.get_text(strip=True, separator="\n")

    def summarize_content(content: str, query: str, max_length: int = 1000) -> str:
        """
        使用LLM对网页内容进行总结 - 优先使用非LLM方法以减少TOKEN成本
        """
        if len(content) <= max_length:
            return content

        # 截取内容的开头部分，保留最重要的信息
        truncated_content = content[
            : max_length * 2
        ]  # 先取两倍长度，以便保留更多上下文

        # 首先尝试使用非LLM方法进行总结（成本更低）
        try:
            # 使用关键句子提取方法
            key_sentences_summary = extract_key_sentences(
                truncated_content, max_length=max_length, num_sentences=6
            )

            if len(key_sentences_summary) > 0:
                return key_sentences_summary

            # 如果关键句子提取失败，使用顶部内容提取方法
            top_content_summary = extract_top_content(
                truncated_content, max_length=max_length
            )

            if len(top_content_summary) > 0:
                return top_content_summary

        except Exception as e:
            print(f"[Content Summarizer] Non-LLM summarization failed: {e}")
            # 如果非LLM方法失败，继续尝试LLM方法

        # 如果非LLM方法不可用或失败，则使用LLM进行总结
        try:
            from .utils import get_llm_client

            client = get_llm_client()
            prompt = f"""
            请对以下网页内容进行简洁准确的总结，重点关注与查询"{query}"相关的信息：

            网页内容：
            {truncated_content}

            请提供一段不超过{max_length}字符的总结，突出关键信息和要点。
            """

            response = client.chat.completions.create(
                model="qwen3-max",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的网页内容总结助手，能够提取关键信息并提供简洁准确的总结。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=max_length,
            )

            summary = response.choices[0].message.content.strip()
            return summary
        except Exception as e:
            print(f"[Content Summarizer] LLM summarization failed: {e}")
            # 如果所有方法都失败，返回截断的内容
            return truncated_content[:max_length] + "..."

    def extract_key_sentences(
        content: str, max_length: int = 2000, num_sentences: int = 8
    ) -> str:
        """
        不使用模型的关键句子提取方法
        基于位置优先和关键词密度的方法提取最重要的句子
        """
        import re

        # 按句子分割文本
        sentences = re.split(r"[。！？!?]+", content)

        # 清理句子，去除空白
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= num_sentences:
            result = "".join([s + "。" for s in sentences])
            return result[:max_length]

        # 位置权重：越靠前的句子权重越高
        weighted_sentences = []
        for i, sentence in enumerate(sentences):
            # 位置权重：前面的句子权重更高
            position_weight = max(0.3, 1.0 - i * 0.02)

            # 长度过滤：太短的句子可能信息量不够
            length_score = min(1.0, len(sentence) / 20.0)

            # 关键词权重：包含重要词汇的句子权重更高
            keyword_score = 0
            keywords = [
                "重要",
                "主要",
                "关键",
                "核心",
                "首先",
                "其次",
                "最后",
                "因此",
                "所以",
                "但是",
                "然而",
                "总之",
            ]
            for keyword in keywords:
                if keyword in sentence:
                    keyword_score += 0.2

            # 计算总权重
            total_weight = (position_weight + length_score + keyword_score) / 3
            weighted_sentences.append((sentence, total_weight, i))

        # 按权重排序，选择权重最高的句子
        weighted_sentences.sort(key=lambda x: x[1], reverse=True)
        selected_sentences = weighted_sentences[:num_sentences]

        # 按原文顺序排列选中的句子
        selected_sentences.sort(key=lambda x: x[2])

        # 组合结果
        result = "".join([s[0] + "。" for s in selected_sentences])

        # 限制最大长度
        if len(result) > max_length:
            result = result[:max_length]
            # 确保以句号结尾
            if not result[-1] in ["。", "！", "？", ".", "!", "?"]:
                result += "..."

        return result

    def extract_top_content(content: str, max_length: int = 2000) -> str:
        """
        提取网页内容的顶部重要部分，不过滤任何内容
        """
        # 直接截取内容的前max_length个字符
        if len(content) <= max_length:
            return content

        # 尝试在句子边界处截断，避免截断句子
        truncated = content[:max_length]

        # 寻找最后一个句号，避免截断句子
        last_sentence_end = max(
            truncated.rfind("。"),
            truncated.rfind("！"),
            truncated.rfind("？"),
            truncated.rfind("."),
            truncated.rfind("!"),
            truncated.rfind("?"),
        )

        if last_sentence_end > max_length * 0.8:  # 确保截断位置不太靠前
            truncated = truncated[: last_sentence_end + 1]

        if len(truncated) < len(content):
            truncated += "..."

        return truncated

    def sync_enhance_search_results_with_content(
        results: List[Dict], query: str
    ) -> List[Dict]:
        """
        同步版本的搜索结果增强函数
        """
        import concurrent.futures
        import time

        def fetch_content_sync(result):
            """同步获取单个结果的内容"""
            url = result.get("url")
            if not url:
                return result

            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()

                content = extract_content_from_html(response.text, url)
                summary = summarize_content(content, query)

                enhanced_result = result.copy()
                enhanced_result["detailed_content"] = summary
                enhanced_result["enhanced_summary"] = (
                    result.get("summary", "")
                    + "\n\n详细内容摘要："
                    + summary[:300]
                    + "..."
                )
                return enhanced_result
            except Exception as e:
                print(f"[Sync Content Fetcher] Failed to fetch {url}: {e}")
                return result

        # 使用线程池并行处理
        enhanced_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # 提交所有任务
            future_to_result = {
                executor.submit(fetch_content_sync, result): result
                for result in results
            }

            # 收集结果
            for future in concurrent.futures.as_completed(future_to_result):
                try:
                    enhanced_result = future.result()
                    enhanced_results.append(enhanced_result)
                except Exception as e:
                    print(f"[Sync Enhancer] Error processing result: {e}")
                    # 添加原始结果
                    original_result = future_to_result[future]
                    enhanced_results.append(original_result)

        # 按原始顺序排序
        result_url_map = {res.get("url"): res for res in enhanced_results}
        ordered_results = []
        for original_result in results:
            url = original_result.get("url")
            if url and url in result_url_map:
                ordered_results.append(result_url_map[url])
            else:
                ordered_results.append(original_result)

        return ordered_results


def _fetch_local_trafilatura(url: str, timeout: int = 5) -> Optional[str]:
    """本地快速抓取"""
    if not _TRAFILATURA_AVAILABLE:
        return None
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_tables=True)
            if text and len(text) > 200:  # 只有内容足够才算成功
                return text
    except Exception:
        pass
    return None


def web_fetch(url: str, max_bytes: int = 200_000) -> str:
    try:
        print(f"[Monitoring] web_fetch called with url='{url}'")

        # URL去重检测
        normalized_url = _normalize_url(url)
        if normalized_url in _URL_FETCH_CACHE:
            cached_content, cached_time = _URL_FETCH_CACHE[normalized_url]
            # 缓存有效期：5分钟内直接返回
            if time.time() - cached_time < 300:
                print(
                    f"[WebFetch] URL already fetched recently (cached). Skipping duplicate fetch: {url}"
                )
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
            print(
                f"[WebFetch] Domain {domain} in legacy blacklist. Skip fetch, try snippet fallback."
            )
            raise TimeoutError(f"Domain {domain} known to timeout")

        path_lower = (parsed.path or "").lower()

        # === 4-Level Lightweight Racing Strategy ===
        # 排除 Wikipedia 和 PDF
        if "wikipedia.org" not in parsed.netloc and not url.lower().endswith(".pdf"):
            content_result = None
            source_type = "unknown"

            # Phase 1: Lightweight Race (L1, L2, L3) - No Browser
            # Run Trafilatura, curl_cffi, DrissionSession in parallel
            # Use Global ThreadPool
            futures = {}

            # L1: Trafilatura (Fastest, Static)
            futures[_FETCH_EXECUTOR.submit(_fetch_local_trafilatura, url)] = (
                "trafilatura"
            )

            # L2: curl_cffi (Stealth, No JS)
            futures[_FETCH_EXECUTOR.submit(_fetch_with_curl_cffi, url)] = "curl_cffi"

            # L3: Drission Session (Robust, No JS)
            if _DRISSION_AVAILABLE:
                futures[_FETCH_EXECUTOR.submit(_fetch_with_drission_session, url)] = (
                    "drission_session"
                )

            # Wait for results (fastest wins)
            for future in as_completed(futures, timeout=5):
                try:
                    res = future.result()
                    provider = futures[future]
                    if res and len(res) > 200:
                        print(f"[WebFetch] {provider} won the race for {url}")
                        content_result = res
                        source_type = f"lightweight_{provider}"
                        # Cancel others? Not easy in ThreadPool, just break
                        break
                except Exception:
                    pass

            # Phase 2: Heavyweight Fallback (L4) - Browser
            # Only if all lightweight methods failed
            if not content_result:
                print(
                    f"[WebFetch] Lightweight methods failed. Activating L4: Crawl4AI (Browser)..."
                )
                try:
                    # Try Crawl4AI
                    crawl_text = _fetch_with_crawl4ai(url)
                    if crawl_text and len(crawl_text) > 100:
                        content_result = crawl_text
                        source_type = "crawl4ai_markdown"
                    else:
                        print(f"[WebFetch] Crawl4AI returned empty or short content.")

                        # Last Resort: DrissionPage Headless Browser (if Crawl4AI failed)
                        if _DRISSION_AVAILABLE:
                            print(
                                f"[WebFetch] Activating Last Resort: DrissionPage Browser..."
                            )
                            drission_text = _fetch_with_drission(url)
                            if drission_text:
                                content_result = drission_text
                                source_type = "drission_browser_fallback"
                except Exception as e:
                    print(f"[WebFetch] Heavyweight fetch failed: {e}")

            if content_result:
                # 缓存
                try:
                    result = json.dumps(
                        {
                            "source": url,
                            "content": content_result[:20000],
                            "type": source_type,
                        },
                        ensure_ascii=False,
                    )
                    _URL_FETCH_CACHE[normalized_url] = (result, time.time())
                    if len(_URL_FETCH_CACHE) > _URL_FETCH_LIMIT:
                        oldest_key = min(
                            _URL_FETCH_CACHE.keys(),
                            key=lambda k: _URL_FETCH_CACHE[k][1],
                        )
                        del _URL_FETCH_CACHE[oldest_key]
                except Exception:
                    pass

                return json.dumps(
                    {
                        "source": url,
                        "content": content_result[:20000],
                        "type": source_type,
                    },
                    ensure_ascii=False,
                )
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
                        if i >= 10:
                            break
                        try:
                            extracted = page.extract_text() or ""
                            if extracted:
                                text += extracted + "\n"
                        except Exception:
                            continue

                    if len(text) < 50:
                        return json.dumps(
                            {
                                "error": "pdf_text_empty",
                                "message": "Parsed PDF but found little text (scanned?)",
                            },
                            ensure_ascii=False,
                        )
                    return json.dumps(
                        {"source": url, "content": text[:15000], "type": "pdf"},
                        ensure_ascii=False,
                    )
                except Exception as e:
                    print(f"[Warn] PDF parse error: {e}")
                    return json.dumps(
                        {"error": "pdf_parse_error", "message": str(e)},
                        ensure_ascii=False,
                    )

            except Exception as e:
                print(
                    f"[Warn] PDF processing failed: {e}. Attempting Snippet Fallback."
                )
                try:
                    fallback_res = web_search(url, top_k=1)
                    fallback_data = json.loads(fallback_res)
                    if "results" in fallback_data and fallback_data["results"]:
                        first = fallback_data["results"][0]
                        snippet = first.get("summary") or first.get("snippet") or ""
                        title = first.get("title") or ""
                        if snippet:
                            return json.dumps(
                                {
                                    "source": url,
                                    "content": f"Title: {title}\nSnippet: {snippet}\n\n[System Note]: PDF download failed. This is the search snippet.",
                                    "type": "snippet_fallback",
                                },
                                ensure_ascii=False,
                            )
                except Exception as e_fallback:
                    print(f"[Warn] PDF Fallback failed: {e_fallback}")

                # If fallback failed, just return error
                return json.dumps(
                    {"error": "pdf_failed", "message": str(e)}, ensure_ascii=False
                )

        if "wikipedia.org" in parsed.netloc:
            wiki_res = _fetch_wikipedia_rest(url)
            if wiki_res:
                print(f"[Monitoring] Wiki fetch success via API for {url}")
                return json.dumps(wiki_res, ensure_ascii=False)
            print(
                f"[Monitoring] Wiki API fetch failed for {url}, attempting Snippet Fallback immediately"
            )
            try:
                fallback_res = web_search(url, top_k=1)
                fallback_data = json.loads(fallback_res)
                if "results" in fallback_data and fallback_data["results"]:
                    first = fallback_data["results"][0]
                    snippet = first.get("summary") or first.get("snippet") or ""
                    title = first.get("title") or ""
                    if snippet:
                        return json.dumps(
                            {
                                "source": url,
                                "content": f"Title: {title}\nSnippet: {snippet}\n\n[System Note]: Wiki API failed. This is the search snippet.",
                                "type": "snippet_fallback",
                            },
                            ensure_ascii=False,
                        )
            except Exception as e_wiki:
                print(f"[Monitoring] Wiki Snippet Fallback failed: {e_wiki}")
            print(
                f"[Monitoring] Wiki Snippet Fallback failed or empty, continuing to standard fetch..."
            )

        if _TRAFILATURA_AVAILABLE:
            try:
                # 使用智能请求器获取自适应超时
                timeout = intelligent_fetcher.domain_status.get_recommended_timeout(
                    domain, 0
                )

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(trafilatura.fetch_url, url)
                    try:
                        downloaded = future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError:
                        print(
                            f"[Warn] Trafilatura fetch timed out for {url} after {timeout}s"
                        )
                        downloaded = None

                if downloaded:
                    text = trafilatura.extract(
                        downloaded, include_comments=False, include_tables=True
                    )
                    if text and len(text) > 100:
                        # 成功时标记域名为可达
                        intelligent_fetcher.domain_status.mark_reachable(domain)
                        return json.dumps(
                            {"source": url, "content": text[:15000], "type": "html"},
                            ensure_ascii=False,
                        )
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
                verify_ssl=False,
            )

            if resp is None:
                # 请求失败，抛出异常进入fallback逻辑
                raise Exception(error_msg or "Fetch failed")

            # 强制使用UTF-8编码，避免gbk编码错误
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            for t in soup(
                [
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "noscript",
                    "svg",
                    "button",
                ]
            ):
                t.extract()
            text = soup.get_text(separator="\n")
            import re as _re2

            text = _re2.sub(r"\n\s*\n", "\n", text)
            return json.dumps(
                {"source": url, "content": text[:15000], "type": "html_fallback"},
                ensure_ascii=False,
            )
        except Exception as e:
            # 不再手动管理黑名单，由智能请求器自动处理
            print(
                f"[Monitoring] Fetch failed ({e}), attempting Snippet Fallback for {url}..."
            )

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
                return json.dumps(
                    {
                        "source": url,
                        "content": final_content,
                        "type": "snippet_fallback",
                    },
                    ensure_ascii=False,
                )

            return json.dumps(
                {"error": "fetch_failed", "message": str(e)}, ensure_ascii=False
            )
    except Exception as e:
        result = json.dumps(
            {"error": "unexpected_error", "message": str(e)}, ensure_ascii=False
        )
        return result
    finally:
        # 缓存成功的fetch结果（仅在没有异常时）
        try:
            if "result" not in locals():
                # 获取最后一次成功返回的内容
                import inspect

                frame = inspect.currentframe()
                if frame and frame.f_locals.get("text"):
                    result = json.dumps(
                        {"source": url, "content": frame.f_locals["text"][:15000]},
                        ensure_ascii=False,
                    )
                    normalized_url = _normalize_url(url)
                    _URL_FETCH_CACHE[normalized_url] = (result, time.time())
                    # 限制缓存大小
                    if len(_URL_FETCH_CACHE) > _URL_FETCH_LIMIT:
                        # 删除最旧的条目
                        oldest_key = min(
                            _URL_FETCH_CACHE.keys(),
                            key=lambda k: _URL_FETCH_CACHE[k][1],
                        )
                        del _URL_FETCH_CACHE[oldest_key]
        except Exception:
            pass


def browse_page(url: str, instructions: str, max_bytes: int = 150_000) -> str:
    try:
        print(
            f"[Monitoring] browse_page url='{url}' instructions='{str(instructions)[:80]}'"
        )
        fetched = web_fetch(url, max_bytes=max_bytes)
        data = json.loads(fetched)
        if "error" in data:
            return fetched
        content = str(data.get("content") or "")
        title = str(data.get("title") or "")
        prompt = [
            {
                "role": "system",
                "content": "<instruction><role>研究助理</role><task>生成简洁的结构化摘要。</task></instruction>",
            },
            {
                "role": "user",
                "content": f"<input><task>{instructions}</task><title>{title}</title><content>{content[:8000]}</content></input>",
            },
        ]
        client = get_llm_client(timeout=30.0)
        resp = client.chat.completions.create(
            model="qwen3-max",
            stream=False,
            temperature=0.3,
            max_tokens=800,
            messages=prompt,
        )
        out = ""
        try:
            out = resp.choices[0].message.content or ""
        except Exception:
            out = ""
        if len(out) > 2000:
            out = out[:2000]
        return json.dumps({"source": url, "summary": out}, ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"error": "browse_failed", "message": str(e)}, ensure_ascii=False
        )


def x_keyword_search(query: str, top_k: int = 5) -> str:
    try:
        base_q = f"(site:x.com OR site:twitter.com) {query}"
        return web_search(base_q, top_k=top_k)
    except Exception as e:
        return json.dumps(
            {"error": "x_search_failed", "message": str(e)}, ensure_ascii=False
        )


def search_pdf_attachment(url: str, query: str, max_pages: int = 6) -> str:
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": _pick_ua(0)})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            data = resp.read(2_000_000)
        if "application/pdf" not in ctype and not url.lower().endswith(".pdf"):
            return json.dumps(
                {"error": "not_pdf", "suggestions": ["ensure URL points to PDF"]},
                ensure_ascii=False,
            )
        text = ""
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = reader.pages[:max_pages]
            for p in pages:
                t = p.extract_text() or ""
                if t:
                    text += "\n" + t
        except Exception as e:
            return json.dumps(
                {
                    "error": "pdf_extract_failed",
                    "message": str(e),
                    "suggestions": ["install pypdf", "try browse_pdf_attachment"],
                },
                ensure_ascii=False,
            )
        toks = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", text)
        hits = []
        q = str(query or "").lower()
        if q:
            for i in range(0, len(toks), 100):
                seg = " ".join(toks[i : i + 100])
                if q in seg.lower():
                    hits.append({"segment": seg[:300]})
        return json.dumps(
            {"source": url, "matches": hits[:5], "bytes": len(data)}, ensure_ascii=False
        )
    except Exception as e:
        return json.dumps(
            {"error": "pdf_search_failed", "message": str(e)}, ensure_ascii=False
        )


def browse_pdf_attachment(url: str, instructions: str, max_pages: int = 6) -> str:
    try:
        print(
            f"[Monitoring] browse_pdf_attachment url='{url}' instructions='{str(instructions)[:80]}'"
        )
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": _pick_ua(1)})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            ctype = resp.headers.get("Content-Type", "").lower()
            data = resp.read(2_000_000)
        if "application/pdf" not in ctype and not url.lower().endswith(".pdf"):
            return json.dumps(
                {"error": "not_pdf", "suggestions": ["ensure URL points to PDF"]},
                ensure_ascii=False,
            )
        text = ""
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = reader.pages[:max_pages]
            for p in pages:
                t = p.extract_text() or ""
                if t:
                    text += "\n" + t
        except Exception as e:
            return json.dumps(
                {
                    "error": "pdf_extract_failed",
                    "message": str(e),
                    "suggestions": ["install pypdf"],
                },
                ensure_ascii=False,
            )
        prompt = [
            {
                "role": "system",
                "content": "<instruction><role>Research Assistant</role><task>Summarize PDF content into concise structured facts.</task></instruction>",
            },
            {
                "role": "user",
                "content": f"<input><task>{instructions}</task><content>{text[:8000]}</content></input>",
            },
        ]
        client = get_llm_client(timeout=30.0)
        resp = client.chat.completions.create(
            model="qwen3-max",
            stream=False,
            temperature=0.3,
            max_tokens=800,
            messages=prompt,
        )
        out = ""
        try:
            out = resp.choices[0].message.content or ""
        except Exception:
            out = ""
        if len(out) > 2000:
            out = out[:2000]
        return json.dumps({"source": url, "summary": out}, ensure_ascii=False)
    except Exception as e:
        return json.dumps(
            {"error": "browse_pdf_failed", "message": str(e)}, ensure_ascii=False
        )


def get_weather(location: str) -> str:
    return f"The weather of {location} is sunny."
