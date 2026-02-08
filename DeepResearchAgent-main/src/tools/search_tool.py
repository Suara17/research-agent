from src.tools.tools import AsyncTool, ToolResult
from duckduckgo_search import DDGS
import asyncio

class SearchTool(AsyncTool):
    name: str = "search_tool"
    description: str = "Search the web for information using DuckDuckGo."
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query to search for.",
            },
        },
        "required": ["query"],
    }

    async def forward(self, query: str) -> ToolResult:
        try:
            # Use run_in_executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, lambda: DDGS().text(query, max_results=5))
            
            if not results:
                return ToolResult(output="No results found.")
                
            output = ""
            for r in results:
                output += f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}\n\n"
            return ToolResult(output=output)
        except Exception as e:
            return ToolResult(error=f"Search failed: {str(e)}")
