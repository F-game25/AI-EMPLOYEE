# Codex Engine — ML/AI Code Analysis Module

**Phase 2.3 of the AI Employee System**

Codex is a production-grade Python module that analyzes source code files using large language models (LLMs) and returns structured insights about bugs, style issues, performance concerns, and refactoring opportunities.

## Quick Start

### Installation

No additional dependencies required. Codex integrates with existing system:
- Uses `core.orchestrator.LLMClient` for LLM calls
- Works with Anthropic, Ollama, and OpenRouter providers
- Manages caching automatically

### Basic Usage

```python
from core.codex import CodexEngine

# Create engine
engine = CodexEngine()

# Analyze code
result = engine.analyze(
    file_path="src/auth.py",
    content=open("src/auth.py").read(),
    language="python"  # Optional, auto-detected from extension
)

# Access results
print(f"Bugs found: {len(result.bugs)}")
print(f"Complexity: {result.summary.complexity}")
for bug in result.bugs:
    print(f"  Line {bug.line}: {bug.description}")
```

### HTTP API Integration

```python
from fastapi import FastAPI
from core.codex_api import CodexAnalyzeRequest, CodexAnalyzeResponse, get_handler

app = FastAPI()

@app.post("/api/codex/analyze", response_model=CodexAnalyzeResponse)
async def analyze_code(request: CodexAnalyzeRequest):
    handler = get_handler()
    return await handler.analyze(request)
```

## Architecture

### Core Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **CodexEngine** | Main analysis engine, LLM calls, caching | `runtime/core/codex.py` |
| **CodexAPIHandler** | HTTP endpoint wrapper for FastAPI | `runtime/core/codex_api.py` |
| **Data Models** | Type-safe request/response dataclasses | `runtime/core/codex.py` + `runtime/core/codex_api.py` |

### Data Flow

```
File Upload
    ↓
CodexEngine.analyze(file_path, content, language)
    ↓
[Detect Language] → [Check Cache] → [Cache Hit?] → Return
    ↓ (Cache Miss)
[Call LLM Provider] → [Parse JSON] → [Validate Structure]
    ↓
[Save to Cache] + [Log Analysis]
    ↓
Return AnalysisResult
```

## Features

### Code Analysis Capabilities

**Bugs & Vulnerabilities**
- Null reference errors
- SQL injection vulnerabilities
- Race conditions
- Memory leaks
- Logic errors

**Code Style Issues**
- Variable naming conventions
- Code formatting
- Comment quality
- Cyclomatic complexity

**Performance Concerns**
- N+1 query problems
- Memory leaks
- Inefficient loops
- Unnecessary allocations

**Refactoring Opportunities**
- Extract method candidates
- Reduce code duplication
- Improve abstractions
- Simplify complexity

### Technical Features

- **Language Detection** — Auto-detect from file extension
- **Content-Based Caching** — SHA256 keying, avoid re-analysis
- **Graceful Degradation** — Return degraded response if LLM fails
- **File Size Handling** — Truncate large files (>20KB) with warning
- **JSONL Logging** — All analyses logged for observability
- **Provider Agnostic** — Works with Anthropic, Ollama, OpenRouter
- **Type Safety** — Full type hints throughout
- **Error Resilience** — Comprehensive error handling

## API Reference

### CodexEngine Class

```python
class CodexEngine:
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        state_dir: Optional[Path] = None
    ):
        """Initialize with optional custom directories."""

    def analyze(
        self,
        file_path: str,
        content: str,
        language: Optional[str] = None
    ) -> AnalysisResult:
        """
        Analyze code file.
        
        Args:
            file_path: Path or name of file
            content: Full text content
            language: Programming language (auto-detected if None)
        
        Returns:
            AnalysisResult with complete analysis
        """
```

### AnalysisResult Dataclass

