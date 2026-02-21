"""
Test script to verify Chinese search configuration
Tests the 3rd question from validation set
"""
import os
import sys
import json

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from research_agent.search import web_search


def test_chinese_search():
    """Test Chinese search with 3rd validation question"""
    
    # 3rd question from validation.jsonl (Chinese)
    question = "一位物理学领域的学者为一种经典棋盘游戏设计的评分系统，后来被一家北美游戏公司广泛应用于其一款多人在线战术竞技游戏中。这家公司的母公司是一家亚洲科技巨头，该巨头在21世纪10年代完成了对前者的全资收购，并涉足量子计算等前沿科技领域。在这家北美公司开发的另一款第一人称射击游戏中，有一件适合近距离作战的武器，其名称与上述亚洲巨头代理发行的一款格斗手游中的一名在登场角色中年龄偏大的武术教官角色相同。这款格斗手游的名字是什么？"
    
    expected_answer = "魂武者"
    
    print("=" * 60)
    print("Testing Chinese Search Configuration")
    print("=" * 60)
    print(f"\nQuestion: {question[:100]}...")
    print(f"Expected Answer: {expected_answer}")
    print("\n" + "-" * 60)
    
    # Test search
    print("\nExecuting web search...\n")
    result = web_search(question, top_k=5)
    
    # Parse result
    try:
        data = json.loads(result)
        
        print("Search Results:")
        print("-" * 40)
        
        # Print source info
        primary_provider = data.get("primary_provider", "unknown")
        source = data.get("source", "unknown")
        providers_used = data.get("providers_used", 0)
        
        print(f"Primary Provider: {primary_provider}")
        print(f"Source: {source}")
        print(f"Providers Used: {providers_used}")
        print("-" * 40)
        
        # Print results
        results = data.get("results", [])
        if results:
            print(f"\nFound {len(results)} results:\n")
            for i, r in enumerate(results, 1):
                title = r.get("title", "N/A")
                summary = r.get("summary", r.get("snippet", "N/A"))[:150]
                url = r.get("url", "N/A")
                src = r.get("source", "unknown")
                
                print(f"Result {i}:")
                print(f"  Title: {title}")
                print(f"  Summary: {summary}...")
                print(f"  URL: {url}")
                print(f"  Source: {src}")
                print()
                
                # Check if expected answer is in results
                if expected_answer in title:
                    print(f"  ✓ FOUND expected answer in result {i}!")
        else:
            print("No results found!")
            
        # Check relevance
        print("\n" + "=" * 60)
        print("Relevance Check:")
        print("-" * 40)
        
        if results:
            # Check if any result mentions game-related content
            found_relevant = False
            for r in results:
                title = r.get("title", "")
                summary = r.get("summary", "").lower()
                content = title + " " + summary
                
                # Check for game-related keywords
                if "游戏" in content or "魂武" in content or "手游" in content or "格斗" in content:
                    found_relevant = True
                    print(f"✓ Result is RELEVANT: Found game-related content")
                    break
                # Check for publisher/company keywords
                if "腾讯" in content or "网易" in content or "米哈游" in content:
                    found_relevant = True
                    print(f"✓ Result is RELEVANT: Found publisher/company content")
                    break
            
            if not found_relevant:
                print("? Results may need manual review for relevance")
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        
    except json.JSONDecodeError as e:
        print(f"Error parsing result: {e}")
        print(f"Raw result: {result[:500]}...")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("CHINESE SEARCH TEST - Validation Question 3")
    print("=" * 60)
    print("\nThis test verifies:")
    print("1. Baidu is used as primary provider for Chinese queries")
    print("2. Results are relevant to the question")
    print("=" * 60 + "\n")
    
    test_chinese_search()
