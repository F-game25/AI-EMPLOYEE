#!/usr/bin/env python3
"""
Codex Engine — Usage Examples

This script demonstrates how to use the CodexEngine for code analysis.
Run: python3 runtime/core/codex_example.py
"""

import sys
from pathlib import Path

# Add runtime to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.codex import CodexEngine, analyze_code
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Example 1: Simple Python Code Analysis
PYTHON_EXAMPLE = '''
def fetch_user_data(user_id):
    """Fetch user data by ID."""
    # BUG: No null check, potential null reference error
    user = database.query(f"SELECT * FROM users WHERE id = {user_id}")
    return user.email.lower()


def inefficient_search(items):
    """Search items inefficiently."""
    results = []
    # BUG: N+1 problem — querying inside loop
    for item_id in items:
        item = db.query(f"SELECT * FROM items WHERE id = {item_id}")
        results.append(item)
    return results


# STYLE: Variable name 'x' is not descriptive
x = []
for i in range(100):
    x.append(i * 2)
'''


# Example 2: JavaScript Code Analysis
JAVASCRIPT_EXAMPLE = '''
async function fetchUserProfile(userId) {
  // BUG: Unnecessary await
  const response = await fetch(`/api/users/${userId}`);
  const data = await response.json();

  // STYLE: Using 'var' instead of 'const'
  var userName = data.name;

  return { name: userName, id: userId };
}

function processData() {
  // PERF: Potential memory leak, listener not removed
  element.addEventListener('click', function handler() {
    console.log('clicked');
    // handler never removed
  });
}

// DUPLICATION: These functions are nearly identical
function validateEmail(email) {
  if (!email || !email.includes('@')) return false;
  return true;
}

function validatePhone(phone) {
  if (!phone || !phone.includes('-')) return false;
  return true;
}
'''


# Example 3: SQL with Injection Vulnerability
SQL_EXAMPLE = '''
SELECT * FROM users
WHERE id = {user_id}
  AND username = '{username}'
  AND email = '{email}';
'''


def example_basic_analysis():
    """Example 1: Basic code analysis."""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic Python Code Analysis")
    print("=" * 80)

    engine = CodexEngine()
    result = engine.analyze("example.py", PYTHON_EXAMPLE, "python")

    print(f"\nFile: {result.file_path}")
    print(f"Language: {result.language}")
    print(f"Analysis Time: {result.analysis_time_ms}ms")
    print(f"Cache Hit: {result.cache_hit}")

    print(f"\nSummary:")
    print(f"  Purpose: {result.summary.purpose}")
    print(f"  Complexity: {result.summary.complexity}")
    print(f"  Tech Stack: {', '.join(result.summary.tech_stack)}")
    print(f"  LOC: {result.summary.loc_count}")

    print(f"\nBugs Found: {len(result.bugs)}")
    for i, bug in enumerate(result.bugs, 1):
        print(f"  {i}. [{bug.severity.upper()}] Line {bug.line}: {bug.type}")
        print(f"     Issue: {bug.description}")
        print(f"     Fix: {bug.fix_suggestion}")

    print(f"\nStyle Issues: {len(result.style_issues)}")
    for i, issue in enumerate(result.style_issues, 1):
        print(f"  {i}. Line {issue.line}: {issue.issue_type}")
        print(f"     Issue: {issue.description}")
        print(f"     Suggestion: {issue.suggestion}")

    print(f"\nPerformance Concerns: {len(result.perf_concerns)}")
    for i, concern in enumerate(result.perf_concerns, 1):
        print(f"  {i}. [{concern.severity.upper()}] {concern.concern_type}")
        print(f"     Issue: {concern.description}")
        print(f"     Suggestion: {concern.suggestion}")

    print(f"\nRefactoring Opportunities: {len(result.refactoring)}")
    for i, opp in enumerate(result.refactoring, 1):
        print(f"  {i}. {opp.opportunity_type} ({opp.impact} impact)")
        print(f"     {opp.description}")

    # Convert to JSON for API response
    print(f"\nJSON Response (for API):")
    print(json.dumps(result.to_dict(), indent=2)[:500] + "...")


