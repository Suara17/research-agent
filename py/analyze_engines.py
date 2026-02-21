#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析SearXNG配置文件中的搜索引擎
"""
import re

def analyze_engines():
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

    # Count enabled and disabled engines
    enabled_engines = [name for name, config in engines if not config['disabled']]
    disabled_engines = [name for name, config in engines if config['disabled']]

    print(f'SearXNG 引擎总数: {len(engines)}')
    print(f'启用的引擎数量: {len(enabled_engines)}')
    print(f'禁用的引擎数量: {len(disabled_engines)}')
    print()
    print('启用的搜索引擎:')
    for engine in enabled_engines:
        print(f'- {engine}')
    print()
    print('禁用的搜索引擎 (部分示例):')
    for i, engine in enumerate(disabled_engines[:10]):
        print(f'- {engine}')
    if len(disabled_engines) > 10:
        print(f'... 还有 {len(disabled_engines)-10} 个禁用的引擎')

if __name__ == "__main__":
    analyze_engines()