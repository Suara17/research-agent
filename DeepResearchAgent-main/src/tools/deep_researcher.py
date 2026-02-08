from src.tools.tools import AsyncTool, ToolResult
from src.registry import TOOL

@TOOL.register_module(name="deep_researcher_tool")
class DeepResearcherTool(AsyncTool):
    name = "deep_researcher_tool"
    description = "A deep researcher tool that can conduct extensive web searches."
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The research task to perform"
            }
        },
        "required": ["task"]
    }
    output_type = "string"

    def __init__(self, model_id=None, max_depth=2, max_insights=20, time_limit_seconds=60, max_follow_ups=3):
        super().__init__()
        self.model_id = model_id or "qwen-max"

    async def forward(self, task: str) -> ToolResult:
        return ToolResult(output=f"Researching: {task}")
