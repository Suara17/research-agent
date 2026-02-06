#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Question Complexity Analyzer
动态计算问题复杂度，为不同类型问题分配合理的搜索步数
"""

import re
from typing import Dict


def calculate_max_steps(question: str, base_steps: int = 8) -> int:
    """
    根据问题复杂度动态计算最大步数

    Args:
        question: 用户问题
        base_steps: 基础步数（简单问题的默认值）

    Returns:
        建议的最大步数（8-30之间）
    """
    complexity_score = 0
    analysis_details = []

    # ========== 复杂度评估规则 ==========

    # 1. 多条件约束（每个额外条件 +4步）
    multi_condition_keywords = ['且', '同时', '并且', 'and', 'also', 'while', 'whereas']
    condition_count = sum(question.count(kw) for kw in multi_condition_keywords)
    if condition_count >= 2:
        score_add = min(condition_count * 4, 12)  # 上限12步
        complexity_score += score_add
        analysis_details.append(f"多条件约束({condition_count}个): +{score_add}步")

    # 2. 历史事实验证（需要查证宪法、法律、历史事件）
    historical_keywords = [
        '宪法', '修订', '颁布', '生效', 'constitution', 'amendment', 'enacted',
        '任期', 'term limit', '职权', 'powers', '根本大法'
    ]
    if any(kw in question for kw in historical_keywords):
        complexity_score += 8
        analysis_details.append("历史事实验证（宪法/法律）: +8步")

    # 3. 教育背景验证（需要查证学历）
    education_keywords = [
        '留学', '深造', '学习', 'studied', 'educated', 'graduated',
        '大学', 'university', '学府', 'institution', '学位', 'degree'
    ]
    if any(kw in question for kw in education_keywords):
        complexity_score += 6
        analysis_details.append("教育背景验证: +6步")

    # 4. 丑闻/腐败验证（需要查证新闻报道）
    scandal_keywords = [
        '丑闻', '风波', '腐败', 'scandal', 'corruption', 'controversy',
        '调查', 'investigation', '指控', 'allegation', '亲属', 'relatives',
        '财产', 'assets', 'property'
    ]
    if any(kw in question for kw in scandal_keywords):
        complexity_score += 4
        analysis_details.append("丑闻/腐败验证: +4步")

    # 5. 人物身份验证（需要交叉验证多个来源）
    person_keywords = ['谁', 'who', '人物', 'person', '首脑', 'leader', '总理', 'prime minister', '总统', 'president']
    if any(kw in question.lower() for kw in person_keywords):
        complexity_score += 4
        analysis_details.append("人物身份验证: +4步")

    # 6. 多跳推理（需要分步查询）
    # 检测是否有嵌套描述（"...的...的..."模式）
    nested_pattern = r'(的.{2,15}){3,}'  # 连续3个以上"的"字结构
    if re.search(nested_pattern, question):
        complexity_score += 8
        analysis_details.append("多跳推理（嵌套描述）: +8步")

    # 7. 时间跨度大（需要查询多个时间段）
    time_keywords = ['年代', 'decade', '世纪', 'century', '时期', 'period', 'era']
    time_mentions = sum(question.count(kw) for kw in time_keywords)
    if time_mentions >= 2:
        score_add = min(time_mentions * 2, 6)
        complexity_score += score_add
        analysis_details.append(f"时间跨度验证({time_mentions}个时期): +{score_add}步")

    # 8. 问题长度（长问题通常更复杂）
    question_length = len(question)
    if question_length > 150:
        complexity_score += 4
        analysis_details.append(f"问题长度({question_length}字符): +4步")
    elif question_length > 100:
        complexity_score += 2
        analysis_details.append(f"问题长度({question_length}字符): +2步")

    # 9. 包含数字精确性要求
    number_keywords = ['精确', 'exact', '准确', 'precise', '具体', 'specific']
    if any(kw in question for kw in number_keywords):
        complexity_score += 4
        analysis_details.append("数字精确性要求: +4步")

    # 10. 多国家/地区比较
    country_mentions = len(re.findall(r'[\u4e00-\u9fff]{2,}国|[A-Z][a-z]+(?:ia|land|stan)', question))
    if country_mentions >= 2:
        complexity_score += 4
        analysis_details.append(f"多国家比较({country_mentions}个): +4步")

    # ========== 计算最终步数 ==========

    # 基础步数 + 复杂度分数，上限30步
    max_steps = base_steps + complexity_score
    max_steps = min(max_steps, 30)  # 硬性上限
    max_steps = max(max_steps, base_steps)  # 至少保证基础步数

    # 输出日志
    print(f"[Complexity] Question length: {question_length} chars")
    print(f"[Complexity] Complexity score: {complexity_score}")
    for detail in analysis_details:
        print(f"[Complexity]   - {detail}")
    print(f"[Complexity] Calculated max_steps: {max_steps} (base={base_steps}, score={complexity_score})")

    return max_steps


def get_complexity_details(question: str) -> Dict[str, any]:
    """
    返回详细的复杂度分析结果（用于调试和监控）

    Returns:
        {
            "max_steps": int,
            "complexity_score": int,
            "analysis_details": [str],
            "question_length": int
        }
    """
    base_steps = 5
    complexity_score = 0
    analysis_details = []

    # 复用 calculate_max_steps 的逻辑...
    # （为简洁起见，这里直接调用主函数）
    max_steps = calculate_max_steps(question, base_steps)

    return {
        "max_steps": max_steps,
        "complexity_score": max_steps - base_steps,
        "analysis_details": analysis_details,
        "question_length": len(question)
    }


# 为了方便导入，提供默认函数
__all__ = ["calculate_max_steps", "get_complexity_details"]
