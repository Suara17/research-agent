#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试增强的查询优化策略"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_agent.search import _optimize_search_query, _extract_search_slots, _is_entity_query

# 测试查询
TEST_QUERIES = [
    {
        "name": "问题1: 复杂历史事件",
        "original": "在某一年，一位法国天文学家对一颗彗星的光谱进行了开创性观测，同年的一张太阳黑子照片后来在东亚某大都市的天文展览中展出。也正是在这一年，一位尚不满二十岁的南欧创业者，在家乡小镇创办了他的出版事业。十余年后，他将公司总部迁往了该国北部的商业中心。他所创立的这家出版公司的名字是什么？",
        "expected_entity": True,
    },
    {
        "name": "问题2: 美国军事历史",
        "original": "What is the name of the significant military operation in which the first Hispanic to attain the rank of Master Gunnery Sergeant in their Military Occupational Specialty served?",
        "expected_entity": True,
    },
    {
        "name": "问题3: 简单书籍查询",
        "original": "谁写了《战争与和平》这本书？",
        "expected_entity": True,
    },
    {
        "name": "问题4: 如何做某事",
        "original": "如何安装Python？",
        "expected_entity": False,  # 这个问题不是实体查询
    },
    {
        "name": "问题5: 最新新闻",
        "original": "今天有什么重大新闻？",
        "expected_entity": False,
    },
]

def test_enhanced_optimization():
    print("="*80)
    print("增强查询优化策略测试")
    print("="*80)
    
    for i, q in enumerate(TEST_QUERIES):
        original = q["original"]
        expected_entity = q.get("expected_entity", True)
        
        print(f"\n[{i+1}] {q['name']}")
        print(f"    原始查询: {original[:60]}...")
        
        # 1. 测试实体查询检测
        is_entity = _is_entity_query(original)
        print(f"    实体查询检测: {is_entity} (预期: {expected_entity})")
        
        # 2. 测试查询优化
        optimized = _optimize_search_query(original)
        print(f"    优化后: {optimized[:80]}...")
        
        # 3. 测试槽位提取（带降级）
        try:
            slots = _extract_search_slots(original)
            print(f"    类型: {slots.get('type', 'N/A')}")
            print(f"    硬约束: {slots.get('hard_constraints', [])}")
            print(f"    锚点: {slots.get('anchors', [])}")
        except Exception as e:
            print(f"    槽位提取错误: {e}")
        
        # 4. 验证实体查询检测是否正确
        if is_entity != expected_entity:
            print(f"    ⚠️  实体检测可能不准确!")

if __name__ == "__main__":
    test_enhanced_optimization()
