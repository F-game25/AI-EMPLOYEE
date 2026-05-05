import React from 'react'
import { KPITile } from '../nexus-ui'
import './ExecutionMetrics.css'

export default function ExecutionMetrics({ totalTasks, activeNow, successRate, avgLatency }) {
  const getSuccessTone = (rate) => {
    if (rate >= 85) return 'success'
    if (rate >= 70) return 'warn'
    return 'alert'
  }

  return (
    <div className="execution-metrics">
      <KPITile
        label="Total Tasks"
        value={totalTasks}
        icon="∑"
        iconTone="cool"
        hover={true}
        size="md"
      />

      <KPITile
        label="Active Now"
        value={activeNow}
        icon="⚡"
        iconTone={activeNow > 0 ? 'gold' : 'idle'}
        pulse={activeNow > 0}
        hover={true}
        size="md"
      />

      <KPITile
        label="Success Rate"
        value={`${successRate}%`}
        icon="✓"
        iconTone={getSuccessTone(successRate)}
        hover={true}
        size="md"
      />

      <KPITile
        label="Avg Latency"
        value={`${avgLatency}ms`}
        icon="⏱"
        iconTone="cool"
        hover={true}
        size="md"
      />
    </div>
  )
}
