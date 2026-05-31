"""
Codex API — HTTP endpoint wrapper for code analysis.

Provides FastAPI/Flask-compatible handlers for integrating CodexEngine
into the Python backend REST API.

Usage (in runtime/agents/problem-solver-ui/server.py):
    from core.codex_api import CodexAPIHandler
    handler = CodexAPIHandler()

    # In your FastAPI app:
    @app.post("/api/codex/analyze")
    async def analyze_code(request: CodexAnalyzeRequest):
        return await handler.analyze(request)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from core.codex import AnalysisResult, CodexEngine, analyze_code

logger = logging.getLogger("codex_api")


# ============================================================================
# Request/Response Models
# ============================================================================

class CodexAnalyzeRequest(BaseModel):
    """Request payload for code analysis."""
    file_path: str = Field(..., description="Path or filename of the code file")
    content: str = Field(..., description="Full text content of the file")
    language: Optional[str] = Field(None, description="Programming language (auto-detected if not provided)")
    cache_override: bool = Field(False, description="Force re-analysis even if cached")

    class Config:
        schema_extra = {
            "example": {
                "file_path": "src/auth.py",
                "content": "def login(user_id):\n    user = get_user(user_id)\n    return user.email",
                "language": "python",
                "cache_override": False,
            }
        }


class BugResponse(BaseModel):
    """Bug analysis result."""
    type: str = Field(..., description="Bug type: null_ref, sql_injection, race_condition, memory_leak, logic_error, other")
    severity: str = Field(..., description="Severity: critical, high, medium, low")
    line: int = Field(..., description="Line number where bug appears")
    description: str = Field(..., description="Description of the bug")
    fix_suggestion: str = Field(..., description="Suggested fix")


class StyleIssueResponse(BaseModel):
    """Code style issue."""
    issue_type: str = Field(..., description="Issue type: naming, formatting, comments, complexity, etc.")
    line: int = Field(..., description="Line number")
    description: str = Field(..., description="Description of the issue")
    suggestion: str = Field(..., description="Suggestion for improvement")


class PerfConcernResponse(BaseModel):
    """Performance concern."""
    concern_type: str = Field(..., description="Concern type: n_plus_one, memory_leak, inefficient_loop, etc.")
    severity: str = Field(..., description="Severity: critical, high, medium, low")
    description: str = Field(..., description="Description of the concern")
    suggestion: str = Field(..., description="Suggestion for improvement")


class RefactoringResponse(BaseModel):
    """Refactoring opportunity."""
    opportunity_type: str = Field(..., description="Type: extract_method, reduce_duplication, improve_abstraction, etc.")
    description: str = Field(..., description="Description of the opportunity")
    impact: str = Field(..., description="Impact: high, medium, low")


class CodeSummaryResponse(BaseModel):
    """High-level code summary."""
    purpose: str = Field(..., description="One-line description of code purpose")
    complexity: str = Field(..., description="Complexity: low, medium, high")
    tech_stack: list[str] = Field(..., description="List of detected technologies/dependencies")
    loc_count: int = Field(..., description="Lines of code")


class CodexAnalyzeResponse(BaseModel):
    """Response payload for code analysis."""
    file_path: str = Field(..., description="Path of the analyzed file")
    language: str = Field(..., description="Programming language")
    summary: CodeSummaryResponse = Field(..., description="High-level code summary")
    bugs: list[BugResponse] = Field(..., description="List of detected bugs")
    style_issues: list[StyleIssueResponse] = Field(..., description="List of style issues")
    perf_concerns: list[PerfConcernResponse] = Field(..., description="List of performance concerns")
    refactoring: list[RefactoringResponse] = Field(..., description="List of refactoring opportunities")
    analysis_time_ms: int = Field(..., description="Time taken for analysis in milliseconds")
    cache_hit: bool = Field(..., description="Whether result was loaded from cache")
    truncated: bool = Field(..., description="Whether file was truncated due to size limit")

    class Config:
        schema_extra = {
            "example": {
                "file_path": "src/auth.py",
                "language": "python",
                "summary": {
                    "purpose": "Authentication module with login/logout functionality",
                    "complexity": "medium",
                    "tech_stack": ["flask", "sqlalchemy", "bcrypt"],
                    "loc_count": 156,
                },
                "bugs": [
                    {
                        "type": "sql_injection",
                        "severity": "critical",
                        "line": 45,
                        "description": "Raw SQL in login query",
                        "fix_suggestion": "Use parameterized queries",
                    }
                ],
                "style_issues": [],
                "perf_concerns": [],
                "refactoring": [],
                "analysis_time_ms": 2150,
                "cache_hit": False,
                "truncated": False,
            }
        }


class CodexErrorResponse(BaseModel):
    """Error response."""
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")


# ============================================================================
# API Handler
# ============================================================================

class CodexAPIHandler:
    """Handles HTTP requests for code analysis."""

    def __init__(self, cache_dir: Optional[Path] = None, state_dir: Optional[Path] = None):
        """Initialize handler with CodexEngine instance."""
        self.engine = CodexEngine(cache_dir=cache_dir, state_dir=state_dir)

    async def analyze(self, request: CodexAnalyzeRequest) -> CodexAnalyzeResponse | CodexErrorResponse:
        """
        Analyze code file and return structured results.

        Args:
            request: CodexAnalyzeRequest with file_path, content, and optional language

        Returns:
            CodexAnalyzeResponse with analysis results, or CodexErrorResponse on error.
        """
        try:
            logger.info(f"Analyzing {request.file_path} ({request.language or 'auto-detect'})")

            # Call engine
            result: AnalysisResult = self.engine.analyze(
                file_path=request.file_path,
                content=request.content,
                language=request.language,
            )

            # Convert to response model
            response = self._result_to_response(result)
            logger.info(f"Analysis complete: {len(result.bugs)} bugs, {len(result.style_issues)} style issues")
            return response

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return CodexErrorResponse(
                error="Analysis failed",
                details=str(e),
            )

    def _result_to_response(self, result: AnalysisResult) -> CodexAnalyzeResponse:
        """Convert AnalysisResult to CodexAnalyzeResponse."""
        return CodexAnalyzeResponse(
            file_path=result.file_path,
            language=result.language,
            summary=CodeSummaryResponse(
                purpose=result.summary.purpose,
                complexity=result.summary.complexity,
                tech_stack=result.summary.tech_stack,
                loc_count=result.summary.loc_count,
            ),
            bugs=[
                BugResponse(
                    type=b.type,
                    severity=b.severity,
                    line=b.line,
                    description=b.description,
                    fix_suggestion=b.fix_suggestion,
                )
                for b in result.bugs
            ],
            style_issues=[
                StyleIssueResponse(
                    issue_type=s.issue_type,
                    line=s.line,
                    description=s.description,
                    suggestion=s.suggestion,
                )
                for s in result.style_issues
            ],
            perf_concerns=[
                PerfConcernResponse(
                    concern_type=p.concern_type,
                    severity=p.severity,
                    description=p.description,
                    suggestion=p.suggestion,
                )
                for p in result.perf_concerns
            ],
            refactoring=[
                RefactoringResponse(
                    opportunity_type=r.opportunity_type,
                    description=r.description,
                    impact=r.impact,
                )
                for r in result.refactoring
            ],
            analysis_time_ms=result.analysis_time_ms,
            cache_hit=result.cache_hit,
            truncated=result.truncated,
        )


# ============================================================================
# Convenience Functions for FastAPI Integration
# ============================================================================

_handler_instance: Optional[CodexAPIHandler] = None


def get_handler() -> CodexAPIHandler:
    """Get or create singleton CodexAPIHandler."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = CodexAPIHandler()
    return _handler_instance


# ============================================================================
# FastAPI Route Example (for reference)
# ============================================================================

"""
Example integration into runtime/agents/problem-solver-ui/server.py:

from fastapi import FastAPI, HTTPException
from core.codex_api import CodexAnalyzeRequest, CodexAnalyzeResponse, CodexErrorResponse, get_handler

app = FastAPI()

@app.post("/api/codex/analyze", response_model=CodexAnalyzeResponse)
async def analyze_code(request: CodexAnalyzeRequest):
    handler = get_handler()
    response = await handler.analyze(request)

    if isinstance(response, CodexErrorResponse):
        raise HTTPException(status_code=400, detail=response.dict())

    return response
"""
