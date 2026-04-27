# Task Progress Integration Guide

**Objective:** Wire TaskProgressBlock component to actual agent execution pipeline.  
**Status:** Implementation guide for connecting UI to backend task tracking.

---

## Overview

The TaskProgressBlock is a React component that displays live task execution progress. It should show:
- What step we're on
- How long it's taking
- Overall progress percentage
- Activity graph trending

---

## Architecture

```
┌─────────────────────────────────┐
│   Chat Message (UI)             │
│   ├─ Regular text message       │
│   ├─ Code block                 │
│   └─ TaskProgressBlock ←─────┐  │
└─────────────────────────────┼──┘
                              │
                    ┌─────────┴────────┐
                    │                  │
            ┌───────▼────┐     ┌──────▼────┐
            │ WebSocket  │     │ Poll API  │
            │  (real-    │     │ (/tasks)  │
            │   time)    │     │           │
            └───────┬────┘     └──────┬────┘
                    │                 │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Task Storage   │
                    │  (Redis/Memory) │
                    └────────┬────────┘
                             │
                    ┌────────▼────────────┐
                    │  AgentController    │
                    │  (Real Execution)   │
                    └─────────────────────┘
```

---

## 1. Frontend: TaskProgressBlock Component

**Location:** `frontend/src/components/ui/TaskProgressBlock.jsx`

```jsx
import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'

export default function TaskProgressBlock({ taskId }) {
  const [task, setTask] = useState(null)
  const [steps, setSteps] = useState([])
  const [loading, setLoading] = useState(true)
  const wsRef = useRef(null)

  useEffect(() => {
    // 1. Initial load: fetch current task state
    const fetchTask = async () => {
      const res = await fetch(`/api/tasks/${taskId}`)
      const data = await res.json()
      setTask(data.task)
      setSteps(data.steps || [])
      setLoading(false)
    }
    
    fetchTask()

    // 2. WebSocket: subscribe to live updates
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    wsRef.current = new WebSocket(`${protocol}//${window.location.host}/api/tasks/${taskId}/ws`)
    
    wsRef.current.onmessage = (event) => {
      const update = JSON.parse(event.data)
      
      if (update.type === 'step_update') {
        setSteps(prev => {
          const idx = prev.findIndex(s => s.id === update.step_id)
          if (idx >= 0) {
            const newSteps = [...prev]
            newSteps[idx] = { ...newSteps[idx], ...update.data }
            return newSteps
          }
          return prev
        })
      }
      
      if (update.type === 'task_update') {
        setTask(prev => ({ ...prev, ...update.data }))
      }
    }

    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [taskId])

  if (loading) return <div>Loading task...</div>
  if (!task) return <div>Task not found</div>

  const elapsed = Math.round((Date.now() - new Date(task.started_at).getTime()) / 1000)
  const completedSteps = steps.filter(s => s.status === 'done').length

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        background: 'rgba(0,0,0,0.3)',
        border: '3px solid rgba(229,199,107,0.3)',
        borderRadius: 8,
        padding: 12,
        marginBottom: 12
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'rgba(229,199,107,1)' }}>
          {task.name || 'Task'}
          {task.status === 'running' && <span style={{ marginLeft: 8, animation: 'pulse 2s infinite' }}>●</span>}
        </div>
        <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.5)' }}>
          {elapsed}s
        </div>
      </div>

      {/* Progress bar */}
      <div style={{ height: 3, background: 'rgba(139,81,32,0.2)', borderRadius: 2, marginBottom: 12, overflow: 'hidden' }}>
        <motion.div
          layoutId="progress"
          style={{
            height: '100%',
            background: 'linear-gradient(90deg, #E5C76B, #FFD97A)',
            width: `${(completedSteps / steps.length) * 100}%`
          }}
          transition={{ duration: 0.3 }}
        />
      </div>

      {/* Steps list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {steps.map((step, idx) => {
          const icons = {
            pending: '○',
            active: '●',
            done: '✓',
            error: '✗'
          }
          const colors = {
            pending: 'rgba(255,255,255,0.3)',
            active: '#20D6C7',
            done: '#22C55E',
            error: '#FF3B3B'
          }
          return (
            <motion.div
              key={step.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.05 }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 10,
                color: colors[step.status],
                fontFamily: 'monospace'
              }}
            >
              <span>{icons[step.status]}</span>
              <span style={{ flex: 1 }}>{step.label}</span>
              {step.elapsed_ms && <span style={{ fontSize: 9, opacity: 0.7 }}>{Math.round(step.elapsed_ms / 1000)}s</span>}
            </motion.div>
          )
        })}
      </div>

      {/* Summary */}
      {task.status === 'done' && (
        <div style={{ marginTop: 12, padding: 8, background: 'rgba(34,197,94,0.1)', borderRadius: 4, fontSize: 10, color: '#22C55E' }}>
          Task complete: {completedSteps}/{steps.length} steps
        </div>
      )}
    </motion.div>
  )
}
```

---

## 2. Backend: Task Tracking API

**Add to `backend/server.js`:**

```javascript
// Task storage (in-memory for demo; use Redis for production)
const taskStore = new Map()

