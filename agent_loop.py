import inspect
import json
import os
import re
import time
import math
import hashlib
import urllib.parse
from dataclasses import dataclass
from typing import (
    Any,
    AsyncIterator,
    Callable,
    List,
    Literal,
    Optional,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from openai import OpenAI
from openai.types.chat import ChatCompletionChunk
from langgraph.graph import StateGraph, END
from skills import (
    SkillIntegrationTools,
    SkillMetadata,
    build_skills_system_prompt,
    discover_skills,
)

DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


@dataclass
class ToolCall:
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arguments: Optional[dict] = None


@dataclass
class Chunk:
    step_index: int
    type: Literal["text", "tool_call", "tool_call_result"]
    content: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    tool_result: Optional[Any] = None


class MemoryStore:
    def __init__(self, max_short: int = 64):
        self.short: List[str] = []
        self.max_short = max_short
        self.long_path = os.path.join(os.getcwd(), "memory_store.jsonl")
        self.index = {}
        self.doc_len = {}
        self.doc_texts: List[str] = []
        self.avgdl = 0.0

    def add_short(self, item: str) -> None:
        if not item:
            return
        self.short.append(item)
        if len(self.short) > self.max_short:
            self.short = self.short[-self.max_short :]

    def add_long(self, item: str) -> None:
        try:
            with open(self.long_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": int(time.time()), "text": item}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        try:
            doc_id = len(self.doc_texts)
            self._index_doc(doc_id, item)
        except Exception:
            pass

    def _tokenize(self, text: str) -> List[str]:
        try:
            import re
            import unicodedata
            s = unicodedata.normalize("NFKC", str(text)).lower()
            stop_en = {"the","and","or","a","an","of","to","in","on","for","is","are","was","were","be","been","with","as","by","at","from"}
            stop_cn = {"的","了","在","是","我","有","和","与","及","等","为","不","也","这","那","你","他","她","它","其","并","对","以"}
            toks = []
            words = re.findall(r"[A-Za-z0-9]+", s)
            for w in words:
                if w in stop_en:
                    continue
                toks.append(w)
                if len(w) >= 2:
                    for i in range(len(w) - 1):
                        toks.append(w[i : i + 2])
                if len(w) >= 3:
                    for i in range(len(w) - 2):
                        toks.append(w[i : i + 3])
            seqs = re.findall(r"[\u4e00-\u9fff]+", s)
            for seq in seqs:
                cands = [seq, re.sub(r"(集团公司|集团|有限公司|公司|大学|学院|学校|电视台|报社|出版社|研究院|研究所)$", "", seq)]
                seen = set()
                for cand in cands:
                    if not cand or cand in seen:
                        continue
                    seen.add(cand)
                    for ch in cand:
                        if ch in stop_cn:
                            continue
                        toks.append(ch)
                    if len(cand) >= 2:
                        for i in range(len(cand) - 1):
                            toks.append(cand[i : i + 2])
                    if len(cand) >= 3:
                        for i in range(len(cand) - 2):
                            toks.append(cand[i : i + 3])
            return toks
        except Exception:
            return []

    def _index_doc(self, doc_id: int, text: str) -> None:
        from collections import Counter
        toks = self._tokenize(text)
        tf = Counter(toks)
        self.doc_len[doc_id] = sum(tf.values())
        self.doc_texts.append(text)
        for term, cnt in tf.items():
            posting = self.index.get(term)
            if posting is None:
                posting = {}
                self.index[term] = posting
            posting[doc_id] = cnt
        n = len(self.doc_texts)
        if n:
            self.avgdl = sum(self.doc_len.values()) / float(n)

    def build_index(self) -> None:
        self.index = {}
        self.doc_len = {}
        self.doc_texts = []
        self.avgdl = 0.0
        if not os.path.exists(self.long_path):
            return
        try:
            with open(self.long_path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        j = json.loads(s)
                        text = str(j.get("text") or "")
                        doc_id = len(self.doc_texts)
                        self._index_doc(doc_id, text)
                    except Exception:
                        continue
        except Exception:
            pass

    def _df(self, term: str) -> int:
        posting = self.index.get(term)
        return len(posting) if posting else 0

    def search(self, query: str, top_k: int = 5) -> List[dict]:
        import unicodedata
        k1 = 1.5
        b = 0.75
        if any("\u4e00" <= ch <= "\u9fff" for ch in str(query)):
            k1 = 1.2
            b = 0.6
        toks = self._tokenize(query)
        N = len(self.doc_texts)
        if N == 0 or not toks:
            return []
        scores = {}
        for t in set(toks):
            posting = self.index.get(t)
            df = self._df(t)
            if not posting or df == 0:
                continue
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
            for doc_id, tf in posting.items():
                dl = self.doc_len.get(doc_id, 0)
                denom = tf + k1 * (1 - b + b * (dl / (self.avgdl or 1.0)))
                s = idf * (tf * (k1 + 1) / (denom or 1.0))
                prev = scores.get(doc_id, 0.0)
                scores[doc_id] = prev + s
        phrase = unicodedata.normalize("NFKC", str(query)).strip()
        if phrase:
            for doc_id in list(scores.keys()):
                try:
                    c = self.doc_texts[doc_id].count(phrase)
                    if c > 0:
                        scores[doc_id] = scores[doc_id] + 0.3 * float(c)
                except Exception:
                    pass
        try:
            import re
            s = unicodedata.normalize("NFKC", str(query)).lower()
            seqs = re.findall(r"[\u4e00-\u9fff]+", s)
            bigrams = []
            trigrams = []
            for seq in seqs:
                if len(seq) >= 2:
                    for i in range(len(seq) - 1):
                        bigrams.append(seq[i : i + 2])
                if len(seq) >= 3:
                    for i in range(len(seq) - 2):
                        trigrams.append(seq[i : i + 3])
            for doc_id in list(scores.keys()):
                text = self.doc_texts[doc_id]
                bc = sum(text.count(bg) for bg in bigrams)
                tc = sum(text.count(tg) for tg in trigrams)
                if bc > 0:
                    scores[doc_id] = scores[doc_id] + 0.15 * float(bc)
                if tc > 0:
                    scores[doc_id] = scores[doc_id] + 0.25 * float(tc)
        except Exception:
            pass
        qset = set(toks)
        for doc_id in list(scores.keys()):
            matched = 0
            for t in qset:
                posting = self.index.get(t)
                if posting and doc_id in posting:
                    matched += 1
            if len(qset) > 0:
                cov = matched / float(len(qset))
                scores[doc_id] = scores[doc_id] * (1.0 + 0.2 * cov)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max(1, int(top_k))]
        return [{"text": self.doc_texts[d], "score": float(sc)} for d, sc in ranked]


class StateStore:
    def __init__(self) -> None:
        base = os.path.join(os.getcwd(), "state_store")
        try:
            os.makedirs(base, exist_ok=True)
        except Exception:
            pass
        self.base = base

    def save(self, cid: str, state: dict) -> None:
        try:
            p = os.path.join(self.base, f"{cid}.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps(state, ensure_ascii=False))
        except Exception:
            pass


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


def extract_answer_from_search_results(search_results: list, query: str) -> dict:
    """
    从搜索结果标题/摘要中提取候选答案
    """
    try:
        from collections import Counter
        import re as _re

        candidates = []
        if not search_results:
             return {"candidates": [], "extraction_method": "no_results"}

        # 策略1: 提取引号内容
        for result in search_results:
            title = result.get('title', '')
            # Support both 'summary' and 'snippet' keys
            snippet = result.get('summary') or result.get('snippet') or ''
            combined = f"{title} {snippet}"
            quoted = _re.findall(r'"([^"]+)"', combined)
            candidates.extend(quoted)
            book_names = _re.findall(r'《([^》]+)》', combined)
            candidates.extend(book_names)

        # 策略2: 提取标题中的关键实体
        for result in search_results[:3]:
            title = result.get('title', '')
            capitalized = _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', title)
            candidates.extend(capitalized)

        if not candidates:
            return {"candidates": [], "extraction_method": "no_candidates"}

        counter = Counter(candidates)
        ranked_candidates = []
        for text, count in counter.most_common(5):
            if len(text) < 3 or len(text) > 100:
                continue
            confidence = min(0.9, (count / len(search_results)) * 0.5 + 0.3)
            if search_results and text in search_results[0].get('title', ''):
                confidence = min(0.95, confidence + 0.2)
            ranked_candidates.append({
                "text": text,
                "confidence": round(confidence, 2),
                "sources": count
            })

        return {
            "candidates": ranked_candidates,
            "extraction_method": "search_metadata"
        }
    except Exception as e:
        print(f"[Monitoring] extract_answer_from_search_results error: {e}")
        return {"candidates": [], "extraction_method": "error"}


def calculate_answer_confidence(answer: str, search_history: list) -> float:
    """计算答案置信度"""
    if not answer or not search_history:
        return 0.5
        
    confidence = 0.5  # 基础分
    
    # 规则1：如果答案出现在多次搜索查询中 (假设 search_history 是 results 列表? 不，应该是 queries? 
    # 用户代码: query_appearances = sum(1 for q in search_history if answer in q) -> search_history 似乎是 queries 列表
    # 但后面: for result in search_history: if result.get('rank_score') ... -> search_history 似乎是 results 列表
    # 我将假设 search_history 是包含 results 的列表，或者 meta 中的信息。
    # 为了简化，我将传入 meta (包含 searched_keywords) 和 last_search_results
    
    # 这里我稍微调整一下签名，只用 last_search_results 来做简单判断，或者传入 meta
    # 用户的伪代码混用了 query 和 result。我将分开处理。
    return 0.5 # Placeholder, logic will be inside agent_loop or expanded here

def calculate_confidence_impl(answer: str, searched_keywords: list, search_results: list) -> float:
    try:
        confidence = 0.5
        # 规则1：如果答案出现在多次搜索查询中
        query_appearances = sum(1 for q in searched_keywords if answer in q)
        if query_appearances >= 2:
            confidence += 0.2

        # 规则2：如果答案出现在高分搜索结果中
        # 假设 search_results 是 [{"title":..., "summary":...}]
        for i, result in enumerate(search_results):
            # Support both 'summary' and 'snippet' keys
            snippet = result.get('summary') or result.get('snippet') or ''
            text = (result.get('title', '') + " " + snippet).lower()
            if answer.lower() in text:
                if i == 0: confidence += 0.2
                elif i < 3: confidence += 0.1
        
        # 规则3：多个来源 (简化版)
        if len(search_results) >= 3:
             confidence += 0.1
             
        return min(0.95, confidence)
    except Exception:
        return 0.5


async def agent_loop(
    input_messages: list,
    tool_functions: List[Callable],
    skill_directories: Optional[List[str]] = ["skills"],
    max_steps: int = 200,
) -> AsyncIterator[Chunk]:
    assert os.getenv("IFLOW_API_KEY"), "IFLOW_API_KEY is not set"
    client = OpenAI(
        base_url="https://apis.iflow.cn/v1",
        api_key=os.getenv("IFLOW_API_KEY"),
        timeout=30.0,
    )
    skills: List[SkillMetadata] = discover_skills(skill_directories) if skill_directories else []
    skills_prompt = build_skills_system_prompt(skills)
    prompt_messages = input_messages.copy()
    system_prompt_addition = ""
    if skills_prompt:
        system_prompt_addition += f"\n\n{skills_prompt}"
        # 添加 Skill 使用指导（强制优先级提示）
        system_prompt_addition += """

### 🚀 搜索效率与摘要优先原则 (Search Efficiency)
1. **优先使用 Summary**: `web_search` 返回的结果中包含 `summary` 字段。这是搜索结果的精华摘要。
2. **避免滥用 Full Content**: 在决定调用 `web_fetch` 读取完整网页之前，请**务必**先检查 `summary` 是否已经包含了足够回答问题的关键信息。
3. **何时使用 Full Content**: 仅当 `summary` 被截断(...)、信息模糊、或者你需要深度验证细节（如具体数据、完整列表）时，才使用 `web_fetch`。
4. **节省资源**: 如果能通过 `summary` 直接回答，请直接回答，不要为了"看一眼"而抓取网页。

### 🕒 深度思考与充分验证（重要）
你拥有充足的时间（单次问题上限 60 分钟）来解决问题。
1. **适度深度搜索**：系统要求**至少进行 10 次不同方向的搜索**来验证答案。对于显而易见的事实，可以在 10 次搜索后提交；对于复杂问题，请继续挖掘。
2. **多角度验证**：对于关键事实，尝试从不同来源（Wiki, 官网, 学术库）进行验证。
3. **充分推理**：对于复杂问题，请进行多步推理，将大问题拆解为小问题逐个击破。
4. **最大步数**：你有高达 200 步的操作空间，请充分利用。不要急于结束。
5. **多方面搜索**：鼓励进行广泛的背景调查和交叉验证，确保答案的每一个细节都准确无误。

### ⚠️ CRITICAL: Skills 使用优先级（必须遵守 - 违反将导致任务失败）

**硬性要求（不可违反）：遇到以下场景，必须先使用对应的 Skill，不要直接使用 web_search！**

1. **长描述/谜语型实体搜索 (Riddle Queries)**
   - 特征：问题很长，没有直接说名字，而是说 "一位...的人"、"一个...的公司"、"A person who..."
   - 示例："一位欧洲学者的某项开源硬件项目..."、"Who is the author of the article that..."
   - **行动**：立即调用 `smart-search`，将整段描述作为 `query` 传入。**必须先泛搜定实体（如 RepRap），再精搜查属性。**

2. **跨语言/特定名称搜索**
   - 特征：中文提问但要求 "英文名称"、"全称"、"拉丁学名"。
   - **行动**：调用 `smart-search`，它会自动生成包含 "English name" 等后缀的查询。

3. **学术/论文/时间线细节**
   - 特征：询问论文标题、具体年份、"哪一年"、技术史。
   - **行动**：调用 `smart-search` (strategy='academic' 或 'timeline')。**学术和年份题必须使用此模式。**

4. **PDF 深度阅读 (PDF Deep Reading)**
   - 特征：搜索结果中出现 PDF 链接（如 Springer, 官方报告）。
   - **行动**：**尽量**使用 `browse_pdf_attachment` 或 `web_fetch` 读取 PDF 全文。关键细节（如具体年份、化学机制）往往隐藏在正文中，摘要不可靠。

5. **找到候选答案需验证** → 必须使用 `multi-source-verify` Skill
   - 要求：关键事实需要多个独立来源确认
   - **强制要求**：验证答案时必须使用 multi-source-verify

6. **置信度中等（<0.8）** → 必须使用 `chain-of-verification` Skill
   - 生成验证问题，独立搜索验证答案

7. **需要多步深度研究** → 必须使用 `deep-research` Skill
   - 复杂多跳推理问题

### 如何使用 Skills（标准流程 - 必须严格遵守）

**第1步：加载 Skill 说明**
```json
{
  "tool": "load_skill_file",
  "arguments": {"skill_name": "smart-search"}
}
```

**第2步：执行 Skill（参数格式必须严格遵守）**
```json
{
  "tool": "execute_script",
  "arguments": {
    "skill_name": "smart-search",
    "args": {
      "query": "你的搜索问题",
      "entities": ["关键实体1", "关键实体2"],
      "strategy": "academic"
    }
  }
}
```

**注意：args 必须是字典对象，包含具体参数！禁止将 JSON 字符串作为 args 的值，必须是解析后的字典。**

**第3步：强制执行 Skill 返回的指导（不可跳过）**
- 当 Skill 返回 `optimized_queries` 时，你**必须**立即使用这些查询调用 web_search
- 当 Skill 返回 `verification_queries` 时，你**必须**依次执行这些验证查询
- **禁止**自己编造新的查询词，**禁止**跳过 Skill 的输出

### 完整示例流程（必须严格遵守）

**示例1: 使用 smart-search（正确流程）**
```
Thought: 这是一个学术问题，我应该使用 smart-search skill。
Action: load_skill_file
Action Input: {"skill_name": "smart-search"}
Observation: [技能说明已加载，了解到需要 query、entities、strategy 参数]

Thought: 现在执行 smart-search，使用 academic 策略。
Action: execute_script
Action Input: {
  "skill_name": "smart-search",
  "args": {
    "query": "RepRap 3D打印机发明人",
    "entities": ["RepRap", "3D打印机"],
    "strategy": "academic"
  }
}
Observation: {
  "status": "success",
  "optimized_queries": [
    "site:edu OR site:org \"RepRap\" \"3D打印机\"",
    "\"RepRap\" filetype:pdf"
  ]
}
[System Enforced]: Skill 'smart-search' 已生成优化查询。你**必须**使用这些查询执行 web_search。

Thought: 收到 Skill 返回的优化查询，现在**必须**使用第一个查询。
Action: web_search
Action Input: {"query": "site:edu OR site:org \"RepRap\" \"3D打印机\""}
```

**错误示例（禁止）：**
```
❌ Observation: {"optimized_queries": ["site:edu RepRap", "RepRap filetype:pdf"]}
❌ Thought: 我自己想一个更好的查询词
❌ Action: web_search {"query": "RepRap inventor"}  # 违规：没有使用 Skill 返回的查询
```

**示例2: 使用 multi-source-verify（正确流程）**
```
Thought: 我找到了候选答案 "Adrian Bowyer"，需要多源验证。
Action: load_skill_file
Action Input: {"skill_name": "multi-source-verify"}
Observation: [技能说明已加载]

Action: execute_script
Action Input: {
  "skill_name": "multi-source-verify",
  "args": {
    "answer": "Adrian Bowyer",
    "entities_to_verify": ["Adrian Bowyer", "RepRap", "2005"]
  }
}
Observation: {
  "status": "success",
  "verification_queries": [
    {"purpose": "直接验证", "query": "\"Adrian Bowyer\" RepRap verify"},
    {"purpose": "验证实体", "query": "\"Adrian Bowyer\" site:edu"}
  ]
}
[System Enforced]: 你**必须**使用这些验证查询。

Thought: 收到验证查询，现在**必须**执行第一个验证查询。
Action: web_search
Action Input: {"query": "\"Adrian Bowyer\" RepRap verify"}
```

**示例3: 使用 chain-of-verification**
```
Action: execute_script
Action Input: {
  "skill_name": "chain-of-verification",
  "args": {
    "question": "谁发明了RepRap?",
    "candidate_answer": "Adrian Bowyer",
    "confidence": 0.65
  }
}
```

**示例4: 使用 deep-research**
```
Action: execute_script
Action Input: {
  "skill_name": "deep-research",
  "args": {
    "query": "象限仪座流星雨的母体小行星",
    "depth": 4,
    "focus_areas": ["天文学家", "彗星残骸"]
  }
}
```

### Skill 使用优先级（必须遵守 - 违反将被系统检测并强制纠正）
- 初次搜索复杂主题 → 使用 **smart-search**（参数: query, entities, strategy）
- 找到候选答案需验证 → 使用 **multi-source-verify**（参数: answer, entities_to_verify）
- 置信度<0.8需深度验证 → 使用 **chain-of-verification**（参数: question, candidate_answer, confidence）
- 需要多步深度研究 → 使用 **deep-research**（参数: query, depth, focus_areas）

### 关键注意事项（不可违反）
1. **args 必须是字典**：{"skill_name": "xxx", "args": {...}}。**绝对禁止**将 JSON 字符串作为 args 的值。
2. **参数名称要准确**：参考上述示例中的参数名
3. **强制执行 Skill 输出**：
   - 收到 `optimized_queries` → 下一步**必须**是 web_search，使用返回的查询
   - 收到 `verification_queries` → **必须**依次执行这些查询
   - 收到任何 Skill 指导 → **禁止**自己编造替代方案
4. **系统监控**：违反规则将被自动检测，系统会强制插入纠正提示
"""
    system_prompt_addition += f"\n\nIMPORTANT: You have a maximum of {max_steps} steps. If you cannot find the exact answer after 5-6 steps, please synthesize the best possible answer from the information you have gathered so far. Do not get stuck in a loop of repeated searches."
    if prompt_messages:
        if prompt_messages[0].get("role") == "system":
            original_content = prompt_messages[0].get("content", "")
            prompt_messages[0] = {"role": "system", "content": f"{original_content}{system_prompt_addition}\n\nREMINDER: Output ONLY the answer string. No explanations. Answer in the SAME LANGUAGE as the question (unless explicitly requested otherwise). Even if uncertain, guess the most likely one."}
        else:
            prompt_messages.insert(0, {"role": "system", "content": f"{DEFAULT_SYSTEM_PROMPT}{system_prompt_addition}\n\nREMINDER: Output ONLY the answer string. No explanations. Answer in the SAME LANGUAGE as the question (unless explicitly requested otherwise). Even if uncertain, guess the most likely one."})
    llm_tools = (tool_functions or []).copy()
    if skills:
        skill_tools = SkillIntegrationTools(skills)
        llm_tools.extend([skill_tools.load_skill_file, skill_tools.execute_script])
    memory = MemoryStore()
    memory.build_index()
    user_query = ""
    for m in reversed(prompt_messages):
        if m.get("role") == "user":
            user_query = str(m.get("content") or "")
            break
    def _extract_core_entities(query: str) -> list:
        try:
            import re as _re
            s = str(query or "")
            # 匹配驼峰命名（如 RepRap）
            camel_case = _re.findall(r'\b([A-Z][a-z]*(?:[A-Z][a-z]*)+)\b', s)
            # 匹配普通大写开头的词（如 Adrian Bowyer）
            latin = _re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b', s)
            # 匹配引号内容
            quoted = _re.findall(r'"([^"]+)"', s) + _re.findall(r"'([^']+)'", s)
            # 匹配连续的英文字母数字组合（如 3D, PDF）
            alphanumeric = _re.findall(r'\b([A-Z0-9]{2,})\b', s)
            # 匹配中文实体（排除疑问词）
            chinese = _re.findall(r'[\u4e00-\u9fff]{2,}', s)
            chinese = [c for c in chinese if c not in {'谁发明', '什么时候', '哪一年', '多少钱', '是什么', '怎么样'}]

            ents = []
            # 优先级：引号 > 驼峰 > 字母数字 > 普通拉丁词 > 中文
            for cand in quoted + camel_case + alphanumeric + latin + chinese:
                c = cand.strip()
                if c and c.lower() not in {"rep","and","or","the","is","are","was","were"} and c not in ents:
                    ents.append(c)
            if not ents and s.strip():
                ents.append(s.strip())
            return ents[:8]
        except Exception:
            return [str(query or "").strip()] if str(query or "").strip() else []
    mem_hits = memory.search(user_query, top_k=4)
    if mem_hits:
        joined = "\n".join([(hit.get("text") or "")[:500] for hit in mem_hits])
        prompt_messages.insert(1, {"role": "system", "content": f"<memory_context>\n{joined}\n</memory_context>"})
        print(f"[Monitoring] memory_context_hits={len(mem_hits)} for_query='{user_query}'")
    ents = _extract_core_entities(user_query)
    if ents:
        prompt_messages.insert(1, {"role": "system", "content": f"Core entities: {', '.join(ents)}. Search precisely for these."})
        print(f"[Monitoring] core_entities_extracted={ents} for_query='{user_query}'")
    tool_schema = [function_to_schema(tool_function) for tool_function in llm_tools]
    tool_functions_map = {func.__name__: func for func in llm_tools}
    state_store = StateStore()
    cid_src = json.dumps(prompt_messages, ensure_ascii=False)
    cid = hashlib.sha256(cid_src.encode("utf-8")).hexdigest()[:16]
    params = {
        "model": "qwen3-max",
        "stream": True,
        "tools": tool_schema,
        "max_tokens": 1024,
        "temperature": 0.4,
    }

    def llm_step(state: dict) -> dict:
        emitted: List[Chunk] = []
        tool_calls_buffer = {}
        stream = client.chat.completions.create(messages=state["messages"], **params)
        for chunk in stream:
            chunk = cast(ChatCompletionChunk, chunk)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                emitted.append(Chunk(type="text", content=delta.content, step_index=state["step_index"]))
                memory.add_short(delta.content)
            if delta.tool_calls:
                for tc_chunk in delta.tool_calls:
                    idx = tc_chunk.index
                    if idx is None:
                        idx = 0
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": tc_chunk.id or f"call_{idx}",
                            "function": {"name": tc_chunk.function.name or "", "arguments": ""},
                        }
                    if tc_chunk.function.name:
                        tool_calls_buffer[idx]["function"]["name"] = tc_chunk.function.name
                    if tc_chunk.function.arguments:
                        tool_calls_buffer[idx]["function"]["arguments"] += tc_chunk.function.arguments
        assistant_tool_calls_data = []
        for idx in sorted(tool_calls_buffer.keys()):
            raw_tool = tool_calls_buffer[idx]
            assistant_tool_calls_data.append(
                {
                    "id": raw_tool["id"],
                    "type": "function",
                    "function": {
                        "name": raw_tool["function"]["name"],
                        "arguments": raw_tool["function"]["arguments"],
                    },
                }
            )
        new_messages = state["messages"][:]
        if assistant_tool_calls_data:
            new_messages.append({"role": "assistant", "tool_calls": assistant_tool_calls_data})
        return {
            **state,
            "pending_tool_calls": assistant_tool_calls_data,
            "had_tool_calls": bool(assistant_tool_calls_data),
            "messages": new_messages,
            "emitted": emitted,
        }

    def execute_tools(state: dict) -> dict:
        emitted: List[Chunk] = state.get("emitted", [])
        new_messages = state["messages"][:]
        meta = state.get("meta") or {"searched_keywords": [], "seen_entities": [], "last_skill_output": None}
        searched_before = set(meta.get("searched_keywords") or [])
        for tool_data in state.get("pending_tool_calls") or []:
            call_id = tool_data["id"]
            func_name = tool_data["function"]["name"]
            func_args_str = tool_data["function"]["arguments"]
            tool_result_content = ""
            parsed_args = {}
            tool_call = ToolCall(tool_call_id=call_id, tool_name=func_name, tool_arguments={})
            try:
                parsed_args = json.loads(func_args_str)
                tool_call.tool_arguments = parsed_args
                emitted.append(Chunk(step_index=state["step_index"], type="tool_call", tool_call=tool_call))
                if func_name == "web_search":
                    q0 = str(parsed_args.get("query") or "")
                    sim_high = False
                    for old in searched_before:
                        ta = set([x for x in q0.lower().split() if x])
                        tb = set([x for x in str(old).lower().split() if x])
                        if ta and tb:
                            inter = len(ta & tb)
                            union = len(ta | tb)
                            if union > 0 and (inter / union) >= 0.7:
                                sim_high = True
                                break
                    if sim_high:
                        ents2 = _extract_core_entities(q0)
                        if ents2:
                            quoted = " ".join([f'"{e}"' for e in ents2[:3]])
                            parsed_args["query"] = f"site:edu OR site:org {quoted}"
                        else:
                            parsed_args["query"] = f'"{q0}" site:edu OR site:org'
                        tool_call.tool_arguments = parsed_args
                        print(f"[Monitoring] web_search_rewrite original='{q0}' rewritten='{parsed_args['query']}' entities={ents2}")
                if func_name in tool_functions_map:
                    func = tool_functions_map[func_name]
                    attempt = 0
                    last_err = None
                    while attempt < 2:
                        try:
                            result = func(**parsed_args)
                            tool_result_content = str(result)
                            last_err = None
                            break
                        except Exception as e:
                            last_err = e
                            time.sleep(0.2 * (attempt + 1))
                            attempt += 1
                    if last_err is not None and not tool_result_content:
                        tool_result_content = f"Error: Execution failed - {str(last_err)}"

                    # 🔥 方案1：强制执行 Skill 输出
                    if func_name == "execute_script":
                        try:
                            skill_name = parsed_args.get("skill_name", "")
                            # 尝试解析 Skill 的输出
                            skill_output = None
                            try:
                                # 从 <stdout> 标签中提取内容
                                import re
                                stdout_match = re.search(r'<stdout>\s*(.*?)\s*</stdout>', tool_result_content, re.DOTALL)
                                if stdout_match:
                                    stdout_content = stdout_match.group(1).strip()
                                    skill_output = json.loads(stdout_content)
                            except:
                                pass

                            if skill_output and isinstance(skill_output, dict):
                                # 保存 Skill 输出到 meta，供后续验证使用
                                meta["last_skill_output"] = {
                                    "skill_name": skill_name,
                                    "output": skill_output,
                                    "step_index": state["step_index"]
                                }

                                # 🔥 强制提示：如果 Skill 返回了优化查询
                                if "optimized_queries" in skill_output:
                                    queries = skill_output["optimized_queries"]
                                    if queries and len(queries) > 0:
                                        hint = f"\n\n[System Enforced]: Skill '{skill_name}' 已生成优化查询。你**必须**使用这些查询执行 web_search，不要自己编造查询词。\n优化查询列表（按优先级排序）：\n"
                                        for i, q in enumerate(queries[:3], 1):
                                            hint += f"  {i}. {q}\n"
                                        hint += f"\n⚠️ 强制要求：下一个 Action **必须**是 web_search，使用上述查询之一。"
                                        tool_result_content += hint
                                        print(f"[Monitoring] skill_enforcement skill={skill_name} queries_count={len(queries)}")

                                # 🔥 强制提示：如果 Skill 返回了验证查询
                                if "verification_queries" in skill_output:
                                    queries = skill_output["verification_queries"]
                                    if queries and len(queries) > 0:
                                        hint = f"\n\n[System Enforced]: Skill '{skill_name}' 已生成验证查询。你**必须**依次执行这些验证查询。\n验证查询列表：\n"
                                        for i, q_obj in enumerate(queries[:3], 1):
                                            if isinstance(q_obj, dict):
                                                purpose = q_obj.get("purpose", "")
                                                query = q_obj.get("query", "")
                                                hint += f"  {i}. [{purpose}] {query}\n"
                                            else:
                                                hint += f"  {i}. {q_obj}\n"
                                        hint += f"\n⚠️ 强制要求：必须依次验证上述查询。"
                                        tool_result_content += hint
                                        print(f"[Monitoring] skill_enforcement skill={skill_name} verification_queries_count={len(queries)}")
                        except Exception as e:
                            print(f"[Monitoring] skill_enforcement_failed: {e}")

                    if func_name == "web_search":
                        if "error" in tool_result_content or "No results" in tool_result_content or "[]" in tool_result_content:
                            tool_result_content += "\n[System Hint]: 搜索结果为空。可能是关键词太长或太具体。请尝试：\n1. 只搜索核心实体名。\n2. 将中文关键词翻译成英文搜索（很多学术/技术内容英文更准）。\n3. 去掉 'site:' 等限制。"
                        try:
                            res_json = json.loads(tool_result_content)
                            if isinstance(res_json, dict) and "results" in res_json:
                                meta["last_search_results"] = res_json["results"]
                        except:
                            pass

                    if func_name == "web_fetch":
                         if "fetch_failed" in tool_result_content or "403" in tool_result_content:
                             print(f"[Monitoring] web_fetch_403_detected url={parsed_args.get('url')}")
                             
                             # 尝试备用策略 1: 从上次搜索结果提取
                             last_results = meta.get("last_search_results")
                             fallback_success = False
                             if last_results:
                                 extracted = extract_answer_from_search_results(last_results, "")
                                 if extracted["candidates"]:
                                     fallback_res = {
                                         "source": "search_metadata_fallback",
                                         "candidates": extracted["candidates"],
                                         "original_error": "403/Fetch Failed"
                                     }
                                     tool_result_content = json.dumps(fallback_res, ensure_ascii=False)
                                     fallback_success = True
                             
                             if not fallback_success:
                                 # 尝试备用策略 2: Edu/Gov -> Wiki
                                 url = parsed_args.get("url", "")
                                 try:
                                     domain = urllib.parse.urlparse(url).netloc
                                     if "edu" in domain or "gov" in domain:
                                         target = url.split('/')[-1].replace('-', ' ').replace('_', ' ')
                                         alt_query = f'"{target}" site:wikipedia.org OR site:imdb.com'
                                         print(f"[Monitoring] 403_fallback_trigger query='{alt_query}'")
                                         if "web_search" in tool_functions_map:
                                             ws_res = tool_functions_map["web_search"](query=alt_query)
                                             tool_result_content = ws_res
                                             fallback_success = True
                                 except Exception as e:
                                     print(f"[Monitoring] 403_fallback_error: {e}")

                             if not fallback_success:
                                 tool_result_content += "\n[System Hint]: 网页抓取失败。请尝试搜索该信息的其他来源（其他网站），不要再次尝试同一个 URL。"
                else:
                    tool_result_content = f"Error: Tool '{func_name}' not found."
            except json.JSONDecodeError as e:
                tool_result_content = f"Error: Failed to parse tool arguments JSON: {func_args_str}. Error: {e}"
                emitted.append(Chunk(step_index=state["step_index"], type="tool_call", tool_call=tool_call))
            except Exception as e:
                tool_result_content = f"Error: Execution failed - {str(e)}"
            emitted.append(Chunk(type="tool_call_result", tool_result=tool_result_content, step_index=state["step_index"], tool_call=tool_call))
            new_messages.append({"role": "tool", "tool_call_id": call_id, "content": tool_result_content})
            memory.add_short(tool_result_content)
            memory.add_long(tool_result_content)
            if func_name == "web_search":
                q = str(parsed_args.get("query") or "")
                if q:
                    if q not in meta["searched_keywords"]:
                        meta["searched_keywords"].append(q)
                        print(f"[Monitoring] search_keyword_added step_index={state['step_index']} query='{q}'")
        return {
            **state,
            "messages": new_messages,
            "emitted": emitted,
            "pending_tool_calls": [],
            "step_index": state["step_index"] + 1,
            "meta": meta,
        }

    def update_memory(state: dict) -> dict:
        return {**state}

    def persist_state(state: dict) -> dict:
        dump = {
            "cid": cid,
            "step_index": state["step_index"],
            "short_memory": memory.short,
            "messages_len": len(state["messages"]),
        }
        state_store.save(cid, dump)
        return {**state}

    def memory_query(query: str, top_k: int = 5) -> str:
        hits = memory.search(query, top_k=top_k)
        return json.dumps({"results": hits}, ensure_ascii=False)

    llm_tools.append(memory_query)
    tool_schema = [function_to_schema(tool_function) for tool_function in llm_tools]
    tool_functions_map = {func.__name__: func for func in llm_tools}

    g = StateGraph(dict)
    g.add_node("llm_step", llm_step)
    g.add_node("execute_tools", execute_tools)
    g.add_node("update_memory", update_memory)
    g.add_node("persist_state", persist_state)
    g.add_edge("__start__", "llm_step")
    g.add_edge("llm_step", "execute_tools")
    g.add_edge("execute_tools", "update_memory")
    g.add_edge("update_memory", "persist_state")
    g.add_edge("persist_state", END)
    graph = g.compile()

    state = {"messages": prompt_messages, "step_index": 0, "pending_tool_calls": [], "meta": {"searched_keywords": [], "seen_entities": []}, "reflection_injected": False, "reflexion_count": 0}
    while state["step_index"] < max_steps:
        state = graph.invoke(state)
        if (state.get("meta") or {}).get("searched_keywords") and state["step_index"] > 0 and (state["step_index"] % 3 == 0):
            kws = (state.get("meta") or {}).get("searched_keywords") or []
            state["messages"].append({"role": "system", "content": f"Reflection step: attempted keywords: {', '.join(kws[-6:])}. Avoid repeating similar queries. Prefer precise entities and advanced operators (site:edu OR site:org, filetype:pdf). If relevance remains low, synthesize best answer so far."})
            print(f"[Monitoring] reflection_step_inserted step_index={state['step_index']} keywords={kws[-6:]}")
        # if state["step_index"] >= 10:
        #    break
        for ch in state.get("emitted") or []:
            yield ch
        if not state.get("had_tool_calls"):
            # --- Reflexion 机制 ---
            last_msg = state["messages"][-1]
            content = str(last_msg.get("content") or "")
            reflexion_msg = ""
            needs_reflexion = False
            
            # [System Enforced] 最小搜索深度检查
            searched_kws = (state.get("meta") or {}).get("searched_keywords") or []
            search_count = len(searched_kws)
            if search_count < 10 and state.get("reflexion_count", 0) < 5:
                # 如果是明确的"无法回答"或"不知道"，也强制重试一次
                is_giving_up = any(phrase in content.lower() for phrase in ["cannot find", "unable to", "don't know", "无法", "不知道"])
                
                if is_giving_up:
                     reflexion_msg = f"Reflexion: [System Enforced] 你似乎想放弃，但搜索次数不足 ({search_count}/10)。请尝试更换关键词（例如用英文搜索、拆分实体）再试一次。"
                     needs_reflexion = True
                else:
                     reflexion_msg = f"Reflexion: [System Enforced] 目前仅进行了 {search_count} 次搜索。对于已有把握的题目，请确保至少验证 10 次；若仍不确定，请继续寻找证据。"
                     needs_reflexion = True

            elif "Final Answer:" in content:
                final_ans = content.split("Final Answer:")[-1].strip()
                # 检查点 1: 答案是否为空或太短
                if len(final_ans) < 2 and state.get("reflexion_count", 0) < 2:
                    reflexion_msg = "Reflexion: 你的答案太短或为空。请重新检查之前的 Observation，如果找不到信息，请尝试用英文搜索关键词。"
                    needs_reflexion = True
                # 检查点 2: 答案格式校验 (针对数字/年份题)
                elif ("年份" in user_query or "多少" in user_query) and not any(c.isdigit() for c in final_ans):
                    if state.get("reflexion_count", 0) < 2:
                        reflexion_msg = "Reflexion: 用户询问的是数字/年份，但你的答案中不包含数字。请重新检索或从文中提取准确数值。"
                        needs_reflexion = True
                
                # 检查点 3: 不确定性检查 (如果搜索步数还充裕)
                # 如果答案包含不确定性词汇，且搜索次数未达到 25 次，且 Reflexion 次数 < 5，强制继续搜索
                elif search_count < 25 and state.get("reflexion_count", 0) < 5:
                    uncertainty_keywords = ["可能", "probably", "unconfirmed", "not found", "unknown", "未找到", "无法确认", "suggests", "likely"]
                    if any(k in final_ans.lower() for k in uncertainty_keywords):
                        reflexion_msg = f"Reflexion: 你的答案包含不确定性词汇 ('{final_ans[:20]}...')。请继续搜索验证，尝试查找更多来源以确认答案。"
                        needs_reflexion = True
            
            # [Fix] 如果 LLM 输出了答案但没有使用 "Final Answer:" 前缀，或者输出格式混乱
            # 强制检测：如果这是最后一步 (max_steps reached or explicit stop)，但没有检测到 Final Answer
            # 但这里我们是在 loop 内部。run_batch 会在 loop 结束后提取。
            # 问题是 run_batch 可能在 generator 结束前就认为结束了？不，它 iterate 直到结束。
            # 关键：如果 LLM 在最后一步没有输出文本，或者文本被 tool calls 淹没。
            
            if needs_reflexion:
                state["messages"].append({"role": "user", "content": reflexion_msg})
                state["reflexion_count"] = state.get("reflexion_count", 0) + 1
                state["step_index"] += 1
                print(f"[Monitoring] Reflexion triggered: {reflexion_msg}")
                continue

            # 如果没有触发 Reflexion，且已经有 Final Answer，或者步数已满，循环自然结束
            # 如果没有 Final Answer 且步数未满，继续循环 (LLM 会继续生成)
            # 但如果 LLM 输出了 "Final Answer: xxx" 并且没有触发 needs_reflexion，我们应该 break 吗？
            # 是的，为了避免死循环或多余输出。
            if "Final Answer:" in content and not needs_reflexion:
                 print(f"[Monitoring] Answer found and verified, stopping loop.")
                 break
                 
            break
    final_messages = state["messages"][:]
    s = str(user_query or "")
    
    # 1. Check for explicit English request
    explicit_en = re.search(r"(answer|respond|output|provide).*(in|with).*english", s, re.IGNORECASE) or \
                  re.search(r"english (name|title|version)", s, re.IGNORECASE) or \
                  re.search(r"(英文|英语)(名|全名|称|回答|输出)", s)
                  
    # 2. Check for explicit Chinese request
    explicit_cn = re.search(r"(answer|respond|output|provide).*(in|with).*chinese", s, re.IGNORECASE) or \
                  re.search(r"chinese (name|title|version)", s, re.IGNORECASE) or \
                  re.search(r"(中文|汉语)(名|全名|称|回答|输出)", s)
    
    # 3. Determine prompt language
    use_cn_prompt = False
    
    if explicit_cn:
        use_cn_prompt = True
    elif explicit_en:
        use_cn_prompt = False
    else:
        # Fallback to character detection
        has_cn = any("\u4e00" <= ch <= "\u9fff" for ch in s)
        use_cn_prompt = has_cn

    if use_cn_prompt:
        system_content = f"""现在请基于已检索与已抓取的内容，给出简洁明确的最终答案。
1. **只输出答案文本**，不要解释过程，不要包含"Answer is"等前缀。
2. **禁止放弃**：即使信息不完全，也必须根据现有线索推断最可能的答案。**绝对禁止**输出"未找到"、"无法确认"、"Unknown"、"I don't know"等放弃性语句。
3. **语言一致性**：请用中文回答。
4. 如果有多个候选，选择可能性最高的一个。"""
    else:
        system_content = f"""Based on the retrieved and fetched content, please provide a concise and clear final answer.
1. **Output ONLY the answer text**, do not explain the process, do not include prefixes like "Answer is".
2. **DO NOT GIVE UP**: Even if information is incomplete, you must infer the most likely answer based on existing clues. **ABSOLUTELY FORBIDDEN** to output "Not found", "Unable to confirm", "Unknown", "I don't know", etc.
3. **Language Consistency**: Please answer in English.
4. If there are multiple candidates, choose the most likely one."""

    final_messages.insert(
        0,
        {
            "role": "system",
            "content": system_content,
        },
    )
    params2 = {
        "model": "qwen3-max",
        "stream": True,
        "max_tokens": 1024,
        "temperature": 0.2,
    }
    try:
        stream2 = client.chat.completions.create(messages=final_messages, **params2)
        final_emitted = False
        full_ans = ""
        for chunk in stream2:
            chunk = cast(ChatCompletionChunk, chunk)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                # Accumulate but DO NOT yield yet, because we need to verify/clean
                full_ans += delta.content
        
        # Verify and Clean
        if full_ans:
            try:
                # Local import to avoid circular dependency
                from agent import clean_answer, verify_answer
                
                # 1. Clean format
                cleaned_ans = clean_answer(full_ans)
                
                # 2. Verify content (LLM check)
                verified_ans = verify_answer(user_query, cleaned_ans)
                
                # 3. Final clean
                final_ans_str = clean_answer(verified_ans)
                
                if final_ans_str:
                    full_ans = final_ans_str
                    
                print(f"[Monitoring] Final Answer Processed: '{full_ans}'")
                
            except Exception as e:
                print(f"[Warn] Verification failed: {e}")
                
            # Now yield the final verified answer
            yield Chunk(type="text", content=full_ans, step_index=state["step_index"])
            final_emitted = True

        if full_ans:
             searched_kws = (state.get("meta") or {}).get("searched_keywords") or []
             last_res = (state.get("meta") or {}).get("last_search_results") or []
             conf = calculate_confidence_impl(full_ans, searched_kws, last_res)
             print(f"[Monitoring] Answer Confidence: {conf} (Answer length: {len(full_ans)})")

        if not final_emitted and not full_ans:
            # yield Chunk(step_index=state["step_index"], type="text", content="未检索到明确答案。")
            pass
    except Exception as e:
        print(f"[Monitoring] Final synthesis failed: {e}")
        # 只有在完全没有输出的情况下才返回兜底文案，避免拼接
        if not full_ans:
             # yield Chunk(step_index=state["step_index"], type="text", content="未检索到明确答案。")
             pass

if __name__ == "__main__":
    import asyncio
    import sys
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)
    
    # Import tools from agent.py (must be after defining agent_loop to avoid circular import)
    # But since agent.py imports agent_loop, we need to be careful.
    # Actually, we can define the tool list here or import them inside main.
    
    async def main():
        if len(sys.argv) < 2:
            print("Usage: python agent_loop.py \"your question\"")
            return
            
        question = sys.argv[1]
        
        # Import tools inside main to avoid circular import issues
        import agent
        tools = [
            agent.web_search, 
            agent.web_fetch, 
            agent.browse_page, 
            agent.extract_entities, 
            agent.x_keyword_search, 
            agent.search_pdf_attachment, 
            agent.browse_pdf_attachment, 
            agent.multi_hop_search, 
            agent.get_weather
        ]
        
        messages = [{"role": "user", "content": question}]
        result = ""
        
        print(f"--- Question: {question} ---")
        async for chunk in agent_loop(messages, tools, max_steps=15):
            if chunk.type == "text" and chunk.content:
                print(chunk.content, end="", flush=True)
                result += chunk.content
            elif chunk.type == "tool_call":
                print(f"\n[Tool Call] {chunk.tool_call.tool_name}({json.dumps(chunk.tool_call.tool_arguments, ensure_ascii=False)})")
            elif chunk.type == "tool_call_result":
                print(f"[Tool Result] {str(chunk.tool_result)[:100]}...")
        
        # Clean answer
        final_answer = agent.clean_answer(result)
        # Verify answer
        final_answer = agent.verify_answer(question, final_answer)
        
        print(f"\n\n--- Final Answer ---\n{final_answer}")

    if len(sys.argv) > 1:
        asyncio.run(main())
    else:
        print("Usage: python agent_loop.py \"your question\"")
