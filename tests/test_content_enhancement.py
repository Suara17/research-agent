#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 SearXNG 搜索结果的内容增强功能
"""
import os
import sys
import asyncio
import json
from typing import List, Dict

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_agent.search import web_search
import content_enhancer
from content_enhancer import (
    enhance_search_results_with_content,
    sync_enhance_search_results_with_content,
    extract_content_from_html,
    summarize_content,
    extract_key_sentences,
    extract_top_content
)

def test_basic_web_search():
    """测试基本的网络搜索功能"""
    print("=" * 60)
    print("测试 1: 基本网络搜索功能")
    print("=" * 60)
    
    query = "Python编程语言简介"
    print(f"搜索查询: {query}")
    
    # 执行搜索
    result_json = web_search(query, top_k=3)
    result = json.loads(result_json)
    
    print(f"搜索结果数量: {len(result.get('results', []))}")
    print(f"来源: {result.get('source', 'unknown')}")
    
    for i, res in enumerate(result.get('results', [])):
        print(f"\n结果 {i+1}:")
        print(f"  标题: {res.get('title', 'N/A')[:100]}...")
        print(f"  摘要: {res.get('summary', 'N/A')[:150]}...")
        print(f"  URL: {res.get('url', 'N/A')[:80]}...")
        print(f"  来源: {res.get('source', 'N/A')}")
    
    return result.get('results', [])


def test_content_extraction():
    """测试内容提取功能"""
    print("\n" + "=" * 60)
    print("测试 2: 内容提取功能")
    print("=" * 60)
    
    # 使用一个简单的HTML示例
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>测试页面</title>
        <script>alert('test');</script>
        <style>body { margin: 0; }</style>
    </head>
    <body>
        <header>头部信息</header>
        <nav>导航栏</nav>
        <main>
            <article>
                <h1>Python编程语言介绍</h1>
                <p>Python是一种高级编程语言，由Guido van Rossum于1991年首次发布。</p>
                <p>它以简洁易读的语法著称，广泛应用于Web开发、数据科学、人工智能等领域。</p>
                <section>
                    <h2>特点</h2>
                    <ul>
                        <li>易于学习和使用</li>
                        <li>丰富的标准库</li>
                        <li>跨平台兼容</li>
                    </ul>
                </section>
            </article>
        </main>
        <footer>页脚信息</footer>
        <aside>侧边栏广告</aside>
    </body>
    </html>
    """
    
    extracted_content = extract_content_from_html(sample_html, "https://example.com")
    print(f"提取的内容:\n{extracted_content}")
    

def test_content_summarization():
    """测试内容总结功能"""
    print("\n" + "=" * 60)
    print("测试 3: 内容总结功能")
    print("=" * 60)
    
    sample_content = """
    Python是一种高级编程语言，由Guido van Rossum于1991年首次发布。
    它以简洁易读的语法著称，广泛应用于Web开发、数据科学、人工智能等领域。
    Python的设计哲学强调代码的可读性和简洁的语法，使得开发者可以用更少的代码表达想法。
    Python支持多种编程范式，包括面向对象、命令式、函数式和过程式编程。
    它拥有一个巨大的标准库，被称为"batteries included"哲学，提供了大量的预构建模块和功能。
    Python解释器本身也可以作为一个独立的程序使用，允许交互式编程。
    Python被设计为一门易于阅读的语言，有着相对较少的语法结构。
    Python语言的风格是"优雅"、"明确"、"简单"。
    Python社区经常使用"Python之禅"来描述Python的设计理念，强调代码的可读性。
    """
    
    query = "Python编程语言的特点"
    summary = summarize_content(sample_content, query, max_length=200)
    print(f"原始内容长度: {len(sample_content)} 字符")
    print(f"LLM总结后长度: {len(summary)} 字符")
    print(f"LLM总结内容:\n{summary}")


