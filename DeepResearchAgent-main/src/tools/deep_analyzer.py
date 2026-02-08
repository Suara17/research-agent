from src.tools.tools import AsyncTool, ToolResult
from src.models import model_manager
from src.registry import TOOL

@TOOL.register_module(name="deep_analyzer_tool")
class DeepAnalyzerTool(AsyncTool):
    name = "deep_analyzer_tool"
    description = "A deep analyzer tool that can perform systematic, step-by-step analysis."
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The analysis task to perform"
            }
        },
        "required": ["task"]
    }
    output_type = "string"

    def __init__(self, analyzer_model_ids=None, summarizer_model_id=None):
        super().__init__()
        self.analyzer_model_ids = analyzer_model_ids or ["qwen-max"]
        self.summarizer_model_id = summarizer_model_id or "qwen-max"

    async def forward(self, task: str) -> ToolResult:
        # Placeholder implementation - in real usage this would call the agent logic
        # Since this tool is usually wrapping an agent or model call
        return ToolResult(output=f"Analysis for: {task}")
