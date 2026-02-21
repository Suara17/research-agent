"""
详细测试 search.py 的查询优化策略
展示关键词提取和查询优化的完整过程
"""

import os
import sys
import json
import logging
from datetime import datetime

# 设置日志
log_file = f"logs/test_query_optimization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# 读取第一个测试问题
def load_first_question():
    """从 validation.jsonl 读取第一个问题"""
    try:
        with open('validation.jsonl', 'r', encoding='utf-8') as f:
            first_line = f.readline()
            data = json.loads(first_line)
            return data.get('question', ''), data.get('answer', '')
    except Exception as e:
        logger.error(f"读取 validation.jsonl 失败: {e}")
        return None, None

def test_query_optimization():
    """测试查询优化过程"""
    logger.info("="*60)
    logger.info("测试查询优化策略")
    logger.info("="*60)
    
    # 导入search模块的优化函数
    from research_agent.search import (
        _optimize_search_query,
        _is_entity_query,
        _extract_search_slots,
        expand_query_language
    )
    
    # 加载问题
    question, expected_answer = load_first_question()
    if not question:
        logger.error("无法加载测试问题")
        return
    
    logger.info(f"原始问题: {question}")
    logger.info(f"预期答案: {expected_answer}")
    
    # 1. 测试实体查询检测
    logger.info("\n" + "-"*40)
    logger.info("【步骤1】实体查询检测")
    logger.info("-"*40)
    is_entity = _is_entity_query(question)
    logger.info(f"是否为实体查询: {is_entity}")
    
    # 2. 测试查询优化
    logger.info("\n" + "-"*40)
    logger.info("【步骤2】查询优化 (提取关键词)")
    logger.info("-"*40)
    optimized = _optimize_search_query(question)
    logger.info(f"优化后的查询: {optimized}")
    logger.info(f"原始长度: {len(question)} 字符")
    logger.info(f"优化后长度: {len(optimized)} 字符")
    
    # 3. 测试多语言扩展
    logger.info("\n" + "-"*40)
    logger.info("【步骤3】多语言查询扩展")
    logger.info("-"*40)
    expanded_queries = expand_query_language(question)
    logger.info(f"扩展的查询: {expanded_queries}")
    
    # 4. 测试搜索槽位提取
    logger.info("\n" + "-"*40)
    logger.info("【步骤4】搜索槽位提取 (结构化信息)")
    logger.info("-"*40)
    try:
        slots = _extract_search_slots(question)
        logger.info(f"提取的槽位信息: {json.dumps(slots, ensure_ascii=False, indent=2)}")
    except Exception as e:
        logger.warning(f"槽位提取失败: {e}")
    
    # 5. 执行实际搜索
    logger.info("\n" + "-"*40)
    logger.info("【步骤5】执行优化后的搜索")
    logger.info("-"*40)
    
    from research_agent.search import web_search
    result = web_search(optimized, top_k=5)
    result_data = json.loads(result)
    
    logger.info(f"搜索来源: {result_data.get('source', 'unknown')}")
    logger.info(f"获取到 {len(result_data.get('results', []))} 个结果")
    
    for i, r in enumerate(result_data.get('results', [])[:3]):
        logger.info(f"\n--- 结果 {i+1} ---")
        logger.info(f"标题: {r.get('title', 'N/A')[:80]}")
        logger.info(f"摘要: {r.get('summary', 'N/A')[:150]}")
        logger.info(f"URL: {r.get('url', 'N/A')}")
    
    return result_data

def main():
    logger.info("开始测试 search.py 的查询优化策略")
    logger.info(f"日志文件: {log_file}")
    
    result = test_query_optimization()
    
    logger.info("\n" + "="*60)
    logger.info("测试完成")
    logger.info(f"日志已保存到: {log_file}")
    logger.info("="*60)

if __name__ == "__main__":
    main()
