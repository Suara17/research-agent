import os
import re
import json
import inspect
from curl_cffi import requests
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry
from typing import Callable, Any, List, Union, Literal, Optional, get_origin, get_args, get_type_hints
from dataclasses import dataclass
from openai import OpenAI

# -------------------------------------------------------------------------
# HTTP Session
# -------------------------------------------------------------------------

import random

def get_session() -> requests.Session:
    # Use curl_cffi Session with Chrome impersonation for better anti-detection
    session = requests.Session(impersonate="chrome124")
    
    # User-Agent Rotation List (kept for reference, but impersonate handles it mostly)
    # We can still set some custom headers if needed, but be careful not to break the impersonation profile.
    # Generally, with impersonate, we should let it handle the headers.
    
    # However, setting Accept-Language might be useful.
    session.headers.update({
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    })
    
    return session

# -------------------------------------------------------------------------
# LLM Client
# -------------------------------------------------------------------------

def get_llm_client(timeout=30.0):
    """Factory for OpenAI client."""
    return OpenAI(
        base_url="https://apis.iflow.cn/v1", 
        api_key=os.getenv("IFLOW_API_KEY"), 
        timeout=timeout
    )

# -------------------------------------------------------------------------
# Text Cleaning
# -------------------------------------------------------------------------

def clean_answer(raw_answer: str) -> str:
    """
    工程级后处理：强制清洗答案格式
    """
    if not raw_answer:
        return ""
    
    # 0. 优先提取答案标记后的内容（取最后一次出现，避免中间过程干扰）
    # 覆盖常见中英文答案标记变体
    _ANSWER_MARKERS = (
        r"Final Answer",       # 英文标准格式
        r"最终答案",            # 中文标准格式
        r"正确答案",
        r"答案",               # 通用中文（放最后，避免误匹配"答案是..."推理过程）
        r"The Answer",
        r"Answer",
    )
    _MARKER_PATTERN = r"(?:" + "|".join(_ANSWER_MARKERS) + r")[:：]\s*(.*)"
    # findall 取所有匹配，使用最后一个（最终答案总在末尾）
    all_matches = re.findall(_MARKER_PATTERN, raw_answer, re.IGNORECASE | re.DOTALL)
    if all_matches:
        extracted = all_matches[-1].strip()
        if extracted:
            raw_answer = extracted
            # 截断 Thought:/Action: 等推理痕迹（模型在答案后继续推理的情况）
            thought_match = re.search(r"(.*?)(?:Thought|Action|Observation)[:：]", raw_answer, re.IGNORECASE | re.DOTALL)
            if thought_match:
                raw_answer = thought_match.group(1).strip()

    # 1. 去除 Markdown 标记 (只去除 ``` 符号，保留内容)
    clean = re.sub(r'```\w*', '', raw_answer)
    clean = clean.replace('```', '')
    clean = clean.replace('`', '').strip()
    
    # 2. 如果模型输出了 JSON 格式 ({"answer": "..."})，尝试提取
    try:
        start = clean.find('{')
        end = clean.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = clean[start:end+1]
            data = json.loads(json_str)
            if 'answer' in data:
                clean = str(data['answer'])
    except:
        pass

    # 3. 去除常见的废话前缀（与第0步标记列表保持一致，兜底处理第0步未命中的情况）
    patterns = [
        r"^(?:Final Answer|最终答案|正确答案|答案|The Answer|Answer)[:：]\s*",
        r"^(?:answer|the answer is|output)[:：\s-]*",
        r"^答案是[:：]\s*",
        r"^The answer is[:：]\s*",
        r"^根据搜索结果[:：,，]\s*",
        r"^综上所述[:：,，]\s*",
        r"^经检索[:：,，]\s*",
        r"^因此[:：,，]\s*",
    ]
    
    for _ in range(3):
        changed = False
        for p in patterns:
            new_clean = re.sub(p, "", clean, flags=re.IGNORECASE).strip()
            if new_clean != clean:
                clean = new_clean
                changed = True
        if not changed:
            break

    # 4. 去除常见的废话后缀 (尤其是表示不确定的后缀)
    suffix_patterns = [
        r"[\(（]未检索到明确答案[\)）]$",
        r"[\(（]未找到明确答案[\)）]$",
        r"未检索到明确答案$",
        r"未找到明确答案$",
        r"No clear answer found$",
        r"not found$",
        r"[\(（]not found[\)）]$",
        r"Unknown$",
        r"无法确定$",
        r"[\(（]uncertain[\)）]$"
    ]
    
    for _ in range(3):
        changed = False
        for p in suffix_patterns:
            # specifically for suffixes, using sub with $ might be enough, but regex replacement is safer
            new_clean = re.sub(p, "", clean, flags=re.IGNORECASE).strip()
            if new_clean != clean:
                clean = new_clean
                changed = True
        if not changed:
            break

    # 5. Remove trailing punctuation
    clean = clean.strip(" .,;?!。，；？！")
            
    # 4. 激进清洗 (Original logic continues)
    clean = clean.strip(" 。.,'\"")
    
    # [New] Remove common noise suffixes like "List"
    if clean.endswith("List") and len(clean) > 4 and clean[-5] != " ":
        clean = clean[:-4]
    
    # 5. 去重逻辑 (增强版 - 防止混乱拼接)
    # 先检测并修复混乱拼接（如 '196419661966' -> '1966'）
    if clean and len(clean) >= 4:
        # 检查是否是纯数字且长度为4的倍数（可能是年份重复）
        if clean.isdigit() and len(clean) % 4 == 0 and len(clean) > 4:
            # 尝试按4位分割
            chunks = [clean[i:i+4] for i in range(0, len(clean), 4)]
            # 如果所有块都是有效年份（1900-2100），取最后一个
            if all(1900 <= int(c) <= 2100 for c in chunks):
                clean = chunks[-1]
                print(f"[CleanAnswer] 检测到年份混乱拼接，修正: '{clean}' (原始: {chunks})")

    # 原有去重逻辑
    m = re.match(r'^(.+?)(?:[ \t\n。,;!?.|]+)\1$', clean, re.IGNORECASE | re.DOTALL)
    if m:
        clean = m.group(1)
    else:
        m2 = re.match(r'^(.+?)\1$', clean, re.IGNORECASE | re.DOTALL)
        if m2:
            clean = m2.group(1)
        else:
            m3 = re.match(r'^(.+?)(?:[ \t\n。,;!?.|]*)\1', clean, re.IGNORECASE | re.DOTALL)
            found_prefix_dupe = False
            if m3:
                part1 = m3.group(1)
                if len(part1) > 2:
                    suffix = clean[m3.end():]
                    clean = part1 + suffix
                    found_prefix_dupe = True
            
    return clean

