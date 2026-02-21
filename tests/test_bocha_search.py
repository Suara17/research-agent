"""
测试博查(Bocha) API 搜索功能
API-KEY: sk-c5947f46bbde409ea6d8b200b954991c
"""
import os
import sys
import json
import logging
import urllib.request
import ssl
from datetime import datetime

# 设置日志
log_filename = f"logs/test_bocha_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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

# 博查API配置
BOCHA_API_KEY = "sk-c5947f46bbde409ea6d8b200b954991c"
BOCHA_API_URL = "https://api.bochaai.com/v1/web-search"

# 测试问题
FIRST_QUESTION = "在某一年，一位法国天文学家对一颗彗星的光谱进行了开创性观测，同年的一张太阳黑子照片后来在东亚某大都市的天文展览中展出。也正是在这一年，一位尚不满二十岁的南欧创业者，在家乡小镇创办了他的出版事业。十余年后，他将公司总部迁往了该国北部的商业中心。他所创立的这家出版公司的名字是什么？"

SIMPLIFIED_QUESTION = "法国天文学家 彗星光谱观测 1859年 太阳黑子照片 出版公司 南欧创业者 20岁创办 总部迁往北部商业中心"

ENGLISH_QUESTION = "French astronomer comet spectral observation 1859 sunspot photo exhibition East Asia publishing company founded by young Italian entrepreneur moved to northern city"

EXPECTED_ANSWER = "阿诺尔多·蒙达多利出版社"


def search_bocha(query: str, count: int = 5):
    """使用博查API进行搜索 - 使用urllib"""
    import urllib.request
    import json
    
    # 创建不验证SSL的上下文
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    data = {
        "query": query,
        "count": count,
        "page": 1,
        "webPages": True,
        "news": False,
        "relatedLinks": False
    }
    
    json_data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(
        BOCHA_API_URL,
        data=json_data,
        headers={
            "Authorization": f"Bearer {BOCHA_API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
            result = response.read().decode('utf-8')
            return json.loads(result)
    except Exception as e:
        logger.error(f"博查API请求失败: {e}")
        
        # 尝试不使用SSL验证
        try:
            import urllib.error
            # 使用httpx作为备用
            try:
                import httpx
                
                headers = {
                    "Authorization": f"Bearer {BOCHA_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "query": query,
                    "count": count,
                    "page": 1,
                    "webPages": True,
                    "news": False,
                    "relatedLinks": False
                }
                
                response = httpx.post(
                    BOCHA_API_URL, 
                    headers=headers, 
                    json=data, 
                    timeout=30,
                    verify=False
                )
                return response.json()
            except ImportError:
                pass
                
        except Exception as e2:
            logger.error(f"备用方法也失败: {e2}")
            
        return None


def main():
    logger.info("=" * 80)
    logger.info("开始测试博查(Bocha) API 搜索功能")
    logger.info("=" * 80)
    
    # 记录测试问题
    logger.info(f"测试问题: {FIRST_QUESTION}")
    logger.info(f"简化问题: {SIMPLIFIED_QUESTION}")
    logger.info(f"英文问题: {ENGLISH_QUESTION}")
    logger.info(f"预期答案: {EXPECTED_ANSWER}")
    logger.info("-" * 80)
    
    # 测试多个查询
    test_queries = [
        ("原始问题", FIRST_QUESTION),
        ("简化问题", SIMPLIFIED_QUESTION),
        ("英文问题", ENGLISH_QUESTION),
    ]
    
    all_results = {}
    
    for query_name, query in test_queries:
        logger.info("\n" + "=" * 80)
        logger.info(f">>> 测试查询: {query_name}")
        logger.info(f">>> 查询内容: {query}")
        logger.info("=" * 80)
        
        result = search_bocha(query, count=5)
        
        if result:
            logger.info(f"API响应: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}...")
            
            # 解析结果
            web_pages = result.get("data", {}).get("webPages", {}).get("value", [])
            
            if web_pages:
                logger.info(f"获取到 {len(web_pages)} 个搜索结果")
                
                all_results[query_name] = {
                    'query': query,
                    'count': len(web_pages),
                    'results': web_pages
                }
                
                for i, item in enumerate(web_pages):
                    logger.info(f"\n--- 搜索结果 {i+1} ---")
                    logger.info(f"标题: {item.get('name', 'N/A')}")
                    logger.info(f"摘要: {item.get('snippet', 'N/A')[:200]}...")
                    logger.info(f"URL: {item.get('url', 'N/A')}")
            else:
                logger.warning("未获取到搜索结果")
                all_results[query_name] = {
                    'query': query,
                    'count': 0,
                    'results': []
                }
        else:
            logger.error("搜索请求失败")
            all_results[query_name] = {
                'query': query,
                'count': 0,
                'results': []
            }
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("测试完成 - 总结")
    logger.info("=" * 80)
    
    for query_name, data in all_results.items():
        logger.info(f"\n查询: {query_name}")
        logger.info(f"  结果数: {data.get('count', 0)}")
        if data.get('results'):
            logger.info(f"  第一个结果标题: {data['results'][0].get('name', 'N/A')}")
    
    logger.info(f"\n日志文件保存至: {log_filename}")


if __name__ == "__main__":
    main()