```python
@dataclass
class AnalysisResult:
    file_path: str              # File being analyzed
    language: str               # Programming language
    summary: CodeSummary        # High-level summary
    bugs: list[Bug]             # Found bugs/vulnerabilities
    style_issues: list[StyleIssue]  # Code style issues
    perf_concerns: list[PerfConcern]  # Performance concerns
    refactoring: list[RefactoringOpportunity]  # Refactoring ideas
    analysis_time_ms: int       # Time taken (milliseconds)
    cache_hit: bool             # Whether result was cached
    truncated: bool             # Whether file was truncated
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
```

### Supported Languages

| Extension | Language |
|-----------|----------|
| .py | Python |
| .js, .jsx | JavaScript |
| .ts, .tsx | TypeScript |
| .java | Java |
| .cpp, .c | C/C++ |
| .cs | C# |
| .go | Go |
| .rs | Rust |
| .rb | Ruby |
| .php | PHP |
| .swift | Swift |
| .kt | Kotlin |
| .scala | Scala |
| .sh | Bash |
| .sql | SQL |
| ... and 10+ more | See `LANGUAGE_MAP` |

## Testing

### Run Test Suite

```bash
# All tests
python3 -m pytest tests/test_codex.py -v

# Specific test class
python3 -m pytest tests/test_codex.py::TestCaching -v

# With coverage
python3 -m pytest tests/test_codex.py --cov=runtime/core/codex
```

### Test Coverage

- **25 total tests**, all passing
- **90.9% code coverage**
- Coverage areas:
  - Language detection (5 tests)
  - Caching mechanism (3 tests)
  - Response parsing (5 tests)
  - Prompt generation (4 tests)
  - File size handling (2 tests)
  - Integration (3 tests)
  - Data models (3 tests)

### Key Tests

```python
# Language detection
test_python_detection, test_javascript_detection, test_unknown_extension

# Caching
test_cache_key_generation, test_cache_save_and_load, test_cache_miss

# Response parsing
test_parse_valid_json_response, test_parse_invalid_json

# Integration
test_full_analysis_flow, test_cache_hit_avoids_llm_call, 
test_llm_failure_graceful_degradation
```

## Configuration

### Environment Variables

```bash
# State directory (default: state/)
export AI_EMPLOYEE_STATE_DIR=/path/to/state

# LLM Provider (default: anthropic)
export LLM_BACKEND=anthropic
export ANTHROPIC_API_KEY=sk-...
```

### Programmatic Configuration

```python
from pathlib import Path
from core.codex import CodexEngine

engine = CodexEngine(
    cache_dir=Path("cache/codex"),
    state_dir=Path("state")
)
```

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Max file size | 20 KB |
| Cache hit latency | <5 ms |
| Cache miss latency | 2-5 seconds |
| Anthropic (default) | ~2 seconds |
| Ollama (local) | ~1-3 seconds |
| Memory per analysis | ~1-2 MB |

## Storage

### Cache Storage

```
state/codex_cache/
├── a3f2b1c4d5e6f7g8h9i0j1k2l3m4n5o6.json  # SHA256(content)
├── b4g3c2d5e6f7h8i9j0k1l2m3n4o5p6q7.json
└── ...
```

### Analysis Log

```
state/codex_analysis.jsonl  # One JSON object per line
```

Log entries contain:
```json
{
  "timestamp": 1715000000.123,
  "file_path": "src/auth.py",
  "language": "python",
  "from_cache": false,
  "analysis_time_ms": 2150,
  "bugs_count": 1,
  "style_issues_count": 0,
  "perf_concerns_count": 0,
  "refactoring_count": 0,
  "truncated": false
}
```

## Error Handling

### LLM Failure Graceful Degradation

If the LLM call fails, Codex returns a degraded response:

```python
{
    "file_path": "error.py",
    "language": "python",
    "summary": {
        "purpose": "Analysis failed",
        "complexity": "unknown",
        "tech_stack": [],
        "loc_count": 42
    },
    "bugs": [],
    "style_issues": [],
    "perf_concerns": [],
    "refactoring": [],
    "analysis_time_ms": 5000,
    "cache_hit": false,
    "truncated": false
}
```