// GET /api/tasks/:taskId
app.get('/api/tasks/:taskId', (req, res) => {
  const task = taskStore.get(req.params.taskId)
  if (!task) return res.status(404).json({ error: 'Task not found' })
  res.json(task)
})

// WebSocket: /api/tasks/:taskId/ws
const wss = new WebSocketServer({ noServer: true })

server.on('upgrade', (req, socket, head) => {
  const match = req.url.match(/^\/api\/tasks\/([a-f0-9\-]+)\/ws$/)
  if (!match) {
    socket.destroy()
    return
  }
  
  const taskId = match[1]
  
  wss.handleUpgrade(req, socket, head, (ws) => {
    // Send current state
    const task = taskStore.get(taskId)
    if (task) {
      ws.send(JSON.stringify({
        type: 'task_state',
        task: task.task,
        steps: task.steps
      }))
    }
    
    // Store connection for broadcasting updates
    if (!taskConnections) taskConnections = new Map()
    if (!taskConnections.has(taskId)) {
      taskConnections.set(taskId, new Set())
    }
    taskConnections.get(taskId).add(ws)
    
    ws.on('close', () => {
      taskConnections.get(taskId).delete(ws)
    })
  })
})

// Broadcast task update to all connected clients
function broadcastTaskUpdate(taskId, update) {
  if (!taskConnections || !taskConnections.has(taskId)) return
  
  const msg = JSON.stringify(update)
  taskConnections.get(taskId).forEach(ws => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(msg)
    }
  })
}
```

---

## 3. Integration with Agent Controller

**Update `runtime/core/agent_controller.py`:**

```python
import json
import requests
from datetime import datetime, timezone

class AgentController:
    def __init__(self, backend_url="http://localhost:8787"):
        self.backend_url = backend_url
    
    def run_task_with_progress(self, task_id, agents_sequence, initial_context):
        """Execute task sequence and report progress to UI"""
        
        # Initialize task in backend
        task_data = {
            'task_id': task_id,
            'name': f'Task {task_id}',
            'status': 'running',
            'started_at': datetime.now(timezone.utc).isoformat(),
            'steps': []
        }
        
        # Create steps for each agent
        for i, agent_id in enumerate(agents_sequence):
            task_data['steps'].append({
                'id': f'step_{i}',
                'label': f'Running {agent_id}',
                'status': 'pending',
                'started_at': None,
                'elapsed_ms': 0
            })
        
        # Store initial state
        requests.post(f"{self.backend_url}/api/tasks/{task_id}/init", json=task_data)
        
        # Execute each agent
        context = initial_context
        for i, agent_id in enumerate(agents_sequence):
            step_id = f'step_{i}'
            
            # Mark step as active
            self._update_step(task_id, step_id, {
                'status': 'active',
                'started_at': datetime.now(timezone.utc).isoformat()
            })
            
            try:
                # Run agent
                agent = self._get_agent(agent_id)
                result = agent.execute({
                    'task_id': task_id,
                    'context': context,
                    **context.get('input', {})
                })
                
                # Mark step as done
                self._update_step(task_id, step_id, {
                    'status': 'done',
                    'result': result
                })
                
                # Update context for next agent
                context = {
                    **context,
                    'previous_results': result
                }
                
            except Exception as e:
                # Mark step as error
                self._update_step(task_id, step_id, {
                    'status': 'error',
                    'error': str(e)
                })
                break
        
        # Mark task as complete
        requests.post(f"{self.backend_url}/api/tasks/{task_id}/complete", json={
            'status': 'done',
            'result': context.get('previous_results', {})
        })
    
    def _update_step(self, task_id, step_id, updates):
        """Send step update to backend"""
        requests.post(f"{self.backend_url}/api/tasks/{task_id}/steps/{step_id}", json=updates)
