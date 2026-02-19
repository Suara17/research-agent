# -*- coding: utf-8 -*-
"""
Search Optimization Module
Question type classification and smart query rewriting
"""
import re


def classify_query_type(query: str) -> dict:
    """
    分类查询类型，返回优化策略
    """
    query_type = {
        "type": "unknown",
        "is_chinese": False,
        "has_time_constraint": False,
        "has_location_constraint": False,
        "has_person_constraint": False,
        "has_org_constraint": False,
        "target_type": "unknown",
        "search_strategy": "general"
    }
    
    # 检测语言
    query_type["is_chinese"] = any("\u4e00" <= ch <= "\u9fff" for ch in query[:50])
    
    # 检测时间约束
    time_patterns = [r"\d{4}年", r"同年", r"十余年后", r"世纪初", r"年代", r"世纪末"]
    query_type["has_time_constraint"] = any(re.search(p, query) for p in time_patterns)
    
    # 检测地点约束
    location_patterns = [r"东亚|南欧|北欧|西欧|欧洲|亚洲|北美|南美|非洲", r"国家|城市|首都|省"]
    query_type["has_location_constraint"] = any(re.search(p, query) for p in location_patterns)
    
    # 检测组织/公司约束
    org_patterns = [r"公司|出版社|企业|集团|机构|组织|协会|委员会"]
    query_type["has_org_constraint"] = any(re.search(p, query) for p in org_patterns)
    
    # 检测人物约束
    person_patterns = [r"创业者|企业家|天文学家|科学家|政治家|艺术家|作家|导演|球员|总统|总理|首相"]
    query_type["has_person_constraint"] = any(re.search(p, query) for p in person_patterns)
    
    # 判断目标类型
    if any(kw in query for kw in ["公司", "出版社", "企业", "集团", "机构"]):
        query_type["target_type"] = "company"
    elif any(kw in query for kw in ["谁", "人名", "人物", "作者", "创始人", "名字", "名称"]):
        query_type["target_type"] = "person"
    elif any(kw in query for kw in ["哪一年", "年份", "年", "时间", "时候"]):
        query_type["target_type"] = "year"
    elif any(kw in query for kw in ["哪里", "城市", "地点", "位置", "哪个国家", "哪个城市"]):
        query_type["target_type"] = "location"
    elif query.endswith("?"):
        query_type["target_type"] = "entity"
    
    # 判断问题类型
    if query_type["has_time_constraint"] or query_type["target_type"] == "year":
        query_type["type"] = "time"
    elif query_type["has_org_constraint"] or query_type["target_type"] == "company":
        query_type["type"] = "organization"
    elif query_type["has_person_constraint"] or query_type["target_type"] == "person":
        query_type["type"] = "person"
    
    # 选择搜索策略
    if query_type["type"] == "organization" or query_type["target_type"] == "company":
        query_type["search_strategy"] = "company_focused"
    elif query_type["type"] == "person":
        query_type["search_strategy"] = "person_focused"
    elif query_type["type"] == "time":
        query_type["search_strategy"] = "time_focused"
    else:
        query_type["search_strategy"] = "general"
    
    return query_type


def smart_query_rewrite(query: str, query_type: dict) -> str:
    """
    根据问题类型智能重写查询
    """
    strategy = query_type.get("search_strategy", "general")
    
    if strategy == "company_focused":
        keywords = []
        locations = re.findall(r"(东亚|南欧|北欧|西欧|欧洲|亚洲|北美|日本|意大利|法国|德国|英国|美国|西班牙|韩国)", query)
        keywords.extend(locations)
        if "出版" in query:
            keywords.append("出版社")
        if "科技" in query:
            keywords.append("科技公司")
        if "创业者" in query or "创始人" in query:
            keywords.append("创始人")
        if keywords:
            return " ".join(keywords)
    
    elif strategy == "person_focused":
        keywords = []
        roles = re.findall(r"(天文学家|科学家|政治家|艺术家|作家|企业家)", query)
        keywords.extend(roles)
        nationalities = re.findall(r"(法国|意大利|德国|英国|美国|欧洲|亚洲)", query)
        keywords.extend(nationalities)
        if keywords:
            return " ".join(keywords)
    
    elif strategy == "time_focused":
        keywords = []
        years = re.findall(r"\d{4}年", query)
        keywords.extend(years)
        if "成立" in query:
            keywords.append("成立")
        if "创办" in query:
            keywords.append("创办")
        if keywords:
            return " ".join(keywords)
    
    return None  # 返回 None 表示使用默认处理


def select_search_engine_by_type(query_type: dict) -> str:
    """根据问题类型选择最佳搜索引擎"""
    is_chinese = query_type.get("is_chinese", False)
    strategy = query_type.get("search_strategy", "general")
    
    if strategy == "company_focused":
        return "serper"
    if strategy == "person_focused" and not is_chinese:
        return "serper"
    if strategy == "time_focused":
        return "searxng"
    if is_chinese:
        return "bocha"
    return "serper"


def rerank_by_query_type(results: list, query: str, query_type: dict) -> list:
    """基于问题类型对结果进行相关性重排"""
    if not results:
        return results
    
    strategy = query_type.get("search_strategy", "general")
    target_type = query_type.get("target_type", "unknown")
    
    key_concepts = set()
    if target_type == "company":
        key_concepts.update(["公司", "出版社", "集团", "企业", "corporation", "company", "inc", "ltd"])
    elif target_type == "person":
        key_concepts.update(["人", "作者", "创始人", "person", "founder", "born", "died"])
    
    if strategy == "company_focused":
        key_concepts.update(["创办", "创始人", "总部", "founder", "established"])
    elif strategy == "person_focused":
        key_concepts.update(["出生于", "逝世", "著名", "born", "died", "famous"])
    
    scored = []
    for r in results:
        score = r.get("score", 0.5)
        content = (r.get("title", "") + " " + r.get("summary", "")).lower()
        
        for concept in key_concepts:
            if concept.lower() in content:
                score += 0.5
        
        # 惩罚不相关（公司查询但出现天文内容）
        if target_type == "company" or strategy == "company_focused":
            if any(kw in content for kw in ["天文学", "恒星", "astronomy"]):
                if not any(c in content for c in ["公司", "corporation", "company", "集团"]):
                    score -= 1.0
        
        scored.append((r, score))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    return [r for r, s in scored]
