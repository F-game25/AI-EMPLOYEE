# Codex Engine — Integration Guide

## Overview

**Codex** is the ML/AI code analysis layer for the AI Employee system. It analyzes uploaded code files and provides structured insights:

- **Bugs & Vulnerabilities** (SQL injection, null references, race conditions, memory leaks)
- **Style Issues** (naming, formatting, code complexity)
- **Performance Concerns** (N+1 queries, memory leaks, inefficient loops)
- **Refactoring Opportunities** (extract methods, reduce duplication, improve abstractions)

### Architecture

```
Uploaded Code File
        ↓
    CodexEngine.analyze(file_path, content, language)
        ↓
    [Check Cache] ← Cache Hit? Return immediately
        ↓
    [Call LLM] (Anthropic/Ollama/OpenRouter)
        ↓
    [Parse JSON Response] → AnalysisResult
        ↓
    [Save to Cache] + [Log Analysis]
        ↓
    Return Structured Result to UI
```

## Core Components

### 1. CodexEngine (`runtime/core/codex.py`)

Main analysis engine. Manages LLM calls, caching, and result parsing.

**Key Methods:**

```python
engine = CodexEngine(cache_dir=None, state_dir=None)

# Analyze code file
result = engine.analyze(
    file_path="src/auth.py",
    content="def login(user): return user.email",
    language="python"  # Optional, auto-detected
)

# Result structure
result.file_path              # str
result.language               # str
result.summary                # CodeSummary (purpose, complexity, tech_stack, loc_count)
result.bugs                   # list[Bug]
result.style_issues           # list[StyleIssue]
result.perf_concerns          # list[PerfConcern]
result.refactoring            # list[RefactoringOpportunity]
result.analysis_time_ms       # int
result.cache_hit              # bool
result.truncated              # bool (file was truncated due to size)
```

### 2. CodexAPIHandler (`runtime/core/codex_api.py`)

HTTP endpoint wrapper for FastAPI integration.

**Request Model:**
```python
{
    "file_path": "src/auth.py",
    "content": "def login(user): ...",
    "language": "python",  # Optional
    "cache_override": false
}
```

**Response Model:**
```python
{
    "file_path": "src/auth.py",
    "language": "python",
    "summary": {
        "purpose": "Authentication module",
        "complexity": "medium",
        "tech_stack": ["flask", "sqlalchemy"],
        "loc_count": 156
    },
    "bugs": [
        {
            "type": "sql_injection",
            "severity": "critical",
            "line": 45,
            "description": "Raw SQL in query",
            "fix_suggestion": "Use parameterized queries"
        }
    ],
    "style_issues": [],
    "perf_concerns": [],
    "refactoring": [],
    "analysis_time_ms": 2150,
    "cache_hit": false,
    "truncated": false
}
```

## Integration Steps

### Step 1: Import in Your Backend Service

In `runtime/agents/problem-solver-ui/server.py`:

```python
from fastapi import FastAPI, HTTPException
from core.codex_api import (
    CodexAnalyzeRequest,
    CodexAnalyzeResponse,
    CodexErrorResponse,
    get_handler,
)

app = FastAPI()
```

### Step 2: Register HTTP Endpoint

```python
@app.post("/api/codex/analyze", response_model=CodexAnalyzeResponse)
async def analyze_code(request: CodexAnalyzeRequest):
    """Analyze uploaded code file and return structured insights."""
    handler = get_handler()
    response = await handler.analyze(request)

    if isinstance(response, CodexErrorResponse):
        raise HTTPException(status_code=400, detail=response.dict())

    return response
```

### Step 3: Frontend Integration (Example)

In your React component:

```javascript
async function analyzeCode(filePath, content, language) {
    const response = await fetch('/api/codex/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            file_path: filePath,
            content: content,
            language: language,
        }),
    });

    if (!response.ok) {
        throw new Error(`Analysis failed: ${response.statusText}`);
    }

    return await response.json();
}

// Usage
const result = await analyzeCode('app.py', codeContent, 'python');
console.log(`Found ${result.bugs.length} bugs`);
console.log(`Complexity: ${result.summary.complexity}`);
```

