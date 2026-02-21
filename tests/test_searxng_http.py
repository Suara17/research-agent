#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接测试SearXNG HTTP响应
"""
import requests

def test_searxng_http():
    searxng_url = "http://localhost:8083/search"
    
    # 测试原始请求（无特殊头部）
    print("Testing SearXNG without special headers...")
    try:
        params = {
            "q": "hello world",
            "format": "json"
        }
        resp = requests.get(searxng_url, params=params, timeout=10)
        print(f"Status code: {resp.status_code}")
        if resp.status_code == 403:
            print("Got 403 Forbidden - bot detection still active")
        elif resp.status_code == 200:
            print("Got 200 OK - no bot detection")
        else:
            print(f"Got status code: {resp.status_code}")
    except Exception as e:
        print(f"Error making request without headers: {e}")
    
    print("\nTesting SearXNG with special headers (our fix)...")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-Forwarded-For': '127.0.0.1',
            'X-Real-IP': '127.0.0.1',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        }
        params = {
            "q": "hello world",
            "format": "json"
        }
        resp = requests.get(searxng_url, params=params, headers=headers, timeout=10)
        print(f"Status code: {resp.status_code}")
        if resp.status_code == 403:
            print("Still getting 403 Forbidden - fix didn't work")
        elif resp.status_code == 200:
            print("Got 200 OK - fix worked!")
            try:
                data = resp.json()
                print(f"Results count: {len(data.get('results', []))}")
            except Exception as e:
                print(f"Could not parse JSON response: {e}")
        else:
            print(f"Got status code: {resp.status_code}")
    except Exception as e:
        print(f"Error making request with headers: {e}")

if __name__ == "__main__":
    test_searxng_http()