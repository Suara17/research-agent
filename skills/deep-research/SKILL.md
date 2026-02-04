---
name: deep-research
description: Use when the user asks a complex question that requires multi-step research or when initial search results are insufficient.
---

# Deep Research Strategy

## Goal
To answer complex questions by performing deep research, verifying information from multiple sources, and extracting detailed evidence.

## Workflow

1.  **Analyze the Request**: Identify the core entities, relationships, and specific facts needed.
2.  **Initial Search**: Use `web_search` to get an overview and identify potential high-quality sources.
3.  **Source Selection & Fetching**:
    *   Identify promising URLs from the search results (e.g., official docs, news articles, encyclopedias).
    *   Use `web_fetch` to retrieve the full content of these pages.
4.  **Evidence Extraction**:
    *   Read the fetched content.
    *   Extract specific facts, dates, names, or numbers that answer the user's question.
    *   *Self-Correction*: If the fetched page doesn't contain the info, go back to step 2 with a refined query.
5.  **Synthesis**: Combine the extracted evidence into a coherent answer.

## Tips
*   **Refine Queries**: If "weather in Beijing" fails, try "Beijing weather report 2024" or "China Meteorological Administration Beijing".
*   **Verify Facts**: If two sources conflict, search for a third source or prioritize the more official one.
*   **Be Precise**: When answering "who" or "what", provide the exact name or entity, not a vague description.

## Constraints
*   Do not invent information. If you can't find it after multiple attempts, admit it.
*   Keep the final answer in the user's language.
