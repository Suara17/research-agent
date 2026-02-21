#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试SearXNG修复的脚本
"""
import os
import sys
import asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from research_agent.search import web_search, _safe_search_searxng

def test_direct_searxng_call():
    print("Direct test of SearXNG API call...")
    
    # 设置环境变量
    searxng_url = os.getenv("SEARXNG_BASE_URL", "http://localhost:8083/")
    print(f"Using SearXNG address: {searxng_url}")
    
    try:
        # 直接调用SearXNG函数
        results = _safe_search_searxng("hello world", 3, searxng_url)
        print(f"SearXNG returned {len(results)} results")
        if results:
            print("[SUCCESS] SearXNG call succeeded and returned results")
            for i, result in enumerate(results[:2]):  # 显示前两个结果
                print(f"  Result {i+1}: {result.get('title', 'N/A')}")
        else:
            print("[WARNING] SearXNG call completed but returned no results")
        return len(results) > 0
        
    except Exception as e:
        print(f"[ERROR] SearXNG call failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_web_search_integration():
    print("\nTesting web_search integration...")
    
    # 设置环境变量
    if not os.getenv("SEARXNG_BASE_URL"):
        os.environ["SEARXNG_BASE_URL"] = "http://localhost:8083/"
    
    print(f"Using SearXNG address: {os.getenv('SEARXNG_BASE_URL')}")
    
    try:
        # 测试搜索
        result = web_search("hello world", top_k=3)
        print("Complete search result:")
        print(result)
        
        # 检查是否包含错误信息
        if '"error"' in result:
            print("[ERROR] Search failed with error")
            return False
        else:
            print("[SUCCESS] Search completed without obvious errors")
            return True
            
    except Exception as e:
        print(f"[ERROR] Search process failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=== Testing SearXNG Fix ===")
    
    # 测试直接调用
    direct_success = test_direct_searxng_call()
    
    # 测试集成调用
    integration_success = asyncio.run(test_web_search_integration())
    
    print(f"\nSummary:")
    print(f"- Direct SearXNG call: {'Success' if direct_success else 'Failed'}")
    print(f"- Integrated search call: {'Success' if integration_success else 'Failed'}")
    
    if direct_success or integration_success:
        print("\n[SUCCESS] At least one test passed, SearXNG API 403 error may be resolved")
    else:
        print("\n[ERROR] All tests failed, please check if SearXNG service is running properly")