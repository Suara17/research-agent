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
    print("直接测试SearXNG API调用...")
    
    # 设置环境变量
    searxng_url = os.getenv("SEARXNG_BASE_URL", "http://localhost:8083/")
    print(f"使用SearXNG地址: {searxng_url}")
    
    try:
        # 直接调用SearXNG函数
        results = _safe_search_searxng("hello world", 3, searxng_url)
        print(f"SearXNG返回结果数量: {len(results)}")
        if results:
            print("✅ SearXNG调用成功，返回了结果")
            for i, result in enumerate(results[:2]):  # 显示前两个结果
                print(f"  结果 {i+1}: {result.get('title', 'N/A')}")
        else:
            print("⚠️ SearXNG调用完成但没有返回结果")
        return len(results) > 0
        
    except Exception as e:
        print(f"❌ SearXNG调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_web_search_integration():
    print("\n测试web_search集成...")
    
    # 设置环境变量
    if not os.getenv("SEARXNG_BASE_URL"):
        os.environ["SEARXNG_BASE_URL"] = "http://localhost:8083/"
    
    print(f"使用SearXNG地址: {os.getenv('SEARXNG_BASE_URL')}")
    
    try:
        # 测试搜索
        result = web_search("hello world", top_k=3)
        print("完整搜索结果:")
        print(result)
        
        # 检查是否包含错误信息
        if '"error"' in result:
            print("❌ 搜索失败，存在错误")
            return False
        else:
            print("✅ 搜索完成，无明显错误")
            return True
            
    except Exception as e:
        print(f"❌ 搜索过程中出现异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=== 测试SearXNG修复 ===")
    
    # 测试直接调用
    direct_success = test_direct_searxng_call()
    
    # 测试集成调用
    integration_success = asyncio.run(test_web_search_integration())
    
    print(f"\n总结:")
    print(f"- 直接SearXNG调用: {'成功' if direct_success else '失败'}")
    print(f"- 集成搜索调用: {'成功' if integration_success else '失败'}")
    
    if direct_success or integration_success:
        print("\n🎉 至少有一个测试成功，SearXNG API 403错误可能已解决")
    else:
        print("\n❌ 所有测试都失败，请检查SearXNG服务是否正常运行")