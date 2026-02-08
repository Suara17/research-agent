from dataclasses import dataclass
from typing import Optional, Literal, Any

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
