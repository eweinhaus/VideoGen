# Scene Planner Tests

Comprehensive test suite for the Scene Planner module, verifying compliance with PRD.md and Tech.md specifications.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_director_knowledge.py  # Director knowledge loader tests
├── test_script_generator.py    # Clip script generation tests
├── test_transitions.py        # Transition planning tests
├── test_llm_client.py         # LLM API integration tests
├── test_validator.py          # Validation tests
├── test_style_analyzer.py     # Style consistency tests
├── test_planner.py           # Core planner integration tests
├── test_prd_compliance.py    # PRD format compliance tests
├── test_integration.py       # End-to-end integration tests
└── fixtures/
    └── sample_audio_analysis.json  # Sample test data
```

## Running Tests

### Run All Tests
```bash
# From project root
pytest project/backend/modules/scene_planner/tests/ -v

# Or use the test script
./project/backend/modules/scene_planner/tests/run_tests.sh
```

### Run Specific Test Files
```bash
# Test PRD compliance
pytest project/backend/modules/scene_planner/tests/test_prd_compliance.py -v

# Test integration
pytest project/backend/modules/scene_planner/tests/test_integration.py -v

# Test LLM client
pytest project/backend/modules/scene_planner/tests/test_llm_client.py -v
```

### Run with Coverage
```bash
pytest project/backend/modules/scene_planner/tests/ \
    --cov=modules.scene_planner \
    --cov-report=term-missing \
    --cov-report=html
```

## Test Categories

### 1. Unit Tests
- **test_director_knowledge.py**: Tests knowledge base loading
- **test_script_generator.py**: Tests clip script generation
- **test_transitions.py**: Tests transition planning logic
- **test_llm_client.py**: Tests LLM API calls (mocked)
- **test_validator.py**: Tests validation logic
- **test_style_analyzer.py**: Tests style consistency checking

### 2. Integration Tests
- **test_planner.py**: Tests full planning pipeline with mocked LLM
- **test_integration.py**: End-to-end tests with all dependencies mocked

### 3. PRD Compliance Tests
- **test_prd_compliance.py**: Verifies inputs/outputs match PRD.md specifications
  - Input format validation (user_prompt 50-500 chars, AudioAnalysis structure)
  - Output format validation (ScenePlan structure matching PRD example)
  - Success criteria verification

## PRD Compliance Checklist

The tests verify:

✅ **Input Validation**
- User prompt: 50-500 characters
- AudioAnalysis: Required fields (bpm, duration, beat_timestamps, song_structure, mood, clip_boundaries)
- Job ID: Valid UUID

✅ **Output Format**
- ScenePlan structure matches PRD example
- Character: id, description, role
- Scene: id, description, time_of_day
- Style: color_palette (≥3 colors), visual_style, mood, lighting, cinematography
- ClipScript: All required fields, beat_intensity in ["low", "medium", "high"]
- Transition: from_clip, to_clip, type, duration, rationale

✅ **Success Criteria**
- Scripts for all clips generated (count matches clip_boundaries)
- Style consistent across clips
- Scripts align to beat boundaries (±0.5s tolerance)
- Director knowledge applied (verified in prompt building)
- Valid JSON output (ScenePlan serializes correctly)
- Auto-retry: 3 attempts for LLM (tested with mocked retries)
- Fallback: Simple scene descriptions if LLM fails (tested with mocked failures)

## Mocking Strategy

Tests use `unittest.mock` to mock external dependencies:

- **LLM API**: Mocked OpenAI client responses
- **Cost Tracking**: Mocked cost tracker
- **Director Knowledge**: Mocked file loading (or uses actual file)

## Fixtures

Shared fixtures in `conftest.py`:
- `job_id`: Test job UUID
- `sample_user_prompt`: Valid user prompt (50-500 chars)
- `sample_audio_analysis`: Complete AudioAnalysis matching PRD format
- `calm_audio_analysis`: Calm mood AudioAnalysis for mood-specific tests
- `sample_scene_plan_dict`: Sample LLM response matching PRD format

## Example Test Run

```bash
$ pytest project/backend/modules/scene_planner/tests/test_prd_compliance.py -v

test_prd_compliance.py::TestPRDInputFormat::test_user_prompt_length_validation PASSED
test_prd_compliance.py::TestPRDInputFormat::test_audio_analysis_structure PASSED
test_prd_compliance.py::TestPRDOutputFormat::test_scene_plan_structure PASSED
test_prd_compliance.py::TestPRDOutputFormat::test_character_structure PASSED
test_prd_compliance.py::TestPRDOutputFormat::test_scene_structure PASSED
test_prd_compliance.py::TestPRDOutputFormat::test_style_structure PASSED
test_prd_compliance.py::TestPRDOutputFormat::test_clip_script_structure PASSED
test_prd_compliance.py::TestPRDOutputFormat::test_transition_structure PASSED
test_prd_compliance.py::TestPRDSuccessCriteria::test_valid_json_output PASSED
```

## Notes

- Tests that require actual LLM API calls are marked with `@pytest.mark.skip` and use mocks instead
- Integration tests use mocked LLM responses to avoid API costs during testing
- PRD compliance tests verify structure and format, not actual LLM output quality (that's tested separately)

