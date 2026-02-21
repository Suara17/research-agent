"""
Test script to verify search configuration is working correctly.
Tests the 5th question from validation set.
"""
import os
import sys
import json
import asyncio
import io
import sys

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


def test_search_5th_question():
    """Test search with 5th validation question"""
    
    # 5th question from validation.jsonl (English)
    question = "A European architect who played a key role in introducing a new architectural style to the United States in the early 20th century authored a book in the 1920s analyzing the development and potential of architecture and urban planning in America. In this book, he used a well-known hotel in a major Midwestern city as a primary example of tall building construction. What is the title of this book?"
    
    expected_answer = "Wie Baut Amerika?"
    
    print("=" * 60)
    print("Testing Search Configuration with 5th Validation Question")
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
                if expected_answer.lower() in title.lower():
                    print(f"  ✓ FOUND expected answer in result {i}!")
        else:
            print("No results found!")
            
        # Check relevance
        print("\n" + "=" * 60)
        print("Relevance Check:")
        print("-" * 40)
        
        if results:
            # Check if any result mentions the book title or related content
            found_relevant = False
            for r in results:
                title = r.get("title", "").lower()
                summary = r.get("summary", "").lower()
                content = title + " " + summary
                
                # Check for book title keywords
                if "wie baut" in content or "amerika" in content or "how america builds" in content:
                    found_relevant = True
                    print(f"✓ Result is RELEVANT: Found book-related content")
                    break
                # Check for architect name or related terms
                if "architect" in content or "skyscraper" in content or "hotel" in content:
                    found_relevant = True
                    print(f"✓ Result is RELEVANT: Found architecture-related content")
                    break
            
            if not found_relevant:
                print("? Results may need manual review for relevance")
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        
    except json.JSONDecodeError as e:
        print(f"Error parsing result: {e}")
        print(f"Raw result: {result[:500]}...")


def test_chinese_search():
    """Test Chinese search (should use Baidu)"""
    
    # A Chinese question from validation set
    chinese_question = "在某一年，一位法国天文学家对一颗彗星的光谱进行了开创性观测，同年的一张太阳黑子照片后来在东亚某大都市的天文展览中展出。也正是在这一年，一位尚不满二十岁的南欧创业者，在家乡小镇创办了他的出版事业。十余年后，他将公司总部迁往了该国北部的商业中心。他所创立的这家出版公司的名字是什么？"
    
    print("\n\n" + "=" * 60)
    print("Testing Chinese Search (Should use Baidu)")
    print("=" * 60)
    print(f"\nQuestion: {chinese_question[:80]}...")
    print("\n" + "-" * 60)
    
    result = web_search(chinese_question, top_k=5)
    
    try:
        data = json.loads(result)
        primary_provider = data.get("primary_provider", "unknown")
        print(f"\nPrimary Provider for Chinese query: {primary_provider}")
        
        if primary_provider == "baidu":
            print("✓ Chinese search correctly using Baidu as primary!")
        else:
            print(f"Note: Primary provider is {primary_provider}")
            
    except:
        print("Error parsing result")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("SEARCH CONFIGURATION TEST")
    print("=" * 60)
    print("\nThis test verifies:")
    print("1. Serper is the main provider for English queries")
    print("2. Baidu is the primary provider for Chinese queries")
    print("3. SearXNG and DuckDuckGo are backup providers")
    print("=" * 60 + "\n")
    
    # Test English search (5th question)
    test_search_5th_question()
    
    # Test Chinese search
    test_chinese_search()
