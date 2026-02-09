import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from research_agent.answer_synthesis import verify_and_clean_answer

class TestAnswerCleaner(unittest.TestCase):
    
    @patch("research_agent.answer_synthesis.get_llm_client")
    def test_clean_success(self, mock_get_client):
        # Mock LLM response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "1966"
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        raw_output = "The Final Answer is: 1966."
        question = "What year did the Cultural Revolution begin?"
        
        result = verify_and_clean_answer(raw_output, question)
        self.assertEqual(result, "1966")
        
    @patch("research_agent.answer_synthesis.get_llm_client")
    def test_translation_needed(self, mock_get_client):
        # Mock LLM response performing translation
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "苹果" # Translated "Apple" to Chinese
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        raw_output = "Final Answer: Apple"
        question = "这个水果叫什么？" # Chinese question
        
        result = verify_and_clean_answer(raw_output, question)
        self.assertEqual(result, "苹果")

    @patch("research_agent.answer_synthesis.get_llm_client")
    def test_error_handling(self, mock_get_client):
        # Mock LLM returning ERROR
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "ERROR: NO_ANSWER_TAG"
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client
        
        raw_output = "I don't know."
        question = "Question?"
        
        # Should return raw output on error
        result = verify_and_clean_answer(raw_output, question)
        self.assertEqual(result, raw_output)

if __name__ == "__main__":
    unittest.main()