# -------------------------------------------------------------------------
# Type Conversion & Schema
# -------------------------------------------------------------------------

def python_type_to_json_type(t):
    """Map Python types to JSON types."""
    origin = get_origin(t)
    if t is str:
        return "string"
    elif t is int:
        return "integer"
    elif t is float:
        return "number"
    elif t is bool:
        return "boolean"
    elif t is list or origin is list:
        return "array"
    elif t is dict or origin is dict:
        return "object"
    elif origin is Union:
        args = get_args(t)
        for arg in args:
            if arg is dict or get_origin(arg) is dict:
                return "object"
            if arg is list or get_origin(arg) is list:
                return "array"
    return "string"

# Cleaned up duplicate

def function_to_schema(func: Callable) -> dict:
    """
    Convert a Python function to an OpenAI API Tool Schema.
    """
    type_hints = get_type_hints(func)
    signature = inspect.signature(func)

    parameters = {"type": "object", "properties": {}, "required": []}

    for name, param in signature.parameters.items():
        if name in ("self", "cls"):
            continue

        annotation = type_hints.get(name, str)
        param_type = python_type_to_json_type(annotation)

        param_info = {"type": param_type}

        if get_origin(annotation) == Literal:
            param_info["enum"] = list(get_args(annotation))
            param_info["type"] = python_type_to_json_type(type(get_args(annotation)[0]))

        parameters["properties"][name] = param_info
        if param.default == inspect.Parameter.empty:
            parameters["required"].append(name)

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": (func.__doc__ or "").strip(),
            "parameters": parameters,
        },
    }

# -------------------------------------------------------------------------
# JSON Serialization & Data Structures
# -------------------------------------------------------------------------

from .schema import ToolCall, Chunk, make_json_serializable
