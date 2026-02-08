import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from mmengine import DictAction

# Add project root to sys.path
root = str(Path(__file__).resolve().parent)
sys.path.append(root)

from src.logger import logger
from src.config import config
from src.models import model_manager
from src.agent import create_agent

def parse_args():
    parser = argparse.ArgumentParser(description='Run batch questions')
    parser.add_argument("--config", default=os.path.join(root, "configs", "config_main.py"), help="config file path")
    parser.add_argument("--input", default="../question.jsonl", help="Input jsonl file path")
    parser.add_argument("--output", default="../answers.jsonl", help="Output jsonl file path")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of questions to run")
    parser.add_argument(
        '--cfg-options',
        nargs='+',
        action=DictAction,
        help='override some settings in the used config')
    args = parser.parse_args()
    return args

def load_questions(file_path):
    questions = []
    if not os.path.exists(file_path):
        print(f"Error: Input file {file_path} not found.")
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
    return questions

def load_answers(file_path):
    answers = set()
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        answers.add(data['id'])
                    except:
                        pass
    return answers

async def main():
    args = parse_args()
    
    # Initialize config
    config.init_config(args.config, args)
    
    # Initialize logger
    logger.init_logger(log_path=config.log_path)
    logger.info(f"| Logger initialized at: {config.log_path}")
    
    # Initialize models
    model_manager.init_models(use_local_proxy=config.use_local_proxy)
    
    input_path = os.path.abspath(args.input)
    output_path = os.path.abspath(args.output)
    
    print(f"Reading questions from: {input_path}")
    print(f"Writing answers to: {output_path}")
    
    questions = load_questions(input_path)
    processed_ids = load_answers(output_path)
    
    logger.info(f"Total questions: {len(questions)}")
    logger.info(f"Already processed: {len(processed_ids)}")
    
    questions_to_run = [q for q in questions if q['id'] not in processed_ids]
    
    if args.limit:
        questions_to_run = questions_to_run[:args.limit]
        
    logger.info(f"Questions to run: {len(questions_to_run)}")
    
    for i, q in enumerate(questions_to_run):
        q_id = q['id']
        question_text = q['question']
        
        logger.info(f"Processing Question ID: {q_id}")
        logger.info(f"Question: {question_text}")
        
        try:
            # Create a new agent for each question to ensure fresh state
            agent = await create_agent(config)
            
            # Run the agent
            result = await agent.run(question_text)
            
            # Save result
            output_entry = {
                "id": q_id,
                "question": question_text,
                "answer": result
            }
            
            with open(output_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(output_entry, ensure_ascii=False) + "\n")
                
            logger.info(f"Saved answer for ID: {q_id}")
            
        except Exception as e:
            logger.error(f"Error processing ID {q_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
if __name__ == '__main__':
    asyncio.run(main())
