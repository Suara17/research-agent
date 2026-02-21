#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
精确启用SearXNG中常用的搜索引擎
"""
import re

def enable_common_engines_precise():
    # 读取配置文件
    with open('E:/Research_Agent/searxng/settings.yml', 'r', encoding='utf-8') as f:
        content = f.read()

    # 定义要启用的常用搜索引擎
    common_engines = [
        'google', 'google images', 'google news', 'google videos', 'google scholar',
        'bing', 'bing images', 'bing news', 'bing videos',
        'duckduckgo', 'duckduckgo images', 'duckduckgo videos', 'duckduckgo news',
        'yandex', 'yandex images', 'yandex music',
        'yahoo', 'yahoo news',
        'wikipedia', 'wikidata', 'wikinews', 'wikiquote', 'wiktionary',
        'youtube', 'dailymotion', 'vimeo',
        'startpage', 'startpage news', 'startpage images',
        'brave', 'brave.images', 'brave.videos', 'brave.news',
        'qwant', 'qwant news', 'qwant images', 'qwant videos',
        'arxiv', 'pubmed', 'openstreetmap',
        'github', 'gitlab', 'stackoverflow', 'askubuntu', 'superuser',
        'reddit', 'lobste.rs', 'hackernews',
        'soundcloud', 'bandcamp', 'mixcloud',
        'imgur', 'flickr', 'deviantart',
        'pixabay', 'unsplash', 'openverse'
    ]

    # 分别处理每个引擎
    for engine_name in common_engines:
        # 创建正则表达式来匹配特定引擎的配置块
        # 匹配从 - name: [engine_name] 开始到下一个 - name: 或文件结尾的块
        pattern = rf"(- name: {re.escape(engine_name)}\s+.*?)(disabled:\s*true)"
        # 使用非贪婪匹配，确保只匹配到下一个引擎定义或文件结尾
        content = re.sub(pattern, 
                        lambda m: m.group(1) + 'disabled: false', 
                        content, 
                        flags=re.DOTALL)

    # 写回文件
    with open('E:/Research_Agent/searxng/settings.yml', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f'已尝试启用 {len(common_engines)} 个常用搜索引擎:')
    for engine in common_engines:
        print(f'- {engine}')

if __name__ == "__main__":
    enable_common_engines_precise()