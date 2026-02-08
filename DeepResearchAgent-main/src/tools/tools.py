from pydantic import BaseModel
from typing import Any, Optional, Dict, Union
import inspect
import asyncio

class ToolResult(BaseModel):
    output: Optional[str] = None
    error: Optional[str] = None
    system: Optional[str] = None
    
    def __str__(self):
        if self.error:
            return f"Error: {self.error}"
        return str(self.output)

class Tool:
    name: str
    description: str
    parameters: dict
    
    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)

    def forward(self, *args, **kwargs):
        raise NotImplementedError

class AsyncTool(Tool):
    async def __call__(self, *args, **kwargs):
        return await self.forward(*args, **kwargs)

    async def forward(self, *args, **kwargs):
        raise NotImplementedError

def make_tool_instance(tool_cls, **kwargs):
    return tool_cls(**kwargs)
