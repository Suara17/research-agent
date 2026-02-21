#!/usr/bin/env python3
"""
测试 search.py 优化效果
使用 validation.jsonl 第一题进行测试
"""
import os
import sys
import json
import time
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env
from dotenv import load_dotenv
load_dotenv()

def get_first_question():
    """从 validation.jsonl 获取第一题"""
    validation_path = "validation.jsonl"
    if not os.path.exists(validation_path):
        # 尝试其他位置
        for root, dirs, files in os.walk("."):
            for f in files:
                if f == "validation.jsonl":
                    validation_path = os.path.join(root, f)
                    break
    
    print(f"Looking for validation.jsonl at: {validation_path}")
    
    if not os.path.exists(validation_path):
        # 尝试 py 目录
        validation_path = "py/validation.jsonl"
    
    if os.path.exists(validation_path):
        with open(validation_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                return data.get("question", data.get("q", ""))
    
    return None


def test_search_optimization():
    """测试搜索优化"""
    print("=" * 60)
    print("Testing Search Optimization")
    print("=" * 60)
    
    # 获取第一题
    question = get_first_question()
    if not question:
        print("Could not find first question from validation.jsonl")
        # 使用测试问题
        question = "一家在21世纪20年代初收购了某重工集团子公司的日本企业，在南欧收购了另一家由当地创业者创办的出版公司，这个企业叫什么？"
        print(f"Using test question: {question}")
    else:
        print(f"First question: {question}")
    
    print("\n" + "=" * 60)
    print("Testing search.py with optimized functions")
    print("=" * 60)
    
    # 导入搜索模块
    from research_agent.search import (
        _classify_query_type,
        _smart_query_rewrite,
        _select_search_engine_by_type,
        _rerank_by_query_type,
        web_search
    )
    
    # 1. 测试问题类型分类
    print("\n[1] Testing query classification...")
    query_type = _classify_query_type(question)
    print(f"Query type info: {json.dumps(query_type, ensure_ascii=False, indent=2)}")
    
    # 2. 测试智能查询重写
    print("\n[2] Testing smart query rewrite...")
    rewritten_q = _smart_query_rewrite(question, query_type)
    print(f"Original: {question[:80]}...")
    print(f"Rewritten: {rewritten_q}")
    
    # 3. 测试搜索引擎选择
    print("\n[3] Testing engine selection...")
    selected_engine = _select_search_engine_by_type(query_type)
    print(f"Selected engine: {selected_engine}")
    
    # 4. 测试实际搜索
    print("\n[4] Testing actual search...")
    start_time = time.time()
    result = web_search(question, top_k=5)
    elapsed = time.time() - start_time
    print(f"Search completed in {elapsed:.2f}s")
    
    # 解析结果
    result_data = json.loads(result)
    print(f"\nResults source: {result_data.get('source', 'unknown')}")
    print(f"Providers used: {result_data.get('providers_used', 0)}")
    
    if "results" in result_data:
        results = result_data["results"]
        print(f"\nGot {len(results)} results:")
        for i, r in enumerate(results[:5]):
            title = r.get("title", "")[:60]
            summary = r.get("summary", "")[:80]
            score = r.get("score", 0)
            print(f"\n  [{i+1}] {title}")
            print(f"      {summary}...")
            print(f"      Score: {score:.2f}")
    else:
        print(f"\nError in results: {result_data.get('error', 'unknown')}")
        print(f"Message: {result_data.get('message', '')}")
    
    # 5. 测试问题类型重排
    print("\n[5] Testing result reranking...")
    if "results" in result_data and result_data["results"]:
        reranked = _rerank_by_query_type(result_data["results"], question, query_type)
        print(f"Reranked {len(reranked)} results")
        print("\nTop 3 after reranking:")
        for i, r in enumerate(reranked[:3]):
            title = r.get("title", "")[:60]
            print(f"  [{i+1}] {title}")
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
    
    return result_data


if __name__ == "__main__":
    test_search_optimization()
