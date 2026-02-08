from src.tools.tools import AsyncTool, ToolResult
from src.registry import TOOL
import sys
import io

@TOOL.register_module(name="python_interpreter_tool")
class PythonInterpreterTool(AsyncTool):
    name = "python_interpreter_tool"
    description = "Execute python code."
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The python code to execute"
            }
        },
        "required": ["code"]
    }
    output_type = "string"

    async def forward(self, code: str) -> ToolResult:
        try:
            # Basic safe execution environment
            # Note: In production, use a sandboxed environment
            old_stdout = sys.stdout
            redirected_output = sys.stdout = io.StringIO()
            
            exec(code, {}, {})
            
            sys.stdout = old_stdout
            return ToolResult(output=redirected_output.getvalue())
        except Exception as e:
            return ToolResult(error=str(e))
