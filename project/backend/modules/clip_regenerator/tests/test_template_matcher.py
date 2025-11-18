"""
Unit tests for template matcher module.
"""
import pytest
from modules.clip_regenerator.template_matcher import (
    match_template,
    apply_template,
    TemplateMatch,
    TEMPLATES
)


class TestMatchTemplate:
    """Test template matching logic."""
    
    def test_match_brighter(self):
        """Test matching brighter template."""
        match = match_template("make it brighter")
        assert match is not None
        assert match.template_id == "brighter"
        assert "bright lighting" in match.transformation.lower()
        assert match.cost_savings == 0.01
    
    def test_match_darker(self):
        """Test matching darker template."""
        match = match_template("can you darken this?")
        assert match is not None
        assert match.template_id == "darker"
        assert "dark lighting" in match.transformation.lower()
    
    def test_match_nighttime(self):
        """Test matching nighttime template."""
        match = match_template("make it nighttime")
        assert match is not None
        assert match.template_id == "nighttime"
        assert "nighttime" in match.transformation.lower()
    
    def test_match_daytime(self):
        """Test matching daytime template."""
        match = match_template("make it daytime")
        assert match is not None
        assert match.template_id == "daytime"
        assert "daytime" in match.transformation.lower()
    
    def test_match_more_motion(self):
        """Test matching more_motion template."""
        match = match_template("add more motion")
        assert match is not None
        assert match.template_id == "more_motion"
        assert "dynamic" in match.transformation.lower()
    
    def test_match_less_motion(self):
        """Test matching less_motion template."""
        match = match_template("make it calm")
        assert match is not None
        assert match.template_id == "less_motion"
        assert "static" in match.transformation.lower()
    
    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        match1 = match_template("MAKE IT BRIGHTER")
        match2 = match_template("make it brighter")
        assert match1 is not None
        assert match2 is not None
        assert match1.template_id == match2.template_id
    
    def test_first_match_wins(self):
        """Test first match wins strategy."""
        # "brighter" comes before "nighttime" in TEMPLATES dict
        match = match_template("make it brighter and nighttime")
        assert match is not None
        assert match.template_id == "brighter"  # First match wins
    
    def test_no_match(self):
        """Test no template match."""
        match = match_template("make it more colorful")
        assert match is None
    
    def test_empty_instruction(self):
        """Test empty instruction returns None."""
        assert match_template("") is None
        assert match_template("   ") is None
        assert match_template(None) is None
    
    def test_multi_word_keywords(self):
        """Test multi-word keyword matching."""
        match = match_template("add more motion to this clip")
        assert match is not None
        assert match.template_id == "more_motion"
        
        match = match_template("less motion please")
        assert match is not None
        assert match.template_id == "less_motion"


class TestApplyTemplate:
    """Test template application."""
    
    def test_apply_template(self):
        """Test applying template to prompt."""
        original = "A cyberpunk street scene"
        template = TemplateMatch(
            template_id="nighttime",
            transformation="nighttime scene, dark sky, stars visible, night lighting, cool tones",
            cost_savings=0.01
        )
        
        result = apply_template(original, template)
        assert result == f"{original}, {template.transformation}"
        assert "nighttime" in result.lower()
        assert "cyberpunk" in result
    
    def test_apply_template_empty_original(self):
        """Test applying template to empty prompt."""
        template = TemplateMatch(
            template_id="brighter",
            transformation="bright lighting, well-lit, high exposure",
            cost_savings=0.01
        )
        
        result = apply_template("", template)
        assert result == template.transformation
    
    def test_apply_template_all_templates(self):
        """Test applying all templates."""
        original = "A test scene"
        
        for template_id, template_data in TEMPLATES.items():
            template = TemplateMatch(
                template_id=template_id,
                transformation=template_data["transformation"],
                cost_savings=template_data["cost_savings"]
            )
            result = apply_template(original, template)
            assert original in result
            assert template.transformation in result

