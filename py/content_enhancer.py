#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网页内容抓取和总结模块
"""
import asyncio
import re
from typing import List, Dict, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests
from research_agent.utils import get_llm_client

def extract_content_from_html(html: str, url: str) -> str:
    """
    从HTML中提取主要内容
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # 移除不必要的标签
    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', '广告', 'advertisement']):
        tag.decompose()
    
    # 尝试获取特定区域的内容
    content_selectors = [
        'article', '.content', '#content', '.post', '.article',
        '.main-content', '[role="main"]', '.entry-content', '.post-content'
    ]
    
    for selector in content_selectors:
        content_elem = soup.select_one(selector)
        if content_elem:
            return content_elem.get_text(strip=True, separator='\n')
    
    # 如果没有找到特定区域，返回body内容
    body = soup.find('body')
    if body:
        return body.get_text(strip=True, separator='\n')
    
    # 否则返回整个文档的文本
    return soup.get_text(strip=True, separator='\n')

def summarize_content(content: str, query: str, max_length: int = 1000) -> str:
    """
    对网页内容进行总结 - 优先使用非LLM方法以减少TOKEN成本
    """
    if len(content) <= max_length:
        return content

    # 截取内容的开头部分，保留最重要的信息
    truncated_content = content[:max_length*2]  # 先取两倍长度，以便保留更多上下文

    # 首先尝试使用非LLM方法进行总结（成本更低）
    try:
        # 使用关键句子提取方法
        key_sentences_summary = extract_key_sentences(truncated_content, max_length=max_length, num_sentences=6)
        
        if len(key_sentences_summary) > 0:
            return key_sentences_summary
            
        # 如果关键句子提取失败，使用顶部内容提取方法
        top_content_summary = extract_top_content(truncated_content, max_length=max_length)
        
        if len(top_content_summary) > 0:
            return top_content_summary
            
    except Exception as e:
        print(f"[Content Summarizer] Non-LLM summarization failed: {e}")
        # 如果非LLM方法失败，继续尝试LLM方法

    # 如果非LLM方法不可用或失败，则使用LLM进行总结
    try:
        client = get_llm_client()
        prompt = f"""
        请对以下网页内容进行简洁准确的总结，重点关注与查询"{query}"相关的信息：

        网页内容：
        {truncated_content}

        请提供一段不超过{max_length}字符的总结，突出关键信息和要点。
        """

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[
                {"role": "system", "content": "你是一个专业的网页内容总结助手，能够提取关键信息并提供简洁准确的总结。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=max_length
        )

        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(f"[Content Summarizer] LLM summarization failed: {e}")
        # 如果所有方法都失败，返回截断的内容
        return truncated_content[:max_length] + "..."


def extract_key_sentences(content: str, max_length: int = 2000, num_sentences: int = 8) -> str:
    """
    不使用模型的关键句子提取方法
    基于位置优先和关键词密度的方法提取最重要的句子
    """
    import re
    
    # 按句子分割文本
    sentences = re.split(r'[。！？!?]+', content)
    
    # 清理句子，去除空白
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) <= num_sentences:
        result = ''.join([s + '。' for s in sentences])
        return result[:max_length]
    
    # 位置权重：越靠前的句子权重越高
    weighted_sentences = []
    for i, sentence in enumerate(sentences):
        # 位置权重：前面的句子权重更高
        position_weight = max(0.3, 1.0 - i * 0.02)
        
        # 长度过滤：太短的句子可能信息量不够
        length_score = min(1.0, len(sentence) / 20.0)
        
        # 关键词权重：包含重要词汇的句子权重更高
        keyword_score = 0
        keywords = ['重要', '主要', '关键', '核心', '首先', '其次', '最后', '因此', '所以', '但是', '然而', '总之']
        for keyword in keywords:
            if keyword in sentence:
                keyword_score += 0.2
        
        # 计算总权重
        total_weight = (position_weight + length_score + keyword_score) / 3
        weighted_sentences.append((sentence, total_weight, i))
    
    # 按权重排序，选择权重最高的句子
    weighted_sentences.sort(key=lambda x: x[1], reverse=True)
    selected_sentences = weighted_sentences[:num_sentences]
    
    # 按原文顺序排列选中的句子
    selected_sentences.sort(key=lambda x: x[2])
    
    # 组合结果
    result = ''.join([s[0] + '。' for s in selected_sentences])
    
    # 限制最大长度
    if len(result) > max_length:
        result = result[:max_length]
        # 确保以句号结尾
        if not result[-1] in ['。', '！', '？', '.', '!', '?']:
            result += '...'
    
    return result


