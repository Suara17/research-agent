"""
Debug script to test search providers individually
"""
import os
import sys
import json

# Set up path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Test each provider
def test_serper():
    """Test Serper API"""
    from research_agent.search import _safe_search_serper
    
    serper_key = os.getenv("SERPER_API_KEY")
    print(f"\n=== Testing Serper ===")
    print(f"API Key present: {bool(serper_key)}")
    if serper_key:
        print(f"First few chars: {serper_key[:10]}...")
    
    try:
        result = _safe_search_serper("Wie Baut Amerika book", 3, serper_key)
        print(f"Results count: {len(result)}")
        if result:
            print(f"First result: {result[0].get('title', 'N/A')}")
        return result
    except Exception as e:
        print(f"Serper Error: {e}")
        return []


def test_searxng():
    """Test SearXNG"""
    from research_agent.search import _safe_search_searxng
    
    searxng_url = os.getenv("SEARXNG_BASE_URL")
    print(f"\n=== Testing SearXNG ===")
    print(f"URL: {searxng_url}")
    
    try:
        result = _safe_search_searxng("Wie Baut Amerika book", 3, searxng_url)
        print(f"Results count: {len(result)}")
        if result:
            print(f"First result: {result[0].get('title', 'N/A')}")
        return result
    except Exception as e:
        print(f"SearXNG Error: {e}")
        return []


def test_baidu():
    """Test Baidu"""
    from research_agent.search import _safe_search_baidu, _BAIDU_AVAILABLE
    
    print(f"\n=== Testing Baidu ===")
    print(f"Baidu Available: {_BAIDU_AVAILABLE}")
    
    if not _BAIDU_AVAILABLE:
        print("Baidu library not installed")
        return []
    
    try:
        result = _safe_search_baidu("阿诺尔多·蒙达多利出版社", 3)
        print(f"Results count: {len(result)}")
        if result:
            print(f"First result: {result[0].get('title', 'N/A')}")
        return result
    except Exception as e:
        print(f"Baidu Error: {e}")
        return []


def test_ddgs():
    """Test DuckDuckGo"""
    from research_agent.search import _safe_search_ddgs, _DDGS_AVAILABLE
    
    print(f"\n=== Testing DuckDuckGo ===")
    print(f"DDGS Available: {_DDGS_AVAILABLE}")
    
    if not _DDGS_AVAILABLE:
        print("DDGS library not installed")
        return []
    
    try:
        result = _safe_search_ddgs("Wie Baut Amerika book", 3)
        print(f"Results count: {len(result)}")
        if result:
            print(f"First result: {result[0].get('title', 'N/A')}")
        return result
    except Exception as e:
        print(f"DDGS Error: {e}")
        return []


def test_network():
    """Test basic network connectivity"""
    import requests
    
    print("\n=== Testing Network ===")
    
    # Test SearXNG URL
    searxng_url = os.getenv("SEARXNG_BASE_URL", "")
    if searxng_url:
        try:
            resp = requests.get(searxng_url, timeout=5)
            print(f"SearXNG accessible: {resp.status_code}")
        except Exception as e:
            print(f"SearXNG not accessible: {e}")
    
    # Test Serper API
    print("Testing Serper API endpoint...")
    try:
        url = "https://google.serper.dev/search"
        test_payload = json.dumps({"q": "test", "num": 1})
        headers = {"X-API-KEY": os.getenv("SERPER_API_KEY", "").split(",")[0], "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, data=test_payload, timeout=10)
        print(f"Serper API status: {resp.status_code}")
    except Exception as e:
        print(f"Serper API error: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("SEARCH PROVIDER DEBUG TEST")
    print("=" * 60)
    
    # Test network first
    test_network()
    
    # Test each provider
    serper_results = test_serper()
    searxng_results = test_searxng()
    baidu_results = test_baidu()
    ddgs_results = test_ddgs()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Serper results: {len(serper_results)}")
    print(f"SearXNG results: {len(searxng_results)}")
    print(f"Baidu results: {len(baidu_results)}")
    print(f"DDGS results: {len(ddgs_results)}")
