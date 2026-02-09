import os
import re
import json
import inspect
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Callable, Any, List, Union, Literal, Optional, get_origin, get_args, get_type_hints
from dataclasses import dataclass
from openai import OpenAI

# -------------------------------------------------------------------------
# HTTP Session
# -------------------------------------------------------------------------

import random

def get_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=3,  # Increased from 2 to 3 for better robustness
        backoff_factor=1.0, # Increased from 0.5 to 1.0
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # User-Agent Rotation List
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/121.0.0.0 Safari/537.36"
    ]
    
    session.headers.update(
        {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }
    )
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
    
    # 0. 优先提取 "Final Answer:" 后的内容
    # Use regex to find "Final Answer:" (case insensitive) and capture everything after it
    # We look for the last occurrence to avoid capturing intermediate thoughts if any slipped through
    final_answer_match = re.search(r"Final Answer[:：]\s*(.*)", raw_answer, re.IGNORECASE | re.DOTALL)
    if final_answer_match:
        # If found, replace raw_answer with the captured content
        # We take the content after the marker
        extracted = final_answer_match.group(1).strip()
        if extracted:
             raw_answer = extracted
             # Also check if there are any trailing "Thought:" sections and remove them
             # (In case the model outputs Final Answer then starts thinking again)
             thought_match = re.search(r"(.*?)Thought[:：]", raw_answer, re.IGNORECASE | re.DOTALL)
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

    # 3. 去除常见的废话前缀/后缀
    patterns = [
        r"^(answer|final answer|the answer is|output)[:：\s-]*",
        r"^答案是[:：]\s*",
        r"^The answer is[:：]\s*",
        r"^根据搜索结果[:：,，]\s*",
        r"^Final Answer[:：]\s*",
        r"^综上所述[:：,，]\s*",
        r"^经检索[:：,，]\s*",
        r"^因此[:：,，]\s*"
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

    # [New] LLM Fallback: If result is still a thought trace (regex failed)
    # Trigger if:
    # 1. Contains thought keywords
    # 2. OR Length > 20 words (English) or > 60 chars (approx 20-30 Chinese words/chars context)
    # Use a simple heuristic: split by space for words, or raw length for CJK
    word_count = len(clean.split())
    
    if (len(clean) > 60 or word_count > 20) or any(k in clean for k in ["Thought:", "Action:", "Observation:", "Step 1:", "首先", "我需要"]):
        print("[CleanAnswer] Result is long or looks like a trace. Attempting LLM extraction...")
        try:
            client = get_llm_client()
            response = client.chat.completions.create(
                model="qwen3-max",
                messages=[
                    {"role": "system", "content": "<instruction><role>Answer Extractor</role><task>Read the provided text and extract the Final Answer.</task><rules><rule>Output ONLY the answer text.</rule><rule>Do not output 'The answer is...'.</rule><rule>If no answer is found, output the most relevant conclusion.</rule></rules></instruction>"},
                    {"role": "user", "content": f"<input><text>{clean[:2000]}</text></input>"} # Truncate to avoid context limit
                ],
                temperature=0.1,
                max_tokens=200
            )
            extracted = response.choices[0].message.content.strip()
            # Basic validation of extracted answer
            if extracted and len(extracted) < len(clean):
                 # Recurse once to clean the LLM output (e.g. remove quotes)
                 # But avoid infinite recursion by ensuring length reduced
                 clean = extracted.strip(" `\"'")
                 print(f"[CleanAnswer] LLM Extracted: {clean[:50]}...")
        except Exception as e:
            print(f"[CleanAnswer] LLM Extraction failed: {e}")

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

class CandidatePool:
    """候选答案池 - 管理多个候选答案,避免重复验证相同错误答案"""
    def __init__(self):
        self.candidates = []  # [(answer, confidence, sources)]
        self.rejected = []    # [(answer, reason)]

    def add_candidate(self, answer: str, confidence: float, sources: list):
        """添加候选答案(自动去重)"""
        # 使用 clean_answer 进行标准化清洗
        answer = clean_answer(answer)
        if not answer:
            return

        # 去重检查
        if not any(self._is_similar(answer, c[0]) for c in self.candidates):
            self.candidates.append((answer, confidence, sources))
            # 按置信度排序
            self.candidates.sort(key=lambda x: x[1], reverse=True)
            print(f"[CandidatePool] Added: '{answer}' (confidence={confidence:.2f})")

    def reject(self, answer: str, reason: str):
        """拒绝某个答案,并从候选池移除"""
        answer = str(answer or "").strip()
        if not answer:
            return

        self.rejected.append((answer, reason))
        # 从候选池移除相似答案
        self.candidates = [c for c in self.candidates
                          if not self._is_similar(answer, c[0])]
        print(f"[CandidatePool] Rejected: '{answer[:50]}...' (total rejected={len(self.rejected)})")

    def get_next_best(self) -> Optional[str]:
        """返回下一个未尝试的最高分候选"""
        for ans, conf, sources in self.candidates:
            # 检查是否已被拒绝
            if not any(self._is_similar(ans, r[0]) for r in self.rejected):
                print(f"[CandidatePool] Next candidate: '{ans}' (confidence={conf:.2f}, sources={len(sources)})")
                return ans
        return None

    def _is_similar(self, a: str, b: str) -> bool:
        """判断两个答案是否相似(>80%重合)"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.8

    def get_rejected_names(self) -> list:
        """获取所有被拒绝的答案名称"""
        return [r[0] for r in self.rejected]

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
