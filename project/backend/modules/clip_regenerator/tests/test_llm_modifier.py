"""
Unit tests for LLM modifier module.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from uuid import UUID

from modules.clip_regenerator.llm_modifier import (
    get_system_prompt,
    build_user_prompt,
    parse_llm_prompt_response,
    modify_prompt_with_llm,
    estimate_llm_cost,
    _estimate_tokens,
    _truncate_context_if_needed
)


class TestSystemPrompt:
    """Test system prompt generation."""
    
    def test_system_prompt_not_empty(self):
        """Test system prompt is not empty."""
        prompt = get_system_prompt()
        assert len(prompt) > 0
        assert "video editing assistant" in prompt.lower()
        assert "preserve" in prompt.lower()
        assert "temperature" in prompt.lower()  # Should include temperature instructions
        assert "json" in prompt.lower()  # Should request JSON format


class TestBuildUserPrompt:
    """Test user prompt building."""
    
    def test_build_user_prompt_basic(self):
        """Test building basic user prompt."""
        original_prompt = "A cyberpunk street scene"
        user_instruction = "make it nighttime"
        context = {
            "style_info": "cyberpunk",
            "character_names": ["protagonist"],
            "scene_locations": ["street"],
            "mood": "dark"
        }
        conversation_history = []
        
        prompt = build_user_prompt(
            original_prompt,
            user_instruction,
            context,
            conversation_history
        )
        
        assert original_prompt in prompt
        assert user_instruction in prompt
        assert "cyberpunk" in prompt
        assert "protagonist" in prompt
        assert "street" in prompt
        assert "dark" in prompt
    
    def test_build_user_prompt_with_conversation(self):
        """Test building prompt with conversation history."""
        original_prompt = "A test scene"
        user_instruction = "make it brighter"
        context = {
            "style_info": "test",
            "character_names": [],
            "scene_locations": [],
            "mood": "neutral"
        }
        conversation_history = [
            {"role": "user", "content": "make it darker"},
            {"role": "assistant", "content": "I'll make it darker"}
        ]
        
        prompt = build_user_prompt(
            original_prompt,
            user_instruction,
            context,
            conversation_history
        )
        
        assert "User: make it darker" in prompt
        assert "Assistant: I'll make it darker" in prompt
        assert user_instruction in prompt
    
    def test_build_user_prompt_limits_conversation(self):
        """Test conversation history is limited to last 3 messages."""
        original_prompt = "A test scene"
        user_instruction = "make it brighter"
        context = {
            "style_info": "test",
            "character_names": [],
            "scene_locations": [],
            "mood": "neutral"
        }
        conversation_history = [
            {"role": "user", "content": "message 1"},
            {"role": "assistant", "content": "response 1"},
            {"role": "user", "content": "message 2"},
            {"role": "assistant", "content": "response 2"},
            {"role": "user", "content": "message 3"},
            {"role": "assistant", "content": "response 3"},
        ]
        
        prompt = build_user_prompt(
            original_prompt,
            user_instruction,
            context,
            conversation_history
        )
        
        # Should only include last 3 messages (response 2, message 3, response 3)
        assert "message 1" not in prompt
        assert "response 1" not in prompt
        assert "response 2" in prompt  # Last 3 messages include this
        assert "message 3" in prompt
        assert "response 3" in prompt


class TestParseLLMPromptResponse:
    """Test LLM response parsing."""
    
    def test_parse_clean_response(self):
        """Test parsing clean response."""
        response = "A modified cyberpunk street scene with nighttime lighting"
        result = parse_llm_prompt_response(response)
        assert result == response
    
    def test_parse_markdown_code_block(self):
        """Test parsing response with markdown code block."""
        response = "```\nA modified prompt\n```"
        result = parse_llm_prompt_response(response)
        assert "```" not in result
        assert "A modified prompt" in result
    
    def test_parse_with_prefix(self):
        """Test parsing response with common prefix."""
        response = "Modified prompt: A cyberpunk street scene"
        result = parse_llm_prompt_response(response)
        assert "Modified prompt:" not in result
        assert "A cyberpunk street scene" in result
    
    def test_parse_with_explanation(self):
        """Test parsing response with explanation."""
        response = "A cyberpunk street scene because the user wants nighttime. This will create a dark atmosphere."
        result = parse_llm_prompt_response(response)
        # Should extract the longest sentence
        assert len(result) > 0
    
    def test_parse_empty_response(self):
        """Test parsing empty response."""
        result = parse_llm_prompt_response("")
        assert result == ""
    
    def test_parse_multiple_prefixes(self):
        """Test parsing with multiple possible prefixes."""
        response = "Here's the modified prompt: A test scene"
        result = parse_llm_prompt_response(response)
        assert "Here's the modified prompt:" not in result
        assert "A test scene" in result


class TestTokenEstimation:
    """Test token estimation."""
    
    def test_estimate_tokens(self):
        """Test token estimation."""
        text = "A" * 100  # 100 characters
        tokens = _estimate_tokens(text)
        # Rough estimate: 4 chars per token = ~25 tokens
        assert tokens > 0
        assert tokens < 50
    
    def test_estimate_tokens_empty(self):
        """Test token estimation for empty text."""
        assert _estimate_tokens("") == 0


class TestTruncateContext:
    """Test context truncation."""
    
    def test_truncate_context_within_budget(self):
        """Test context within budget is not truncated."""
        context = {
            "style_info": "test style",
            "character_names": ["char1"],
            "scene_locations": ["scene1"]
        }
        result = _truncate_context_if_needed(context, max_tokens=2000)
        assert result == context
    
    def test_truncate_context_exceeds_budget(self):
        """Test context exceeding budget is truncated."""
        # Create large context
        context = {
            "style_info": "A" * 1000,  # Large style info
            "character_names": ["char1", "char2", "char3", "char4", "char5"],
            "scene_locations": ["scene1", "scene2", "scene3", "scene4", "scene5"]
        }
        result = _truncate_context_if_needed(context, max_tokens=100)
        # Should truncate scenes first (lowest priority)
        assert len(result["scene_locations"]) <= len(context["scene_locations"])
    
    def test_truncate_priority_order(self):
        """Test truncation priority: scenes > characters > style."""
        context = {
            "style_info": "A" * 500,
            "character_names": ["char1", "char2", "char3", "char4"],
            "scene_locations": ["scene1", "scene2", "scene3", "scene4", "scene5"]
        }
        result = _truncate_context_if_needed(context, max_tokens=50)
        # Scenes should be truncated first
        assert len(result["scene_locations"]) < len(context["scene_locations"])


class TestModifyPromptWithLLM:
    """Test LLM prompt modification."""
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.llm_modifier.get_openai_client')
    @patch('modules.clip_regenerator.llm_modifier.cost_tracker')
    async def test_modify_prompt_success(self, mock_cost_tracker, mock_get_client):
        """Test successful prompt modification with JSON response."""
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        
        # Mock JSON response
        import json
        json_response = {
            "prompt": "A modified cyberpunk street scene with nighttime lighting",
            "temperature": 0.6,
            "reasoning": "Moderate change requested"
        }
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(json_response)
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        # Mock cost tracker
        mock_cost_tracker.track_cost = AsyncMock()
        
        original_prompt = "A cyberpunk street scene"
        user_instruction = "make it nighttime"
        context = {
            "style_info": "cyberpunk",
            "character_names": [],
            "scene_locations": [],
            "mood": "dark"
        }
        conversation_history = []
        job_id = UUID("12345678-1234-5678-1234-567812345678")
        
        result = await modify_prompt_with_llm(
            original_prompt,
            user_instruction,
            context,
            conversation_history,
            job_id=job_id
        )
        
        assert isinstance(result, dict)
        assert "prompt" in result
        assert "temperature" in result
        assert "reasoning" in result
        assert result["prompt"] == json_response["prompt"]
        assert result["temperature"] == 0.6
        assert result["reasoning"] == json_response["reasoning"]
        mock_client.chat.completions.create.assert_called_once()
        # Check that response_format is set to json_object
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["response_format"]["type"] == "json_object"
        mock_cost_tracker.track_cost.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.llm_modifier.get_openai_client')
    @patch('modules.clip_regenerator.llm_modifier.cost_tracker')
    async def test_modify_prompt_json_fallback(self, mock_cost_tracker, mock_get_client):
        """Test fallback when JSON parsing fails."""
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        
        # Mock text response (invalid JSON)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "A modified cyberpunk street scene with nighttime lighting"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        # Mock cost tracker
        mock_cost_tracker.track_cost = AsyncMock()
        
        original_prompt = "A cyberpunk street scene"
        user_instruction = "make it nighttime"
        context = {
            "style_info": "cyberpunk",
            "character_names": [],
            "scene_locations": [],
            "mood": "dark"
        }
        conversation_history = []
        job_id = UUID("12345678-1234-5678-1234-567812345678")
        
        result = await modify_prompt_with_llm(
            original_prompt,
            user_instruction,
            context,
            conversation_history,
            job_id=job_id
        )
        
        # Should fallback to text parsing with default temperature
        assert isinstance(result, dict)
        assert "prompt" in result
        assert "temperature" in result
        assert result["temperature"] == 0.7  # Default fallback
        assert "nighttime" in result["prompt"].lower()
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.llm_modifier.get_openai_client')
    @patch('modules.clip_regenerator.llm_modifier.cost_tracker')
    async def test_modify_prompt_temperature_validation(self, mock_cost_tracker, mock_get_client):
        """Test temperature validation and clamping."""
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        
        # Mock JSON response with invalid temperature
        import json
        json_response = {
            "prompt": "A modified scene",
            "temperature": 1.5,  # Invalid: > 1.0
            "reasoning": "Test"
        }
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(json_response)
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_cost_tracker.track_cost = AsyncMock()
        
        result = await modify_prompt_with_llm(
            "test prompt",
            "test instruction",
            {"style_info": "test"},
            []
        )
        
        # Temperature should be clamped to 1.0
        assert result["temperature"] == 1.0
    
    @pytest.mark.asyncio
    @patch('modules.clip_regenerator.llm_modifier.get_openai_client')
    async def test_modify_prompt_empty_response(self, mock_get_client):
        """Test handling empty LLM response."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        from shared.errors import GenerationError
        
        with pytest.raises(GenerationError):
            await modify_prompt_with_llm(
                "test prompt",
                "test instruction",
                {"style_info": "test"},
                []
            )


class TestEstimateLLMCost:
    """Test LLM cost estimation."""
    
    def test_estimate_llm_cost(self):
        """Test LLM cost estimation."""
        cost = estimate_llm_cost()
        assert isinstance(cost, Decimal)
        assert cost > 0

