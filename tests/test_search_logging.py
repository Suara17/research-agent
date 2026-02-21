"""
测试 search.py 的搜索和网页抓取功能
将结果保存到日志文件中
"""
import os
import sys
import json
import logging
from datetime import datetime

# 设置日志
log_filename = f"logs/test_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 第一个问题（来自 validation.jsonl）
FIRST_QUESTION = "在某一年，一位法国天文学家对一颗彗星的光谱进行了开创性观测，同年的一张太阳黑子照片后来在东亚某大都市的天文展览中展出。也正是在这一年，一位尚不满二十岁的南欧创业者，在家乡小镇创办了他的出版事业。十余年后，他将公司总部迁往了该国北部的商业中心。他所创立的这家出版公司的名字是什么？"

# 简化版本 - 搜索关键信息
SIMPLIFIED_QUESTION = "法国天文学家 彗星光谱观测 1859年 太阳黑子照片 出版公司 南欧创业者 20岁创办 总部迁往北部商业中心"

# 英文搜索词
ENGLISH_QUESTION = "French astronomer comet spectral observation 1859 sunspot photo exhibition East Asia publishing company founded by young Italian entrepreneur moved to northern city"

EXPECTED_ANSWER = "阿诺尔多·蒙达多利出版社"

def main():
    logger.info("=" * 80)
    logger.info("开始测试 search.py 搜索和网页抓取功能")
    logger.info("=" * 80)
    
    # 记录测试问题
    logger.info(f"测试问题: {FIRST_QUESTION}")
    logger.info(f"简化问题: {SIMPLIFIED_QUESTION}")
    logger.info(f"英文问题: {ENGLISH_QUESTION}")
    logger.info(f"预期答案: {EXPECTED_ANSWER}")
    logger.info("-" * 80)
    
    try:
        # 导入 search 模块
        logger.info("导入 research_agent.search 模块...")
        from research_agent import search
        
        # 测试多个查询
        test_queries = [
            ("原始问题", FIRST_QUESTION),
            ("简化问题", SIMPLIFIED_QUESTION),
            ("英文问题", ENGLISH_QUESTION),
        ]
        
        all_search_results = {}
        
        for query_name, query in test_queries:
            logger.info("\n" + "=" * 80)
            logger.info(f">>> 测试查询: {query_name}")
            logger.info(f">>> 查询内容: {query}")
            logger.info("=" * 80)
            
            search_result = search.web_search(query, top_k=5)
            
            try:
                search_data = json.loads(search_result)
                logger.info(f"搜索结果来源: {search_data.get('source', 'unknown')}")
                logger.info(f"使用的提供商数量: {search_data.get('providers_used', 0)}")
                
                results = search_data.get('results', [])
                logger.info(f"获取到 {len(results)} 个搜索结果")
                
                all_search_results[query_name] = {
                    'query': query,
                    'source': search_data.get('source', 'unknown'),
                    'results': results
                }
                
                # 记录每个搜索结果
                for i, result in enumerate(results):
                    logger.info(f"\n--- 搜索结果 {i+1} ---")
                    logger.info(f"标题: {result.get('title', 'N/A')}")
                    summary = result.get('summary', 'N/A')
                    if summary and len(summary) > 100:
                        summary = summary[:100] + "..."
                    logger.info(f"摘要: {summary}")
                    logger.info(f"URL: {result.get('url', 'N/A')}")
                    logger.info(f"来源: {result.get('source', 'N/A')}")
                    logger.info(f"评分: {result.get('score', 'N/A')}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"解析搜索结果失败: {e}")
                logger.error(f"原始结果: {search_result[:500]}...")
        
        # 测试网页抓取 - 使用第二个查询的有效URL
        logger.info("\n" + "=" * 80)
        logger.info(">>> 测试网页抓取功能")
        logger.info("=" * 80)
        
        # 尝试找到一个有效的URL进行抓取
        test_url = None
        for query_name, data in all_search_results.items():
            for result in data.get('results', []):
                url = result.get('url', '')
                if url and url.startswith('http') and 'baidu.com/link' not in url:
                    test_url = url
                    logger.info(f"使用URL进行抓取测试: {test_url}")
                    break
            if test_url:
                break
        
        if test_url:
            logger.info(f"\n>>> 开始抓取: {test_url}")
            fetch_result = search.web_fetch(test_url)
            
            try:
                fetch_data = json.loads(fetch_result)
                logger.info(f"抓取结果类型: {fetch_data.get('type', 'unknown')}")
                
                content = fetch_data.get('content', '')
                if content:
                    logger.info(f"抓取内容长度: {len(content)} 字符")
                    logger.info(f"抓取内容预览:\n{content[:800]}...")
                else:
                    logger.warning("抓取内容为空")
                    
                if 'error' in fetch_data:
                    logger.error(f"抓取错误: {fetch_data.get('error')}")
                    logger.error(f"错误信息: {fetch_data.get('message', 'N/A')}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"解析抓取结果失败: {e}")
                logger.error(f"原始结果: {fetch_result[:500]}...")
        else:
            logger.warning("没有找到有效的URL进行抓取测试")
            
        # 总结
        logger.info("\n" + "=" * 80)
        logger.info("测试完成 - 总结")
        logger.info("=" * 80)
        
        for query_name, data in all_search_results.items():
            logger.info(f"\n查询: {query_name}")
            logger.info(f"  来源: {data.get('source', 'unknown')}")
            logger.info(f"  结果数: {len(data.get('results', []))}")
            
    except Exception as e:
        logger.exception(f"测试过程中发生错误: {e}")
        
    logger.info("\n" + "=" * 80)
    logger.info(f"日志文件保存至: {log_filename}")
    logger.info("=" * 80)

if __name__ == "__main__":
    main()
