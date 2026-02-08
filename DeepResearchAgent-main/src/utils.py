import os
import json
import base64
import requests
from io import BytesIO

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

def assemble_project_path(path: str) -> str:
    """Get absolute path relative to project root"""
    if os.path.isabs(path):
        return path
    # Assuming this is called from within src/utils.py, project root is one level up (src/..)
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(root, path)

def _is_package_available(pkg_name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(pkg_name) is not None

def encode_image_base64(image_input) -> str:
    """
    Encode an image to base64 string.
    Input can be a file path, a PIL Image, or bytes.
    """
    try:
        if isinstance(image_input, str):
            if os.path.isfile(image_input):
                with open(image_input, "rb") as image_file:
                    return base64.b64encode(image_file.read()).decode('utf-8')
        elif isinstance(image_input, bytes):
            return base64.b64encode(image_input).decode('utf-8')
        # Handle PIL Image if pillow is available (though we are removing it)
        elif hasattr(image_input, "save"): 
            buffered = BytesIO()
            image_input.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception:
        pass
    return ""

def make_image_url(base64_image: str) -> str:
    return f"data:image/jpeg;base64,{base64_image}"

from dataclasses import dataclass
from typing import Optional

@dataclass
class AgentText:
    text: str
    source: Optional[str] = None

@dataclass
class AgentImage:
    path: Optional[str] = None
    url: Optional[str] = None

@dataclass
class AgentAudio:
    path: Optional[str] = None
    url: Optional[str] = None

def parse_json_blob(text: str) -> tuple[dict, str]:
    """
    Parse a JSON blob from text.
    Returns (parsed_dict, error_message).
    """
    try:
        # Try finding JSON block
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            json_str = text[start:end+1]
            return json.loads(json_str), ""
        return {}, "No JSON found"
    except Exception as e:
        return {}, str(e)

def escape_code_brackets(text: str) -> str:
    """Escape brackets in text for rich library compatibility"""
    return text.replace("[", "\\[").replace("]", "\\]")

def make_json_serializable(obj):
    """Recursively convert object to JSON serializable format."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [make_json_serializable(x) for x in obj]
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return make_json_serializable(obj.__dict__)
    return str(obj)

def truncate_content(content: str, max_length: int) -> str:
    if len(content) <= max_length:
        return content
    return content[:max_length] + "...[truncated]"

def parse_code_blobs(text: str) -> list[str]:
    """Parse code blocks from markdown text."""
    # Simple regex for ```python ... ```
    import re
    return re.findall(r"```python\n(.*?)\n```", text, re.DOTALL)

def extract_code_from_text(text: str) -> str:
    blobs = parse_code_blobs(text)
    if blobs:
        return blobs[0]
    return ""

def is_valid_name(name: str) -> bool:
    return name.isidentifier()

def make_init_file(path: str):
    pass

def handle_agent_output_types(output):
    return output

BASE_BUILTIN_MODULES = [
    "collections",
    "datetime",
    "itertools",
    "math",
    "random",
    "re",
    "statistics",
    "string",
    "time",
    "json",
]
