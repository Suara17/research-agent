"""
答案合成逻辑优化模块 - 通用优化方案4
在强制合成前进行实体关系验证和时间线解析
"""
import json
import re
from typing import Dict, List, Optional, Tuple
from .utils import get_llm_client


def verify_entity_relationships(
    entities: List[Dict],
    relationships: List[Tuple[str, str, str]],
    constraints: List[Tuple[str, str, str]]
) -> Tuple[bool, List[str]]:
    """
    验证实体关系的逻辑一致性

    Args:
        entities: 实体列表 [{id, name, type, attributes}]
        relationships: 关系列表 [(entity1_id, relation, entity2_id)]
        constraints: 约束列表 [(entity_id, constraint_type, value)]

    Returns:
        (是否一致, 问题列表)
    """
    issues = []

    # 构建实体映射
    entity_map = {e["id"]: e for e in entities}

    # 验证1: 位置关系的一致性
    location_graph = {}  # {entity_id: {positive: set(), negative: set()}}

    for e1, rel, e2 in relationships:
        if rel in ["located_in", "situated_in", "based_in"]:
            if e1 not in location_graph:
                location_graph[e1] = {"in": set(), "not_in": set()}
            location_graph[e1]["in"].add(e2)

    for entity_id, c_type, value in constraints:
        if c_type in ["not_located_in", "not_situated_in"]:
            if entity_id not in location_graph:
                location_graph[entity_id] = {"in": set(), "not_in": set()}
            # 查找value对应的entity_id
            for eid, edata in entity_map.items():
                if edata["name"] == value:
                    location_graph[entity_id]["not_in"].add(eid)
                    break

    # 检查冲突
    for entity_id, locs in location_graph.items():
        conflict = locs["in"] & locs["not_in"]
        if conflict:
            entity_name = entity_map.get(entity_id, {}).get("name", entity_id)
            conflict_names = [entity_map.get(c, {}).get("name", c) for c in conflict]
            issues.append(
                f"位置冲突: '{entity_name}' 同时要求在 {conflict_names} 和不在 {conflict_names}"
            )

    # 验证2: 传递关系
    for e1, rel1, e2 in relationships:
        if rel1 in ["located_in", "situated_in"]:
            for e3, rel2, e4 in relationships:
                if e3 == e2 and rel2 in ["located_in", "situated_in"]:
                    # e1在e2, e2在e4 => e1应在e4
                    # 检查是否有e1 not_in e4
                    if e1 in location_graph and e4 in location_graph[e1]["not_in"]:
                        n1 = entity_map.get(e1, {}).get("name", e1)
                        n2 = entity_map.get(e2, {}).get("name", e2)
                        n4 = entity_map.get(e4, {}).get("name", e4)
                        issues.append(
                            f"传递关系冲突: '{n1}'在'{n2}'，'{n2}'在'{n4}'，"
                            f"但约束要求'{n1}'不在'{n4}'"
                        )

    return len(issues) == 0, issues


def resolve_timeline(facts: List[Dict]) -> Dict[str, List[Dict]]:
    """
    解析并整理时间线

    Args:
        facts: 事实列表 [{entity, event, year, source}]

    Returns:
        按年份组织的时间线 {year: [events]}
    """
    timeline = {}

    for fact in facts:
        year = fact.get("year")
        if year:
            year_str = str(year)
            if year_str not in timeline:
                timeline[year_str] = []
            timeline[year_str].append(fact)

    # 排序
    sorted_timeline = {}
    for year in sorted(timeline.keys()):
        sorted_timeline[year] = timeline[year]

    return sorted_timeline


def extract_candidate_answers(
    question: str,
    search_results: List[Dict],
    tool_results: List[str]
) -> List[Dict]:
    """
    从搜索结果和工具结果中提取候选答案

    Args:
        question: 原始问题
        search_results: 搜索结果列表
        tool_results: 工具调用结果列表

    Returns:
        候选答案列表 [{answer, confidence, evidence}]
    """
    try:
        client = get_llm_client(timeout=30.0)

        # 整合上下文
        context = "搜索结果摘要:\n"
        for i, result in enumerate(search_results[:10]):
            title = result.get("title", "")
            summary = result.get("summary") or result.get("snippet", "")
            context += f"{i+1}. {title}: {summary[:200]}\n"

        context += "\n工具调用结果摘要:\n"
        for i, result in enumerate(tool_results[-5:]):
            context += f"{i+1}. {result[:300]}\n"

        prompt = f"""基于以下信息，提取问题的候选答案。

问题: {question}

信息来源:
{context[:3000]}

请输出JSON格式:
{{
  "candidates": [
    {{
      "answer": "候选答案1",
      "confidence": 0.9,
      "evidence": ["证据1", "证据2"],
      "reasoning": "推理过程"
    }}
  ]
}}

要求:
1. 至少提取1个候选答案，最多3个
2. confidence范围0-1，表示置信度
3. evidence列出支持该答案的关键证据
4. 按confidence降序排列
"""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return result.get("candidates", [])

    except Exception as e:
        print(f"[AnswerSynthesis] 候选答案提取失败: {e}")
        return []


