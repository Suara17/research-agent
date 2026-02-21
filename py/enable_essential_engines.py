#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启用SearXNG中最重要的搜索引擎（精简版）
"""
import re

def enable_essential_engines():
    # 读取配置文件
    with open('E:/Research_Agent/searxng/settings.yml', 'r', encoding='utf-8') as f:
        content = f.read()

    # 定义要启用的核心搜索引擎（精简版）
    essential_engines = [
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
        'github', 'gitlab', 'stackoverflow', 'askubuntu', 'superuser',
        'reddit', 'hackernews',
        'imgur', 'flickr',
        'openstreetmap'
    ]

    # 逐个处理每个引擎
    for engine_name in essential_engines:
        # 创建正则表达式来匹配特定引擎的disabled设置
        pattern = rf"(-\s*name:\s*{re.escape(engine_name)}\s+.*?disabled:\s*)true"
        # 替换为 disabled: false
        content = re.sub(pattern, rf'\1false', content, flags=re.DOTALL)

    # 写回文件
    with open('E:/Research_Agent/searxng/settings.yml', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f'已启用 {len(essential_engines)} 个核心搜索引擎:')
    for engine in essential_engines:
        print(f'- {engine}')
    print()
    print('注意：已移除可能导致性能问题的过多引擎')

if __name__ == "__main__":
    enable_essential_engines()