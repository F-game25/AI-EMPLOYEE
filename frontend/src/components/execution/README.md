# Pipeline Visualization (Phase 3.3)

Real-time visualization of the 10-phase pipeline execution with live status updates and detailed metrics.

## Components

### PipelineVisualizer.jsx

Main orchestrator component that displays all 10 phases as a vertical timeline.

**Features:**
- Renders 10-phase pipeline with status indicators (pending, running, done, failed)
- Real-time WebSocket updates for phase transitions
- Hover tooltips showing phase name, description, and duration
- Click to open detail panel for selected phase
- Animated status indicators (spinning gold for running, green checkmark for done, red X for failed)

**Props:**
```jsx
<PipelineVisualizer taskId="task-abc123" />
```

- `taskId` (required): Task ID to fetch and monitor pipeline execution

**Data Format:**
```javascript
{
  taskId: 'task-123',
  phases: [
    {
      phaseNum: 1,
      name: 'Input',
      status: 'done',
      duration_ms: 125,
      startedAt: '2026-05-05T12:00:00Z',
      completedAt: '2026-05-05T12:00:00.125Z',
      logs: [],
      metrics: {}
    },
    // ... 9 more phases
  ]
}
```

### PhaseDetail.jsx

Conditional sidebar that displays detailed information about a selected phase.

**Features:**
- Slide-in sidebar on right side of screen
- Overlay click to dismiss
- Close button
- Displays: phase name, status badge, description
- Timing section: start time, end time, duration
- Logs section: last 5 logs from phase execution
- Metrics section: key performance indicators
- Error section: if phase failed
- Success badge: if phase completed

**Props:**
```jsx
<PhaseDetail phase={selectedPhase} onClose={() => {}} />
```

## API Endpoints

### GET /api/execution/pipeline/:taskId

Fetch the complete 10-phase execution trace for a task.

**Response:**
```json
{
  "ok": true,
  "data": {
    "taskId": "task-abc123",
    "tenantId": "tenant-default",
    "createdAt": "2026-05-05T12:00:00Z",
    "phases": [...]
  }
}
```

## WebSocket

### /ws/execution-trace?taskId=<taskId>

Subscribe to real-time phase updates for a task.

**Initial Message:**
```json
{
  "type": "pipeline_trace",
  "data": { /* full trace object */ }
}
```

**Phase Update Messages:**
```json
{
  "phaseNum": 2,
  "status": "running",
  "startedAt": "2026-05-05T12:00:05Z",
  "duration_ms": 0
}
```

After phase completion:
```json
{
  "phaseNum": 2,
  "status": "done",
  "completedAt": "2026-05-05T12:00:15Z",
  "duration_ms": 10000,
  "metrics": { /* phase metrics */ }
}
```

## Usage Example

```jsx
import { useState } from 'react'
import PipelineVisualizer from './PipelineVisualizer'

function TaskExecutionView({ taskId }) {
  return (
    <div style={{ width: '100%', height: '100vh' }}>
      <PipelineVisualizer taskId={taskId} />
    </div>
  )
}
```

## Integration into Dashboard/Pages

### Option 1: Tasks Page

Add to `TasksPageNEW.jsx`:

```jsx
import PipelineVisualizer from '../execution/PipelineVisualizer'

// In the detail panel for selected task:
{selectedTask && (
  <div className="execution-panel">
    <PipelineVisualizer taskId={selectedTask.id} />
  </div>
)}
```

### Option 2: New Execution Page

Create `ExecutionPage.jsx`:

```jsx
import { useAppStore } from '../../store/appStore'
import PipelineVisualizer from '../execution/PipelineVisualizer'

export default function ExecutionPage() {
  const selectedTaskId = useAppStore(s => s.selectedTaskId)
  
  if (!selectedTaskId) {
    return <div>Select a task to view execution pipeline</div>
  }
  
  return (
    <div className="execution-page">
      <PipelineVisualizer taskId={selectedTaskId} />
    </div>
  )
}
```

Then add to Dashboard.jsx:

```jsx
const ExecutionPage = lazy(() => import('./pages/ExecutionPage'))

const PAGES = {
  // ... existing pages ...
  'execution': ExecutionPage,
}
```

### Option 3: Inline in Control Center

```jsx
// In ControlCenterPage.jsx or similar
import PipelineVisualizer from '../execution/PipelineVisualizer'

{/* Execution trace for selected task */}
<PipelineVisualizer taskId={selectedTaskId} />
```

## 10 Phases (from unified_pipeline.py)

1. **Input** — Parse user input and initialize pipeline
2. **Retrieve Nodes** — Fetch relevant knowledge from graph
3. **Build Context** — Assemble context for LLM
4. **Classify Decision** — Intent classification and agent ranking
5. **Call LLM** — Execute LLM inference
6. **Validate Tasks** — Schema validation and task planning
7. **Execute Tasks** — Execute agents and collect results
8. **Format Response** — Format and validate output
9. **Update Graph** — Update knowledge graph with results
10. **Monitor & Improve** — Telemetry and performance monitoring

## Status Indicators

- **Pending** (gray): Phase not yet started
- **Running** (spinning gold): Phase currently executing
- **Done** (green checkmark): Phase completed successfully
- **Failed** (red X): Phase encountered an error

## Styling

Uses Nexus-UI color tokens:
- `--nexus-primary`: Primary action color (#6366f1)
- `--nexus-success`: Success state (#10b981)
- `--nexus-error`: Error state (#ef4444)
- `--nexus-neutral`: Neutral/pending state (#6b7280)

Gold animation for running state:
- `--gold-primary`: #fbbf24
- `--gold-dark`: #f59e0b

## Performance Considerations

- **Initial Load**: Fetch from `/api/execution/pipeline/:taskId` (typically <100ms)
- **Real-time Updates**: WebSocket messages for each phase transition (~10-100 bytes each)
- **Memory**: Stores one trace in memory per connected WebSocket (minimal)
- **Rendering**: Timeline renders 10 fixed phases (no virtualization needed)

## Error Handling

- WebSocket disconnection: Component remains functional, falls back to polling
- Missing task: Displays empty timeline with all phases pending
- Network errors: Shown in error banner above timeline
- Phase errors: Displayed in detail panel and styled in red

## Future Enhancements

1. **Trace History**: Browse historical pipeline executions
2. **Phase Comparison**: Compare metrics across multiple executions
3. **Export**: Download trace as JSON/CSV
4. **Filtering**: Filter phases by status or duration threshold
5. **Aggregation**: Show average metrics across 10 most recent executions
6. **Alerts**: Notify on phase timeout or error
