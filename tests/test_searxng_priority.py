#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 SearXNG 优先搜索功能
"""
import os
import json
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_agent.search import web_search

def test_searxng_priority():
    """测试 SearXNG 优先功能"""
    print("=" * 60)
    print("测试 SearXNG 优先搜索功能")
    print("=" * 60)
    
    # 检查是否设置了 SearXNG URL
    searxng_url = os.getenv("SEARXNG_BASE_URL")
    print(f"SearXNG Base URL: {searxng_url}")
    
    if not searxng_url:
        print("警告: 未设置 SEARXNG_BASE_URL 环境变量，将使用其他搜索提供商")
    
    query = "Python编程语言简介"
    print(f"搜索查询: {query}")
    
    # 执行搜索
    result_json = web_search(query, top_k=3)
    result = json.loads(result_json)
    
    print(f"搜索结果数量: {len(result.get('results', []))}")
    print(f"数据源: {result.get('source', 'unknown')}")
    print(f"主要提供商: {result.get('primary_provider', 'unknown')}")
    print(f"使用提供商数量: {result.get('providers_used', 0)}")
    
    print("\n搜索结果:")
    for i, res in enumerate(result.get('results', [])):
        print(f"\n  结果 {i+1}:")
        print(f"    标题: {res.get('title', 'N/A')[:60]}...")
        print(f"    摘要: {res.get('summary', 'N/A')[:100]}...")
        print(f"    URL: {res.get('url', 'N/A')[:60]}...")
        print(f"    来源: {res.get('source', 'N/A')}")
    
    print(f"\n{'='*60}")
    print("测试完成!")
    print(f"{'='*60}")


if __name__ == "__main__":
    test_searxng_priority()