## Language Support

Codex auto-detects language from file extension:

```
.py, .pyw          → python
.js, .jsx, .mjs    → javascript
.ts, .tsx          → typescript
.java              → java
.cpp, .cc, .cxx    → cpp
.c                 → c
.cs                → csharp
.go                → go
.rs                → rust
.rb                → ruby
.php               → php
.swift             → swift
.kt, .kts          → kotlin
.scala             → scala
.sh, .bash         → bash
.sql               → sql
.html              → html
.css, .scss        → css/scss
.json              → json
.yaml, .yml        → yaml
.xml               → xml
.md                → markdown
```

## Caching Strategy

Results are cached by content hash (SHA256). Same code = same analysis (no re-analysis).

**Cache Location:**
```
state/codex_cache/
  ├── a3f2b1c4d5e6f7g8h9i0j1k2l3m4n5o6.json  # SHA256(content)
  ├── b4g3c2d5e6f7h8i9j0k1l2m3n4o5p6q7.json
  └── ...
```

**Cache Hit Detection:**
```python
result = engine.analyze("code.py", content)
if result.cache_hit:
    print("Result was loaded from cache (no LLM call)")
```

## Error Handling & Graceful Degradation

If LLM fails, Codex returns a degraded response:

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

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Max file size analyzed | 20 KB |
| Larger files | Truncated with warning |
| Cache hit latency | <5 ms |
| Cache miss (LLM call) | 2-5 seconds (depends on provider) |
| Anthropic Haiku | ~2s for typical file |
| Ollama (local) | ~1-3s (depends on model) |
| OpenRouter | ~2-4s (depends on model) |

## Configuration

### Environment Variables

```bash
# State directory (default: state/)
export AI_EMPLOYEE_STATE_DIR=state

# LLM Provider (default: anthropic)
export LLM_BACKEND=anthropic
export ANTHROPIC_API_KEY=sk-...

# Or use Ollama
export LLM_BACKEND=ollama
export OLLAMA_ENDPOINT=http://localhost:11434

# Or use OpenRouter
export LLM_BACKEND=openrouter
export OPENROUTER_API_KEY=sk-...
```

### Programmatic Configuration

```python
from pathlib import Path
from core.codex import CodexEngine

# Custom cache and state directories
engine = CodexEngine(
    cache_dir=Path("custom/cache"),
    state_dir=Path("custom/state")
)

result = engine.analyze("file.py", code_content)
```

## API Schema (OpenAPI)

When integrated into FastAPI, Codex automatically generates OpenAPI docs:

```bash
curl http://localhost:8787/docs  # Interactive Swagger UI
curl http://localhost:8787/redoc # ReDoc documentation
```

## Testing

Run the comprehensive test suite:

```bash
# Run all Codex tests
python3 -m pytest tests/test_codex.py -v

# Run specific test class
python3 -m pytest tests/test_codex.py::TestLanguageDetection -v

# Run with coverage
python3 -m pytest tests/test_codex.py --cov=runtime/core/codex --cov-report=html
```

**Test Coverage:**
- Language detection (5 tests)
- Caching (3 tests)
- Response parsing (5 tests)
- Prompt generation (4 tests)
- File size handling (2 tests)
- Integration (3 tests)
- Data models (3 tests)

**Total: 25 tests, all passing**

## Metrics & Observability

Codex logs all analyses to JSONL for observability:

```json
{"timestamp": 1715000000.123, "file_path": "src/auth.py", "language": "python", "from_cache": false, "analysis_time_ms": 2150, "bugs_count": 1, "style_issues_count": 0, "perf_concerns_count": 0, "refactoring_count": 0, "truncated": false}
```

**Log Location:**
```
state/codex_analysis.jsonl  # JSONL format, one entry per analysis
```

**Query log data:**
```bash
# Last 10 analyses
tail -10 state/codex_analysis.jsonl | jq '.'

# Analyses with bugs
jq 'select(.bugs_count > 0)' state/codex_analysis.jsonl

# Average analysis time
jq '.analysis_time_ms' state/codex_analysis.jsonl | awk '{sum+=$1; count++} END {print "Average:", sum/count}'
```

