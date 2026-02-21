#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试完整的SearXNG修复方案
"""
import os
import sys
import asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from research_agent.search import web_search

async def test_full_integration():
    print("=== 测试完整的SearXNG修复方案 ===")
    
    # 设置环境变量
    os.environ["SEARXNG_BASE_URL"] = "http://localhost:8083/"
    
    print(f"使用SearXNG地址: {os.environ['SEARXNG_BASE_URL']}")
    
    try:
        # 测试搜索
        result = web_search("test query", top_k=2)
        print("搜索结果:")
        print(result)
        
        # 检查是否包含错误信息
        if '"error"' in result:
            print("❌ 搜索失败，可能存在403错误或其他问题")
            return False
        else:
            print("✅ 搜索成功，403错误已解决")
            return True
            
    except Exception as e:
        print(f"❌ 搜索过程中出现异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_full_integration())
    if success:
        print("\n🎉 集成测试通过！SearXNG API 403错误已解决")
    else:
        print("\n❌ 集成测试失败，请检查SearXNG服务配置")