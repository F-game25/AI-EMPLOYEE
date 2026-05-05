# Codex UI Components

Phase 2.4 dashboard for displaying code analysis results from the Codex engine.

## Components

### CodexAnalyzer (350+ lines)

Main orchestrator component. Handles:
- File upload/selection via props
- API calls to `/api/codex/analyze`
- State management for issues, filters, selections
- Layout composition (summary + split view)
- Error/loading states

**Usage:**

```jsx
<CodexAnalyzer
  fileId="file-123"
  fileName="app.py"
  fileContent={content}
  onClose={handleClose}
/>
```

**Key Features:**
- Auto-analyzes when `fileContent` changes
- Combines bugs, style, perf, refactoring into single issues array
- Severity-based sorting (critical → high → medium → low)
- Line number filtering
- Responsive 2-column → 1-column layout

### AnalysisSummary (100 lines)

KPI metrics display using nexus-ui KPITile components.

**Shows:**
- Total issue count with critical/high breakdown
- Bug count
- Style issue count
- Performance concern count
- Refactoring opportunity count
- Analysis time (ms/s)

**Tones:**
- Critical/High issues: `alert` (red)
- Medium issues: `warn` (orange)
- Low issues: `cool` (blue)
- No issues: `success` (green)

### CodePreview (180 lines)

Syntax-highlighted code display with issue annotations.

**Features:**
- Line-numbered display
- Per-line severity highlighting (background color)
- Issue badges (emoji + count) on problematic lines
- Clickable line numbers to filter to that line
- Scrollable with sticky line numbers
- Responsive monospace font

**Line Highlighting:**
- Critical: Dark red background
- High: Orange background
- Medium: Gold background
- Low: Subtle green background
- Selected: Gold highlight + border

### IssuesList (200 lines)

Scrollable list of all issues with filtering support.

**Features:**
- Issue type badge (🐛 bug, 🎨 style, ⚙ perf, ♻ refactoring)
- Severity pill (critical/high/medium/low)
- Line number reference
- Title + description snippet
- Click to select → shows detail panel
- Highlighted when selected

**Filtering:**
- Cumulative filters: severity, type, line number
- Shows count of matching issues
- Dynamically updates on filter change

### IssueDetail (150 lines)

Slide-up overlay panel with full issue information.

**Sections:**
- Issue title, severity, line number (header)
- Description (problem explanation)
- Code snippet (problematic code)
- Fix suggestion (with copy button)
- Impact (consequences of issue)
- Recommendation (how to fix)

**Actions:**
- Close button (top-right or footer button)
- Copy Fix button → copies fix_suggestion to clipboard
- Overlay click → close

**Visual Design:**
- Slide-up animation
- Overlay with backdrop blur
- Green-tinted fix suggestion box
- Rounded corners at top

## API Contract

### Request

```bash
POST /api/codex/analyze
Content-Type: application/json

{
  "file_name": "example.py",
  "content": "def foo():\n    pass",
  "language": "python"
}
```

### Response

```json
{
  "data": {
    "bugs": [
      {
        "line": 3,
        "severity": "critical",
        "type": "bug",
        "title": "Unused variable",
        "description": "Variable 'x' is never used",
        "code_snippet": "x = 5",
        "fix_suggestion": "# Remove unused variable",
        "impact": "Dead code increases complexity",
        "recommendation": "Delete the assignment"
      }
    ],
    "style_issues": [...],
    "perf_concerns": [...],
    "refactoring": [...],
    "analysis_time_ms": 142
  }
}
```

## Styling

### CSS Files

Each component has its own CSS module:

- `CodexAnalyzer.css` - Main layout, header, filters, splits
- `AnalysisSummary.css` - KPI grid layout
- `CodePreview.css` - Code table, line highlighting, badges
- `IssuesList.css` - List items, scrolling
- `IssueDetail.css` - Overlay panel, animations, fix box

### Design Tokens

Uses CSS custom properties from `index.css`:

```css
/* Colors */
--gold: #E5C76B              /* Primary accent */
--error: #EF4444             /* Critical severity */
--warning: #F59E0B           /* High severity */
--success: #22C55E           /* Low severity */

/* Backgrounds */
--bg-base: #070810
--bg-card: #0C0E18
--bg-deep: #050608

/* Text */
--text-primary: #EAEAF0
--text-secondary: #9A9AA5
--text-muted: #666670

/* Borders */
--border-gold-dim: rgba(229, 199, 107, 0.1)
--border-gold: rgba(229, 199, 107, 0.3)
```

### Responsive Breakpoints

