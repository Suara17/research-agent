#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SearXNG 搜索结果内容增强功能 - 最终演示
展示了优化后的多层信息获取功能：
1. 标题和摘要：基础信息获取
2. 详细内容抓取：从网页获取完整内容（控制长度）
3. 智能总结：优先使用非LLM方法以减少TOKEN成本
"""
import os
import sys
import json
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_agent.search import web_search
from content_enhancer import (
    sync_enhance_search_results_with_content,
    extract_content_from_html,
    summarize_content,
    extract_key_sentences,
    extract_top_content
)

def demo_multi_layer_info_retrieval():
    """演示多层信息获取功能"""
    print("=" * 80)
    print("SearXNG 搜索结果内容增强功能 - 多层信息获取演示")
    print("=" * 80)
    print("功能特点:")
    print("1. 标题和摘要：基础信息获取")
    print("2. 详细内容抓取：从网页获取完整内容（长度控制在2000字符左右）")
    print("3. 智能总结：优先使用非LLM方法，减少TOKEN成本")
    print("-" * 80)
    
    # 执行搜索
    query = "量子计算的基本原理"
    print(f"搜索查询: {query}")
    
    result_json = web_search(query, top_k=2)
    result = json.loads(result_json)
    
    print(f"\n搜索结果数量: {len(result.get('results', []))}")
    print(f"来源: {result.get('source', 'unknown')}")
    
    # 显示原始结果
    print("\n原始搜索结果:")
    for i, res in enumerate(result.get('results', [])):
        print(f"\n  结果 {i+1}:")
        print(f"    标题: {res.get('title', 'N/A')[:60]}...")
        summary = res.get('summary', 'N/A')[:100]
        # 安全打印，移除特殊字符
        safe_summary = summary.encode('ascii', errors='ignore').decode('ascii', errors='ignore')
        print(f"    摘要: {safe_summary}")
        print(f"    URL: {res.get('url', 'N/A')[:60]}...")
        print(f"    来源: {res.get('source', 'N/A')}")
    
    # 演示内容增强
    print(f"\n{'-'*80}")
    print("应用内容增强功能...")
    print(f"{'-'*80}")
    
    # 设置环境变量启用内容增强
    original_value = os.environ.get("ENHANCE_SEARCH_CONTENT")
    os.environ["ENHANCE_SEARCH_CONTENT"] = "true"
    
    try:
        enhanced_results = sync_enhance_search_results_with_content(
            result.get('results', [])[:2],  # 只处理前2个结果
            query
        )
        
        print("\n增强后的结果 (包含详细内容和智能总结):")
        for i, res in enumerate(enhanced_results):
            print(f"\n  增强结果 {i+1}:")
            print(f"    标题: {res.get('title', 'N/A')[:60]}...")
            original_summary = res.get('summary', 'N/A')[:100]
            safe_original_summary = original_summary.encode('ascii', errors='ignore').decode('ascii', errors='ignore')
            print(f"    原始摘要: {safe_original_summary}...")
            
            # 显示详细内容（已控制长度）
            if 'detailed_content' in res:
                detail_len = len(res['detailed_content'])
                detail_preview = res['detailed_content'][:200]
                print(f"    详细内容长度: {detail_len} 字符")
                safe_detail = detail_preview.encode('ascii', errors='ignore').decode('ascii', errors='ignore')
                print(f"    详细内容预览: {safe_detail}...")
            
            # 显示增强摘要
            if 'enhanced_summary' in res:
                enhanced_len = len(res['enhanced_summary'])
                preview = res['enhanced_summary'][:200] + "..." if len(res['enhanced_summary']) > 200 else res['enhanced_summary']
                print(f"    增强摘要长度: {enhanced_len} 字符")
                safe_preview = preview.encode('ascii', errors='ignore').decode('ascii', errors='ignore')
                print(f"    增强摘要: {safe_preview}")
            
            print(f"    URL: {res.get('url', 'N/A')[:60]}...")
    
    finally:
        # 恢复环境变量
        if original_value is not None:
            os.environ["ENHANCE_SEARCH_CONTENT"] = original_value
        else:
            os.environ.pop("ENHANCE_SEARCH_CONTENT", None)


def demo_cost_reduction_techniques():
    """演示成本降低技术"""
    print(f"\n{'='*80}")
    print("成本降低技术演示")
    print("=" * 80)
    
    sample_content = """
    量子计算是一种基于量子力学原理的计算方式，利用量子比特（qubit）进行信息处理。
    与经典计算机使用的比特只能处于0或1状态不同，量子比特可以同时处于0和1的叠加态。
    这种特性使得量子计算机在某些特定问题上具有指数级的加速能力。
    量子计算的核心概念包括叠加、纠缠和干涉。
    叠加是指量子比特可以同时表示多种状态；
    纠缠是指多个量子比特之间存在特殊的关联关系；
    干涉是指量子态之间的相互作用可以增强或抵消某些结果的概率。
    当前量子计算面临的主要挑战包括量子退相干、错误率控制和量子比特扩展等问题。
    尽管如此，量子计算在密码学、材料科学、药物发现等领域展现出巨大潜力。
    主要的量子计算公司包括IBM、Google、Microsoft、Rigetti等。
    """
    
    print(f"原始内容长度: {len(sample_content)} 字符")
    print("内容: ", sample_content.strip()[:100], "...\n")
    
    # 演示非LLM方法的成本效益
    print("1. 关键句子提取方法 (无TOKEN成本):")
    key_sentences = extract_key_sentences(sample_content, max_length=300, num_sentences=5)
    print(f"   输出长度: {len(key_sentences)} 字符")
    print(f"   内容: {key_sentences}")
    
    print("\n2. 顶部内容提取方法 (无TOKEN成本):")
    top_content = extract_top_content(sample_content, max_length=300)
    print(f"   输出长度: {len(top_content)} 字符")
    print(f"   内容: {top_content}")
    
    print("\n3. 优化后的总结方法 (优先非LLM，必要时使用LLM):")
    optimized_summary = summarize_content(sample_content, "量子计算", max_length=300)
    print(f"   输出长度: {len(optimized_summary)} 字符")
    print(f"   内容: {optimized_summary}")
    
    print(f"\n总结: 通过优先使用非LLM方法，显著降低了TOKEN成本！")


def main():
    """主函数"""
    demo_multi_layer_info_retrieval()
    demo_cost_reduction_techniques()
    
    print(f"\n{'='*80}")
    print("演示完成！")
    print("优化亮点:")
    print("- 详细内容长度控制在合理范围内 (~2000字符)")
    print("- 优先使用非LLM方法进行内容总结，大幅降低成本")
    print("- 保持了高质量的信息提取和总结能力")
    print("- 支持多层信息获取：标题摘要 -> 详细内容 -> 智能总结")
    print("=" * 80)


if __name__ == "__main__":
    main()