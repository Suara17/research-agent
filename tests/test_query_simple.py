#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试查询优化策略 - 仅测试优化逻辑，不发起网络请求"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 直接导入优化函数
from research_agent.search import _optimize_search_query, _extract_search_slots

# 测试查询
TEST_QUERIES = [
    {
        "original": "在某一年，一位法国天文学家对一颗彗星的光谱进行了开创性观测，同年的一张太阳黑子照片后来在东亚某大都市的天文展览中展出。也正是在这一年，一位尚不满二十岁的南欧创业者，在家乡小镇创办了他的出版事业。十余年后，他将公司总部迁往了该国北部的商业中心。他所创立的这家出版公司的名字是什么？",
        "expected_key_entities": ["法国天文学家", "彗星", "光谱", "太阳黑子", "出版公司", "南欧"]
    },
    {
        "original": "What is the name of the significant military operation in which the first Hispanic to attain the rank of Master Gunnery Sergeant in their Military Occupational Specialty served?",
        "expected_key_entities": ["Master Gunnery Sergeant", "Hispanic", "military operation"]
    },
    {
        "original": "谁写了《战争与和平》这本书？",
        "expected_key_entities": ["战争与和平", "作者"]
    }
]

def test_optimization():
    print("="*80)
    print("查询优化策略测试")
    print("="*80)
    
    for i, q in enumerate(TEST_QUERIES):
        original = q["original"]
        
        print(f"\n[{i+1}] 原始查询: {original[:60]}...")
        
        # 1. 测试查询优化
        optimized = _optimize_search_query(original)
        print(f"    优化后: {optimized[:80]}")
        
        # 2. 测试槽位提取
        try:
            slots = _extract_search_slots(original)
            print(f"    类型: {slots.get('type', 'N/A')}")
            print(f"    硬约束: {slots.get('hard_constraints', [])}")
            print(f"    锚点: {slots.get('anchors', [])}")
        except Exception as e:
            print(f"    槽位提取失败: {e}")

if __name__ == "__main__":
    test_optimization()
