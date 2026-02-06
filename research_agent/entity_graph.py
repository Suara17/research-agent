"""
实体关系图模块 - 通用优化方案1
用于构建和验证多实体问题的逻辑关系
"""
import json
import re
from typing import Dict, List, Set, Tuple
from .utils import get_llm_client


class EntityRelationshipGraph:
    """实体关系图，用于追踪复杂问题中的实体及其关系"""

    def __init__(self):
        self.entities = {}  # {entity_id: {name, type, attributes}}
        self.relationships = []  # [(entity1, relation, entity2)]
        self.constraints = []  # [(entity, constraint_type, value)]

    def add_entity(self, entity_id: str, name: str, entity_type: str, attributes: Dict = None):
        """添加实体"""
        self.entities[entity_id] = {
            "name": name,
            "type": entity_type,
            "attributes": attributes or {}
        }

    def add_relationship(self, entity1_id: str, relation: str, entity2_id: str):
        """添加实体关系"""
        self.relationships.append((entity1_id, relation, entity2_id))

    def add_constraint(self, entity_id: str, constraint_type: str, value):
        """添加约束条件"""
        self.constraints.append((entity_id, constraint_type, value))

    def verify_consistency(self) -> Tuple[bool, List[str]]:
        """验证实体关系的逻辑一致性"""
        issues = []

        # 检查1: 所有关系中的实体是否都已定义
        all_entity_ids = set(self.entities.keys())
        for e1, rel, e2 in self.relationships:
            if e1 not in all_entity_ids:
                issues.append(f"关系中引用了未定义的实体: {e1}")
            if e2 not in all_entity_ids:
                issues.append(f"关系中引用了未定义的实体: {e2}")

        # 检查2: 冲突的位置约束
        location_map = {}  # {entity_id: set_of_locations}
        for entity_id, c_type, value in self.constraints:
            if c_type in ["located_in", "not_located_in", "situated_in"]:
                if entity_id not in location_map:
                    location_map[entity_id] = {"positive": set(), "negative": set()}

                if c_type.startswith("not_"):
                    location_map[entity_id]["negative"].add(value)
                else:
                    location_map[entity_id]["positive"].add(value)

        # 检查位置冲突
        for entity_id, locs in location_map.items():
            overlap = locs["positive"] & locs["negative"]
            if overlap:
                entity_name = self.entities.get(entity_id, {}).get("name", entity_id)
                issues.append(f"实体 '{entity_name}' 的位置约束冲突: 同时要求在 {overlap} 和不在 {overlap}")

        # 检查3: 传递关系验证
        # 如果A在B, B在C, 则A应在C (除非有"not_in"约束)
        for e1, rel1, e2 in self.relationships:
            if rel1 in ["located_in", "situated_in"]:
                for e3, rel2, e4 in self.relationships:
                    if e3 == e2 and rel2 in ["located_in", "situated_in"]:
                        # e1在e2, e2在e4 => e1应在e4
                        # 检查是否有e1 not_in e4的约束
                        for ent_id, c_type, val in self.constraints:
                            if ent_id == e1 and c_type == "not_located_in" and val == self.entities.get(e4, {}).get("name"):
                                name1 = self.entities.get(e1, {}).get("name", e1)
                                name4 = self.entities.get(e4, {}).get("name", e4)
                                issues.append(f"逻辑冲突: '{name1}' 通过传递关系应在 '{name4}', 但约束要求不在")

        return len(issues) == 0, issues

    def get_missing_information(self) -> List[str]:
        """识别缺失的关键信息"""
        missing = []

        # 检查每个实体是否有足够的属性
        for entity_id, entity_data in self.entities.items():
            entity_type = entity_data["type"]
            attributes = entity_data["attributes"]

            if entity_type == "place":
                if "opening_year" not in attributes and "founded" not in attributes:
                    missing.append(f"实体 '{entity_data['name']}' (类型: {entity_type}) 缺少开放/成立年份")

            elif entity_type == "venue":
                if "accreditation" not in attributes:
                    missing.append(f"场馆 '{entity_data['name']}' 缺少认证信息")

            elif entity_type == "organization":
                if "headquarters" not in attributes and "based_in" not in attributes:
                    missing.append(f"组织 '{entity_data['name']}' 缺少总部/所在地信息")

        return missing

    def to_dict(self) -> Dict:
        """转换为字典格式用于序列化"""
        return {
            "entities": self.entities,
            "relationships": self.relationships,
            "constraints": self.constraints
        }


