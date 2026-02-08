import os
import json
import re
import time
import logging
import urllib.parse
import urllib.request
import requests
import concurrent.futures
import ssl
import io
import random
from html.parser import HTMLParser
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from pypdf import PdfReader
from openai import OpenAI
from src.tools.tools import AsyncTool, ToolResult
import asyncio
from src.registry import TOOL

# Optional dependencies
try:
    from duckduckgo_search import DDGS
    _DDGS_AVAILABLE = True
except ImportError:
    _DDGS_AVAILABLE = False

try:
    import trafilatura
    _TRAFILATURA_AVAILABLE = True
except ImportError:
    _TRAFILATURA_AVAILABLE = False

logger = logging.getLogger(__name__)

# --- Configuration & Helpers ---

def get_llm_client(timeout=30.0):
    """Factory for OpenAI client, preferring IFLOW then DASHSCOPE."""
    api_key = os.getenv("IFLOW_API_KEY")
    base_url = "https://apis.iflow.cn/v1"
    
    if not api_key:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        
    return OpenAI(
        base_url=base_url, 
        api_key=api_key, 
        timeout=timeout
    )

def get_session() -> requests.Session:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]
    
    session.headers.update({
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    })
    return session

def _extract_core_entities(query: str) -> list:
    """Simplified entity extraction for reranking."""
    s = str(query or "").strip()
    if not s: return []
    
    # Remove common noise
    s = re.sub(r'site:\S+', '', s)
    s = re.sub(r'filetype:\S+', '', s)
    
    ents = []
    # Extract years
    ents.extend(re.findall(r'\b(19\d{2}|20\d{2})\b', s))
    # Extract quoted terms
    ents.extend(re.findall(r'"([^"]+)"', s))
    ents.extend(re.findall(r"'([^']+)'", s))
    # Extract Capitalized Words (English)
    ents.extend(re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2})\b', s))
    # Extract Chinese words (2+ chars)
    ents.extend(re.findall(r'[^\x00-\x7f\s]{2,}', s))
    
    return list(set(ents))

# --- Intelligent Fetcher Logic ---

class DomainStatus:
    def __init__(self):
        self.status_cache = {}
        self.blocked_urls = {}
        self.cooldown_period = 300

    def is_blocked(self, domain: str) -> bool:
        if domain not in self.status_cache: return False
        status = self.status_cache[domain]
        if status['state'] == 'unreachable':
            if time.time() - status['last_failure'] < self.cooldown_period:
                return True
        return False

    def is_url_blocked(self, url: str) -> bool:
        if url in self.blocked_urls:
            if time.time() - self.blocked_urls[url] < self.cooldown_period:
                return True
            else:
                del self.blocked_urls[url]
        return False

    def mark_url_failed(self, url: str, reason: str):
        self.blocked_urls[url] = time.time()

    def mark_unreachable(self, domain: str, reason: str, error_type: str):
        self.status_cache[domain] = {
            'state': 'unreachable', 'last_failure': time.time(),
            'reason': reason, 'error_type': error_type
        }

    def mark_reachable(self, domain: str):
        self.status_cache[domain] = {'state': 'reachable', 'last_success': time.time()}

    def get_recommended_timeout(self, domain: str, attempt: int) -> int:
        fast_domains = {'en.wikipedia.org', 'zh.wikipedia.org', 'baike.baidu.com'}
        if domain in fast_domains: return 5
        return min(5 + attempt * 3, 10)

class IntelligentFetcher:
    def __init__(self):
        self.domain_status = DomainStatus()
        self._init_problematic_domains()

    def _init_problematic_domains(self):
        for d in ['instagram.com', 'facebook.com', 'twitter.com', 'x.com']:
            self.domain_status.mark_unreachable(d, "Preconfigured block", "PRECONFIGURED")

    def should_attempt_fetch(self, url: str) -> tuple[bool, Optional[str]]:
        if self.domain_status.is_url_blocked(url): return False, "URL blocked"
        domain = urllib.parse.urlparse(url).netloc
        if self.domain_status.is_blocked(domain): return False, "Domain blocked"
        return True, None

    def fetch_with_retry(self, url: str, session, max_retries=1, verify_ssl=False):
        domain = urllib.parse.urlparse(url).netloc
        for attempt in range(max_retries + 1):
            timeout = self.domain_status.get_recommended_timeout(domain, attempt)
            try:
                resp = session.get(url, timeout=timeout, verify=verify_ssl)
                resp.raise_for_status()
                self.domain_status.mark_reachable(domain)
                return resp, None
            except Exception as e:
                # Simplified error handling
                if attempt < max_retries:
                    time.sleep(min(2**attempt, 5))
                    continue
                self.domain_status.mark_url_failed(url, str(e))
                return None, str(e)
        return None, "Max retries reached"

