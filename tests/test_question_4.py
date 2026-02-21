"""
测试验证集第4个问题，保存所有搜索和抓取日志
"""
import os
import json
import logging
from datetime import datetime

# 设置日志
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f"test_q4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 配置日志格式
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 第4个问题
QUESTION_4 = "Which protein was identified as an interactor of PAD4 yet shows no evidence of interacting with ADF3 or contributing to powdery mildew defense or EHM targeting?"

# 保存完整日志数据
full_log_data = {
    "question": QUESTION_4,
    "timestamp": datetime.now().isoformat(),
    "search_results": [],
    "fetch_results": [],
    "errors": []
}

def test_search_and_fetch():
    """测试搜索和抓取功能"""
    try:
        logger.info("="*80)
        logger.info(f"测试问题: {QUESTION_4}")
        logger.info("="*80)
        
        # 导入搜索模块
        from research_agent.search import web_search, web_fetch
        
        # 1. 执行搜索
        logger.info("\n[1] 开始执行搜索...")
        search_result = web_search(QUESTION_4, top_k=5)
        
        # 解析搜索结果
        search_data = json.loads(search_result)
        logger.info(f"搜索结果: {json.dumps(search_data, ensure_ascii=False, indent=2)[:2000]}")
        
        # 保存搜索结果
        full_log_data["search_results"] = search_data
        
        # 提取搜索结果中的URL
        urls_to_fetch = []
        if "results" in search_data:
            for i, result in enumerate(search_data["results"]):
                url = result.get("url", "")
                title = result.get("title", "")
                summary = result.get("summary", "")[:200]
                logger.info(f"搜索结果 {i+1}: {title}")
                logger.info(f"  URL: {url}")
                logger.info(f"  摘要: {summary}...")
                if url:
                    urls_to_fetch.append(url)
        
        logger.info(f"\n[2] 共找到 {len(urls_to_fetch)} 个URL需要抓取")
        
        # 2. 对每个URL执行抓取
        for i, url in enumerate(urls_to_fetch):
            logger.info(f"\n[2.{i+1}] 抓取 URL: {url}")
            try:
                fetch_result = web_fetch(url)
                fetch_data = json.loads(fetch_result)
                
                content = fetch_data.get("content", "")[:1000]  # 截取前1000字符
                fetch_type = fetch_data.get("type", "unknown")
                
                logger.info(f"  抓取类型: {fetch_type}")
                logger.info(f"  内容长度: {len(fetch_data.get('content', ''))} 字符")
                logger.info(f"  内容预览: {content[:500]}...")
                
                # 保存抓取结果
                full_log_data["fetch_results"].append({
                    "url": url,
                    "type": fetch_type,
                    "content_length": len(fetch_data.get("content", "")),
                    "content_preview": content[:500]
                })
                
            except Exception as e:
                logger.error(f"  抓取失败: {e}")
                full_log_data["errors"].append({
                    "url": url,
                    "error": str(e)
                })
        
        # 3. 保存完整日志到JSON文件
        log_json_file = os.path.join(log_dir, f"test_q4_full_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(log_json_file, 'w', encoding='utf-8') as f:
            json.dump(full_log_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"\n[3] 完整日志已保存到: {log_json_file}")
        logger.info(f"日志文件路径: {log_file}")
        
        return full_log_data
        
    except Exception as e:
        logger.error(f"测试执行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        full_log_data["errors"].append({"error": str(e), "traceback": traceback.format_exc()})
        return full_log_data

if __name__ == "__main__":
    logger.info("开始测试验证集第4个问题...")
    result = test_search_and_fetch()
    logger.info(f"\n测试完成! 共抓取 {len(result.get('fetch_results', []))} 个页面")