```

---

## 4. Chat Panel Integration

**Update `frontend/src/components/dashboard/ChatPanel.jsx`:**

```jsx
import TaskProgressBlock from '../ui/TaskProgressBlock'

export default function ChatPanel() {
  // ... existing code ...

  const renderMessage = (msg, idx) => {
    // Handle task progress messages
    if (msg.type === 'task_progress') {
      return (
        <div key={idx} style={{ marginBottom: 12 }}>
          <TaskProgressBlock taskId={msg.taskId} />
        </div>
      )
    }
    
    // Handle regular messages
    return (
      <div key={idx}>
        {/* existing message rendering */}
      </div>
    )
  }

  return (
    // ... existing chat panel JSX ...
    {messages.map((msg, idx) => renderMessage(msg, idx))}
  )
}
```

---

## 5. Triggering Task Progress from Backend

**When starting an agent task:**

```python
# In unified_pipeline.py or agent_controller.py

def process_user_input(user_message):
    task_id = str(uuid.uuid4())
    
    # Add progress message to chat
    add_chat_message({
        'type': 'task_progress',
        'taskId': task_id,
        'role': 'system'
    })
    
    # Execute agents in background
    asyncio.create_task(
        agent_controller.run_task_with_progress(
            task_id,
            agents=['lead_hunter', 'email_ninja', 'sales_closer'],
            initial_context={...}
        )
    )
    
    return { 'task_id': task_id, 'status': 'queued' }
```

---

## 6. Testing Integration

### Test Task Progress Flow

```bash
# 1. Start a task
curl -X POST http://localhost:8787/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "agents": ["lead_hunter", "email_ninja"],
    "input": {"niche": "SaaS", "location": "US"}
  }'

# Response: { "task_id": "abc123" }

# 2. Poll task state
curl http://localhost:8787/api/tasks/abc123

# 3. Connect WebSocket to watch live updates
wscat -c ws://localhost:8787/api/tasks/abc123/ws
```

---

## 7. Production Considerations

### Redis-Backed Task Store

```python
import redis

redis_client = redis.Redis(host='localhost', port=6379)

def store_task(task_id, task_data):
    redis_client.setex(
        f'task:{task_id}',
        3600,  # 1 hour TTL
        json.dumps(task_data)
    )

def broadcast_update(task_id, update):
    redis_client.publish(f'task:{task_id}:updates', json.dumps(update))
```

### Metrics & Monitoring

Track:
- Step execution time
- Agent performance
- Error rates per agent
- Total task duration

---

## 8. Next Steps

- [ ] Implement TaskProgressBlock component in React
- [ ] Add task tracking API endpoints
- [ ] Wire AgentController to send progress updates
- [ ] Add WebSocket support for live updates
- [ ] Test with actual agent execution
- [ ] Add Redis for persistence
- [ ] Set up task cleanup (TTL)
- [ ] Monitor task performance metrics

---

**Status:** Ready for implementation  
**Owner:** Backend + Frontend teams
