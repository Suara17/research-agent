#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试SearXNG结果筛选功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from research_agent.search import _safe_search_searxng

def test_filtered_search():
    print("测试SearXNG结果筛选功能")
    print("=" * 50)
    
    # 测试查询
    test_query = "人工智能发展趋势"
    
    print(f"查询: {test_query}")
    print()
    
    # 调用SearXNG搜索
    results = _safe_search_searxng(test_query, 5, "http://localhost:8083/")
    
    print(f"返回结果数量: {len(results)}")
    print()
    
    if results:
        print("筛选后的结果:")
        for i, result in enumerate(results, 1):
            title = result.get('title', 'N/A')
            summary = result.get('summary', 'N/A')[:200] + "..." if len(result.get('summary', '')) > 200 else result.get('summary', 'N/A')
            source = result.get('source', 'N/A')
            url = result.get('url', 'N/A')
            
            print(f"{i}. 来源: {source}")
            print(f"   标题: {title}")
            print(f"   摘要: {summary}")
            print(f"   链接: {url}")
            print()
    else:
        print("未找到相关结果")
    
    print("测试完成")

if __name__ == "__main__":
    test_filtered_search()