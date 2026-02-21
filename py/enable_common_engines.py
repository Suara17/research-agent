#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启用SearXNG中常用的搜索引擎
"""
import re

def enable_common_engines():
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

    # 对每个引擎进行处理
    lines = content.split('\n')
    updated_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        updated_lines.append(line)
        
        # 检查是否是引擎名称行
        name_match = re.search(r'^\s*- name:\s*(.+)', line)
        if name_match:
            engine_name = name_match.group(1).strip(' \"\'')
            
            # 如果是常用引擎，查找并修改disabled行
            if engine_name.lower() in common_engines:
                # 在接下来的几行中查找disabled设置
                j = i + 1
                while j < len(lines) and j < i + 10:  # 查找接下来最多10行
                    next_line = lines[j]
                    if re.search(r'^\s*- name:', next_line):  # 下一个引擎开始
                        break
                    if 'disabled:' in next_line:
                        # 修改disabled为false
                        updated_lines[-1] = re.sub(r'disabled:\s*true', 'disabled: false', next_line)
                        break
                    j += 1
        
        i += 1

    # 写回文件
    with open('E:/Research_Agent/searxng/settings.yml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(updated_lines))
    
    print(f'已尝试启用 {len(common_engines)} 个常用搜索引擎:')
    for engine in common_engines:
        print(f'- {engine}')

if __name__ == "__main__":
    enable_common_engines()