def extract_top_content(content: str, max_length: int = 2000) -> str:
    """
    提取网页内容的顶部重要部分，不过滤任何内容
    """
    # 直接截取内容的前max_length个字符
    if len(content) <= max_length:
        return content
    
    # 尝试在句子边界处截断，避免截断句子
    truncated = content[:max_length]
    
    # 寻找最后一个句号，避免截断句子
    last_sentence_end = max(
        truncated.rfind('。'),
        truncated.rfind('！'),
        truncated.rfind('？'),
        truncated.rfind('.'),
        truncated.rfind('!'),
        truncated.rfind('?')
    )
    
    if last_sentence_end > max_length * 0.8:  # 确保截断位置不太靠前
        truncated = truncated[:last_sentence_end + 1]
    
    if len(truncated) < len(content):
        truncated += "..."
    
    return truncated

async def fetch_and_summarize_url(url: str, query: str) -> Optional[str]:
    """
    异步抓取URL并生成内容总结
    """
    try:
        # 发送请求获取网页内容
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # 提取内容
        content = extract_content_from_html(response.text, url)
        
        # 总结内容
        summary = summarize_content(content, query)
        
        return summary
    except Exception as e:
        print(f"[Content Fetcher] Failed to fetch {url}: {e}")
        return None

async def enhance_search_results_with_content(results: List[Dict], query: str, max_concurrent: int = 3) -> List[Dict]:
    """
    为搜索结果添加网页内容总结
    """
    if not results:
        return results
    
    enhanced_results = []
    
    # 限制并发数量，避免对网站造成过大压力
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_result(result):
        async with semaphore:
            url = result.get('url')
            if not url:
                return result
            
            content_summary = await fetch_and_summarize_url(url, query)
            if content_summary:
                # 创建增强版结果
                enhanced_result = result.copy()
                enhanced_result['detailed_content'] = content_summary
                enhanced_result['enhanced_summary'] = result.get('summary', '') + "\n\n详细内容摘要：" + content_summary[:300] + "..."
                return enhanced_result
            
            return result
    
    # 并发处理所有结果
    tasks = [process_result(result) for result in results]
    enhanced_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 过理异常
    final_results = []
    for i, item in enumerate(enhanced_results):
        if isinstance(item, Exception):
            print(f"[Enhancer] Error processing result {i}: {item}")
            final_results.append(results[i])  # 回退到原始结果
        else:
            final_results.append(item)
    
    return final_results

def sync_enhance_search_results_with_content(results: List[Dict], query: str) -> List[Dict]:
    """
    同步版本的搜索结果增强函数
    """
    import concurrent.futures
    import threading
    import time
    
    def fetch_content_sync(result):
        """同步获取单个结果的内容"""
        url = result.get('url')
        if not url:
            return result
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            content = extract_content_from_html(response.text, url)
            summary = summarize_content(content, query)
            
            enhanced_result = result.copy()
            enhanced_result['detailed_content'] = summary
            enhanced_result['enhanced_summary'] = result.get('summary', '') + "\n\n详细内容摘要：" + summary[:300] + "..."
            return enhanced_result
        except Exception as e:
            print(f"[Sync Content Fetcher] Failed to fetch {url}: {e}")
            return result
    
    # 使用线程池并行处理
    enhanced_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # 提交所有任务
        future_to_result = {executor.submit(fetch_content_sync, result): result for result in results}
        
        # 收集结果
        for future in concurrent.futures.as_completed(future_to_result):
            try:
                enhanced_result = future.result()
                enhanced_results.append(enhanced_result)
            except Exception as e:
                print(f"[Sync Enhancer] Error processing result: {e}")
                # 添加原始结果
                original_result = future_to_result[future]
                enhanced_results.append(original_result)
    
    # 按原始顺序排序
    result_url_map = {res.get('url'): res for res in enhanced_results}
    ordered_results = []
    for original_result in results:
        url = original_result.get('url')
        if url and url in result_url_map:
            ordered_results.append(result_url_map[url])
        else:
            ordered_results.append(original_result)
    
    return ordered_results

# 示例使用
if __name__ == "__main__":
    # 示例结果
    sample_results = [
        {
            "title": "人工智能发展趋势分析",
            "summary": "人工智能在2024年的发展趋势概览...",
            "url": "https://example.com/ai-trends",
            "source": "google"
        },
        {
            "title": "机器学习最新进展",
            "summary": "机器学习领域的最新研究成果...",
            "url": "https://example.com/ml-progress", 
            "source": "bing"
        }
    ]
    
    print("原始结果:")
    for i, result in enumerate(sample_results):
        print(f"{i+1}. {result['title']}")
        print(f"   摘要: {result['summary']}")
        print(f"   链接: {result['url']}")
        print()
    
    print("增强后的结果示例 (概念):")
    print("- 添加详细内容摘要字段")
    print("- 提供更丰富的上下文信息") 
    print("- 保留关键细节和数据")