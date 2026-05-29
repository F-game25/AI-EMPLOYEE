"""
Tests for Codex Engine — Code analysis module.

Tests cover:
- Language detection from file extensions
- JSON response parsing
- Cache hit/miss behavior
- Graceful error handling
- Data structure validation
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add runtime to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "runtime"))

from core.codex import (
    AnalysisResult,
    Bug,
    CodeSummary,
    CodexEngine,
    PerfConcern,
    RefactoringOpportunity,
    StyleIssue,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_state_dir():
    """Create temporary state directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def codex_engine(temp_state_dir):
    """Create CodexEngine instance with temp directory."""
    return CodexEngine(cache_dir=temp_state_dir / "cache", state_dir=temp_state_dir)


# ============================================================================
# Sample Code for Testing
# ============================================================================

PYTHON_SAMPLE = '''
def process_user(user_id):
    """Process a user by ID."""
    user = get_user(user_id)  # Potential null reference
    return user.name.upper()


def fetch_data():
    """Fetch data inefficiently."""
    results = []
    for item_id in range(1000):
        results.append(db.query("SELECT * FROM items WHERE id = " + str(item_id)))  # N+1 problem
    return results
'''

JAVASCRIPT_SAMPLE = '''
function calculateTotal(items) {
  var total = 0;  // Naming: should be const/let
  for (var i = 0; i < items.length; i++) {
    total += items[i].price;
  }
  return total;
}

async function fetchUser(userId) {
  const response = await fetch(`/api/users/${userId}`);
  return await response.json();  // Unnecessary await
}
'''


# ============================================================================
# Test Language Detection
# ============================================================================

class TestLanguageDetection:
    """Test programming language detection from file extensions."""

    def test_python_detection(self, codex_engine):
        """Test Python file detection."""
        assert codex_engine._detect_language("script.py") == "python"
        assert codex_engine._detect_language("test_module.py") == "python"

    def test_javascript_detection(self, codex_engine):
        """Test JavaScript file detection."""
        assert codex_engine._detect_language("app.js") == "javascript"
        assert codex_engine._detect_language("component.jsx") == "javascript"

    def test_typescript_detection(self, codex_engine):
        """Test TypeScript file detection."""
        assert codex_engine._detect_language("config.ts") == "typescript"
        assert codex_engine._detect_language("component.tsx") == "typescript"

    def test_unknown_extension(self, codex_engine):
        """Test unknown file extension."""
        assert codex_engine._detect_language("file.unknown") == "unknown"
        assert codex_engine._detect_language("README") == "unknown"

    def test_case_insensitive(self, codex_engine):
        """Test case-insensitive extension matching."""
        assert codex_engine._detect_language("SCRIPT.PY") == "python"
        assert codex_engine._detect_language("App.JS") == "javascript"


# ============================================================================
# Test Caching
# ============================================================================

class TestCaching:
    """Test cache functionality."""

    def test_cache_key_generation(self, codex_engine):
        """Test cache key generation from content."""
        key1 = codex_engine._get_cache_key("content1")
        key2 = codex_engine._get_cache_key("content2")
        key1_again = codex_engine._get_cache_key("content1")

        assert len(key1) == 64  # SHA256 hex string
        assert key1 != key2
        assert key1 == key1_again  # Same content = same key

    def test_cache_save_and_load(self, codex_engine):
        """Test saving and loading from cache."""
        # Create a mock result
        result = AnalysisResult(
            file_path="test.py",
            language="python",
            summary=CodeSummary(
                purpose="Test module",
                complexity="medium",
                tech_stack=["pytest"],
                loc_count=42,
            ),
            bugs=[
                Bug(
                    type="null_ref",
                    severity="high",
                    line=10,
                    description="Potential null reference",
                    fix_suggestion="Add null check",
                )
            ],
            style_issues=[],
            perf_concerns=[],
            refactoring=[],
        )

        # Save to cache
        cache_key = codex_engine._get_cache_key("test content")
        codex_engine._save_to_cache(cache_key, result)

        # Load from cache
        loaded = codex_engine._load_from_cache(cache_key)

        assert loaded is not None
        assert loaded.file_path == "test.py"
        assert loaded.language == "python"
        assert loaded.summary.purpose == "Test module"
        assert len(loaded.bugs) == 1
        assert loaded.bugs[0].type == "null_ref"

    def test_cache_miss(self, codex_engine):
        """Test cache miss for non-existent key."""
        result = codex_engine._load_from_cache("nonexistent_key")
        assert result is None