def synthesize_final_answer(
    question: str,
    candidates: List[Dict],
    entity_graph: Optional[Dict] = None
) -> Dict:
    """
    综合所有信息生成最终答案

    Args:
        question: 原始问题
        candidates: 候选答案列表
        entity_graph: 实体关系图(可选)

    Returns:
        最终答案字典 {answer, confidence, reasoning}
    """
    try:
        if not candidates:
            return {
                "answer": "未找到足够信息",
                "confidence": 0.0,
                "reasoning": "搜索未返回有效结果"
            }

        # 如果有高置信度候选答案(>0.8)，直接返回
        top_candidate = candidates[0]
        if top_candidate.get("confidence", 0) > 0.8:
            return {
                "answer": top_candidate["answer"],
                "confidence": top_candidate["confidence"],
                "reasoning": top_candidate.get("reasoning", "")
            }

        # 否则，使用LLM进行综合判断
        client = get_llm_client(timeout=30.0)

        candidates_text = json.dumps(candidates, ensure_ascii=False, indent=2)
        entity_graph_text = json.dumps(entity_graph, ensure_ascii=False, indent=2) if entity_graph else "无"

        prompt = f"""作为最终答案综合专家，请基于候选答案和实体关系图做出最终判断。

问题: {question}

候选答案:
{candidates_text}

实体关系图:
{entity_graph_text}

请输出JSON格式:
{{
  "answer": "最终答案",
  "confidence": 0.85,
  "reasoning": "选择该答案的理由，包括：1)为何选择此候选而非其他 2)实体关系如何支持该答案"
}}

要求:
1. 必须从候选答案中选择一个作为最终答案(不允许回答"不确定")
2. 如果实体关系图显示逻辑冲突，优先选择逻辑一致的候选
3. 确保答案格式符合问题要求(年份/姓名/地名等)
"""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        print(f"[AnswerSynthesis] 最终答案合成失败: {e}")
        # 降级策略：返回最高置信度候选
        if candidates:
            top = candidates[0]
            return {
                "answer": top["answer"],
                "confidence": top.get("confidence", 0.5),
                "reasoning": "基于最高置信度候选"
            }
        return {
            "answer": "无法确定",
            "confidence": 0.0,
            "reasoning": "所有合成策略均失败"
        }


def validate_answer_format(answer: str, question: str) -> Tuple[bool, str]:
    """
    验证答案格式是否符合问题要求

    Args:
        answer: 候选答案
        question: 原始问题

    Returns:
        (是否有效, 修正后的答案或错误信息)
    """
    question_lower = question.lower()

    # 检测问题要求的答案类型
    if any(keyword in question_lower for keyword in ["which year", "in which year", "what year", "年份", "哪一年", "哪年"]):
        # 要求年份
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', answer)
        if year_match:
            return True, year_match.group(1)
        else:
            return False, "答案应包含4位年份，但未找到"

    elif any(keyword in question_lower for keyword in ["english name", "英文名", "english title"]):
        # 要求英文名称
        if not any('a' <= c.lower() <= 'z' for c in answer):
            return False, "答案应为英文名称，但未包含英文字母"
        # 移除中文
        cleaned = re.sub(r'[\u4e00-\u9fff]', '', answer).strip()
        return True, cleaned

    elif any(keyword in question_lower for keyword in ["chinese name", "中文名", "chinese title"]):
        # 要求中文名称
        if not any('\u4e00' <= c <= '\u9fff' for c in answer):
            return False, "答案应为中文名称，但未包含中文字符"
        # 移除英文
        cleaned = re.sub(r'[a-zA-Z]', '', answer).strip()
        return True, cleaned

    elif any(keyword in question_lower for keyword in ["how many", "多少个", "number of", "数量"]):
        # 要求数字
        number_match = re.search(r'\b\d+\b', answer)
        if number_match:
            return True, number_match.group(0)
        else:
            return False, "答案应包含数字，但未找到"

    # 默认接受
    return True, answer.strip()