def extract_entity_graph_from_context(context: str, question: str) -> EntityRelationshipGraph:
    """
    从上下文和问题中提取实体关系图
    这是一个通用函数,适用于任何包含多实体关系的复杂问题
    """
    try:
        client = get_llm_client(timeout=30.0)

        prompt = f"""分析以下问题和上下文,提取实体及其关系。

问题: {question}

上下文: {context[:2000]}

请输出JSON格式,包含:
1. entities: 列表,每项包含 {{id, name, type, attributes}}
   - type可以是: place, venue, organization, person, object, event等
   - attributes是该实体的已知属性字典

2. relationships: 列表,每项包含 {{entity1_id, relation, entity2_id}}
   - relation如: located_in, collaborates_with, hosts, houses, funded_by等

3. constraints: 列表,每项包含 {{entity_id, constraint_type, value}}
   - constraint_type如: not_located_in, accreditation_level, opening_year等

示例:
{{
  "entities": [
    {{"id": "e1", "name": "Scottish Football Museum", "type": "place", "attributes": {{"located_in": "Hampden Stadium"}}}},
    {{"id": "e2", "name": "Hampden Stadium", "type": "venue", "attributes": {{"accreditation": "five-star", "located_in": "Glasgow"}}}}
  ],
  "relationships": [
    {{"entity1_id": "e1", "relation": "located_in", "entity2_id": "e2"}}
  ],
  "constraints": [
    {{"entity_id": "e1", "constraint_type": "not_located_in", "value": "Glasgow"}}
  ]
}}
"""

        response = client.chat.completions.create(
            model="qwen3-max",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)

        # 构建图
        graph = EntityRelationshipGraph()

        for entity in result.get("entities", []):
            graph.add_entity(
                entity["id"],
                entity["name"],
                entity["type"],
                entity.get("attributes", {})
            )

        for rel in result.get("relationships", []):
            graph.add_relationship(
                rel["entity1_id"],
                rel["relation"],
                rel["entity2_id"]
            )

        for constraint in result.get("constraints", []):
            graph.add_constraint(
                constraint["entity_id"],
                constraint["constraint_type"],
                constraint["value"]
            )

        return graph

    except Exception as e:
        print(f"[EntityGraph] 提取失败: {e}")
        return EntityRelationshipGraph()


def generate_targeted_queries(graph: EntityRelationshipGraph) -> List[str]:
    """
    基于实体关系图生成针对性搜索查询
    通用函数: 根据缺失信息自动生成搜索策略
    """
    queries = []

    # 策略1: 为缺少关键属性的实体生成查询
    for entity_id, entity_data in graph.entities.items():
        name = entity_data["name"]
        entity_type = entity_data["type"]
        attrs = entity_data["attributes"]

        if entity_type == "place" and "opening_year" not in attrs:
            queries.append(f'"{name}" opening year OR founded OR established')

        if entity_type == "venue" and "accreditation" not in attrs:
            queries.append(f'"{name}" accreditation OR rating OR certification')

        if entity_type == "organization" and "headquarters" not in attrs:
            queries.append(f'"{name}" headquarters OR based in OR location')

    # 策略2: 验证关系
    for e1_id, relation, e2_id in graph.relationships:
        e1_name = graph.entities.get(e1_id, {}).get("name", "")
        e2_name = graph.entities.get(e2_id, {}).get("name", "")

        if e1_name and e2_name:
            if relation == "collaborates_with":
                queries.append(f'"{e1_name}" "{e2_name}" collaboration OR partnership OR project')
            elif relation == "located_in":
                queries.append(f'"{e1_name}" location "{e2_name}"')

    return queries[:5]  # 返回最多5个查询
