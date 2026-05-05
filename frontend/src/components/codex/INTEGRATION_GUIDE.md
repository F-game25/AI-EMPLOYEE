# Codex UI Integration Guide

## Overview

Phase 2.4 Codex UI provides a complete code analysis dashboard for displaying Codex engine results. The system displays:

- Analysis summary (KPI metrics)
- Interactive issue filtering (severity, type, line)
- Code preview with syntax highlighting
- Issue detail panel with fix suggestions

## Component Structure

```
CodexAnalyzer (main container)
├── AnalysisSummary (KPI tiles)
├── CodePreview (left panel - code with issue highlights)
├── IssuesList (right panel - scrollable issues)
└── IssueDetail (overlay panel - full issue details)
```

## Integration with WorkspacePage

### Basic Integration

```jsx
import { CodexAnalyzer } from './codex'

export default function WorkspacePage() {
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState(null)

  // When user clicks a text file
  const openFile = async (file) => {
    const response = await fetch(`/workspace/${file.path}`)
    const content = await response.text()
    setSelectedFile(file)
    setFileContent(content)
  }

  return (
    <div>
      {/* File list */}
      <FileList onSelect={openFile} />

      {/* Code analysis panel */}
      {selectedFile && (
        <CodexAnalyzer
          fileId={selectedFile.id}
          fileName={selectedFile.name}
          fileContent={fileContent}
          onClose={() => setSelectedFile(null)}
        />
      )}
    </div>
  )
}
```

## API Contract

### Request

```javascript
POST /api/codex/analyze
Content-Type: application/json

{
  "file_name": "app.py",
  "content": "def hello():\n    print('hi')",
  "language": "python"
}
```

### Response

```javascript
{
  "data": {
    "summary": {
      "total_issues": 3,
      "bugs": 1,
      "style_issues": 1,
      "performance_issues": 1
    },
    "bugs": [
      {
        "line": 5,
        "severity": "critical",
        "type": "bug",
        "title": "Null pointer dereference",
        "description": "Variable 'config' may be null",
        "code_snippet": "return config.get('api_key')",
        "fix_suggestion": "return config.get('api_key') if config else None",
        "impact": "Runtime crash in production",
        "recommendation": "Add null check before accessing config"
      }
    ],
    "style_issues": [
      {
        "line": 2,
        "severity": "low",
        "type": "style",
        "title": "Incorrect indentation",
        "description": "Expected 4 spaces, found 2",
        "fix_suggestion": "    return data  # 4 spaces"
      }
    ],
    "perf_concerns": [
      {
        "line": 15,
        "severity": "medium",
        "type": "perf",
        "title": "N+1 query pattern",
        "description": "Loop queries database in each iteration",
        "recommendation": "Use batch query or join"
      }
    ],
    "refactoring": [
      {
        "line": 8,
        "severity": "low",
        "type": "refactoring",
        "title": "Extract method",
        "description": "This 20-line function could be split"
      }
    ],
    "analysis_time_ms": 145
  }
}
```

## Props

### CodexAnalyzer

```typescript
interface CodexAnalyzerProps {
  fileId: string                    // Unique file identifier
  fileName: string                  // File name (for language detection)
  fileContent: string               // Raw file content
  onClose?: () => void              // Callback when user closes panel
}
```

### AnalysisSummary

```typescript
interface AnalysisSummaryProps {
  analysis: {
    bugs: Issue[]
    style_issues: Issue[]
    perf_concerns: Issue[]
    refactoring: Issue[]
    analysis_time_ms: number
  }
  issues: Issue[]                   // Combined all issues
}
```

### CodePreview

```typescript
interface CodePreviewProps {
  content: string                   // File content
  language?: string                 // Programming language
  issues?: Issue[]                  // Issues to highlight
  onLineClick?: (lineNum: number) => void   // Line click handler
  selectedLine?: number             // Currently selected line
}
```

### IssuesList

```typescript
interface IssuesListProps {
  issues: Issue[]                   // Issues to display
  selected?: Issue                  // Currently selected issue
  onSelect: (issue: Issue) => void  // Issue selection handler
}
```

