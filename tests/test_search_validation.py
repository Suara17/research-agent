#!/usr/bin/env python3
"""
测试 research_agent/search.py 的搜索和网页抓取功能
使用 validation.jsonl 的第一个问题
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
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# 第一个问题（从 validation.jsonl 获取）
TEST_QUESTION = "在某一年，一位法国天文学家对一颗彗星的光谱进行了开创性观测，同年的一张太阳黑子照片后来在东亚某大都市的天文展览中展出。也正是在这一年，一位尚不满二十岁的南欧创业者，在家乡小镇创办了他的出版事业。十余年后，他将公司总部迁往了该国北部的商业中心。他所创立的这家出版公司的名字是什么？"

# 备用测试问题（英文）
TEST_QUESTION_EN = "What is the name of the significant military operation in which the first Hispanic to attain the rank of Master Gunnery Sergeant in their Military Occupational Specialty served?"

def test_search():
    """测试搜索功能"""
    logger.info("="*60)
    logger.info("开始测试搜索功能")
    logger.info(f"测试问题: {TEST_QUESTION}")
    logger.info("="*60)
    
    try:
        from research_agent.search import web_search
        
        # 测试中文搜索
        logger.info("\n>>> 测试中文搜索...")
        result = web_search(TEST_QUESTION, top_k=5)
        
        # 解析结果
        try:
            data = json.loads(result)
            logger.info(f"搜索结果来源: {data.get('source', 'unknown')}")
            logger.info(f"搜索到 {len(data.get('results', []))} 条结果")
            
            # 打印搜索结果摘要
            for i, r in enumerate(data.get('results', [])[:3], 1):
                logger.info(f"\n--- 搜索结果 {i} ---")
                logger.info(f"标题: {r.get('title', '')}")
                logger.info(f"摘要: {r.get('summary', '')[:200]}...")
                logger.info(f"URL: {r.get('url', '')}")
                logger.info(f"来源: {r.get('source', '')}")
            
            # 保存完整结果
            with open(log_filename.replace('.log', '_search_results.json'), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"搜索结果已保存")
            
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"解析搜索结果失败: {e}")
            logger.error(f"原始结果: {result[:500]}...")
            return None
            
    except Exception as e:
        logger.error(f"搜索失败: {e}", exc_info=True)
        return None


def test_web_fetch():
    """测试网页抓取功能"""
    logger.info("\n" + "="*60)
    logger.info("开始测试网页抓取功能")
    logger.info("="*60)
    
    try:
        from research_agent.search import web_search, web_fetch
        
        # 先搜索获取URL
        logger.info(">>> 先执行搜索获取测试URL...")
        search_result = web_search(TEST_QUESTION, top_k=3)
        data = json.loads(search_result)
        
        results = data.get('results', [])
        if not results:
            logger.error("没有搜索结果可供测试")
            return None
        
        # 测试抓取前3个URL
        fetch_results = []
        for i, r in enumerate(results[:3], 1):
            url = r.get('url', '')
            title = r.get('title', '')
            
            if not url:
                continue
                
            logger.info(f"\n--- 抓取测试 {i}: {title} ---")
            logger.info(f"URL: {url}")
            
            try:
                fetch_result = web_fetch(url)
                fetch_data = json.loads(fetch_result)
                
                content_type = fetch_data.get('type', 'unknown')
                content_preview = fetch_data.get('content', '')[:500]
                
                logger.info(f"抓取成功 - 类型: {content_type}")
                logger.info(f"内容预览: {content_preview}...")
                
                fetch_results.append({
                    'url': url,
                    'title': title,
                    'type': content_type,
                    'content_length': len(fetch_data.get('content', '')),
                    'success': 'error' not in fetch_data
                })
                
            except Exception as e:
                logger.error(f"抓取失败: {e}")
                fetch_results.append({
                    'url': url,
                    'title': title,
                    'error': str(e),
                    'success': False
                })
        
        # 保存抓取结果
        with open(log_filename.replace('.log', '_fetch_results.json'), 'w', encoding='utf-8') as f:
            json.dump(fetch_results, f, ensure_ascii=False, indent=2)
        logger.info(f"抓取结果已保存")
        
        return fetch_results
        
    except Exception as e:
        logger.error(f"网页抓取测试失败: {e}", exc_info=True)
        return None


def test_english_search():
    """测试英文搜索"""
    logger.info("\n" + "="*60)
    logger.info("开始测试英文搜索")
    logger.info(f"测试问题: {TEST_QUESTION_EN}")
    logger.info("="*60)
    
    try:
        from research_agent.search import web_search
        
        result = web_search(TEST_QUESTION_EN, top_k=5)
        data = json.loads(result)
        
        logger.info(f"搜索结果来源: {data.get('source', 'unknown')}")
        logger.info(f"搜索到 {len(data.get('results', []))} 条结果")
        
        for i, r in enumerate(data.get('results', [])[:3], 1):
            logger.info(f"\n--- 搜索结果 {i} ---")
            logger.info(f"标题: {r.get('title', '')}")
            logger.info(f"摘要: {r.get('summary', '')[:200]}...")
            logger.info(f"URL: {r.get('url', '')}")
        
        return data
        
    except Exception as e:
        logger.error(f"英文搜索测试失败: {e}", exc_info=True)
        return None


def main():
    """主函数"""
    logger.info("="*60)
    logger.info("research_agent/search.py 测试开始")
    logger.info(f"日志文件: {log_filename}")
    logger.info("="*60)
    
    # 测试搜索功能
    search_data = test_search()
    
    # 测试网页抓取功能
    fetch_data = test_web_fetch()
    
    # 测试英文搜索
    english_search_data = test_english_search()
    
    # 总结
    logger.info("\n" + "="*60)
    logger.info("测试总结")
    logger.info("="*60)
    logger.info(f"中文搜索: {'成功' if search_data else '失败'}")
    logger.info(f"网页抓取: {'成功' if fetch_data else '失败'}")
    logger.info(f"英文搜索: {'成功' if english_search_data else '失败'}")
    logger.info(f"日志文件: {log_filename}")
    
    return {
        'search_success': search_data is not None,
        'fetch_success': fetch_data is not None,
        'english_search_success': english_search_data is not None
    }


if __name__ == "__main__":
    main()