# ============================================================================
# Test LLM Response Parsing
# ============================================================================

class TestResponseParsing:
    """Test parsing of LLM responses."""

    def test_parse_valid_json_response(self, codex_engine):
        """Test parsing valid JSON response."""
        response = json.dumps({
            "summary": {
                "purpose": "User management module",
                "complexity": "medium",
                "tech_stack": ["sqlalchemy", "flask"],
                "loc_count": 150,
            },
            "bugs": [
                {
                    "type": "sql_injection",
                    "severity": "critical",
                    "line": 45,
                    "description": "SQL injection vulnerability in query",
                    "fix_suggestion": "Use parameterized queries",
                }
            ],
            "style_issues": [
                {
                    "issue_type": "naming",
                    "line": 12,
                    "description": "Variable name 'x' is not descriptive",
                    "suggestion": "Use meaningful variable names",
                }
            ],
            "perf_concerns": [
                {
                    "concern_type": "n_plus_one",
                    "severity": "high",
                    "description": "N+1 query problem in user loading",
                    "suggestion": "Use eager loading or batch queries",
                }
            ],
            "refactoring": [
                {
                    "opportunity_type": "extract_method",
                    "description": "Extract validation logic into separate method",
                    "impact": "high",
                }
            ],
        })

        result = codex_engine._parse_llm_response(response, "module.py", "python", False)

        assert result.file_path == "module.py"
        assert result.language == "python"
        assert result.summary.purpose == "User management module"
        assert len(result.bugs) == 1
        assert result.bugs[0].type == "sql_injection"
        assert len(result.style_issues) == 1
        assert len(result.perf_concerns) == 1
        assert len(result.refactoring) == 1

    def test_parse_json_with_markdown_fence(self, codex_engine):
        """Test parsing JSON wrapped in markdown code fence."""
        response = """```json
{
  "summary": {
    "purpose": "Test",
    "complexity": "low",
    "tech_stack": [],
    "loc_count": 10
  },
  "bugs": [],
  "style_issues": [],
  "perf_concerns": [],
  "refactoring": []
}
```"""

        result = codex_engine._parse_llm_response(response, "test.py", "python", False)
        assert result.summary.purpose == "Test"

    def test_parse_invalid_json(self, codex_engine):
        """Test handling of invalid JSON."""
        with pytest.raises(ValueError, match="not valid JSON"):
            codex_engine._parse_llm_response("not json at all", "test.py", "python", False)

    def test_parse_missing_fields(self, codex_engine):
        """Test handling of missing required fields."""
        incomplete_response = json.dumps({
            "summary": {
                "purpose": "Test",
                # Missing complexity, tech_stack, loc_count
            }
            # Missing bugs, style_issues, perf_concerns, refactoring
        })

        # Should still parse but with defaults
        result = codex_engine._parse_llm_response(incomplete_response, "test.py", "python", False)
        assert result.summary.purpose == "Test"

    def test_parse_empty_arrays(self, codex_engine):
        """Test parsing response with empty bug/style/perf arrays."""
        response = json.dumps({
            "summary": {
                "purpose": "Clean code",
                "complexity": "low",
                "tech_stack": ["pytest"],
                "loc_count": 20,
            },
            "bugs": [],
            "style_issues": [],
            "perf_concerns": [],
            "refactoring": [],
        })

        result = codex_engine._parse_llm_response(response, "clean.py", "python", False)
        assert len(result.bugs) == 0
        assert len(result.style_issues) == 0
        assert len(result.perf_concerns) == 0
        assert len(result.refactoring) == 0


