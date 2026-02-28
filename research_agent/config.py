import os
from pathlib import Path
from dotenv import load_dotenv

def load_environment():
    """Load environment variables from .env file."""
    try:
        # Load .env file
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'), override=True)
        
        # Fallback manual loading if needed (as seen in original code)
        here = Path(__file__).resolve().parent.parent
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

# Initialize on module import
load_environment()


# =============================================================================
# 超时配置（统一管理）
# =============================================================================

class TimeoutConfig:
    """超时配置集中管理类"""
    
    # --- 搜索API超时 ---
    # 主要搜索引擎（SearXNG、博查等聚合搜索）
    SEARCH_PRIMARY = 3  # 主搜索源，3s（SearXNG优先级降低，快速失败）
    # 备用搜索引擎（百度、360、搜狗、头条、Serper等）
    SEARCH_BACKUP = 5    # 备用搜索源，5s（Serper等外部API偶发超时）
    # DuckDuckGo
    SEARCH_DDGS = 3
    
    # --- 网页抓取超时 ---
    # 轻量级方法（Trafilatura、curl_cffi、DrissionSession）
    FETCH_LIGHTWEIGHT = 3
    # 轻量级竞速整体超时（多个方法并行，最快者胜出）
    FETCH_RACE = 5       # 从3s增加到5s，给网络波动留余地
    # Jina Reader（Markdown格式，通常很快）
    FETCH_JINA = 3      # 从8s降低到5s
    # DrissionPage浏览器（重量级）
    FETCH_BROWSER = 3
    # HTTP通用请求
    FETCH_HTTP = 3
    
    # --- 特殊内容超时 ---
    # PDF下载
    PDF_DOWNLOAD = 3    # 从20s降低到15s
    # PDF解析
    PDF_PARSE = 5
    # Wikipedia API
    WIKI_API = 3
    
    # --- 智能请求器超时 ---
    # 快速域名（Wikipedia等）
    SMART_FAST_DOMAIN = 3
    # 首次尝试
    SMART_FIRST_ATTEMPT = 3
    # 最大超时（重试后）
    SMART_MAX_TIMEOUT = 5
    
    # --- LLM调用超时 ---
    LLM_CALL = 10
    
    # --- 重定向解析超时 ---
    REDIRECT_RESOLVE = 5
    
    # --- Agent全局超时 ---
    # Agent执行的最大时间（秒）
    GLOBAL_TIMEOUT = 600  # 10分钟全局超时
    # 提前结束缓冲时间（秒），用于预留LLM调用时间
    GLOBAL_TIMEOUT_BUFFER = 20


# 便捷访问（可选）
SEARCH_PRIMARY = TimeoutConfig.SEARCH_PRIMARY
SEARCH_BACKUP = TimeoutConfig.SEARCH_BACKUP
FETCH_LIGHTWEIGHT = TimeoutConfig.FETCH_LIGHTWEIGHT
FETCH_RACE = TimeoutConfig.FETCH_RACE
FETCH_BROWSER = TimeoutConfig.FETCH_BROWSER
