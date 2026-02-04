#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deep Research Skill - 深度研究
多步骤深度研究,适用于复杂问题
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
        query = args.get("query", "")
        depth = args.get("depth", 3)
        focus_areas = args.get("focus_areas", [])

        if not query:
            print(json.dumps({
                "error": "query parameter is required",
                "usage": {
                    "query": "研究问题",
                    "depth": "研究深度 (1-5, 默认3)",
                    "focus_areas": ["可选的重点研究领域"]
                }
            }, ensure_ascii=False))
            sys.exit(1)

        # 根据深度生成研究计划
        research_steps = []

        # 第1步: 初始搜索
        research_steps.append({
            "step": 1,
            "phase": "初始探索",
            "actions": [
                {
                    "action": "web_search",
                    "query": f'"{query}" overview',
                    "purpose": "获取问题概览"
                },
                {
                    "action": "web_search",
                    "query": f'"{query}" site:edu OR site:org',
                    "purpose": "寻找权威来源"
                }
            ],
            "expected_output": "识别3-5个高质量信息源"
        })

        # 第2步: 深度阅读
        research_steps.append({
            "step": 2,
            "phase": "深度阅读",
            "actions": [
                {
                    "action": "web_fetch",
                    "target": "第1步中识别的每个URL",
                    "purpose": "提取详细信息"
                }
            ],
            "expected_output": "核心事实和关键细节"
        })

        # 第3步: 补充研究 (如果 depth >= 3)
        if depth >= 3:
            research_steps.append({
                "step": 3,
                "phase": "补充验证",
                "actions": [
                    {
                        "action": "multi-source-verify",
                        "target": "第2步提取的关键事实",
                        "purpose": "多源验证准确性"
                    },
                    {
                        "action": "web_search",
                        "query": f'"{query}" latest research OR recent developments',
                        "purpose": "寻找最新进展"
                    }
                ],
                "expected_output": "验证的事实 + 最新信息"
            })

        # 第4步: 深度探究 (如果 depth >= 4)
        if depth >= 4:
            research_steps.append({
                "step": 4,
                "phase": "深度探究",
                "actions": [
                    {
                        "action": "web_search",
                        "query": f'"{query}" case study OR example',
                        "purpose": "寻找具体案例"
                    },
                    {
                        "action": "web_search",
                        "query": f'"{query}" criticism OR limitations',
                        "purpose": "了解局限性和批评"
                    }
                ],
                "expected_output": "全面理解(包括正反面)"
            })

        # 第5步: 综合分析 (如果 depth == 5)
        if depth >= 5:
            research_steps.append({
                "step": 5,
                "phase": "综合分析",
                "actions": [
                    {
                        "action": "chain-of-verification",
                        "target": "综合所有信息后的答案",
                        "purpose": "最终验证"
                    }
                ],
                "expected_output": "高置信度的综合答案"
            })

        # 重点领域补充
        if focus_areas:
            for area in focus_areas:
                research_steps.append({
                    "step": f"专项_{area}",
                    "phase": f"重点研究: {area}",
                    "actions": [
                        {
                            "action": "web_search",
                            "query": f'"{query}" {area}',
                            "purpose": f"深入研究{area}方面"
                        }
                    ],
                    "expected_output": f"{area}领域的详细信息"
                })

        # 输出结果
        result = {
            "status": "success",
            "query": query,
            "research_depth": depth,
            "focus_areas": focus_areas,
            "research_plan": research_steps,
            "estimated_steps": len(research_steps) * 2,  # 每步大约2次工具调用
            "tips": [
                "遵循研究计划逐步执行",
                "每一步都记录关键发现",
                "如果某个来源质量不高,立即寻找替代来源",
                "最后综合所有信息,给出完整答案"
            ],
            "quality_checklist": [
                "□ 至少3个独立来源支持",
                "□ 包含权威来源 (.edu/.gov)",
                "□ 事实经过验证",
                "□ 时间线一致",
                "□ 无未解决的矛盾"
            ]
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
