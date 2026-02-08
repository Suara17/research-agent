from src.tools.tools import AsyncTool, ToolResult
from src.registry import TOOL

@TOOL.register_module(name="planning_tool")
class PlanningTool(AsyncTool):
    name = "planning_tool"
    description = "A planning tool that can plan the steps to complete the task."
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task to plan"
            }
        },
        "required": ["task"]
    }
    output_type = "string"

    async def forward(self, task: str) -> ToolResult:
        return ToolResult(output=f"Plan for: {task}")