# ============================================================================
# Test Analysis Prompt Creation
# ============================================================================

class TestPromptCreation:
    """Test analysis prompt generation."""

    def test_prompt_contains_language(self, codex_engine):
        """Test that prompt includes language name."""
        prompt = codex_engine._create_analysis_prompt("x = 1", "python")
        assert "python" in prompt.lower()

    def test_prompt_contains_code(self, codex_engine):
        """Test that prompt includes the code to analyze."""
        code = "def hello(): return 'world'"
        prompt = codex_engine._create_analysis_prompt(code, "python")
        assert code in prompt

    def test_prompt_contains_json_format(self, codex_engine):
        """Test that prompt specifies JSON format."""
        prompt = codex_engine._create_analysis_prompt("x = 1", "python")
        assert "json" in prompt.lower()
        assert "summary" in prompt.lower()
        assert "bugs" in prompt.lower()

    def test_prompt_contains_line_count(self, codex_engine):
        """Test that prompt includes line count."""
        code = "line1\nline2\nline3"
        prompt = codex_engine._create_analysis_prompt(code, "python")
        assert "3" in prompt  # 3 lines of code


# ============================================================================
# Test File Size Handling
# ============================================================================

class TestFileSizeHandling:
    """Test handling of large files."""

    def test_file_size_within_limit(self, codex_engine):
        """Test normal file size handling."""
        content = "x = 1"
        result_content = content
        assert len(result_content) < CodexEngine.MAX_FILE_SIZE

    def test_file_truncation_flag(self, codex_engine):
        """Test that truncated flag is set for large files."""
        large_content = "x = 1\n" * 5000  # Over 20KB
        assert len(large_content) > CodexEngine.MAX_FILE_SIZE

        # Mock LLM to avoid actual call
        with patch.object(codex_engine, "_call_llm_for_analysis") as mock_llm:
            mock_llm.return_value = json.dumps({
                "summary": {
                    "purpose": "Test",
                    "complexity": "medium",
                    "tech_stack": [],
                    "loc_count": 100,
                },
                "bugs": [],
                "style_issues": [],
                "perf_concerns": [],
                "refactoring": [],
            })

            result = codex_engine.analyze("large.py", large_content, "python")
            assert result.truncated is True


# ============================================================================
# Test Integration (with Mocked LLM)
# ============================================================================

