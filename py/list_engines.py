#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
列出SearXNG配置文件中的所有搜索引擎，并标识出常用的那些
"""
import re

def list_all_engines():
    # Read the settings file
    with open('E:/Research_Agent/searxng/settings.yml', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all engines sections
    engines_section = False
    engines_text = ''
    lines = content.split('\n')
    for line in lines:
        if line.strip() == 'engines:':
            engines_section = True
            continue
        if engines_section:
            if re.match(r'^\w', line) and not line.startswith('  '):  # New top-level section
                break
            engines_text += line + '\n'

    # Parse engine configurations
    engines = []
    current_engine = None
    current_name = None

    for line in engines_text.split('\n'):
        name_match = re.search(r'^\s*- name:\s*(.+)', line)
        if name_match:
            if current_engine and current_name:
                engines.append((current_name, current_engine))
            current_name = name_match.group(1).strip(' \"\'')
            current_engine = {'name': current_name, 'disabled': True}  # 默认禁用
        
        if 'disabled:' in line and current_engine:
            disabled_value = line.split('disabled:')[-1].strip()
            current_engine['disabled'] = disabled_value.lower() == 'true'

    if current_engine and current_name:
        engines.append((current_name, current_engine))

    # 常用搜索引擎列表
    common_engines = {
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
    }

    print(f'SearXNG 引擎总数: {len(engines)}')
    print()
    print('所有搜索引擎列表 (按字母顺序排列):')
    print('=' * 50)
    
    # 按字母顺序排序
    sorted_engines = sorted(engines, key=lambda x: x[0].lower())
    
    for name, config in sorted_engines:
        status = "DISABLED" if config['disabled'] else "ENABLED "
        common_indicator = " [常用]" if name.lower() in common_engines else ""
        print(f'{status} - {name}{common_indicator}')

    print()
    print('常用搜索引擎列表 (推荐启用):')
    print('=' * 50)
    
    common_found = []
    for name, config in sorted_engines:
        if name.lower() in common_engines:
            status = "DISABLED" if config['disabled'] else "ENABLED "
            common_found.append((name, status))
    
    for name, status in common_found:
        print(f'{status} - {name}')

    print()
    print('常用搜索引擎统计:')
    print(f'- 总共识别出 {len(common_found)} 个常用引擎')
    print(f'- 其中已启用: {len([e for e in common_found if e[1] == "ENABLED"])} 个')
    print(f'- 其中已禁用: {len([e for e in common_found if e[1] == "DISABLED"])} 个')

if __name__ == "__main__":
    list_all_engines()