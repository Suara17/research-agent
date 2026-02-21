"""
测试 search.py 的网页搜索和网页抓取功能
使用 validation.jsonl 的第一个问题进行测试
"""

import os
import sys
import json
import logging
from datetime import datetime

# 设置日志
log_file = f"logs/test_search_function_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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

def test_web_search(query):
    """测试网页搜索功能"""
    logger.info("="*60)
    logger.info("测试 web_search 函数")
    logger.info(f"查询: {query}")
    logger.info("="*60)
    
    try:
        from research_agent.search import web_search
        
        result = web_search(query, top_k=5)
        logger.info(f"搜索结果类型: {type(result)}")
        
        # 解析JSON结果
        result_data = json.loads(result)
        logger.info(f"搜索结果来源: {result_data.get('source', 'unknown')}")
        
        results = result_data.get('results', [])
        logger.info(f"获取到 {len(results)} 个结果")
        
        for i, r in enumerate(results[:3]):
            logger.info(f"--- 结果 {i+1} ---")
            logger.info(f"标题: {r.get('title', 'N/A')[:100]}")
            logger.info(f"摘要: {r.get('summary', 'N/A')[:200]}")
            logger.info(f"URL: {r.get('url', 'N/A')}")
            logger.info(f"来源: {r.get('source', 'unknown')}")
        
        return result_data
        
    except Exception as e:
        logger.error(f"web_search 测试失败: {e}", exc_info=True)
        return None

def test_web_fetch(url):
    """测试网页抓取功能"""
    logger.info("="*60)
    logger.info("测试 web_fetch 函数")
    logger.info(f"URL: {url}")
    logger.info("="*60)
    
    try:
        from research_agent.search import web_fetch
        
        result = web_fetch(url)
        logger.info(f"抓取结果类型: {type(result)}")
        
        # 解析JSON结果
        result_data = json.loads(result)
        
        if 'error' in result_data:
            logger.error(f"抓取失败: {result_data.get('error')}, 消息: {result_data.get('message')}")
        else:
            content = result_data.get('content', '')
            logger.info(f"内容长度: {len(content)} 字符")
            logger.info(f"内容类型: {result_data.get('type', 'unknown')}")
            logger.info(f"内容预览: {content[:500]}...")
        
        return result_data
        
    except Exception as e:
        logger.error(f"web_fetch 测试失败: {e}", exc_info=True)
        return None

def main():
    logger.info("开始测试 search.py 的网页搜索和网页抓取功能")
    logger.info(f"日志文件: {log_file}")
    
    # 读取第一个问题
    question, expected_answer = load_first_question()
    if not question:
        logger.error("无法加载测试问题")
        return
    
    logger.info(f"测试问题: {question}")
    logger.info(f"预期答案: {expected_answer}")
    
    # 测试1: 网页搜索
    logger.info("\n" + "="*60)
    logger.info("【测试1】网页搜索功能测试")
    logger.info("="*60)
    
    search_result = test_web_search(question)
    
    # 测试2: 网页抓取
    if search_result and search_result.get('results'):
        results = search_result['results']
        if results:
            # 尝试抓取第一个结果的URL
            test_url = results[0].get('url')
            if test_url:
                logger.info("\n" + "="*60)
                logger.info("【测试2】网页抓取功能测试")
                logger.info("="*60)
                
                fetch_result = test_web_fetch(test_url)
    
    logger.info("\n" + "="*60)
    logger.info("测试完成")
    logger.info(f"日志已保存到: {log_file}")
    logger.info("="*60)

if __name__ == "__main__":
    main()
