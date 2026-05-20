/**
 * RingPanel Component — Usage Examples
 * Demonstrates all features: progressive disclosure, health animations, context locking
 */

import { useState } from 'react'
import RingPanel from './RingPanel'

export default function RingPanelDemo() {
  const [selectedContext, setSelectedContext] = useState(null)

  // Cognition Ring Example
  const cognitionMetrics = [
    { label: 'THOUGHT/SEC', value: 124.5, trend: 2.3, unit: 'thoughts' },
    { label: 'CONTEXT SIZE', value: 4280, trend: -1.2, unit: 'tokens' },
    { label: 'INFERENCE TIME', value: 842, trend: 0, unit: 'ms' },
    { label: 'MEMORY USAGE', value: 87.3, trend: 0.5, unit: '%' },
  ]

  const cognitionAdditional = [
    { label: 'REASONING CHAINS', value: 42, trend: 3.1, unit: 'chains' },
    { label: 'ACTIVE MEMORY', value: 2.1, trend: 1.8, unit: 'MB' },
  ]

  const cognitionEvents = [
    { time: '14:32', text: 'Context window refresh (2.1MB freed)' },
    { time: '14:28', text: 'New reasoning chain initiated' },
    { time: '14:24', text: 'Memory consolidation complete' },
  ]

  // Ops Ring Example
  const opsMetrics = [
    { label: 'AGENTS ACTIVE', value: 12, trend: 0, unit: 'agents' },
    { label: 'TASK QUEUE', value: 34, trend: 4.2, unit: 'tasks' },
    { label: 'SUCCESS RATE', value: 98.5, trend: 0.3, unit: '%' },
    { label: 'AVG LATENCY', value: 245, trend: -2.1, unit: 'ms' },
  ]

  const opsAdditional = [
    { label: 'FAILED TASKS', value: 2, trend: -50, unit: 'tasks' },
    { label: 'RETRY RATE', value: 1.2, trend: -0.8, unit: '%' },
  ]

  const opsEvents = [
    { time: '14:35', text: 'Agent sync completed' },
    { time: '14:30', text: 'Task batch processed (8 tasks)' },
    { time: '14:25', text: 'Workflow execution started' },
  ]

  // Economy Ring Example
  const economyMetrics = [
    { label: 'DAILY REVENUE', value: 4250.50, trend: 12.5, unit: '$' },
    { label: 'CONVERSION RATE', value: 3.8, trend: 0.6, unit: '%' },
    { label: 'PIPELINE VALUE', value: 125000, trend: 8.3, unit: '$' },
    { label: 'ACTIVE LEADS', value: 287, trend: 5.2, unit: 'leads' },
  ]

  const economyAdditional = [
    { label: 'AVG DEAL SIZE', value: 15500, trend: 2.1, unit: '$' },
    { label: 'CLOSE RATE', value: 22.5, trend: 1.3, unit: '%' },
  ]

  const economyEvents = [
    { time: '14:32', text: 'New lead qualified (pipeline +$8.5K)' },
    { time: '14:28', text: 'Deal closed ($22.5K revenue)' },
    { time: '14:20', text: 'Marketing campaign triggered' },
  ]

  // Infra Ring Example
  const infraMetrics = [
    { label: 'CPU USAGE', value: 62.3, trend: 1.2, unit: '%' },
    { label: 'MEMORY USAGE', value: 78.1, trend: 0.8, unit: '%' },
    { label: 'NETWORK I/O', value: 245.6, trend: 2.5, unit: 'MB/s' },
    { label: 'UPTIME', value: 99.9, trend: 0, unit: '%' },
  ]

  const infraAdditional = [
    { label: 'DISK USAGE', value: 54.2, trend: 0.3, unit: '%' },
    { label: 'ERROR RATE', value: 0.02, trend: -0.01, unit: '%' },
  ]

  const infraEvents = [
    { time: '14:30', text: 'Database backup completed' },
    { time: '14:15', text: 'Cache invalidation (cleared 2.1GB)' },
    { time: '14:00', text: 'Load balancer rebalanced' },
  ]

  const handleContextLock = (ringId) => {
    setSelectedContext(ringId)
    window.dispatchEvent(
      new CustomEvent('contextLocked', {
        detail: { context: { ringId } },
      })
    )
  }

  return (
    <div style={{ padding: '40px', backgroundColor: '#070810', minHeight: '100vh' }}>
      <h1 style={{ color: '#00D9FF', fontFamily: 'monospace', marginBottom: '40px' }}>
        RING PANEL COMPONENT DEMO
      </h1>

      <section style={{ marginBottom: '60px' }}>
        <h2 style={{ color: '#20D6C7', fontFamily: 'monospace', marginBottom: '20px' }}>
          All Ring Panels (Click to expand)
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '20px',
          }}
        >
          <RingPanel
            title="COGNITION RING"
            icon="brain"
            color="cyan"
            metrics={cognitionMetrics}
            additionalMetrics={cognitionAdditional}
            recentEvents={cognitionEvents}
            healthStatus="healthy"
            context={{ ringId: 'cognition', type: 'cognitive' }}
            sparklineData={[10, 45, 32, 65, 78, 92, 85, 95, 102, 110, 124]}
            animated
          />

          <RingPanel
            title="OPS RING"
            icon="workflow"
            color="teal"
            metrics={opsMetrics}
            additionalMetrics={opsAdditional}
            recentEvents={opsEvents}
            healthStatus="busy"
            context={{ ringId: 'ops', type: 'operational' }}
            sparklineData={[8, 12, 18, 22, 28, 31, 34, 32, 35, 33]}
            animated
          />

          <RingPanel
            title="ECONOMY RING"
            icon="trending"
            color="gold"
            metrics={economyMetrics}
            additionalMetrics={economyAdditional}
            recentEvents={economyEvents}
            healthStatus="healthy"
            context={{ ringId: 'economy', type: 'economic' }}
            sparklineData={[3200, 3450, 3800, 4100, 4250, 4180, 4220]}
            animated
          />

          <RingPanel
            title="INFRA RING"
            icon="server"
            color="green"
            metrics={infraMetrics}
            additionalMetrics={infraAdditional}
            recentEvents={infraEvents}
            healthStatus="healthy"
            context={{ ringId: 'infra', type: 'infrastructure' }}
            sparklineData={[55, 58, 60, 62, 61, 62, 63]}
            animated
          />
        </div>
      </section>

      <section style={{ marginBottom: '60px' }}>
        <h2 style={{ color: '#20D6C7', fontFamily: 'monospace', marginBottom: '20px' }}>
          Health Status Animations
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '20px',
          }}
        >
          <RingPanel
            title="HEALTHY"
            color="cyan"
            metrics={cognitionMetrics.slice(0, 4)}
            healthStatus="healthy"
            sparklineData={[10, 45, 32, 65, 78]}
          />
          <RingPanel
            title="BUSY"
            color="teal"
            metrics={opsMetrics.slice(0, 4)}
            healthStatus="busy"
            sparklineData={[8, 12, 18, 22, 28]}
          />
          <RingPanel
            title="WARNING"
            color="orange"
            metrics={economyMetrics.slice(0, 4)}
            healthStatus="warning"
            sparklineData={[3200, 3450, 3800, 4100, 4250]}
          />
          <RingPanel
            title="CRITICAL"
            color="red"
            metrics={infraMetrics.slice(0, 4)}
            healthStatus="critical"
            sparklineData={[55, 58, 60, 62, 61]}
          />
          <RingPanel
            title="OFFLINE"
            color="blue"
            metrics={[
              { label: 'STATUS', value: 'OFFLINE', unit: '' },
              { label: 'UPTIME', value: 0, unit: '%' },
            ]}
            healthStatus="offline"
            sparklineData={[100, 100, 100, 100, 100]}
          />
        </div>
      </section>

      <section style={{ marginBottom: '60px' }}>
        <h2 style={{ color: '#20D6C7', fontFamily: 'monospace', marginBottom: '20px' }}>
          Context Locking Demo
        </h2>
        <p style={{ color: 'rgba(184, 184, 196, 0.75)', fontFamily: 'monospace', marginBottom: '20px' }}>
          Selected: <span style={{ color: '#00D9FF' }}>{selectedContext || 'None'}</span>
        </p>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '20px',
          }}
        >
          <div onClick={() => handleContextLock('cognition')}>
            <RingPanel
              title="COGNITION RING"
              icon="brain"
              color="cyan"
              metrics={cognitionMetrics.slice(0, 4)}
              healthStatus={selectedContext === 'cognition' ? 'busy' : 'healthy'}
              context={{ ringId: 'cognition' }}
              sparklineData={[10, 45, 32, 65, 78, 92, 85, 95, 102]}
            />
          </div>
          <div onClick={() => handleContextLock('ops')}>
            <RingPanel
              title="OPS RING"
              icon="workflow"
              color="teal"
              metrics={opsMetrics.slice(0, 4)}
              healthStatus={selectedContext === 'ops' ? 'busy' : 'healthy'}
              context={{ ringId: 'ops' }}
              sparklineData={[8, 12, 18, 22, 28, 31, 34]}
            />
          </div>
          <div onClick={() => handleContextLock('economy')}>
            <RingPanel
              title="ECONOMY RING"
              icon="trending"
              color="gold"
              metrics={economyMetrics.slice(0, 4)}
              healthStatus={selectedContext === 'economy' ? 'busy' : 'healthy'}
              context={{ ringId: 'economy' }}
              sparklineData={[3200, 3450, 3800, 4100, 4250]}
            />
          </div>
          <div onClick={() => handleContextLock('infra')}>
            <RingPanel
              title="INFRA RING"
              icon="server"
              color="green"
              metrics={infraMetrics.slice(0, 4)}
              healthStatus={selectedContext === 'infra' ? 'busy' : 'healthy'}
              context={{ ringId: 'infra' }}
              sparklineData={[55, 58, 60, 62, 61]}
            />
          </div>
        </div>
      </section>

      <section style={{ marginBottom: '60px' }}>
        <h2 style={{ color: '#20D6C7', fontFamily: 'monospace', marginBottom: '20px' }}>
          With Gauge Visualization
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '20px',
          }}
        >
          <RingPanel
            title="QUEUE DEPTH"
            color="cyan"
            metrics={[
              { label: 'CURRENT', value: 34, unit: 'tasks' },
              { label: 'MAX', value: 100, unit: 'limit' },
            ]}
            gaugeData={{ value: 34, max: 100 }}
            healthStatus="healthy"
          />
          <RingPanel
            title="MEMORY"
            color="teal"
            metrics={[
              { label: 'USED', value: 7.8, unit: 'GB' },
              { label: 'TOTAL', value: 16, unit: 'GB' },
            ]}
            gaugeData={{ value: 7.8, max: 16 }}
            healthStatus="healthy"
          />
        </div>
      </section>
    </div>
  )
}