def example_javascript_analysis():
    """Example 2: JavaScript code analysis."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: JavaScript Code Analysis")
    print("=" * 80)

    engine = CodexEngine()
    result = engine.analyze("app.js", JAVASCRIPT_EXAMPLE, "javascript")

    print(f"\nFile: {result.file_path}")
    print(f"Language: {result.language}")
    print(f"Complexity: {result.summary.complexity}")
    print(f"Bugs: {len(result.bugs)}")
    print(f"Style Issues: {len(result.style_issues)}")
    print(f"Performance Concerns: {len(result.perf_concerns)}")
    print(f"Refactoring Opportunities: {len(result.refactoring)}")

    if result.bugs:
        print(f"\nBugs:")
        for bug in result.bugs:
            print(f"  - [{bug.severity}] {bug.description} (line {bug.line})")


def example_caching():
    """Example 3: Demonstrate caching behavior."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Caching Behavior")
    print("=" * 80)

    engine = CodexEngine()
    code = "def hello(): return 'world'"

    print(f"\n1st analysis (cache miss):")
    result1 = engine.analyze("hello.py", code, "python")
    print(f"   Time: {result1.analysis_time_ms}ms")
    print(f"   Cache Hit: {result1.cache_hit}")

    print(f"\n2nd analysis (cache hit):")
    result2 = engine.analyze("hello.py", code, "python")
    print(f"   Time: {result2.analysis_time_ms}ms")
    print(f"   Cache Hit: {result2.cache_hit}")

    print(f"\nSpeed improvement: {result1.analysis_time_ms / (result2.analysis_time_ms or 1):.0f}x faster")


def example_language_detection():
    """Example 4: Language auto-detection."""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Language Auto-Detection")
    print("=" * 80)

    engine = CodexEngine()

    test_cases = [
        ("script.py", "x = 1", "python"),
        ("app.js", "var x = 1;", "javascript"),
        ("config.ts", "const x: number = 1;", "typescript"),
        ("file.go", "func main() {}", "go"),
        ("unknown.xyz", "???", "unknown"),
    ]

    for filename, code, expected in test_cases:
        detected = engine._detect_language(filename)
        status = "✓" if detected == expected else "✗"
        print(f"{status} {filename:20} → {detected:15} (expected: {expected})")


def example_convenience_function():
    """Example 5: Using convenience function."""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Convenience Function")
    print("=" * 80)

    # analyze_code() is a module-level convenience function
    result = analyze_code("simple.py", "def add(a, b): return a + b", "python")

    print(f"\nFile: {result.file_path}")
    print(f"Purpose: {result.summary.purpose}")
    print(f"Bugs: {len(result.bugs)}")


def main():
    """Run all examples."""
    print("\n╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "Codex Engine — Usage Examples".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")

    try:
        # Note: These examples won't run actual LLM calls in production
        # They're designed to show the API usage patterns
        # In a real environment with LLM configured, actual analysis would occur

        example_language_detection()
        example_caching()
        example_convenience_function()

        print("\n" + "=" * 80)
        print("NOTES:")
        print("=" * 80)
        print("""
1. The above examples demonstrate the Codex Engine API usage patterns.

2. In production with an LLM configured (Anthropic/Ollama/OpenRouter):
   - Analyses will call the LLM and return real bugs, style issues, etc.
   - Results will be cached for improved performance
   - Each analysis is logged to state/codex_analysis.jsonl

3. Integration point: Use CodexAPIHandler for FastAPI integration:
   from core.codex_api import get_handler
   result = await get_handler().analyze(CodexAnalyzeRequest(...))

4. For frontend integration, call the /api/codex/analyze HTTP endpoint

5. See CODEX_INTEGRATION.md for complete integration guide
        """)

    except Exception as e:
        logger.error(f"Error running examples: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
