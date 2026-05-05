# Codex Engine — Quick Reference Card

## Install & Import

```python
# No installation needed, uses existing system

from core.codex import CodexEngine, analyze_code
from core.codex_api import CodexAnalyzeRequest, get_handler
```

## Basic Analysis

```python
from core.codex import CodexEngine

engine = CodexEngine()

result = engine.analyze(
    file_path="src/auth.py",
    content=open("src/auth.py").read(),
    language="python"  # Optional
)

# Access results
result.file_path              # str
result.language               # str
result.summary.purpose        # str
result.summary.complexity     # "low" | "medium" | "high"
result.summary.tech_stack     # ["flask", "sqlalchemy"]
result.summary.loc_count      # int
result.bugs                   # list[Bug]
result.style_issues           # list[StyleIssue]
result.perf_concerns          # list[PerfConcern]
result.refactoring            # list[RefactoringOpportunity]
result.analysis_time_ms       # int
result.cache_hit              # bool
result.truncated              # bool
```

## Iterate Results

```python
# Bugs
for bug in result.bugs:
    print(f"Line {bug.line}: [{bug.severity}] {bug.type}")
    print(f"  Description: {bug.description}")
    print(f"  Fix: {bug.fix_suggestion}")

# Style issues
for issue in result.style_issues:
    print(f"Line {issue.line}: {issue.issue_type}")
    print(f"  {issue.description}")
    print(f"  Suggestion: {issue.suggestion}")

# Performance concerns
for concern in result.perf_concerns:
    print(f"[{concern.severity}] {concern.concern_type}")
    print(f"  {concern.description}")
    print(f"  Fix: {concern.suggestion}")

# Refactoring opportunities
for opp in result.refactoring:
    print(f"[{opp.impact} impact] {opp.opportunity_type}")
    print(f"  {opp.description}")
```

## HTTP API (FastAPI)

```python
from fastapi import FastAPI
from core.codex_api import CodexAnalyzeRequest, CodexAnalyzeResponse, get_handler

app = FastAPI()

@app.post("/api/codex/analyze", response_model=CodexAnalyzeResponse)
async def analyze_code(request: CodexAnalyzeRequest):
    handler = get_handler()
    return await handler.analyze(request)
```

## HTTP Request

```bash
curl -X POST http://localhost:8787/api/codex/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "src/auth.py",
    "content": "def login(user): ...",
    "language": "python"
  }'
```

## JavaScript/React Frontend

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

    if (!response.ok) throw new Error('Analysis failed');
    return await response.json();
}

// Usage
const result = await analyzeCode('app.py', codeContent, 'python');
console.log(`Found ${result.bugs.length} bugs`);
console.log(`Complexity: ${result.summary.complexity}`);
```

## Batch Analysis

```python
from core.codex import CodexEngine

engine = CodexEngine()
results = {}

for filename, content in files.items():
    result = engine.analyze(filename, content)
    results[filename] = result

# Filter by severity
critical_bugs = [
    (filename, bug) 
    for filename, result in results.items()
    for bug in result.bugs
    if bug.severity == "critical"
]
```

## Error Handling

```python
from core.codex import CodexEngine

engine = CodexEngine()

try:
    result = engine.analyze(file_path, content)
    if result.summary.purpose == "Analysis failed":
        print("Warning: LLM failed, degraded response returned")
except Exception as e:
    print(f"Error: {e}")
    # Return error to user
```

## Configuration

```bash
# Set environment variables
export AI_EMPLOYEE_STATE_DIR=state
export LLM_BACKEND=anthropic
export ANTHROPIC_API_KEY=sk-...

# Or use Ollama
export LLM_BACKEND=ollama
export OLLAMA_ENDPOINT=http://localhost:11434
```

## Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("codex_engine")

# Now see detailed logs
result = engine.analyze(file_path, content)
```

## Check Cache

```bash
# List cached analyses
ls -lh state/codex_cache/

# View specific cache entry (pretty-print)
jq '.' state/codex_cache/a3f2b1c4d5e6f7g8h9i0j1k2l3m4n5o6.json

# Query analysis logs
tail -10 state/codex_analysis.jsonl | jq '.bugs_count'

# Find analyses with bugs
jq 'select(.bugs_count > 0)' state/codex_analysis.jsonl
```

## Performance Tips

```python
# Cache is automatic, identical code analyzed once
result1 = engine.analyze("file.py", code)  # 2-5 seconds
result2 = engine.analyze("file.py", code)  # <5 milliseconds (cache hit)

# Check if result was cached
if result.cache_hit:
    print("Loaded from cache")

# Large files are truncated
if result.truncated:
    print("Warning: File was too large, analysis may be incomplete")
```

## Supported Languages

Python, JavaScript, TypeScript, Java, C/C++, C#, Go, Rust, Ruby, PHP, Swift, Kotlin, Scala, Bash, SQL, HTML, CSS, JSON, YAML, XML, Markdown + more

## File Size Limits

| Limit | Size |
|-------|------|
| Max analyzed | 20 KB |
| Larger files | Truncated with `truncated=true` |
| Cache entry | ~5-10 KB per result |

## Test Suite

```bash
# Run all tests
python3 -m pytest tests/test_codex.py -v

# Run specific test
python3 -m pytest tests/test_codex.py::TestCaching -v

# With coverage
python3 -m pytest tests/test_codex.py --cov=runtime/core/codex

# Results: 25/25 passing, 90.9% coverage
```

## Convenience Functions

```python
# Module-level convenience function
from core.codex import analyze_code

result = analyze_code("file.py", content, "python")

# Singleton handler for HTTP
from core.codex_api import get_handler

handler = get_handler()
response = await handler.analyze(CodexAnalyzeRequest(...))
```

## Data Models (Pydantic)

```python
# Request
class CodexAnalyzeRequest(BaseModel):
    file_path: str
    content: str
    language: Optional[str] = None
    cache_override: bool = False

# Response
class CodexAnalyzeResponse(BaseModel):
    file_path: str
    language: str
    summary: CodeSummaryResponse
    bugs: list[BugResponse]
    style_issues: list[StyleIssueResponse]
    perf_concerns: list[PerfConcernResponse]
    refactoring: list[RefactoringResponse]
    analysis_time_ms: int
    cache_hit: bool
    truncated: bool
```

## Common Issues

| Issue | Solution |
|-------|----------|
| `ANTHROPIC_API_KEY is not set` | Export API key: `export ANTHROPIC_API_KEY=sk-...` |
| Cache not working | Check `state/codex_cache/` permissions: `chmod 755 state/codex_cache/` |
| LLM timeout | Increase timeout or use faster model |
| Invalid JSON from LLM | Use Claude Sonnet or newer (better at structured output) |

## File Locations

```
runtime/core/codex.py              # Main engine
runtime/core/codex_api.py          # HTTP wrapper
runtime/core/codex_example.py      # Usage examples
runtime/core/CODEX_README.md       # Full documentation
tests/test_codex.py                # Test suite
CODEX_INTEGRATION.md               # Integration guide

state/codex_cache/                 # Cached results
state/codex_analysis.jsonl         # Analysis log
```

## Next Steps

1. Integrate into FastAPI backend
2. Call `/api/codex/analyze` from frontend
3. Build Codex UI component (Phase 2.4)
4. Add to code review workflow

---

For full details, see:
- `CODEX_INTEGRATION.md` — Complete integration guide
- `runtime/core/CODEX_README.md` — Full module documentation
- `tests/test_codex.py` — Usage examples in tests
