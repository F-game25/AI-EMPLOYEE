"""
Codex Engine — ML/AI Code Analysis Module

Analyzes uploaded code files using selected LLM provider (Anthropic/Ollama/OpenRouter).
Provides structured analysis: bugs, style issues, performance concerns, refactoring opportunities.
Implements caching to avoid re-analyzing identical file content.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("codex_engine")


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Bug:
    """Represents a detected bug or vulnerability."""
    type: str  # null_ref, sql_injection, race_condition, memory_leak, logic_error, other
    severity: str  # critical, high, medium, low
    line: int
    description: str
    fix_suggestion: str


@dataclass
class StyleIssue:
    """Represents a code style or formatting issue."""
    issue_type: str  # naming, formatting, comments, complexity, unused_variable, etc.
    line: int
    description: str
    suggestion: str


@dataclass
class PerfConcern:
    """Represents a performance-related concern."""
    concern_type: str  # n_plus_one, memory_leak, inefficient_loop, unnecessary_allocation, etc.
    severity: str  # critical, high, medium, low
    description: str
    suggestion: str


@dataclass
class RefactoringOpportunity:
    """Represents a refactoring or improvement opportunity."""
    opportunity_type: str  # extract_method, reduce_duplication, improve_abstraction, etc.
    description: str
    impact: str  # high, medium, low


@dataclass
class CodeSummary:
    """High-level summary of code file."""
    purpose: str  # One-line purpose of the code
    complexity: str  # low, medium, high
    tech_stack: list[str]  # List of detected technologies/dependencies
    loc_count: int  # Lines of code


@dataclass
class AnalysisResult:
    """Complete analysis result for a code file."""
    file_path: str
    language: str
    summary: CodeSummary
    bugs: list[Bug] = field(default_factory=list)
    style_issues: list[StyleIssue] = field(default_factory=list)
    perf_concerns: list[PerfConcern] = field(default_factory=list)
    refactoring: list[RefactoringOpportunity] = field(default_factory=list)
    analysis_time_ms: int = 0
    cache_hit: bool = False
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, handling nested dataclasses."""
        result = asdict(self)
        # Convert nested dataclasses to dicts (asdict handles this, but be explicit)
        result["summary"] = asdict(self.summary)
        result["bugs"] = [asdict(b) for b in self.bugs]
        result["style_issues"] = [asdict(s) for s in self.style_issues]
        result["perf_concerns"] = [asdict(p) for p in self.perf_concerns]
        result["refactoring"] = [asdict(r) for r in self.refactoring]
        return result


# ============================================================================
# Language Detection
# ============================================================================

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".md": "markdown",
}


# ============================================================================
# Codex Engine
# ============================================================================