def test_non_llm_summarization():
    """测试非LLM的内容总结方法"""
    print("\n" + "=" * 60)
    print("测试 3b: 非LLM内容总结方法")
    print("=" * 60)
    
    sample_content = """
    人工智能（Artificial Intelligence，AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
    人工智能研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。
    1956年，在达特茅斯会议上，“人工智能”这一术语被正式提出，标志着人工智能学科的诞生。
    早期的人工智能研究集中在解决代数应用题、证明几何定理、学习下棋等高度形式化的问题上。
    1960年代，人工智能研究的重点转向了知识表示和推理机制，出现了早期的专家系统。
    1980年代，随着神经网络理论的发展，机器学习开始兴起，为人工智能带来了新的活力。
    进入21世纪，大数据、云计算和深度学习技术的快速发展，推动了人工智能进入新的发展阶段。
    当前，人工智能已在图像识别、语音识别、自然语言处理等领域取得了突破性进展。
    未来，人工智能有望在医疗、教育、交通等领域发挥更大的作用，但也面临着伦理、安全等方面的挑战。
    人工智能的发展历程充满了起伏，经历了多次繁荣与低谷，但总体上呈现出不断进步的趋势。
    这种技术的发展不仅改变了我们的生活方式，也对社会经济结构产生了深远影响。
    人工智能的核心在于模拟人类的认知能力，包括感知、推理、学习、规划和自然语言理解等方面。
    """
    
    print(f"原始内容长度: {len(sample_content)} 字符")
    
    # 测试关键句子提取方法
    key_sentences_summary = extract_key_sentences(sample_content, max_length=2000, num_sentences=8)
    print(f"\n关键句子提取方法结果 (长度: {len(key_sentences_summary)} 字符):")
    print(key_sentences_summary)
    
    # 测试顶部内容提取方法
    top_content_summary = extract_top_content(sample_content, max_length=2000)
    print(f"\n顶部内容提取方法结果 (长度: {len(top_content_summary)} 字符):")
    print(top_content_summary)


def test_async_enhancement():
    """测试异步内容增强功能"""
    print("\n" + "=" * 60)
    print("测试 4: 异步内容增强功能")
    print("=" * 60)
    
    # 创建模拟搜索结果
    mock_results = [
        {
            "title": "Python官方文档",
            "summary": "Python是一种解释型、面向对象、高级编程语言...",
            "url": "https://docs.python.org/",
            "source": "google"
        },
        {
            "title": "Python维基百科",
            "summary": "Python是一种广泛使用的解释型、高级编程、通用型编程语言...",
            "url": "https://zh.wikipedia.org/wiki/Python",
            "source": "wikipedia"
        }
    ]
    
    print("原始结果:")
    for i, result in enumerate(mock_results):
        print(f"  {i+1}. {result['title']}")
        print(f"     摘要: {result['summary']}")
        print(f"     URL: {result['url']}")
    
    # 测试异步增强（由于这是异步函数，我们会在主测试函数中调用）
    print("  [异步增强将在主测试中执行]")


def test_sync_enhancement():
    """测试同步内容增强功能"""
    print("\n" + "=" * 60)
    print("测试 5: 同步内容增强功能")
    print("=" * 60)
    
    # 创建模拟搜索结果
    mock_results = [
        {
            "title": "测试链接 1",
            "summary": "这是一个测试链接的摘要信息。",
            "url": "https://httpbin.org/html",  # 一个简单的HTML页面用于测试
            "source": "test"
        },
        {
            "title": "测试链接 2", 
            "summary": "另一个测试链接的摘要信息。",
            "url": "https://httpbin.org/json",  # 一个JSON页面用于测试
            "source": "test"
        }
    ]
    
    print("原始结果:")
    for i, result in enumerate(mock_results):
        print(f"  {i+1}. {result['title']}")
        print(f"     摘要: {result['summary']}")
        print(f"     URL: {result['url']}")
    
    print("\n正在执行同步内容增强...")
    enhanced_results = sync_enhance_search_results_with_content(mock_results, "测试查询")
    
    print("\n增强后的结果:")
    for i, result in enumerate(enhanced_results):
        print(f"  {i+1}. {result['title']}")
        print(f"     原摘要: {result['summary']}")
        if 'detailed_content' in result:
            print(f"     详细内容: {result['detailed_content'][:200]}...")
        if 'enhanced_summary' in result:
            print(f"     增强摘要: {result['enhanced_summary'][:200]}...")


