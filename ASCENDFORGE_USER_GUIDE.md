# AscendForgePage - User Guide

## Quick Start

Access AscendForgePage at the Forge navigation tab in the dashboard. The page displays:

1. **4 KPI Tiles** - Overall progress, active objectives, completed milestones, estimated revenue
2. **2-Column Layout** - Left: objectives and insights, Right: coding AI and milestones
3. **Shimmer Header** - Gold gradient indicating Forge is active

## Strategic Objectives

### Viewing Objectives

- Objectives list shows all active strategic initiatives
- Each row displays: Phase badge, Title, Priority (HIGH/MED), Owner, Progress bar
- Progress bar fills from left to right with gradient color
- Percentage shown on right side

### Selecting an Objective

- Click any objective row to select it
- Selected row highlights with darker background
- Detail panel appears below showing:
  - Full description of the objective
  - Metrics: Priority, Progress %, Tasks done/total, Due date, Owner, Revenue impact
  - Progress bar visualization
  - EXECUTE and PAUSE action buttons

### Objective Details

- **EXECUTE**: Start working on objective
- **PAUSE**: Temporarily suspend objective
- Each objective maps to a strategic initiative with revenue targets

## Strategic Insights

Three insight cards showing key business signals:

- Each card has a colored left rail (gold/bronze/success)
- Displays actionable insight with recommended next steps
- Example: "Revenue pathway #1 has 3.2× ROI — reallocate agent hours"

## Forge Milestones

Checklist of 6 key milestones:

- **Unchecked (pending)**: Milestone not yet completed
- **Checked (done)**: Milestone completed
- **Click to toggle**: Click milestone to mark done/pending
- **Timestamp**: Shows target date for completion

Visual feedback with animated dots:
- Pending: Hollow circle outline
- Done: Filled circle with glow effect

## Forge Heat Chart

Visual representation of execution intensity:

- X-axis: Time progression
- Y-axis: Forge activity level (higher = more active)
- Area chart with gold to bronze gradient
- Updates in real-time during execution
- Shows if forge is "LIVE" and active

## Coding AI Assistant

### File Upload

Upload source code files for analysis:

1. **Drag & Drop**: Drag files directly into the upload zone
2. **Browse**: Click "Browse" button to select file
3. **Progress**: Watch progress bar during upload
4. **Completion**: Analysis starts automatically

Supported file types: `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.md`, `.txt`, `.json`, `.sh`, `.css`, `.html`, `.csv`, `.yaml`

Max file size: 50MB

### Code Analysis Results

After upload, analysis results display:

**Summary Statistics**
- Bugs: Count of identified bugs
- Style: Code style issues
- Performance: Performance concerns

Click "Show Details" to expand:
- Lists specific issues for each category
- Example bugs: "Null pointer dereference on line 42"
- Example issues: "Variable naming convention violation"

### Getting Improvement Suggestions

1. Upload a file and view analysis
2. Click "Get AI Improvement Suggestions"
3. Chat input auto-fills with analysis-aware prompt
4. AI responds with specific, prioritized fixes

### Chat Interface

**Configuration**
1. Select LLM Provider:
   - Claude (Anthropic) - default
   - OpenRouter
   - Ollama (Local)

2. Select Model:
   - Changes based on provider selected
   - Anthropic: Claude Opus, Sonnet, Haiku
   - OpenRouter: DeepSeek, Claude, others
   - Ollama: Local models

3. API Key (OpenRouter only):
   - Enter API key in password field
   - Click SAVE to store

**Chat Messages**
- Type message in input field
- Press Enter or click SEND
- User messages appear on right (gold background)
- Assistant messages appear on left (darker background)
- Messages include analyzed file context when relevant

**Code in Responses**
- Code blocks display with dark background
- Monospace font for readability
- Syntax-highlighted content
- Can be selected and copied

**Example Queries**
- "Fix the N+1 query on line 42"
- "How can I improve performance of this function?"
- "Explain this error and suggest a fix"
- "Refactor this code to be more maintainable"

### Tips for Best Results

1. **Upload first**: Upload code file before asking questions
2. **Be specific**: Reference line numbers or function names
3. **Ask for priorities**: Request fixes ranked by severity
4. **Get context**: AI knows about detected issues, leverage that
5. **Follow up**: Ask clarifying questions without re-uploading

## KPI Tiles

### Overall Progress
- Aggregated progress across all objectives
- Ranges 0-100%
- Updates as objectives progress

### Active Objectives
- Count of objectives in EXECUTE or BUILD phase
- Total objectives shown as denominator
- Indicates forge activity level

### Milestones Done
- Count of completed milestones
- Total milestones shown as denominator
- Indicator of phase completion

### Est. Revenue
- Projected revenue when all objectives complete
- Shows combined revenue targets
- Usually $20K+/month when executing

## Responsive Design

**Desktop (1100px+)**
- Full 2-column layout
- All panels visible at once
- Optimal for monitoring

**Tablet (600-1100px)**
- Single column layout
- Sections stack vertically
- Scrollable interface

**Mobile (< 600px)**
- Single column
- KPIs grid to 1 column
- Full touch optimization

## Keyboard Shortcuts

- **Enter** in chat input: Send message
- **Tab**: Navigate between sections
- **Space**: Toggle milestone completion

## Troubleshooting

**File upload fails**
- Check file format is supported
- Verify file size < 50MB
- Try different file

**Analysis doesn't trigger**
- Check internet connection
- Backend API may be unavailable
- Try uploading again

**Chat not responding**
- Verify provider/model selection
- Check API keys (if using OpenRouter)
- Verify backend connection

**Code blocks not displaying**
- Ensure code is in triple backticks with language
- Example: \`\`\`python ... \`\`\`

## Best Practices

1. **Organize Uploads**: Only keep relevant files active
2. **Read Full Analysis**: Don't miss important warnings
3. **Iterate**: Ask follow-up questions to refine suggestions
4. **Verify Changes**: Test suggested code before deploying
5. **Track Progress**: Update milestones as objectives complete
6. **Review Insights**: Act on strategic insights promptly

## Keyboard Navigation

All buttons and inputs are keyboard accessible:
- Tab to navigate between elements
- Enter/Space to activate buttons
- Shift+Tab to go backwards

## Performance Tips

- Upload smaller files for faster analysis
- Keep chat history clean (clear old messages if needed)
- Close detail panels when not needed
- Refresh page if UI becomes unresponsive

## Support

For issues or feature requests, contact the development team with:
- What you were doing when the issue occurred
- Which feature was affected
- Error messages shown (if any)
- File type and size (for upload issues)

---

**Last Updated**: May 5, 2026
**Version**: Phase 2.5
