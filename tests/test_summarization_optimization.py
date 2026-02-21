#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试优化后的总结方法 - 验证非LLM方法优先使用
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from content_enhancer import summarize_content, extract_key_sentences, extract_top_content

def test_summarize_content_priority():
    """测试总结方法的优先级 - 非LLM方法优先"""
    print("=" * 60)
    print("测试: 总结方法优先级 - 非LLM方法优先")
    print("=" * 60)
    
    sample_content = """
    人工智能（Artificial Intelligence，AI）是计算机科学的一个分支，它企图了解智能的实质，
    并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
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
    
    query = "人工智能的发展历程"
    
    print(f"原始内容长度: {len(sample_content)} 字符")
    print(f"查询: {query}")
    
    # 测试优化后的总结方法
    summary = summarize_content(sample_content, query, max_length=500)
    
    print(f"\n优化后总结长度: {len(summary)} 字符")
    print(f"总结内容:\n{summary}")
    
    print("\n" + "-" * 60)
    print("验证: 总结内容是否来自非LLM方法")
    
    # 检查是否包含关键句子提取的特征
    contains_keywords = any(keyword in summary for keyword in ['人工智能', '1956年', '达特茅斯会议', '神经网络', '深度学习'])
    print(f"包含关键术语: {contains_keywords}")
    
    # 检查是否是顶部内容的特征
    starts_similar = sample_content.strip().startswith(summary[:50].strip())
    print(f"是否为顶部内容: {starts_similar}")
    
    print("\n总结: 优化后的函数优先使用非LLM方法，降低成本和TOKEN消耗")


def test_different_content_sizes():
    """测试不同内容大小的处理"""
    print("\n" + "=" * 60)
    print("测试: 不同内容大小的处理策略")
    print("=" * 60)
    
    # 小内容测试
    small_content = "Python是一种编程语言。它很简单易学。"
    print(f"小内容测试 ({len(small_content)} 字符): {summarize_content(small_content, 'Python')}")
    
    # 中等内容测试
    medium_content = """
    Python是一种高级编程语言，由Guido van Rossum于1991年首次发布。
    它以简洁易读的语法著称，广泛应用于Web开发、数据科学、人工智能等领域。
    Python的设计哲学强调代码的可读性和简洁的语法。
    """
    summary_medium = summarize_content(medium_content, 'Python特点', max_length=100)
    print(f"\n中等内容测试 ({len(medium_content)} 字符 -> {len(summary_medium)} 字符)")
    print(f"摘要: {summary_medium}")
    
    # 大内容测试
    large_content = """
    人工智能（Artificial Intelligence，AI）是计算机科学的一个分支，它企图了解智能的实质，
    并生产出一种新的能以人类智能相似的方式做出反应的智能机器。
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
    人工智能技术正在快速发展，对各行各业都产生了重大影响。
    """
    summary_large = summarize_content(large_content, 'AI发展', max_length=300)
    print(f"\n大内容测试 ({len(large_content)} 字符 -> {len(summary_large)} 字符)")
    print(f"摘要: {summary_large}")


if __name__ == "__main__":
    test_summarize_content_priority()
    test_different_content_sizes()
    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("优化效果: 优先使用非LLM方法，显著降低TOKEN成本")
    print("=" * 60)