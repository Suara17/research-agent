import os
import sys
import re
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from argparse import Namespace
import asyncio

# Ensure src is in python path
root = str(Path(__file__).resolve().parents[0])
sys.path.append(root)

from src.logger import logger
from src.config import config
from src.models import model_manager
from src.agent import create_agent

app = FastAPI()

class QueryRequest(BaseModel):
    question: str

AGENT_INSTANCE = None

def clean_answer(raw_answer: str) -> str:
    """
    Clean the agent's output to extract the final answer.
    Ported from research_agent/utils.py
    """
    if not raw_answer:
        return ""
    
    # 0. Extract content after "Final Answer:"
    final_answer_match = re.search(r"Final Answer[:：]\s*(.*)", raw_answer, re.IGNORECASE | re.DOTALL)
    if final_answer_match:
        extracted = final_answer_match.group(1).strip()
        if extracted:
            raw_answer = extracted
            # Remove trailing "Thought:" if any
            thought_match = re.search(r"(.*?)Thought[:：]", raw_answer, re.IGNORECASE | re.DOTALL)
            if thought_match:
                raw_answer = thought_match.group(1).strip()

    # 1. Remove Markdown code blocks
    clean = re.sub(r'```\w*', '', raw_answer)
    clean = clean.replace('```', '')
    clean = clean.replace('`', '').strip()
    
    # 2. Try parsing JSON if applicable (omitted for now as we want text)
    
    return clean

@app.on_event("startup")
async def startup_event():
    global AGENT_INSTANCE
    logger.info("Initializing Agent Service...")
    
    # Initialize configuration
    config_path = os.path.join(root, "configs", "config_main.py")
    args = Namespace(config=config_path, cfg_options=None)
    
    config.init_config(config_path, args)
    logger.init_logger(log_path=config.log_path)
    
    # Initialize models
    # use_local_proxy=True matches main.py behavior
    model_manager.init_models(use_local_proxy=True)
    
    # Create agent
    AGENT_INSTANCE = await create_agent(config)
    logger.info("Agent initialized successfully.")

@app.post("/")
async def run_agent(request: QueryRequest):
    global AGENT_INSTANCE
    if not AGENT_INSTANCE:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        logger.info(f"Received task: {request.question}")
        # Run the agent
        # The agent.run method returns the result string
        result = await AGENT_INSTANCE.run(request.question)
        
        # Clean the result
        cleaned_answer = clean_answer(str(result))
        
        return {"answer": cleaned_answer}
        
    except Exception as e:
        logger.error(f"Error during agent execution: {e}")
        # Return error as answer or raise HTTP error depending on requirements.
        # Returning as 500 for now.
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
