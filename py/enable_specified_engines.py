#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启用指定的SearXNG搜索引擎
"""
import re

def enable_specified_engines():
    # 读取配置文件
    with open('E:/Research_Agent/searxng/settings.yml', 'r', encoding='utf-8') as f:
        content = f.read()

    # 定义要启用的指定搜索引擎
    specified_engines = [
        'arxiv',
        'wikipedia',
        'baidu',
        'baidu images',
        'baidu kaifa',
        'bilibili',
        'bing',
        'bing images',
        'bing news',
        'bing videos',
        'google',
        'google images',
        'google news',
        'google videos',
        'google scholar',
        'presearch',
        'presearch images',
        'presearch news',
        'presearch videos',
        'reddit',
        'pubmed',
        'sogou',
        'sogou images',
        'sogou videos',
        'sogou wechat',
        'duckduckgo',
        'duckduckgo images',
        'duckduckgo videos',
        'duckduckgo news',
        'wikidata',
        'wikinews',
        'wikiquote',
        'wikispecies',
        'wikiversity',
        'wikivoyage',
        'wiktionary',
        'wikisource',
        'wikicommons.images',
        'wikicommons.videos',
        'wikicommons.audio',
        'wikicommons.files'
    ]

    # 逐个处理每个引擎
    for engine_name in specified_engines:
        # 创建正则表达式来匹配特定引擎的disabled设置
        pattern = rf"(-\s*name:\s*{re.escape(engine_name)}\s+.*?disabled:\s*)true"
        # 替换为 disabled: false
        content = re.sub(pattern, rf'\1false', content, flags=re.DOTALL)

    # 写回文件
    with open('E:/Research_Agent/searxng/settings.yml', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f'已启用 {len(specified_engines)} 个指定的搜索引擎:')
    for engine in specified_engines:
        print(f'- {engine}')

if __name__ == "__main__":
    enable_specified_engines()