def test_searxng_with_enhancement():
    """测试带有内容增强的SearXNG搜索"""
    print("\n" + "=" * 60)
    print("测试 6: 带内容增强的SearXNG搜索")
    print("=" * 60)
    
    query = "人工智能发展历史"
    print(f"搜索查询: {query}")
    
    # 设置环境变量以启用内容增强
    original_value = os.environ.get("ENHANCE_SEARCH_CONTENT")
    os.environ["ENHANCE_SEARCH_CONTENT"] = "true"
    
    try:
        # 执行搜索（这应该自动应用内容增强）
        result_json = web_search(query, top_k=2)
        result = json.loads(result_json)
        
        print(f"搜索结果数量: {len(result.get('results', []))}")
        
        for i, res in enumerate(result.get('results', [])):
            print(f"\n结果 {i+1}:")
            print(f"  标题: {res.get('title', 'N/A')}")
            print(f"  原始摘要: {res.get('summary', 'N/A')[:200]}...")
            
            # 检查是否包含增强内容
            if 'detailed_content' in res:
                print(f"  详细内容: {res['detailed_content'][:300]}...")
            if 'enhanced_summary' in res:
                print(f"  增强摘要: {res['enhanced_summary'][:300]}...")
                
            print(f"  URL: {res.get('url', 'N/A')}")
            print(f"  来源: {res.get('source', 'N/A')}")
    
    finally:
        # 恢复原始环境变量值
        if original_value is not None:
            os.environ["ENHANCE_SEARCH_CONTENT"] = original_value
        else:
            os.environ.pop("ENHANCE_SEARCH_CONTENT", None)


async def run_async_tests():
    """运行异步测试"""
    print("\n" + "=" * 60)
    print("运行异步内容增强测试")
    print("=" * 60)
    
    # 创建模拟搜索结果
    mock_results = [
        {
            "title": "Python官方网站",
            "summary": "Python是一种解释型、面向对象、高级编程语言...",
            "url": "https://www.python.org/",
            "source": "google"
        }
    ]
    
    print("原始结果:")
    for i, result in enumerate(mock_results):
        print(f"  {i+1}. {result['title']}")
        print(f"     摘要: {result['summary']}")
        print(f"     URL: {result['url']}")
    
    print("\n正在执行异步内容增强...")
    enhanced_results = await enhance_search_results_with_content(mock_results, "Python官方网站")
    
    print("\n增强后的结果:")
    for i, result in enumerate(enhanced_results):
        print(f"  {i+1}. {result['title']}")
        print(f"     原摘要: {result['summary']}")
        if 'detailed_content' in result:
            print(f"     详细内容: {result['detailed_content'][:200]}...")
        if 'enhanced_summary' in result:
            print(f"     增强摘要: {result['enhanced_summary'][:200]}...")


def main():
    """主测试函数"""
    print("SearXNG 搜索结果内容增强功能测试")
    print("测试目标: 验证多层信息获取功能")
    print("- 标题和摘要：基础信息获取")
    print("- 详细内容抓取：从网页获取完整内容") 
    print("- 智能总结：使用LLM对内容进行总结")
    
    # 运行各项测试
    search_results = test_basic_web_search()
    test_content_extraction()
    test_content_summarization()
    test_non_llm_summarization()  # 新增测试
    test_async_enhancement()
    test_sync_enhancement()
    test_searxng_with_enhancement()
    
    # 运行异步测试
    asyncio.run(run_async_tests())
    
    print("\n" + "=" * 60)
    print("所有测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()