class TestIntegration:
    """Integration tests with mocked LLM."""

    @patch("core.orchestrator.LLMClient")
    def test_full_analysis_flow(self, mock_llm_class, codex_engine):
        """Test complete analysis flow from file to result."""
        # Mock LLM response
        llm_response = {
            "output": json.dumps({
                "summary": {
                    "purpose": "User authentication module",
                    "complexity": "high",
                    "tech_stack": ["jwt", "bcrypt"],
                    "loc_count": 200,
                },
                "bugs": [
                    {
                        "type": "sql_injection",
                        "severity": "critical",
                        "line": 56,
                        "description": "SQL injection in login query",
                        "fix_suggestion": "Use parameterized queries",
                    }
                ],
                "style_issues": [
                    {
                        "issue_type": "unused_variable",
                        "line": 23,
                        "description": "Variable 'temp' is never used",
                        "suggestion": "Remove unused variable",
                    }
                ],
                "perf_concerns": [
                    {
                        "concern_type": "memory_leak",
                        "severity": "high",
                        "description": "Event listener not removed",
                        "suggestion": "Clean up listeners in destructor",
                    }
                ],
                "refactoring": [
                    {
                        "opportunity_type": "extract_method",
                        "description": "Extract password validation",
                        "impact": "medium",
                    }
                ],
            })
        }
        mock_client = MagicMock()
        mock_client.complete.return_value = llm_response
        mock_llm_class.return_value = mock_client

        result = codex_engine.analyze("auth.py", PYTHON_SAMPLE, "python")

        assert result.file_path == "auth.py"
        assert result.language == "python"
        assert result.summary.purpose == "User authentication module"
        assert result.summary.complexity == "high"
        assert len(result.bugs) == 1
        assert len(result.style_issues) == 1
        assert len(result.perf_concerns) == 1
        assert len(result.refactoring) == 1
        assert result.analysis_time_ms >= 0  # Can be 0 for very fast mocked calls

    @patch("core.orchestrator.LLMClient")
    def test_cache_hit_avoids_llm_call(self, mock_llm_class, codex_engine):
        """Test that cache hit avoids calling LLM."""
        llm_response = {
            "output": json.dumps({
                "summary": {
                    "purpose": "Test",
                    "complexity": "low",
                    "tech_stack": [],
                    "loc_count": 5,
                },
                "bugs": [],
                "style_issues": [],
                "perf_concerns": [],
                "refactoring": [],
            })
        }
        mock_client = MagicMock()
        mock_client.complete.return_value = llm_response
        mock_llm_class.return_value = mock_client

        # First call — cache miss
        result1 = codex_engine.analyze("test.py", "x = 1", "python")
        assert result1.cache_hit is False
        assert mock_client.complete.call_count == 1

        # Second call with same content — cache hit
        result2 = codex_engine.analyze("test.py", "x = 1", "python")
        assert result2.cache_hit is True
        assert mock_client.complete.call_count == 1  # No new call

    @patch("core.orchestrator.LLMClient")
    def test_llm_failure_graceful_degradation(self, mock_llm_class, codex_engine):
        """Test graceful degradation when LLM fails."""
        mock_client = MagicMock()
        mock_client.complete.side_effect = Exception("LLM timeout")
        mock_llm_class.return_value = mock_client

        result = codex_engine.analyze("error.py", "x = 1", "python")

        assert result.file_path == "error.py"
        assert result.language == "python"
        assert result.summary.purpose == "Analysis failed"
        assert len(result.bugs) == 0
        assert len(result.style_issues) == 0


# ============================================================================
# Test Data Models
# ============================================================================

class TestDataModels:
    """Test dataclass models and serialization."""

    def test_analysis_result_to_dict(self):
        """Test AnalysisResult.to_dict() serialization."""
        result = AnalysisResult(
            file_path="test.py",
            language="python",
            summary=CodeSummary(
                purpose="Test",
                complexity="low",
                tech_stack=["pytest"],
                loc_count=10,
            ),
            bugs=[
                Bug(
                    type="null_ref",
                    severity="low",
                    line=5,
                    description="Null reference",
                    fix_suggestion="Add check",
                )
            ],
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["file_path"] == "test.py"
        assert isinstance(result_dict["summary"], dict)
        assert result_dict["summary"]["purpose"] == "Test"
        assert isinstance(result_dict["bugs"], list)
        assert isinstance(result_dict["bugs"][0], dict)
        assert result_dict["bugs"][0]["type"] == "null_ref"

    def test_bug_dataclass(self):
        """Test Bug dataclass."""
        bug = Bug(
            type="sql_injection",
            severity="critical",
            line=42,
            description="SQL injection vulnerability",
            fix_suggestion="Use prepared statements",
        )
        assert bug.type == "sql_injection"
        assert bug.severity == "critical"
        assert bug.line == 42

    def test_code_summary_dataclass(self):
        """Test CodeSummary dataclass."""
        summary = CodeSummary(
            purpose="Payment processing",
            complexity="high",
            tech_stack=["stripe", "sqlalchemy"],
            loc_count=500,
        )
        assert summary.purpose == "Payment processing"
        assert len(summary.tech_stack) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
