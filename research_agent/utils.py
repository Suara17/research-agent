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
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
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

    # 4. 激进清洗
    clean = clean.strip(" 。.,'\"")
    
    # [New] Remove common noise suffixes like "List"
    if clean.endswith("List") and len(clean) > 4 and clean[-5] != " ":
        clean = clean[:-4]
    
    # 5. 去重逻辑 (增强版 - Simplified for migration)
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
        answer = str(answer or "").strip()
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

@dataclass
class ToolCall:
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arguments: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments
        }

@dataclass
class Chunk:
    step_index: int
    type: Literal["text", "tool_call", "tool_call_result", "final_state"]
    content: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    tool_result: Optional[Any] = None

    def to_dict(self) -> dict:
        return {
            "step_index": self.step_index,
            "type": self.type,
            "content": self.content,
            "tool_call": self.tool_call.to_dict() if self.tool_call else None,
            "tool_result": str(self.tool_result) if self.tool_result else None
        }

def make_json_serializable(obj: Any) -> Any:
    """递归转换对象为可JSON序列化的格式"""
    if isinstance(obj, (Chunk, ToolCall)):
        return obj.to_dict()
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        return str(obj)
    else:
        return obj
