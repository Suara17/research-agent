#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
估算模型接收到的搜索结果字符数
"""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from research_agent.search import web_search

def estimate_result_size():
    print("估算模型接收到的搜索结果字符数")
    print("=" * 50)
    
    # 测试查询
    test_query = "人工智能发展趋势"
    
    print(f"查询: {test_query}")
    print()
    
    # 调用搜索
    result_json = web_search(test_query, top_k=5)
    
    # 解析结果
    result_data = json.loads(result_json)
    
    print(f"结果来源: {result_data.get('source', 'N/A')}")
    print(f"使用提供商数量: {result_data.get('providers_used', 0)}")
    
    results = result_data.get('results', [])
    print(f"返回结果数量: {len(results)}")
    print()
    
    total_chars = 0
    total_words = 0
    
    for i, result in enumerate(results, 1):
        title = result.get('title', '')
        summary = result.get('summary', '')
        url = result.get('url', '')
        source = result.get('source', '')
        
        # 计算字符数和词数
        result_chars = len(title) + len(summary) + len(url) + len(source)
        result_words = len(title.split()) + len(summary.split()) + len(url.split()) + len(source.split())
        
        total_chars += result_chars
        total_words += result_words
        
        print(f"结果 {i}:")
        print(f"  来源: {source}")
        print(f"  标题: {title}")
        print(f"  摘要: {summary[:100]}{'...' if len(summary) > 100 else ''}")
        print(f"  链接: {url}")
        print(f"  字符数: {result_chars}, 词数: {result_words}")
        print()
    
    print(f"总计字符数: {total_chars}")
    print(f"总计词数: {total_words}")
    
    # 计算JSON字符串的大小
    json_size = len(result_json)
    print(f"JSON响应大小: {json_size} 字节")
    
    print()
    print("分析:")
    print(f"- 模型实际接收到的搜索结果文本约 {total_chars} 个字符")
    print(f"- JSON格式的完整响应约 {json_size} 字节")
    print(f"- 平均每个结果约 {total_chars//len(results) if results else 0} 个字符")
    
    return total_chars, json_size

if __name__ == "__main__":
    estimate_result_size()