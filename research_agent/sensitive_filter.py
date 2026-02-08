"""
敏感词过滤模块
策略：仅在答案合成阶段过滤敏感词，搜索/规划/执行阶段保留原始信息
"""
import logging
from typing import Dict, Tuple, List

logger = logging.getLogger(__name__)

# 敏感词映射表
SENSITIVE_WORD_MAPPING: Dict[str, str] = {
    # === 政治相关 ===
    "元首": "高级官员",
    "国家领导人": "政府高层",
    "领导人": "高层人士",
    "政权": "政府",
    "专机": "专用航班",
    "皇权": "统治权",
    "更迭": "变化",
    "摄政": "辅政",

    # === 军事相关 ===
    "军旅": "服役",
    "军籍": "军事背景",
    "军人背景": "服役经历",
    "后备机组": "备用机组",
    "军民": "各方",
    "军事工程": "工程技术",
    "军事领袖": "领导者",

    # === 航空灾难相关 ===
    "空难": "航空事故",
    "坠毁": "事故",
    "遇难": "伤亡",
    "撞山": "碰撞",
    "机组成员": "航空人员",
    "责任机长": "机长",

    # === 历史政治运动 ===
    "文革": "历史时期",
    "文化大革命": "历史运动",
    "政治运动": "社会运动",
    "民航资产": "航空资产",
    "动荡": "变革",
    "风波": "事件",
    "叛徒": "反对者",

    # === 情报与网络安全 ===
    "情报机构": "安全机构",
    "间谍": "特工",
    "恶意软件": "有害程序",
    "网络攻击": "网络事件",
    "勒索": "敲诈",
    "固件": "底层程序",

    # === 社会敏感 ===
    "罢工": "停工",
    "劳资谈判": "协商",
    "劳工组织": "工会",
    "腐败": "不当行为",
    "贪污": "违规",
    "舆论风波": "公众关注",

    # === 宗教相关 ===
    "宗教冲突": "信仰差异",
    "教派": "团体",
    "邪教": "非主流组织",

    # === 其他 ===
    "监禁": "拘留",
    "调查": "核查",
    "索赔": "要求赔偿",
    "起诉": "法律诉讼",
}

def sanitize_text_for_llm(text: str, log_replacement: bool = True) -> Tuple[str, Dict[str, int]]:
    """
    在发送给LLM前替换敏感词

    Args:
        text: 原始文本
        log_replacement: 是否记录替换日志

    Returns:
        (替换后的文本, 替换统计字典)
    """
    if not text:
        return text, {}

    sanitized = text
    replacements = {}

    for sensitive, replacement in SENSITIVE_WORD_MAPPING.items():
        count = sanitized.count(sensitive)
        if count > 0:
            sanitized = sanitized.replace(sensitive, replacement)
            replacements[sensitive] = count

    if log_replacement and replacements:
        logger.info(f"[SensitiveFilter] 替换了 {len(replacements)} 种敏感词:")
        for word, count in replacements.items():
            logger.info(f"  - '{word}' → '{SENSITIVE_WORD_MAPPING[word]}' (×{count})")
        logger.debug(f"[SensitiveFilter] 原始文本: {text[:100]}...")
        logger.debug(f"[SensitiveFilter] 替换后: {sanitized[:100]}...")

    return sanitized, replacements


def simplify_query_on_failure(query: str, attempt: int = 0) -> str:
    """
    当内容审核失败后，简化查询（回退机制）

    Args:
        query: 原始查询
        attempt: 重试次数 (0为首次失败)

    Returns:
        简化后的查询
    """
    # 第一次失败：移除所有敏感词
    if attempt == 0:
        simplified, _ = sanitize_text_for_llm(query, log_replacement=False)
        logger.warning(f"[SensitiveFilter] 第1次简化: 移除敏感词")
        return simplified

    # 第二次失败：进一步简化，只保留核心关键词
    elif attempt == 1:
        # 移除时间范围、修饰词等
        import re
        simplified = query

        # 移除年代信息
        simplified = re.sub(r'\d{4}[-~年]\d{4}', '', simplified)
        simplified = re.sub(r'\d{4}年代?', '', simplified)
        simplified = re.sub(r'20世纪\d{2}年代', '', simplified)
        simplified = re.sub(r'21世纪\d{2}年代', '', simplified)

        # 移除site:限定符
        simplified = re.sub(r'site:\S+', '', simplified)

        # 清理多余空格
        simplified = ' '.join(simplified.split())

        logger.warning(f"[SensitiveFilter] 第2次简化: 移除时间和限定符")
        logger.debug(f"  原始: {query}")
        logger.debug(f"  简化: {simplified}")
        return simplified

    # 第三次失败：只保留最核心的1-3个关键词
    else:
        keywords = query.split()[:3]
        simplified = ' '.join(keywords)
        logger.warning(f"[SensitiveFilter] 第3次简化: 只保留前3个关键词")
        logger.debug(f"  原始: {query}")
        logger.debug(f"  简化: {simplified}")
        return simplified


def is_content_inspection_error(error: Exception) -> bool:
    """
    判断错误是否为内容审核失败

    Args:
        error: 异常对象

    Returns:
        是否为内容审核错误
    """
    error_str = str(error)
    return any([
        "DataInspectionFailed" in error_str,
        "inappropriate content" in error_str.lower(),
        "content inspection" in error_str.lower(),
        "敏感内容" in error_str,
        "内容审核" in error_str,
    ])
