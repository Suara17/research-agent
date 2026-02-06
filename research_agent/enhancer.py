"""
通用Agent优化集成模块
将所有优化策略整合到agent_loop中
"""
from typing import Dict, List, Optional
import json


class AgentEnhancer:
    """Agent增强器 - 整合所有优化模块"""

    def __init__(self):
        from .entity_graph import EntityRelationshipGraph, extract_entity_graph_from_context, generate_targeted_queries
        from .fallback_strategies import FallbackManager, detect_error_type, extract_entity_name_from_url
        from .reflection import ReflectionManager, ConceptVerifier, should_inject_reflection
        from .answer_synthesis import (
            verify_entity_relationships,
            resolve_timeline,
            extract_candidate_answers,
            synthesize_final_answer,
            validate_answer_format
        )

        self.entity_graph_module = {
            "EntityRelationshipGraph": EntityRelationshipGraph,
            "extract_entity_graph_from_context": extract_entity_graph_from_context,
            "generate_targeted_queries": generate_targeted_queries
        }

        self.fallback_manager = FallbackManager()

        self.reflection_manager = ReflectionManager()
        self.concept_verifier = ConceptVerifier()

        self.answer_synthesis = {
            "verify_entity_relationships": verify_entity_relationships,
            "resolve_timeline": resolve_timeline,
            "extract_candidate_answers": extract_candidate_answers,
            "synthesize_final_answer": synthesize_final_answer,
            "validate_answer_format": validate_answer_format
        }

        self.entity_graph = None  # 当前问题的实体关系图
        self.last_reflection_step = -10  # 上次反思的步骤


    def should_trigger_reflection(
        self,
        step_index: int,
        max_steps: int,
        searched_keywords: List[str]
    ) -> Optional[str]:
        """
        判断是否应该触发反思，并返回反思提示

        Returns:
            反思提示文本，如果不需要反思则返回None
        """
        checkpoint = self.reflection_manager.should_trigger(
            current_step=step_index,
            max_steps=max_steps,
            search_count=len(searched_keywords)
        )

        if checkpoint:
            context = {
                "current_step": step_index,
                "max_steps": max_steps,
                "search_count": len(searched_keywords),
                "recent_keywords": searched_keywords
            }
            prompt = self.reflection_manager.generate_reflection_prompt(checkpoint, context)
            self.last_reflection_step = step_index
            return prompt

        return None


    def handle_web_fetch_failure(
        self,
        url: str,
        error_message: str,
        search_func
    ) -> Optional[Dict]:
        """
        处理web_fetch失败，启用回退策略

        Args:
            url: 失败的URL
            error_message: 错误消息
            search_func: web_search函数引用

        Returns:
            回退策略的结果，如果失败返回None
        """
        from .fallback_strategies import detect_error_type, extract_entity_name_from_url

        error_type = detect_error_type(error_message)
        entity_name = extract_entity_name_from_url(url)

        print(f"[AgentEnhancer] 检测到web_fetch失败: {url}")
        print(f"[AgentEnhancer] 错误类型: {error_type}, 实体: {entity_name}")

        result = self.fallback_manager.handle_fetch_failure(
            url=url,
            entity_name=entity_name,
            error_type=error_type,
            search_func=search_func
        )

        return result


    def build_entity_graph(self, question: str, context_messages: List[Dict]) -> bool:
        """
        构建实体关系图

        Args:
            question: 原始问题
            context_messages: 上下文消息列表

        Returns:
            是否成功构建
        """
        try:
            # 提取工具调用结果作为上下文
            context = ""
            for msg in context_messages[-10:]:  # 只看最近10条消息
                if msg.get("role") == "tool":
                    content = str(msg.get("content", ""))
                    context += content[:500] + "\n"

            from .entity_graph import extract_entity_graph_from_context

            self.entity_graph = extract_entity_graph_from_context(context, question)

            # 验证一致性
            is_valid, issues = self.entity_graph.verify_consistency()

            if not is_valid:
                print(f"[AgentEnhancer] 实体关系图发现逻辑冲突:")
                for issue in issues:
                    print(f"  - {issue}")

            # 识别缺失信息
            missing = self.entity_graph.get_missing_information()
            if missing:
                print(f"[AgentEnhancer] 实体关系图识别缺失信息:")
                for m in missing:
                    print(f"  - {m}")

            return True

        except Exception as e:
            print(f"[AgentEnhancer] 构建实体关系图失败: {e}")
            return False


    def generate_targeted_search_queries(self) -> List[str]:
        """
        基于实体关系图生成针对性搜索查询

        Returns:
            查询列表
        """
        if not self.entity_graph:
            return []

        from .entity_graph import generate_targeted_queries
        queries = generate_targeted_queries(self.entity_graph)

        print(f"[AgentEnhancer] 基于实体图生成了 {len(queries)} 个针对性查询")
        return queries


    def verify_concept_understanding(self, question: str, agent_interpretation: str) -> Dict:
        """
        验证Agent对问题的概念理解

        Args:
            question: 原始问题
            agent_interpretation: Agent的理解/搜索策略

        Returns:
            验证结果
        """
        result = self.concept_verifier.verify_concept_understanding(
            question=question,
            agent_interpretation=agent_interpretation
        )

        if not result.get("is_correct", True):
            print(f"[AgentEnhancer] 检测到概念理解错误:")
            for issue in result.get("issues", []):
                print(f"  ❌ {issue}")
            for suggestion in result.get("suggestions", []):
                print(f"  💡 {suggestion}")

        return result


    def synthesize_answer_from_state(
        self,
        question: str,
        search_results: List[Dict],
        tool_results: List[str]
    ) -> Dict:
        """
        从当前状态合成最终答案

        Args:
            question: 原始问题
            search_results: 搜索结果列表
            tool_results: 工具结果列表

        Returns:
            {answer, confidence, reasoning}
        """
        from .answer_synthesis import extract_candidate_answers, synthesize_final_answer, validate_answer_format

        # 提取候选答案
        candidates = extract_candidate_answers(question, search_results, tool_results)

        print(f"[AgentEnhancer] 提取了 {len(candidates)} 个候选答案")

        # 综合实体关系图
        entity_graph_dict = self.entity_graph.to_dict() if self.entity_graph else None

        # 合成最终答案
        result = synthesize_final_answer(question, candidates, entity_graph_dict)

        # 验证格式
        is_valid, corrected = validate_answer_format(result["answer"], question)

        if not is_valid:
            print(f"[AgentEnhancer] 答案格式验证失败: {corrected}")
            result["answer"] = corrected
            result["confidence"] *= 0.7  # 降低置信度

        print(f"[AgentEnhancer] 最终答案: {result['answer']} (置信度: {result['confidence']:.2f})")

        return result


# 全局实例
_enhancer_instance = None


def get_agent_enhancer() -> AgentEnhancer:
    """获取全局AgentEnhancer实例"""
    global _enhancer_instance
    if _enhancer_instance is None:
        _enhancer_instance = AgentEnhancer()
    return _enhancer_instance