_intelligent_fetcher = IntelligentFetcher()
_URL_FETCH_CACHE = {}

# --- Search & Fetch Logic ---

def _filter_search_results(results: list) -> list:
    if not results: return []
    filtered = []
    sensitive = {"porn", "xxx", "sex", "gambling", "casino", "色情", "赌博"}
    for r in results:
        content = (str(r.get("title")) + str(r.get("summary"))).lower()
        if any(kw in content for kw in sensitive): continue
        filtered.append(r)
    return filtered

def _rerank_search_results(results, query: str, top_k: int):
    ents = _extract_core_entities(query)
    if not results or not ents: return results[:top_k]
    
    scored = []
    ents_lower = [str(e).lower() for e in ents]
    for idx, r in enumerate(results):
        score = 0.0
        content = (str(r.get("title")) + str(r.get("summary"))).lower()
        for e in ents_lower:
            if e in content: score += 1.0
        scored.append((score, idx, r))
    
    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    return [x[2] for x in scored][:top_k]

def web_search(query: str, top_k: int = 5) -> str:
    """Multi-source web search."""
    try:
        if not query.strip(): return json.dumps({"error": "empty_query"})
        
        # Sources configuration
        serper_key = os.getenv("SERPER_API_KEY")
        bocha_key = os.getenv("BOCHA_API_KEY")
        
        # 1. Try Serper
        if serper_key:
            try:
                url = "https://google.serper.dev/search"
                payload = json.dumps({"q": query, "num": top_k, "gl": "cn", "hl": "zh-cn"})
                headers = {"X-API-KEY": serper_key, "Content-Type": "application/json"}
                resp = requests.post(url, headers=headers, data=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    for item in data.get("organic", []):
                        results.append({
                            "title": item.get("title"),
                            "summary": item.get("snippet"),
                            "url": item.get("link")
                        })
                    if results:
                        results = _filter_search_results(results)
                        results = _rerank_search_results(results, query, top_k)
                        return json.dumps({"source": "serper", "results": results}, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Serper search failed: {e}")

        # 2. Try Bocha
        if bocha_key:
            try:
                url = "https://api.bocha.cn/v1/web-search"
                headers = {"Authorization": f"Bearer {bocha_key}", "Content-Type": "application/json"}
                payload = {"query": query, "count": top_k, "summary": True}
                resp = requests.post(url, headers=headers, json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    # Bocha data structure handling...
                    items = data.get("data", []) or data.get("webPages", {}).get("value", [])
                    for item in items:
                        if isinstance(item, dict):
                            results.append({
                                "title": item.get("name") or item.get("title"),
                                "summary": item.get("snippet") or item.get("summary"),
                                "url": item.get("url")
                            })
                    if results:
                        results = _filter_search_results(results)
                        results = _rerank_search_results(results, query, top_k)
                        return json.dumps({"source": "bocha", "results": results}, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"Bocha search failed: {e}")

        # 3. Try DDGS (Fallback)
        if _DDGS_AVAILABLE:
            try:
                with DDGS() as ddgs:
                    results = []
                    for r in ddgs.text(query, max_results=top_k, region="cn-zh"):
                        results.append({
                            "title": r.get("title"),
                            "summary": r.get("body"),
                            "url": r.get("href")
                        })
                    if results:
                        results = _filter_search_results(results)
                        results = _rerank_search_results(results, query, top_k)
                        return json.dumps({"source": "ddgs", "results": results}, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"DDGS search failed: {e}")

        return json.dumps({"error": "search_failed", "message": "All providers failed"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "unexpected_error", "message": str(e)}, ensure_ascii=False)

def web_fetch(url: str, max_bytes: int = 200_000) -> str:
    """Smart web page fetcher with PDF support."""
    try:
        # Cache check
        if url in _URL_FETCH_CACHE:
            content, ts = _URL_FETCH_CACHE[url]
            if time.time() - ts < 300: return content

        should, reason = _intelligent_fetcher.should_attempt_fetch(url)
        if not should:
            raise Exception(f"Skipping fetch: {reason}")

        # PDF Handling
        if url.lower().endswith(".pdf"):
            try:
                session = get_session()
                resp = session.get(url, timeout=15, stream=True, verify=False)
                resp.raise_for_status()
                
                # Limit download size
                buf = io.BytesIO()
                for chunk in resp.iter_content(8192):
                    buf.write(chunk)
                    if buf.tell() > 5 * 1024 * 1024: break
                
                reader = PdfReader(buf, strict=False)
                text = ""
                for i, page in enumerate(reader.pages):
                    if i >= 10: break
                    text += (page.extract_text() or "") + "\n"
                
                res = json.dumps({"source": url, "content": text[:15000], "type": "pdf"}, ensure_ascii=False)
                _URL_FETCH_CACHE[url] = (res, time.time())
                return res
            except Exception as e:
                return json.dumps({"error": "pdf_failed", "message": str(e)}, ensure_ascii=False)

        # Jina Reader (Prioritized)
        if "wikipedia.org" not in url:
            try:
                session = get_session()
                jina_url = f"https://r.jina.ai/{url}"
                resp = session.get(jina_url, headers={"X-Return-Format": "markdown"}, timeout=15)
                if resp.status_code == 200 and "jina.ai" not in resp.text[:100]:
                    res = json.dumps({"source": url, "content": resp.text[:15000], "type": "jina_markdown"}, ensure_ascii=False)
                    _URL_FETCH_CACHE[url] = (res, time.time())
                    return res
            except:
                pass

        # Trafilatura
        if _TRAFILATURA_AVAILABLE:
            try:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                    if text:
                        res = json.dumps({"source": url, "content": text[:15000], "type": "html_trafilatura"}, ensure_ascii=False)
                        _URL_FETCH_CACHE[url] = (res, time.time())
                        return res
            except:
                pass

        # Fallback Requests + BS4
        session = get_session()
        resp, err = _intelligent_fetcher.fetch_with_retry(url, session)
        if resp:
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")
            for t in soup(["script", "style", "nav", "footer"]): t.extract()
            text = soup.get_text(separator="\n")
            res = json.dumps({"source": url, "content": text[:15000], "type": "html_bs4"}, ensure_ascii=False)
            _URL_FETCH_CACHE[url] = (res, time.time())
            return res
            
        return json.dumps({"error": "fetch_failed", "message": err or "Unknown error"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": "unexpected_error", "message": str(e)}, ensure_ascii=False)

# --- Tool Classes ---

@TOOL.register_module(name="deep_search_tool")
class DeepSearchTool(AsyncTool):
    name: str = "deep_search_tool"
    description: str = "Search the web using multiple engines (Serper, Bocha, DDGS). Returns structured JSON results."
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "description": "Number of results", "default": 5}
        },
        "required": ["query"]
    }
    output_type = "string"

    async def forward(self, query: str, top_k: int = 5) -> ToolResult:
        try:
            loop = asyncio.get_event_loop()
            result_json = await loop.run_in_executor(None, web_search, query, top_k)
            return ToolResult(output=result_json)
        except Exception as e:
            return ToolResult(error=str(e))

@TOOL.register_module(name="deep_fetch_tool")
class DeepFetchTool(AsyncTool):
    name: str = "deep_fetch_tool"
    description: str = "Fetch web page content, supporting PDF and intelligent parsing. Use this to read search results."
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Target URL"}
        },
        "required": ["url"]
    }
    output_type = "string"

    async def forward(self, url: str) -> ToolResult:
        try:
            loop = asyncio.get_event_loop()
            result_json = await loop.run_in_executor(None, web_fetch, url)
            return ToolResult(output=result_json)
        except Exception as e:
            return ToolResult(error=str(e))
