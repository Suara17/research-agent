from src.tools.tools import Tool, ToolResult

class FinalAnswerTool(Tool):
    name = "final_answer"
    description = "Provides the final answer to the user."
    parameters = {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The final answer"
            }
        },
        "required": ["answer"]
    }
    output_type = "string"

    def forward(self, answer: str) -> ToolResult:
        return ToolResult(output=str(answer))

TOOL_MAPPING = {
    "final_answer": FinalAnswerTool
}
