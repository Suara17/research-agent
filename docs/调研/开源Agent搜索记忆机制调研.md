# 开源 Agent 网络搜索与记忆机制调研

## 一、网络搜索实现

### 1.1 主流实现方式

| 方案 | 项目示例 | 特点 |
|------|----------|------|
| **Tavily** | langgraph-ai-agent | 专业AI搜索API，结果质量高 |
| **DuckDuckGo** | agentic_search_openai_langgraph | 免费，支持Search API |
| **Serper** | 自定义实现 | Google搜索结果，价格适中 |
| **SearXNG** | 自定义部署 | 开源，可自托管 |
| **组合方案** | 你的项目 | 多引擎fallback |

### 1.2 LangGraph 官方推荐方式

```python
# 方式1: 使用 prebuilt create_react_agent
from langgraph.prebuilt import create_react_agent
from langchain_community.tools import TavilySearchResults

# 创建搜索工具
search_tool = TavilySearchResults(max_results=5)

# 创建Agent
agent = create_react_agent(
    llm,
    [search_tool],
    state_modifier="You are a helpful research assistant."
)

# 执行
result = agent.invoke({"messages": [("user", "What is the weather?")]})
```

```python
# 方式2: 自定义 StateGraph
from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)
workflow.add_node("search", search_node)
workflow.add_node("reason", reason_node)
workflow.add_conditional_edges("reason", should_continue, {...})
```

### 1.3 开源项目搜索实现特点

| 项目 | 搜索策略 | 特点 |
|------|----------|------|
| [john-adeojo/graph_websearch_agent](https://github.com/john-adeojo/graph_websearch_agent) | LangGraph + Tavily | 简洁，基于官方模式 |
| [nitesh-lng/langgraph-ai-agent](https://github.com/Nitesh-lng/langgraph-ai-agent) | Groq + Tavily | 快速，便宜 |
| [menonpg/agentic_search_openai_langgraph](https://github.com/menonpg/agentic_search_openai_langgraph) | Tavily + DuckDuckGo | 双引擎fallback |
| [nicolasbahindwa/Research-AI-Assistant](https://github.com/nicolasbahindwa/Research-AI-Assistant) | 多Provider | 支持多种搜索源 |

### 1.4 常见优化策略

1. **并行搜索**：多个搜索引擎同时查询
2. **结果缓存**：避免重复搜索相同query
3. **结果重排序**：使用embedding相似度排序
4. **Snippet增强**：搜索结果附带网页摘要

---

## 二、记忆机制实现

### 2.1 主流方案

| 类型 | 实现方式 | 适用场景 |
|------|----------|----------|
| **短期记忆** | LangGraph Checkpoint | 会话状态保存 |
| **长期记忆** | Vector Store (RAG) | 跨会话知识 |
| **混合记忆** | 分层存储 + JIT检索 | 综合场景 |

### 2.2 开源记忆系统

| 项目 | Stars | 特点 |
|------|-------|------|
| [MemMachine/MemMachine](https://github.com/MemMachine/MemMachine) | 4520 | 通用记忆层，跨会话 |
| [VectorSpaceLab/general-agentic-memory](https://github.com/VectorSpaceLab/general-agentic-memory) | 809 | GAM系统，JIT检索 |
| [orneryd/Mimir](https://github.com/orneryd/Mimir) | - | 向量搜索+多Agent |
| [RecaEngine/RECA](https://github.com/RecaEngine/RECA) | 140 | 轻量，实时recall |

### 2.3 LangGraph 官方记忆

```python
# 方式1: Checkpoint (短期记忆)
from langgraph.checkpoint.memory import MemorySaver

# 创建持久化检查点
checkpointer = MemorySaver()

# 编译图时传入
graph = workflow.compile(checkpointer=checkpointer)

# 恢复状态
config = {"configurable": {"thread_id": "123"}}
result = graph.get_state(config)
```

```python
# 方式2: LangChain Memory + Vector Store
from langchain.memory import ConversationBufferMemory
from langchain_community.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings

# 向量记忆
vectorstore = FAISS.from_documents(docs, OpenAIEmbeddings())
retriever = vectorstore.as_retriever()

# 对话记忆
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)
```

### 2.4 典型记忆架构

```
┌─────────────────────────────────────────────────────┐
│                   Agent State                        │
├─────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │  Working    │  │  Short-term │  │ Long-term  │ │
│  │  Memory     │  │  Memory     │  │ Memory     │ │
│  │  (当前上下文) │  │  (Checkpt)  │  │ (Vector)  │ │
│  └─────────────┘  └─────────────┘  └────────────┘ │
│         ↑                ↑                ↑       │
│         └───────────────┴────────────────┘        │
│                    Memory Manager                  │
│         (JIT检索 + 重要性排序 + 压缩)             │
└─────────────────────────────────────────────────────┘
```

---

## 三、你的项目对比分析

### 3.1 搜索模块

| 方面 | 你的项目 | 主流方案 |
|------|----------|----------|
| 多引擎 | SearXNG/Serper/Baidu/DDGS | Tavily + DuckDuckGo |
| 并行策略 | 串行优先→fallback | 并行竞争 |
| 内容增强 | 可选 | 搜索即返回摘要 |
| **差距** | 可借鉴 Tavily 质量 | - |

### 3.2 记忆模块

| 方面 | 你的项目 | 主流方案 |
|------|----------|----------|
| 短期记忆 | FIFO队列 + BM25 | Checkpoint + 语义 |
| 长期记忆 | JSONL文件 | Vector Store |
| 检索 | BM25 | Embedding + 向量 |
| **差距** | 语义理解弱 | 可用MemMachine |

---

## 四、可借鉴的实现

### 4.1 推荐集成 Tavily

```python
# 安装
pip install langchain-community tavily

# 使用
from langchain_community.tools import TavilySearchResults

tool = TavilySearchResults(
    max_results=5,
    include_answer=True,
    include_raw_content=True
)

# Agent中使用
agent = create_react_agent(llm, [tool, ...])
```

### 4.2 推荐集成 LangGraph Checkpoint

```python
# 短期记忆
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()

# 图编译
agent = workflow.compile(checkpointer=checkpointer)

# 恢复
state = agent.get_state(config={"configurable": {"thread_id": "user_123"}})
```

### 4.3 推荐集成向量记忆

```python
# 长期记忆
from langchain_community.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings

vectorstore = Chroma.from_documents(
    documents=docs,
    embedding=HuggingFaceEmbeddings(model="sentence-transformers/all-MiniLM-L6-v2")
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
```

---

## 五、总结

### 5.1 搜索优化方向

1. **集成Tavily**：专业AI搜索，质量更高
2. **并行竞争**：多引擎同时查询，取最快/最佳
3. **结果缓存**：避免重复搜索

### 5.2 记忆优化方向

1. **Checkpoint**：替换FIFO队列为LangGraph原生
2. **向量检索**：长期记忆用embedding
3. **分层管理**：短期→长期→JIT检索

### 5.3 参考项目

- 搜索参考: [menonpg/agentic_search_openai_langgraph](https://github.com/menonpg/agentic_search_openai_langgraph)
- 记忆参考: [MemMachine/MemMachine](https://github.com/MemMachine/MemMachine)
- 整体架构: [langgraph-ai/langgraph](https://github.com/langchain-ai/langgraph)
