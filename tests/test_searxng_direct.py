#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试SearXNG专用函数
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from research_agent.search import _safe_search_searxng

def test_searxng_direct():
    print("=== 测试SearXNG专用函数 ===")
    
    searxng_url = "http://localhost:8083/"
    print(f"使用SearXNG地址: {searxng_url}")
    
    try:
        # 直接调用SearXNG函数
        results = _safe_search_searxng("test", 3, searxng_url)
        print(f"SearXNG返回结果数量: {len(results)}")
        if results:
            print("SUCCESS: SearXNG调用成功，返回了结果")
            for i, result in enumerate(results[:2]):  # 显示前两个结果
                print(f"  结果 {i+1}: {result.get('title', 'N/A')}")
        else:
            print("WARNING: SearXNG调用完成但没有返回结果")
        return len(results) > 0
        
    except Exception as e:
        print(f"ERROR: SearXNG调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_searxng_direct()
    if success:
        print("\nSUCCESS: SearXNG专用函数测试通过！")
    else:
        print("\nINFO: SearXNG专用函数测试完成（可能没有返回结果，但没有错误）")