class CodexEngine:
    """Main code analysis engine powered by LLM."""

    # Max file size to analyze (20KB)
    MAX_FILE_SIZE = 20480

    def __init__(self, cache_dir: Optional[Path] = None, state_dir: Optional[Path] = None):
        """
        Initialize Codex Engine.

        Args:
            cache_dir: Directory to store analysis cache. Defaults to state/codex_cache/
            state_dir: State directory for logging. Defaults to state/
        """
        self.state_dir = state_dir or Path(os.environ.get("AI_EMPLOYEE_STATE_DIR", "state"))
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.cache_dir = cache_dir or self.state_dir / "codex_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.log_path = self.state_dir / "codex_analysis.jsonl"
        logger.info(f"CodexEngine initialized: cache_dir={self.cache_dir}, state_dir={self.state_dir}")

    def analyze(self, file_path: str, content: str, language: Optional[str] = None) -> AnalysisResult:
        """
        Analyze code file and return structured results.

        Args:
            file_path: Path or name of the file being analyzed
            content: Full text content of the file
            language: Programming language (auto-detected if not provided)

        Returns:
            AnalysisResult with bugs, style issues, performance concerns, refactoring opportunities.
        """
        start_time = time.time()

        # Auto-detect language if not provided
        if not language:
            language = self._detect_language(file_path)

        # Handle file size limit
        truncated = False
        if len(content) > self.MAX_FILE_SIZE:
            logger.warning(f"File {file_path} exceeds {self.MAX_FILE_SIZE} bytes, truncating")
            content = content[: self.MAX_FILE_SIZE]
            truncated = True

        # Check cache
        cache_key = self._get_cache_key(content)
        cached_result = self._load_from_cache(cache_key)
        if cached_result:
            cached_result.cache_hit = True
            cached_result.analysis_time_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Cache hit for {file_path} ({cache_key})")
            self._log_analysis(cached_result, from_cache=True)
            return cached_result

        # Call LLM for analysis
        try:
            llm_response = self._call_llm_for_analysis(content, language)
            result = self._parse_llm_response(llm_response, file_path, language, truncated)
        except Exception as e:
            logger.error(f"LLM analysis failed for {file_path}: {e}")
            # Return graceful degradation: summary only
            result = AnalysisResult(
                file_path=file_path,
                language=language,
                summary=CodeSummary(
                    purpose="Analysis failed",
                    complexity="unknown",
                    tech_stack=[],
                    loc_count=len(content.splitlines()),
                ),
                bugs=[],
                style_issues=[],
                perf_concerns=[],
                refactoring=[],
            )

        result.analysis_time_ms = int((time.time() - start_time) * 1000)
        result.truncated = truncated

        # Cache the result
        self._save_to_cache(cache_key, result)

        # Log the analysis
        self._log_analysis(result, from_cache=False)

        return result

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        path = Path(file_path)
        ext = path.suffix.lower()
        language = LANGUAGE_MAP.get(ext, "unknown")
        logger.debug(f"Detected language for {file_path}: {language} (ext={ext})")
        return language

    def _get_cache_key(self, content: str) -> str:
        """Generate cache key from content hash."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _load_from_cache(self, cache_key: str) -> Optional[AnalysisResult]:
        """Load cached analysis result if it exists."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r") as f:
                data = json.load(f)

            # Reconstruct dataclasses from dict
            summary = CodeSummary(**data["summary"])
            bugs = [Bug(**b) for b in data.get("bugs", [])]
            style_issues = [StyleIssue(**s) for s in data.get("style_issues", [])]
            perf_concerns = [PerfConcern(**p) for p in data.get("perf_concerns", [])]
            refactoring = [RefactoringOpportunity(**r) for r in data.get("refactoring", [])]

            return AnalysisResult(
                file_path=data["file_path"],
                language=data["language"],
                summary=summary,
                bugs=bugs,
                style_issues=style_issues,
                perf_concerns=perf_concerns,
                refactoring=refactoring,
                analysis_time_ms=data.get("analysis_time_ms", 0),
                cache_hit=False,  # Will be set to True by caller
                truncated=data.get("truncated", False),
            )
        except Exception as e:
            logger.warning(f"Failed to load cache for {cache_key}: {e}")
            return None

    def _save_to_cache(self, cache_key: str, result: AnalysisResult) -> None:
        """Save analysis result to cache."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, "w") as f:
                json.dump(result.to_dict(), f, indent=2)
            logger.debug(f"Cached analysis to {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save cache for {cache_key}: {e}")

    def _call_llm_for_analysis(self, content: str, language: str) -> str:
        """Call LLM with code analysis prompt."""
        from core.orchestrator import LLMClient

        prompt = self._create_analysis_prompt(content, language)
        system = "You are an expert code analyzer. Respond with valid JSON only, no additional text."

        client = LLMClient(state_dir=self.state_dir)
        try:
            response = client.complete(prompt=prompt, system=system)
            llm_output = response.get("output", "")
            logger.debug(f"LLM analysis response: {llm_output[:200]}...")
            return llm_output
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _create_analysis_prompt(self, content: str, language: str) -> str:
        """Create structured analysis prompt for LLM."""
        loc_count = len(content.splitlines())

        return f"""Analyze this {language} code file (lines of code: {loc_count}). Return ONLY valid JSON in this exact format, with no markdown backticks or additional text:

