"""
Unit tests for context builder module.
"""
import pytest
from modules.clip_regenerator.context_builder import (
    build_llm_context,
    build_conversation_context,
    summarize_older_messages
)
from shared.models.scene import ScenePlan, Style, Character, Scene


class TestBuildLLMContext:
    """Test LLM context building."""
    
    def test_build_context_full_scene_plan(self):
        """Test building context with full scene plan."""
        scene_plan = ScenePlan(
            style=Style(
                visual_style="cyberpunk",
                mood="dark",
                color_palette=["#000000", "#00ff00"],
                lighting="neon",
                cinematography="dynamic"
            ),
            characters=[
                Character(id="protagonist", name="Protagonist", description="Main character", role="hero")
            ],
            scenes=[
                Scene(id="scene1", description="Street scene", location="Cyberpunk street", time_of_day="night")
            ],
            clip_scripts=[],
            transitions=[]
        )
        
        context = build_llm_context(
            original_prompt="A cyberpunk street scene",
            scene_plan=scene_plan,
            user_instruction="make it nighttime",
            conversation_history=[]
        )
        
        assert context["original_prompt"] == "A cyberpunk street scene"
        assert context["style_info"] == "cyberpunk"
        assert context["mood"] == "dark"
        assert "Protagonist" in context["character_names"]
        assert "Cyberpunk street" in context["scene_locations"]
        assert context["user_instruction"] == "make it nighttime"
    
    def test_build_context_missing_style(self):
        """Test building context with missing style."""
        scene_plan = ScenePlan(
            style=None,
            characters=[],
            scenes=[],
            clip_scripts=[],
            transitions=[]
        )
        
        context = build_llm_context(
            original_prompt="A test scene",
            scene_plan=scene_plan,
            user_instruction="test",
            conversation_history=[]
        )
        
        assert context["style_info"] == "Not specified"
        assert context["mood"] == "Not specified"
    
    def test_build_context_multiple_characters(self):
        """Test building context with multiple characters."""
        scene_plan = ScenePlan(
            style=Style(visual_style="test", mood="neutral", color_palette=[], lighting="", cinematography=""),
            characters=[
                Character(id="char1", name="Character 1", description="", role=""),
                Character(id="char2", name="Character 2", description="", role=""),
                Character(id="char3", name=None, description="", role="")  # No name, should use ID
            ],
            scenes=[],
            clip_scripts=[],
            transitions=[]
        )
        
        context = build_llm_context(
            original_prompt="test",
            scene_plan=scene_plan,
            user_instruction="test",
            conversation_history=[]
        )
        
        assert len(context["character_names"]) == 3
        assert "Character 1" in context["character_names"]
        assert "Character 2" in context["character_names"]
        assert "char3" in context["character_names"]  # Uses ID when name is None
    
    def test_build_context_multiple_scenes(self):
        """Test building context with multiple scenes."""
        scene_plan = ScenePlan(
            style=Style(visual_style="test", mood="neutral", color_palette=[], lighting="", cinematography=""),
            characters=[],
            scenes=[
                Scene(id="scene1", description="", location="Location 1", time_of_day=""),
                Scene(id="scene2", description="", location="Location 2", time_of_day=""),
                Scene(id="scene3", description="", location=None, time_of_day="")  # No location
            ],
            clip_scripts=[],
            transitions=[]
        )
        
        context = build_llm_context(
            original_prompt="test",
            scene_plan=scene_plan,
            user_instruction="test",
            conversation_history=[]
        )
        
        assert len(context["scene_locations"]) == 2  # Only scenes with locations
        assert "Location 1" in context["scene_locations"]
        assert "Location 2" in context["scene_locations"]


class TestBuildConversationContext:
    """Test conversation context building."""
    
    def test_build_conversation_empty(self):
        """Test building conversation context with empty history."""
        result = build_conversation_context([])
        assert result == ""
    
    def test_build_conversation_single_message(self):
        """Test building conversation context with single message."""
        history = [
            {"role": "user", "content": "make it brighter"}
        ]
        result = build_conversation_context(history)
        assert "User: make it brighter" in result
    
    def test_build_conversation_multiple_messages(self):
        """Test building conversation context with multiple messages."""
        history = [
            {"role": "user", "content": "make it brighter"},
            {"role": "assistant", "content": "I'll make it brighter"},
            {"role": "user", "content": "add more motion"}
        ]
        result = build_conversation_context(history)
        assert "User: make it brighter" in result
        assert "Assistant: I'll make it brighter" in result
        assert "User: add more motion" in result
    
    def test_build_conversation_limits_messages(self):
        """Test conversation context limits to max_messages."""
        history = [
            {"role": "user", "content": "message 1"},
            {"role": "assistant", "content": "response 1"},
            {"role": "user", "content": "message 2"},
            {"role": "assistant", "content": "response 2"},
            {"role": "user", "content": "message 3"},
            {"role": "assistant", "content": "response 3"},
        ]
        result = build_conversation_context(history, max_messages=3)
        # Should only include last 3 messages
        assert "message 1" not in result
        assert "response 1" not in result
        assert "message 2" in result
        assert "message 3" in result
    
    def test_build_conversation_missing_role(self):
        """Test handling messages with missing role."""
        history = [
            {"content": "test message"}  # Missing role
        ]
        result = build_conversation_context(history)
        # Should handle gracefully
        assert isinstance(result, str)


class TestSummarizeOlderMessages:
    """Test older message summarization."""
    
    def test_summarize_empty(self):
        """Test summarizing empty message list."""
        result = summarize_older_messages([])
        assert result == ""
    
    def test_summarize_user_messages(self):
        """Test summarizing user messages."""
        older = [
            {"role": "user", "content": "make it brighter"},
            {"role": "assistant", "content": "I'll make it brighter"},
            {"role": "user", "content": "add more motion"}
        ]
        result = summarize_older_messages(older)
        assert "Previous requests" in result
        assert "brighter" in result
        assert "motion" in result
    
    def test_summarize_truncates_long_instructions(self):
        """Test summarizing truncates long instructions."""
        older = [
            {"role": "user", "content": "A" * 100}  # Very long instruction
        ]
        result = summarize_older_messages(older)
        assert len(result) < 200  # Should be truncated
    
    def test_summarize_ignores_assistant_messages(self):
        """Test summarizing ignores assistant-only messages."""
        older = [
            {"role": "assistant", "content": "response 1"},
            {"role": "assistant", "content": "response 2"}
        ]
        result = summarize_older_messages(older)
        # Should return empty if no user messages
        assert result == ""