### Common Issues & Solutions

**Issue: Analysis always times out**
- Check LLM provider connectivity
- Verify API keys are set
- Check network connectivity

**Issue: Cache not working**
- Verify `state/codex_cache/` is writable
- Check file permissions: `chmod 755 state/codex_cache/`

**Issue: LLM returning invalid JSON**
- Some models don't follow structured output well
- Use Claude Sonnet or newer models
- Check the analysis logs for the raw LLM response

## Integration Examples

### FastAPI Integration

```python
from fastapi import FastAPI
from core.codex_api import CodexAnalyzeRequest, get_handler

app = FastAPI()

@app.post("/api/codex/analyze")
async def analyze(request: CodexAnalyzeRequest):
    handler = get_handler()
    return await handler.analyze(request)
```

### Batch Analysis

```python
from core.codex import CodexEngine

engine = CodexEngine()
results = {}

for file_path, content in files.items():
    result = engine.analyze(file_path, content)
    results[file_path] = result
```

### Error Handling

```python
from core.codex import CodexEngine

engine = CodexEngine()

try:
    result = engine.analyze(file_path, content)
except Exception as e:
    logger.error(f"Analysis failed: {e}")
    # Return graceful error response
```

## Next Steps (Phase 2.4)

After Codex Engine is integrated, Phase 2.4 will implement:

- **Codex UI** — React component for file upload and analysis display
- **Result Visualization** — Interactive bug browsing, severity filtering
- **History Tracking** — Store and compare analyses over time
- **Integration** — Link with code review workflows

## Files & Structure

```
runtime/core/
├── codex.py              # Main engine (16 KB, 186 lines)
├── codex_api.py          # HTTP wrapper (11 KB, 250+ lines)
├── codex_example.py      # Usage examples (8 KB)
└── CODEX_README.md       # This file

tests/
└── test_codex.py         # Comprehensive test suite (20 KB, 25 tests)

Documentation/
└── CODEX_INTEGRATION.md  # Full integration guide (13 KB)
```

## Troubleshooting

### Debug Logging

Enable debug logging to see detailed analysis flow:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("codex_engine")
```

### Check Cache Files

```bash
# List cached analyses
ls -lh state/codex_cache/

# View a specific cache entry
cat state/codex_cache/a3f2b1c4d5e6f7g8h9i0j1k2l3m4n5o6.json | jq '.'
```

### Query Analysis Logs

```bash
# Last 10 analyses
tail -10 state/codex_analysis.jsonl | jq '.'

# Analyses with bugs
jq 'select(.bugs_count > 0)' state/codex_analysis.jsonl

# Average analysis time
jq '.analysis_time_ms' state/codex_analysis.jsonl | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count "ms"}'
```

## Performance Optimization

### For Production:

1. **Enable Caching** — Cache results by content hash
2. **Batch Processing** — Process multiple files in parallel
3. **Model Selection** — Use faster models (Haiku) for simple files
4. **Streaming** — Stream results as they arrive

### Caching Effectiveness

With cache enabled:
- First analysis: ~2-5 seconds (LLM call)
- Subsequent identical analyses: <5 milliseconds (cache hit)
- Speed improvement: 400x-1000x faster

## Contributing

To extend Codex:

1. **Add new analysis capability** — Modify `_create_analysis_prompt()`
2. **Support new language** — Add to `LANGUAGE_MAP` dictionary
3. **Custom severity levels** — Extend `Bug.severity` enum
4. **Different cache backends** — Subclass `CodexEngine` and override `_load_from_cache()`

## License

Part of the AI Employee system. See main LICENSE file.

---

**Status:** Phase 2.3 Complete ✓
- Core engine: complete
- API wrapper: complete
- Test suite: complete (25/25 passing, 90.9% coverage)
- Documentation: complete
- **Ready for Phase 2.4 (Codex UI) integration**
