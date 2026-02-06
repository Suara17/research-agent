#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Source Verification Skill - 多源验证
验证关键事实的准确性，要求至少2个独立来源支持
"""

import os
import json
import sys

def main():
    try:
        # 优先从临时文件读取参数（新方案，避免转义问题）
        args_file = os.environ.get("SKILL_ARGS_FILE")

        if args_file and os.path.exists(args_file):
            print(f"[DEBUG] Reading args from file: {args_file}", file=sys.stderr)
            with open(args_file, 'r', encoding='utf-8') as f:
                args = json.load(f)
            print(f"[DEBUG] Loaded args from file successfully", file=sys.stderr)
        else:
            # 兼容旧方案：从环境变量读取
            args_json = os.environ.get("SKILL_ARGS", "{}")
            print(f"[DEBUG] SKILL_ARGS raw value: {repr(args_json)[:200]}", file=sys.stderr)

            args = {}
            if isinstance(args_json, dict):
                args = args_json
            elif isinstance(args_json, str):
                try:
                    args = json.loads(args_json)
                except json.JSONDecodeError as e:
                    print(f"[DEBUG] First parse failed: {e}, trying nested parse", file=sys.stderr)
                    try:
                        args = json.loads(json.loads(args_json))
                    except Exception:
                        if args_json.startswith('"') and args_json.endswith('"'):
                            args_json = args_json[1:-1]
                        args_json_unescaped = args_json.replace('\\"', '"').replace('\\\\', '\\')
                        args = json.loads(args_json_unescaped)

            print(f"[DEBUG] Parsed args successfully", file=sys.stderr)

        # 验证参数类型（修复：移除错误的类型检查）
        if not isinstance(args, dict):
            # 如果仍然是字符串，尝试再次解析
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except:
                    raise TypeError(f"Failed to parse args as JSON: {repr(args)[:200]}")
            else:
                raise TypeError(f"Expected dict, got {type(args).__name__}: {repr(args)[:100]}")

        # 提取参数
        claim = args.get("claim", "")
        answer = args.get("answer", "")
        entities = args.get("entities_to_verify", [])

        # 支持两种参数格式
        if not claim and not answer:
            print(json.dumps({
                "error": "claim or answer parameter is required",
                "usage": {
                    "method1": {"claim": "需要验证的声明"},
                    "method2": {
                        "answer": "候选答案",
                        "entities_to_verify": ["实体1", "实体2", "实体3"]
                    }
                }
            }, ensure_ascii=False))
            sys.exit(1)

        # 处理参数
        if claim:
            target = claim
        else:
            target = answer

        # 自动提取实体(如果未提供)
        if not entities and answer:
            # 简单的实体提取(可以改进)
            import re
            # 提取数字(年份、金额等)
            numbers = re.findall(r'\d{4}|\d+(?:\.\d+)?', answer)
            # 提取大写开头的词组(人名、地名等)
            proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', answer)
            # 提取中文实体
            chinese_entities = re.findall(r'[\u4e00-\u9fff]{2,}', answer)

            entities = list(set(numbers + proper_nouns + chinese_entities))[:5]

        # 生成验证查询
        verification_queries = []

        # 查询1: 直接验证声明
        query1 = ""
        if entities:
             # 使用第一个实体作为上下文（通常是主体）
             context = entities[0]
             # 如果上下文不在目标中，则组合查询
             if context not in target:
                 query1 = f'"{context}" "{target}" verify OR fact check'
             else:
                 query1 = f'"{target}" verify OR fact check'
        else:
             query1 = f'"{target}" verify OR fact check'

        verification_queries.append({
            "purpose": "直接验证声明",
            "query": query1,
            "expected": "找到至少2个独立来源确认"
        })

        # 查询2: 验证关键实体
        for entity in entities[:3]:
            verification_queries.append({
                "purpose": f"验证实体: {entity}",
                "query": f'"{entity}" site:edu OR site:org OR site:gov',
                "expected": "权威来源确认该实体"
            })

        # 查询3: 寻找权威来源
        query3 = ""
        if entities:
             context = entities[0]
             if context not in target:
                 query3 = f'"{context}" "{target}" site:edu OR site:gov'
             else:
                 query3 = f'"{target}" site:edu OR site:gov'
        else:
             query3 = f'{target} site:edu OR site:gov'

        verification_queries.append({
            "purpose": "寻找权威来源",
            "query": query3,
            "expected": "至少1个 .edu/.gov 来源支持"
        })

        # 查询4: 检查冲突信息 (反向验证)
        verification_queries.append({
            "purpose": "检查冲突信息/反向验证",
            "query": f'"{target}" controversy OR dispute OR incorrect OR debunked OR hoax',
            "expected": "无冲突信息,或冲突已被澄清"
        })

        # 查询5: 竞争性假设验证 (如果是 "唯一" 类的声明)
        if "first" in target.lower() or "invented" in target.lower() or "founder" in target.lower() or "best" in target.lower():
             verification_queries.append({
                "purpose": "竞争性假设验证",
                "query": f'"{target}" vs OR alternative OR other candidates',
                "expected": "确认没有更有力的竞争候选"
            })

        # 输出结果
        result = {
            "status": "success",
            "target_claim": target,
            "entities_to_verify": entities,
            "verification_queries": verification_queries,
            "next_actions": [
                "1. 依次执行上述验证查询 (使用 web_search)",
                "2. 对每个查询结果使用 web_fetch 读取全文",
                "3. 从每个来源提取支持/反对证据",
                "4. 统计来源数量和可信度",
                "5. 计算最终置信度 (需要 ≥2 个独立来源支持)"
            ],
            "confidence_formula": {
                "min_sources": 2,
                "source_weight": {
                    ".edu/.gov": 0.95,
                    "权威媒体": 0.85,
                    "Wikipedia": 0.80,
                    "博客/论坛": 0.40
                },
                "calculation": "平均来源可信度 × (实际来源数 / 最小来源数)"
            }
        }

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        error_result = {
            "error": str(e),
            "status": "failed",
            "traceback": str(e.__class__.__name__)
        }
        # 🔥 修复：错误也输出到 stdout，这样强制执行逻辑才能捕获
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