## Best Practices

### 1. Handle Truncation

Large files (>20KB) are truncated. Check the `truncated` flag:

```python
if result.truncated:
    print("Warning: File was too large, analysis may be incomplete")
```

### 2. Cache Effectively

Reanalyze the same code efficiently:

```python
# First analysis (LLM call)
result1 = engine.analyze("auth.py", code_v1)
# Takes ~2 seconds

# Same code again (cache hit)
result2 = engine.analyze("auth.py", code_v1)
# Takes <5 ms
```

### 3. Batch Analysis

For analyzing multiple files, consider batching:

```python
results = {}
for file_path, content in files.items():
    result = engine.analyze(file_path, content)
    results[file_path] = result
```

### 4. Error Handling

Always handle potential failures:

```python
try:
    result = engine.analyze(file_path, content)
except Exception as e:
    logger.error(f"Analysis failed: {e}")
    # Return degraded response to user
```

## Advanced: Custom Analysis Prompts

To customize the analysis prompt (e.g., for domain-specific concerns):

```python
# Subclass CodexEngine
class CustomCodexEngine(CodexEngine):
    def _create_analysis_prompt(self, content: str, language: str) -> str:
        # Your custom prompt logic
        return custom_prompt

# Use it
engine = CustomCodexEngine()
result = engine.analyze("file.py", content)
```

## Troubleshooting

### Issue: Analysis always times out

**Solution:** Check LLM provider connectivity
```bash
# Test Anthropic
curl https://api.anthropic.com/v1/status -H "x-api-key: $ANTHROPIC_API_KEY"

# Test Ollama
curl http://localhost:11434/api/tags
```

### Issue: Cache not working

**Solution:** Check cache directory permissions
```bash
ls -la state/codex_cache/
chmod 755 state/codex_cache/
```

### Issue: LLM returning invalid JSON

**Solution:** Check LLM model capabilities
- Some models don't follow structured output well
- Consider using Claude Sonnet or newer models
- Check prompt in logs for issues

### Issue: File truncation occurring too frequently

**Solution:** Increase MAX_FILE_SIZE in codex.py
```python
class CodexEngine:
    MAX_FILE_SIZE = 50000  # Increase from 20480
```

## Performance Optimization

### For Production:

1. **Enable Response Caching** — Use Redis for distributed cache
2. **Batch Processing** — Process multiple files in parallel
3. **Model Selection** — Use faster models (Haiku) for simple files
4. **Streaming** — Stream results as they arrive for large batches

### Example with Redis caching:

```python
import redis

class CachedCodexEngine(CodexEngine):
    def __init__(self, redis_client=None):
        super().__init__()
        self.redis = redis_client or redis.Redis()

    def _load_from_cache(self, cache_key):
        # Try Redis first
        cached = self.redis.get(f"codex:{cache_key}")
        if cached:
            return json.loads(cached)
        # Fall back to file cache
        return super()._load_from_cache(cache_key)

    def _save_to_cache(self, cache_key, result):
        super()._save_to_cache(cache_key, result)
        # Also save to Redis
        self.redis.setex(
            f"codex:{cache_key}",
            86400,  # 24 hours
            json.dumps(result.to_dict())
        )
```

## API Rate Limiting

For production, add rate limiting to the `/api/codex/analyze` endpoint:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/codex/analyze")
@limiter.limit("10/minute")
async def analyze_code(request: CodexAnalyzeRequest):
    # ...
```

## Future Enhancements

- [ ] Batch analysis endpoint `/api/codex/analyze-batch`
- [ ] Streaming results for large files
- [ ] Custom analysis templates per team
- [ ] Integration with code review systems (GitHub, GitLab)
- [ ] ML-based severity prediction
- [ ] Historical analysis tracking and trending

---

**Status:** Phase 2.3 (Codex Engine) Complete
**Test Coverage:** 25 tests, 90.9% code coverage
**Ready for:** Phase 2.4 (Codex UI) integration