- **Desktop (>1024px)**: Full 2-column layout
- **Tablet (768-1024px)**: Stacked layout
- **Mobile (<640px)**: Single column

## State Management

### CodexAnalyzer State

```javascript
const [analysis, setAnalysis]         // Codex response data
const [loading, setLoading]           // API loading state
const [error, setError]               // Error message
const [selectedIssue, setSelectedIssue] // Currently viewed issue
const [severityFilter, setSeverityFilter] // Filter by severity
const [typeFilter, setTypeFilter]     // Filter by type
const [highlightedLine, setHighlightedLine] // Selected code line
```

### Derived State

```javascript
const filteredIssues = getFilteredIssues() // Applies all filters
const allIssues = getAllIssues()     // Combined from all categories
```

## Accessibility

- Semantic HTML (table for code, button for interactions)
- ARIA labels on buttons
- Keyboard navigation (Escape to close panels)
- Color contrast meets WCAG AA
- Screen reader friendly status pills
- Focus indicators on interactive elements

## Performance Optimizations

- `useCallback` for filter handlers (prevent re-renders)
- `useMemo` for issue processing (expensive array operations)
- Lazy rendering of issues (scrollable container)
- CSS-based highlighting (no DOM nodes per issue)
- Memoized language detection

## Testing

### Test Cases

1. **Load analysis**
   - Upload file → auto-analyze
   - Verify KPI metrics display
   - Verify issue count matches

2. **Filter by severity**
   - Select "Critical" → only critical issues shown
   - Select "Medium" → only medium issues shown
   - Select "All" → all issues shown

3. **Filter by type**
   - Select "Bugs" → only bug-type issues
   - Select "Style" → only style issues
   - Combo: severity + type filters work together

4. **Click code line**
   - Click line number → filter to that line
   - Issues on other lines hidden
   - Click again → clear line filter

5. **Click issue in list**
   - Click issue → detail panel slides up
   - Issue becomes selected (highlighted in list)
   - Detail panel shows full info

6. **Detail panel actions**
   - Copy Fix button → copies suggestion to clipboard
   - Show "✓ Copied" confirmation
   - Close button (X or footer) → hides panel

7. **Responsive**
   - Resize to tablet → layout stacks vertically
   - Resize to mobile → detail panel slides from bottom
   - Filters remain functional

## File Structure

```
frontend/src/components/codex/
├── CodexAnalyzer.jsx       (Main orchestrator, 350+ lines)
├── CodexAnalyzer.css       (Layout, header, filters, splits)
├── AnalysisSummary.jsx     (KPI metrics, 100 lines)
├── AnalysisSummary.css     (Grid layout)
├── CodePreview.jsx         (Code + highlights, 180 lines)
├── CodePreview.css         (Table, line colors, badges)
├── IssuesList.jsx          (Issue list, 200 lines)
├── IssuesList.css          (Item styling, scrolling)
├── IssueDetail.jsx         (Detail panel, 150 lines)
├── IssueDetail.css         (Overlay, animations, sections)
├── index.js                (Barrel export)
├── README.md               (This file)
└── INTEGRATION_GUIDE.md    (Integration instructions)
```

## Key Implementation Details

### Issue Type & Severity Sorting

Issues are sorted by severity (critical first):

```javascript
const SEVERITY_ORDER = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3
}
```

### Language Detection

From file extension (configurable):

```javascript
const langMap = {
  py: 'python', js: 'javascript', ts: 'typescript',
  jsx: 'jsx', tsx: 'tsx', sh: 'bash', ...
}
```

### Line Highlighting

Per-line background color based on most severe issue:

```css
.code-line--critical { background: rgba(239, 68, 68, 0.08); }
.code-line--high     { background: rgba(245, 158, 11, 0.08); }
.code-line--medium   { background: rgba(229, 199, 107, 0.06); }
.code-line--low      { background: rgba(34, 197, 94, 0.06); }
```

### Issue Badges

Issue type emoji badges in code preview:
- 🐛 Bug
- 🎨 Style
- ⚙ Performance
- ♻ Refactoring

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

Uses modern CSS (grid, flexbox, CSS variables) and ES2020+ JavaScript.

## Dependencies

- React 18+
- `nexus-ui` components (KPITile, StatusPill, HexButton, SectionLabel)

No external syntax highlighting required (can be added for enhanced support).

## Future Enhancements

- Syntax highlighting with Prism.js or Highlight.js
- Code virtualization for 10K+ line files
- Issue history/trending
- Custom rule configuration
- Batch analysis
- Integration with IDE extensions
- Auto-fix application
- Issue suppression markers