{{
  "summary": {{
    "purpose": "one-line description of what this code does",
    "complexity": "low|medium|high",
    "tech_stack": ["dep1", "dep2"],
    "loc_count": {loc_count}
  }},
  "bugs": [
    {{"type": "null_ref|sql_injection|race_condition|memory_leak|logic_error|other", "severity": "critical|high|medium|low", "line": 15, "description": "...", "fix_suggestion": "..."}}
  ],
  "style_issues": [
    {{"issue_type": "naming|formatting|comments|complexity|unused_variable|other", "line": 20, "description": "...", "suggestion": "..."}}
  ],
  "perf_concerns": [
    {{"concern_type": "n_plus_one|memory_leak|inefficient_loop|unnecessary_allocation|other", "severity": "critical|high|medium|low", "description": "...", "suggestion": "..."}}
  ],
  "refactoring": [
    {{"opportunity_type": "extract_method|reduce_duplication|improve_abstraction|other", "description": "...", "impact": "high|medium|low"}}
  ]
}}

Code to analyze:
```{language}
{content}
```

Return ONLY the JSON object, no other text."""

    def _parse_llm_response(self, llm_output: str, file_path: str, language: str, truncated: bool) -> AnalysisResult:
        """Parse LLM response into structured AnalysisResult."""
        # Extract JSON from response (handle markdown code blocks)
        llm_output = llm_output.strip()
        if llm_output.startswith("```"):
            llm_output = llm_output.split("```")[1]
            if llm_output.startswith("json"):
                llm_output = llm_output[4:]
            llm_output = llm_output.strip()

        # Parse JSON
        try:
            data = json.loads(llm_output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Raw response: {llm_output[:500]}")
            raise ValueError(f"LLM response is not valid JSON: {e}") from e

        # Validate structure and convert to dataclasses
        try:
            summary_data = data.get("summary", {})
            summary = CodeSummary(
                purpose=str(summary_data.get("purpose", "Unknown")),
                complexity=str(summary_data.get("complexity", "unknown")).lower(),
                tech_stack=list(summary_data.get("tech_stack", [])),
                loc_count=int(summary_data.get("loc_count", 0)),
            )

            bugs = [Bug(**b) for b in data.get("bugs", [])]
            style_issues = [StyleIssue(**s) for s in data.get("style_issues", [])]
            perf_concerns = [PerfConcern(**p) for p in data.get("perf_concerns", [])]
            refactoring = [RefactoringOpportunity(**r) for r in data.get("refactoring", [])]

            return AnalysisResult(
                file_path=file_path,
                language=language,
                summary=summary,
                bugs=bugs,
                style_issues=style_issues,
                perf_concerns=perf_concerns,
                refactoring=refactoring,
                truncated=truncated,
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse LLM response structure: {e}")
            logger.debug(f"Response data: {json.dumps(data, indent=2)}")
            raise ValueError(f"LLM response structure is invalid: {e}") from e

    def _log_analysis(self, result: AnalysisResult, from_cache: bool = False) -> None:
        """Log analysis result to JSONL file."""
        try:
            log_entry = {
                "timestamp": time.time(),
                "file_path": result.file_path,
                "language": result.language,
                "from_cache": from_cache,
                "analysis_time_ms": result.analysis_time_ms,
                "bugs_count": len(result.bugs),
                "style_issues_count": len(result.style_issues),
                "perf_concerns_count": len(result.perf_concerns),
                "refactoring_count": len(result.refactoring),
                "truncated": result.truncated,
            }
            with open(self.log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log analysis: {e}")


# ============================================================================
# Module-level API
# ============================================================================

_engine_instance: Optional[CodexEngine] = None


def get_codex_engine(cache_dir: Optional[Path] = None, state_dir: Optional[Path] = None) -> CodexEngine:
    """Get or create singleton CodexEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = CodexEngine(cache_dir=cache_dir, state_dir=state_dir)
    return _engine_instance


def analyze_code(file_path: str, content: str, language: Optional[str] = None) -> AnalysisResult:
    """Convenience function to analyze code using the singleton engine."""
    engine = get_codex_engine()
    return engine.analyze(file_path, content, language)
