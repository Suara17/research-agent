# Research Agent 开发指南 (天池大赛规范版)

本指南基于 [算法大赛-天池大赛-阿里云的赛制.md](file:///e:/Research_Agent/算法大赛-天池大赛-阿里云的赛制.md) 编写，旨在帮助开发者在 PAI-LangStudio 平台上构建符合赛制要求的 Research Agent。

---

## **1. 核心开发规范 (红线)**

在开发过程中，必须严格遵守以下约束，否则将导致成绩无效：

- **禁止模型微调**：不允许使用 LoRA、Adapter 或任何形式的自训练权重。
- **指定模型范围**：仅允许使用通过 **阿里云百炼** 提供的 Qwen 系列模型或 PAI Model Gallery 部署的 Qwen 基础模型。
- **禁止硬编码**：严禁在代码、提示词或配置中硬编码评测题答案。
- **工具使用限制**：允许使用搜索引擎（如阿里云 IQS、SerpAPI、Bing）和 MCP，但 **禁止调用任何第三方 Agent 服务**。所有 Agent 逻辑必须在项目包内实现。
- **关于框架使用**：允许使用 LangChain、AutoGPT 等开源框架或库来构建逻辑，前提是所有代码必须包含在交付的项目包中，且不得调用外部托管的 Agent API 服务。

---

## **2. 模型配置 (阿里云百炼)**

为了使 Agent 能够调用 Qwen 模型，需要进行以下配置：

### **2.1 环境变量**
在 PAI 平台或本地环境中设置：
- `DASHSCOPE_API_KEY`: 你的阿里云百炼 API Key。

### **2.2 SDK 调用配置 (OpenAI 兼容方式)**
项目建议使用 OpenAI SDK 进行兼容调用。在 [agent_loop.py](file:///e:/Research_Agent/agent_loop.py) 中已实现如下配置：

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
)

# 推荐模型：qwen-plus (平衡性能与速度), qwen-max (最强推理)
params = {
    "model": "qwen-plus",
    "stream": True,
}
```

---

## **3. 交付物要求**

### **第一阶段 (截止 2026-03-09)**
- **验证集结果**：保存为 `question.jsonl`，格式如下：
  ```json
  {"id": 0, "answer": "纯文本答案"}
  ```

### **第二阶段 (截止 2026-03-09)**
- **EAS 服务**：部署成功的公网 Endpoint 与 Bearer Token。
- **LangStudio 项目包**：从 LangStudio 导出的应用流 ZIP 文件。
- **README 文档**：存放在 ZIP 包内，包含架构设计、依赖说明及复现步骤。

---

## **3. 架构设计与实现 (基于本项目)**

### **3.1 核心逻辑：ReAct 模式**
项目采用 ReAct (Reasoning and Acting) 模式。核心循环实现在 [agent_loop.py](file:///e:/Research_Agent/agent_loop.py) 中：
1. **思考 (Thought)**：LLM 分析问题并决定是否需要调用工具。
2. **行动 (Action)**：执行指定的 Python 函数或技能脚本。
3. **观察 (Observation)**：获取工具执行结果并反馈给 LLM。

### **3.2 工具集成 (Tools)**
在 [agent.py](file:///e:/Research_Agent/agent.py) 中定义 Python 函数作为工具。工具必须包含：
- **类型提示**：明确参数和返回值类型。
- **Docstring**：详细描述函数功能，供 LLM 识别调用时机。

### **3.3 技能扩展 (Skills)**
遵循 [Agent Skills](https://agentskills.io) 规范。
- 目录：`skills/`
- 结构：每个技能包含一个 `SKILL.md` (元数据和指令) 及可选的 `scripts/`。
- 优点：模块化管理复杂指令，支持动态加载。

---

## **4. 接口规范 (EAS 部署)**

部署到 EAS 后，必须提供符合以下格式的 API：

- **Endpoint**: `POST /` 或 `POST /stream` (流式)
- **输入格式**:
  ```json
  { "question": "Where is the capital of France?" }
  ```
- **输出格式**:
  ```json
  { "answer": "巴黎" }
  ```
- **答案要求**: 必须为纯文本，且与问题语言保持一致。

---

## **5. 本地测试与部署流**

1. **环境配置**：
   - 设置环境变量 `DASHSCOPE_API_KEY`。
   - 安装依赖：`pip install -r requirements.txt` (如有)。
2. **启动本地服务**：
   ```bash
  python agent.py
  ```
3. **验证结果**：
   运行验证脚本读取 `question.jsonl`，调用本地接口生成答案并校验格式。
4. **部署 EAS**：
   在 LangStudio 中点击“部署”，选择 EAS 环境，获取 Endpoint 和 Token。

---

*注意：请确保 EAS 服务逻辑与提交的 LangStudio 项目包完全一致。*
