#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证SearXNG 403错误修复
"""
import os
import requests

def test_searxng_fix():
    print("=== 验证SearXNG 403错误修复 ===")
    
    searxng_url = "http://localhost:8083/search"
    
    # 测试1: 不带特殊头部的请求（应该失败或返回403）
    print("\n1. 测试不带特殊头部的请求:")
    try:
        params = {"q": "test", "format": "json"}
        resp = requests.get(searxng_url, params=params, timeout=10)
        print(f"   状态码: {resp.status_code}")
        if resp.status_code == 403:
            print("   结果: 仍返回403 (预期)")
        else:
            print("   结果: 不是403 (可能已修复)")
    except Exception as e:
        print(f"   异常: {e}")
    
    # 测试2: 带特殊头部的请求（应该成功）
    print("\n2. 测试带特殊头部的请求:")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-Forwarded-For': '127.0.0.1',
            'X-Real-IP': '127.0.0.1',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        }
        params = {"q": "test", "format": "json"}
        resp = requests.get(searxng_url, params=params, headers=headers, timeout=10)
        print(f"   状态码: {resp.status_code}")
        if resp.status_code == 200:
            print("   结果: ✅ 成功！不再返回403错误")
            try:
                data = resp.json()
                print(f"   返回结果数: {len(data.get('results', []))}")
            except:
                print("   无法解析JSON响应")
        elif resp.status_code == 403:
            print("   结果: ❌ 仍返回403错误")
        else:
            print(f"   结果: 其他状态码 {resp.status_code}")
    except Exception as e:
        print(f"   异常: {e}")
    
    # 测试3: 验证Python代码中的修复
    print("\n3. 测试Python代码中的修复:")
    try:
        from research_agent.search import _safe_search_searxng
        results = _safe_search_searxng("test", 3, "http://localhost:8083/")
        print(f"   Python函数返回结果数: {len(results)}")
        print("   结果: ✅ Python代码修复有效（无异常）")
    except Exception as e:
        print(f"   结果: ❌ Python代码仍有问题: {e}")
    
    print("\n=== 修复验证完成 ===")

if __name__ == "__main__":
    test_searxng_fix()