### IssueDetail

```typescript
interface IssueDetailProps {
  issue: Issue                      // Issue to display
  onClose: () => void               // Callback to close panel
}
```

## Styling & Customization

### Color Tokens

The UI uses CSS custom properties for theming:

```css
/* Severity colors */
--danger: #EF4444        /* Critical */
--warning: #F59E0B       /* High */
--gold: #E5C76B          /* Medium */
--success: #22C55E       /* Low */

/* UI tokens */
--bg-base: #070810
--bg-card: #0C0E18
--text-primary: #EAEAF0
--text-secondary: #9A9AA5
--border-gold-dim: rgba(229, 199, 107, 0.1)
```

### Responsive Behavior

- **Desktop (>1024px)**: Full 2-column split layout
- **Tablet (768-1024px)**: Stacked layout
- **Mobile (<768px)**: Single column, issue detail as slide-up overlay

## Issue Data Structure

```typescript
interface Issue {
  line: number              // Line number where issue occurs
  type: 'bug' | 'style' | 'perf' | 'refactoring'
  severity: 'critical' | 'high' | 'medium' | 'low'
  title: string            // Brief issue title
  description: string      // Full description
  code_snippet?: string    // Problematic code
  fix_suggestion?: string  // Recommended fix
  impact?: string          // Impact description
  recommendation?: string  // How to fix
  id?: string              // Optional unique ID
}
```

## Filtering Behavior

The UI supports multi-dimensional filtering:

1. **Severity**: critical, high, medium, low
2. **Type**: bugs, style, perf, refactoring
3. **Line**: Click line numbers in code preview to filter to that line

Filters are cumulative (AND logic).

## Keyboard Shortcuts

- **Escape**: Close detail panel
- **Enter/Space**: Toggle line filter when line number focused

## Performance Considerations

- Code content is virtualized if >5000 lines (future enhancement)
- Issue list uses scrollable container
- Detail panel uses overlay to avoid reflow
- Memoization used for issue filtering

## Testing Scenarios

```javascript
// Test 1: Basic analysis
const testFile = {
  fileId: 'test-1',
  fileName: 'app.py',
  fileContent: 'def hello():\n    print("world")'
}

// Test 2: File with critical bugs
const testFileBugs = {
  fileName: 'buggy.js',
  fileContent: 'const x = null; x.toString();'
}

// Test 3: Large file (performance)
const largeFile = {
  fileName: 'large.py',
  fileContent: 'x = 0\n'.repeat(10000)
}

// Test 4: Filter interactions
// - Select severity filter
// - Click issue in list
// - Click line number in code
// - Click "Copy Fix" button
// - Close detail panel
```

## Error Handling

The CodexAnalyzer handles:

- **Network errors**: Shows error message with retry button
- **Large files**: Shows "File too large to analyze" message
- **Empty analysis**: Shows "No issues found" with green checkmark
- **No file loaded**: Shows placeholder message

## Backend Integration

The component expects a `/api/codex/analyze` endpoint that:

1. Accepts file content and language
2. Runs analysis using Codex engine
3. Returns structured issue objects
4. Completes within 5 seconds
5. Returns zero issues if no problems found

## Example Backend Handler

```python
@app.post("/api/codex/analyze")
async def analyze_code(request: CodeAnalysisRequest):
    """Run Codex analysis on uploaded file."""
    language = request.language or detect_language(request.file_name)
    
    result = codex_engine.analyze(
        content=request.content,
        language=language,
        file_name=request.file_name
    )
    
    return {
        "data": {
            "bugs": result.bugs,
            "style_issues": result.style_issues,
            "perf_concerns": result.perf_concerns,
            "refactoring": result.refactoring,
            "analysis_time_ms": result.elapsed_ms
        }
    }
```

## Future Enhancements

- Code completion integration
- Quick-fix auto-apply
- Issue suppression/ignore markers
- Custom rule configuration
- Analysis history/trending
- Team code review comments
- Integration with git diff
- Batch file analysis
