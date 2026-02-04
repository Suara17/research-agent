#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chain of Verification Skill - 验证链推理
生成验证问题,独立搜索验证,修正答案
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
        question = args.get("question", "")
        candidate_answer = args.get("candidate_answer", "")
        confidence = args.get("confidence", 0.6)

        if not question or not candidate_answer:
            print(json.dumps({
                "error": "question and candidate_answer are required",
                "usage": {
                    "question": "原始问题",
                    "candidate_answer": "候选答案",
                    "confidence": "当前置信度 (0-1)"
                }
            }, ensure_ascii=False))
            sys.exit(1)

        # 根据问题类型生成验证问题
        verification_queries = []

        # 分析问题类型
        question_lower = question.lower()

        # 人物类问题
        if any(keyword in question_lower for keyword in ["who", "谁", "人", "scientist", "学者", "教授"]):
            verification_queries.extend([
                {
                    "type": "background",
                    "query": f"{candidate_answer} 的职业/专业领域是什么?",
                    "purpose": "验证专业背景"
                },
                {
                    "type": "affiliation",
                    "query": f"{candidate_answer} 在哪个机构/公司工作?",
                    "purpose": "验证身份"
                },
                {
                    "type": "contribution",
                    "query": f"{candidate_answer} 有相关的学术出版物或专利吗?",
                    "purpose": "验证学术贡献"
                },
                {
                    "type": "alternatives",
                    "query": f"除了 {candidate_answer}, 还有其他人做出了类似贡献吗?",
                    "purpose": "寻找潜在反例"
                }
            ])

        # 时间类问题
        elif any(keyword in question_lower for keyword in ["when", "哪一年", "什么时候", "year", "时间"]):
            verification_queries.extend([
                {
                    "type": "timeline",
                    "query": f"相关事件的完整时间线是怎样的?",
                    "purpose": "验证时间上下文"
                },
                {
                    "type": "consistency",
                    "query": f"{candidate_answer} 这个时间是否与相关人物/事件的时间线一致?",
                    "purpose": "时间一致性检查"
                },
                {
                    "type": "sources",
                    "query": f"不同来源对这个时间的记录是否一致?",
                    "purpose": "多源时间验证"
                }
            ])

        # 概念类问题
        elif any(keyword in question_lower for keyword in ["what is", "什么是", "define", "定义"]):
            verification_queries.extend([
                {
                    "type": "principle",
                    "query": f"{candidate_answer} 的核心原理/机制是什么?",
                    "purpose": "验证概念理解"
                },
                {
                    "type": "application",
                    "query": f"{candidate_answer} 有哪些实际应用?",
                    "purpose": "验证概念的实用性"
                },
                {
                    "type": "authority",
                    "query": f"权威来源(教科书/官方文档)如何定义 {candidate_answer}?",
                    "purpose": "获取权威定义"
                }
            ])

        # 因果类问题
        elif any(keyword in question_lower for keyword in ["why", "为什么", "如何", "how", "影响", "导致"]):
            verification_queries.extend([
                {
                    "type": "causality",
                    "query": f"是否有直接证据表明这个因果关系?",
                    "purpose": "验证因果关系"
                },
                {
                    "type": "alternative_causes",
                    "query": f"除了 {candidate_answer}, 还有其他可能的原因吗?",
                    "purpose": "排除其他因素"
                },
                {
                    "type": "research",
                    "query": f"权威研究如何评价这个关系?",
                    "purpose": "科学验证"
                }
            ])

        # 通用验证问题
        else:
            verification_queries.extend([
                {
                    "type": "general",
                    "query": f"{candidate_answer} 是否得到多个独立来源的支持?",
                    "purpose": "多源验证"
                },
                {
                    "type": "contradiction",
                    "query": f"是否有来源与 {candidate_answer} 相矛盾?",
                    "purpose": "寻找反例"
                },
                {
                    "type": "logic",
                    "query": f"{candidate_answer} 是否符合常识和逻辑?",
                    "purpose": "逻辑检查"
                }
            ])

        # 输出结果
        result = {
            "status": "success",
            "original_question": question,
            "candidate_answer": candidate_answer,
            "initial_confidence": confidence,
            "verification_queries": verification_queries[:5],  # 限制5个问题
            "workflow": [
                "第1步: 对每个验证问题独立搜索 (不受候选答案影响)",
                "第2步: 使用 web_fetch 读取权威来源全文",
                "第3步: 提取验证证据,标记 支持✓/矛盾✗/无关-",
                "第4步: 统计验证通过率 (支持数 / 总验证数)",
                "第5步: 根据通过率决定: 确认(≥80%) / 修正(50-80%) / 推翻(<50%)"
            ],
            "confidence_adjustment": {
                "verification_pass_rate_80_100": "提升置信度到 0.90-0.95",
                "verification_pass_rate_50_80": "部分确认,置信度 0.70-0.85",
                "verification_pass_rate_0_50": "推翻答案,重新推理"
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
