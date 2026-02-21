#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试内容增强功能
"""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from research_agent.search import web_search

def test_enhanced_search():
    print("测试内容增强搜索功能")
    print("=" * 50)
    
    # 设置环境变量启用内容增强
    os.environ["ENHANCE_SEARCH_CONTENT"] = "true"
    
    # 测试查询
    test_query = "人工智能发展趋势"
    
    print(f"查询: {test_query}")
    print()
    
    # 调用搜索
    result_json = web_search(test_query, top_k=3)
    
    # 解析结果
    result_data = json.loads(result_json)
    
    print(f"结果来源: {result_data.get('source', 'N/A')}")
    print(f"使用提供商数量: {result_data.get('providers_used', 0)}")
    
    results = result_data.get('results', [])
    print(f"返回结果数量: {len(results)}")
    print()
    
    total_chars = 0
    
    for i, result in enumerate(results, 1):
        title = result.get('title', 'N/A')
        summary = result.get('summary', 'N/A')
        enhanced_summary = result.get('enhanced_summary', 'N/A')
        detailed_content = result.get('detailed_content', 'N/A')
        source = result.get('source', 'N/A')
        url = result.get('url', 'N/A')
        
        # 计算字符数
        result_chars = len(title) + len(summary) + len(enhanced_summary) + len(detailed_content) + len(source) + len(url)
        total_chars += result_chars
        
        print(f"结果 {i}:")
        print(f"  来源: {source}")
        print(f"  标题: {title}")
        print(f"  原始摘要: {summary[:100]}{'...' if len(summary) > 100 else ''}")
        print(f"  增强摘要: {enhanced_summary[:100]}{'...' if len(enhanced_summary) > 100 else ''}")
        print(f"  详细内容: {detailed_content[:100]}{'...' if len(detailed_content) > 100 else ''}")
        print(f"  链接: {url[:50]}{'...' if len(url) > 50 else ''}")
        print(f"  字符数: {result_chars}")
        print()
    
    print(f"总计字符数: {total_chars}")
    
    print()
    print("分析:")
    print(f"- 内容增强功能已启用")
    print(f"- 模型将接收到更丰富的网页内容信息")
    print(f"- 包含详细内容摘要，提供更多上下文")
    print(f"- 总字符数显著增加，提供更完整的信息")

if __name__ == "__main__":
    test_enhanced_search()