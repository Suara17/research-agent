#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试查询优化策略 - 验证关键词提取和优化效果
"""
import os
import sys
from pathlib import Path

# 设置路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env 文件
def load_env_file(env_path=".env"):
    env_file = Path(env_path)
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value.strip()

load_env_file(".env")

from research_agent.search import _optimize_search_query, _extract_search_slots, web_search
import json

# 测试查询
TEST_QUERIES = [
    {
        "original": "在某一年，一位法国天文学家对一颗彗星的光谱进行了开创性观测，同年的一张太阳黑子照片后来在东亚某大都市的天文展览中展出。也正是在这一年，一位尚不满二十岁的南欧创业者，在家乡小镇创办了他的出版事业。十余年后，他将公司总部迁往了该国北部的商业中心。他所创立的这家出版公司的名字是什么？",
        "description": "中文复杂问题 - 需提取关键实体"
    },
    {
        "original": "What is the name of the significant military operation in which the first Hispanic to attain the rank of Master Gunnery Sergeant in their Military Occupational Specialty served?",
        "description": "英文军事问题 - 包含多个约束条件"
    },
    {
        "original": "一位物理学领域的学者为一种经典棋盘游戏设计的评分系统，后来被一家北美游戏公司广泛应用于其一款多人在线战术竞技游戏中。",
        "description": "中文问题 - 涉及游戏和公司"
    },
    {
        "original": "谁写了《战争与和平》这本书？",
        "description": "简单中文问题"
    },
    {
        "original": "Who wrote 'Pride and Prejudice'?",
        "description": "简单英文问题"
    }
]

def test_query_optimization():
    print("="*80)
    print("查询优化策略测试")
    print("="*80)
    
    for i, q in enumerate(TEST_QUERIES):
        original = q["original"]
        desc = q["description"]
        
        print(f"\n{'='*60}")
        print(f"测试 {i+1}: {desc}")
        print(f"{'='*60}")
        print(f"原始查询: {original[:100]}...")
        
        # 1. 测试查询优化
        optimized = _optimize_search_query(original)
        print(f"\n[优化后] {optimized}")
        
        # 2. 测试槽位提取
        slots = _extract_search_slots(original)
        print(f"\n[槽位提取]")
        print(f"  类型: {slots.get('type', 'N/A')}")
        print(f"  硬约束: {slots.get('hard_constraints', [])}")
        print(f"  锚点: {slots.get('anchors', [])}")
        
        # 3. 实际搜索测试
        print(f"\n[搜索测试]")
        result = web_search(original, top_k=3)
        try:
            data = json.loads(result)
            results = data.get("results", [])
            print(f"  返回结果数: {len(results)}")
            for j, r in enumerate(results[:2]):
                title = r.get("title", "")[:50]
                print(f"  {j+1}. {title}")
        except Exception as e:
            print(f"  搜索错误: {e}")

def test_search_slots_directly():
    """直接测试槽位提取的效果"""
    print("\n" + "="*80)
    print("槽位提取详细测试")
    print("="*80)
    
    test_queries = [
        "阿诺尔多·蒙达多利出版社 创始人",
        "Operation Desert Storm 指挥官",
        "爱因斯坦 相对论 1905"
    ]
    
    for q in test_queries:
        print(f"\n查询: {q}")
        slots = _extract_search_slots(q)
        print(f"  类型: {slots.get('type')}")
        print(f"  硬约束: {slots.get('hard_constraints')}")
        print(f"  锚点: {slots.get('anchors')}")

if __name__ == "__main__":
    test_query_optimization()
    test_search_slots_directly()
