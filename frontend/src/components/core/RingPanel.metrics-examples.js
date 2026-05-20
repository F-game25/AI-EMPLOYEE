/**
 * RingPanel Metrics Examples
 * Ready-to-use metric data structures for all 4 dashboard rings
 * Copy and adapt for your specific metrics
 */

// ─────────────────────────────────────────────────────────────────────
// COGNITION RING
// Metrics: reasoning activity, model calls, memory, context depth
// ─────────────────────────────────────────────────────────────────────

export const cognitionMetricsExample = [
  {
    label: 'Thoughts/sec',
    value: '12.3',
    unit: 'k',
    trend: 2.1,
    color: 'cyan'
  },
  {
    label: 'Reasoning chains',
    value: '7',
    unit: 'active',
    color: 'green'
  },
  {
    label: 'Memory writes',
    value: '384',
    unit: 'bytes/s',
    trend: 12,
    color: 'gold'
  },
  {
    label: 'Context depth',
    value: '8192',
    unit: 'tokens',
    color: 'cyan'
  }
]

// ─────────────────────────────────────────────────────────────────────
// OPERATIONS RING
// Metrics: active workflows, agents, deployments, queue depth
// ─────────────────────────────────────────────────────────────────────

export const operationsMetricsExample = [
  {
    label: 'Active Workflows',
    value: 5,
    color: 'gold'
  },
  {
    label: 'Active Agents',
    value: 23,
    color: 'green'
  },
  {
    label: 'Deployments',
    value: 12,
    trend: 3,
    color: 'cyan'
  },
  {
    label: 'Queue Depth',
    value: 42,
    trend: -5,
    color: 'orange'
  }
]

// ─────────────────────────────────────────────────────────────────────
// ECONOMY RING
// Metrics: revenue, monetization, conversion, ROI
// ─────────────────────────────────────────────────────────────────────

export const economyMetricsExample = [
  {
    label: 'Revenue Today',
    value: 2450,
    unit: '$',
    color: 'gold',
    trend: 18.5
  },
  {
    label: 'Active Monetization',
    value: 4,
    unit: 'pipelines',
    color: 'green'
  },
  {
    label: 'Conversion Rate',
    value: '3.24',
    unit: '%',
    color: 'gold'
  },
  {
    label: 'ROI Trend',
    value: '24.8',
    unit: '%',
    trend: 7.2,
    color: 'cyan'
  }
]

// ─────────────────────────────────────────────────────────────────────
// INFRASTRUCTURE RING
// Metrics: CPU, memory, inference queue, connections
// ─────────────────────────────────────────────────────────────────────

export const infrastructureMetricsExample = [
  {
    label: 'CPU Usage',
    value: '68',
    unit: '%',
    color: 'orange',
    trend: -2
  },
  {
    label: 'RAM Usage',
    value: '82',
    unit: '%',
    color: 'red'
  },
  {
    label: 'Inference Queue',
    value: '156',
    unit: 'jobs',
    color: 'gold'
  },
  {
    label: 'WS Connections',
    value: '42',
    unit: 'clients',
    color: 'green'
  }
]

// ─────────────────────────────────────────────────────────────────────
// OBJECT FORMAT EXAMPLES (auto-converted to array)
// ─────────────────────────────────────────────────────────────────────

export const cognitionMetricsObject = {
  'Thoughts/sec': '12.3k',
  'Active Chains': 7,
  'Memory Writes': 384,
  'Context Depth': 8192
}

export const operationsMetricsObject = {
  'Active Workflows': 5,
  'Active Agents': 23,
  'Deployments': 12,
  'Queue Depth': 42
}

export const economyMetricsObject = {
  'Revenue Today': '$2,450',
  'Active Pipelines': 4,
  'Conversion': '3.24%',
  'ROI': '24.8%'
}

export const infrastructureMetricsObject = {
  'CPU': '68%',
  'Memory': '82%',
  'Inference Queue': 156,
  'Connections': 42
}

// ─────────────────────────────────────────────────────────────────────
// GAUGE DATA EXAMPLES (for optional gauge visualization)
// ─────────────────────────────────────────────────────────────────────

export const cpuGaugeData = {
  value: 68,
  max: 100
}

export const memoryGaugeData = {
  value: 82,
  max: 100
}

export const queueGaugeData = {
  value: 156,
  max: 500
}

export const uptimeGaugeData = {
  value: 99.9,
  max: 100
}

// ─────────────────────────────────────────────────────────────────────
// SPARKLINE DATA EXAMPLES (for optional sparkline visualization)
// Historical trends over time
// ─────────────────────────────────────────────────────────────────────

// CPU usage over last 10 minutes (1 data point per minute)
export const cpuSparklineData = [45, 52, 48, 61, 55, 72, 68, 75, 80, 78, 82]

// Memory usage over last 10 minutes
export const memorySparklineData = [56, 58, 60, 64, 66, 70, 72, 76, 80, 82, 82]

// Queue depth over last 10 minutes
export const queueSparklineData = [120, 135, 128, 145, 152, 158, 165, 170, 168, 162, 156]

// Revenue over 12 hours (hourly)
export const revenueSparklineData = [
  150, 180, 165, 210, 195, 225, 240, 280, 250, 300, 320, 340, 380
]

// Active agents over 7 days (daily)
export const agentsSparklineData = [15, 16, 18, 19, 21, 22, 23]

// Error rate over last hour (per minute)
export const errorRateSparklineData = [
  2.1, 2.3, 2.0, 2.8, 2.4, 2.9, 3.1, 2.7, 3.2, 3.5, 3.2, 3.0, 2.8, 2.6, 2.5
]

// ─────────────────────────────────────────────────────────────────────
// HELPER: Generate mock metrics with realistic data
// ─────────────────────────────────────────────────────────────────────

export function generateCognitionMetrics() {
  return [
    {
      label: 'Thoughts/sec',
      value: (Math.random() * 20).toFixed(1),
      unit: 'k',
      trend: (Math.random() * 20 - 10).toFixed(1),
      color: 'cyan'
    },
    {
      label: 'Reasoning chains',
      value: Math.floor(Math.random() * 10),
      unit: 'active',
      color: 'green'
    },
    {
      label: 'Memory writes',
      value: Math.floor(Math.random() * 500),
      unit: 'bytes/s',
      trend: (Math.random() * 30 - 15).toFixed(1),
      color: 'gold'
    },
    {
      label: 'Context depth',
      value: Math.floor(Math.random() * 8000 + 2000),
      unit: 'tokens',
      color: 'cyan'
    }
  ]
}

export function generateOperationsMetrics() {
  return [
    {
      label: 'Active Workflows',
      value: Math.floor(Math.random() * 15),
      color: 'gold'
    },
    {
      label: 'Active Agents',
      value: Math.floor(Math.random() * 50),
      color: 'green'
    },
    {
      label: 'Deployments',
      value: Math.floor(Math.random() * 20),
      trend: (Math.random() * 15 - 7).toFixed(1),
      color: 'cyan'
    },
    {
      label: 'Queue Depth',
      value: Math.floor(Math.random() * 200),
      trend: (Math.random() * 20 - 10).toFixed(1),
      color: 'orange'
    }
  ]
}

export function generateEconomyMetrics() {
  return [
    {
      label: 'Revenue Today',
      value: Math.floor(Math.random() * 5000),
      unit: '$',
      color: 'gold',
      trend: (Math.random() * 50 - 25).toFixed(1)
    },
    {
      label: 'Active Monetization',
      value: Math.floor(Math.random() * 8),
      unit: 'pipelines',
      color: 'green'
    },
    {
      label: 'Conversion Rate',
      value: (Math.random() * 10).toFixed(2),
      unit: '%',
      color: 'gold'
    },
    {
      label: 'ROI Trend',
      value: (Math.random() * 50).toFixed(1),
      unit: '%',
      trend: (Math.random() * 30 - 15).toFixed(1),
      color: 'cyan'
    }
  ]
}

export function generateInfrastructureMetrics() {
  return [
    {
      label: 'CPU Usage',
      value: Math.floor(Math.random() * 100),
      unit: '%',
      color: Math.random() > 0.8 ? 'red' : Math.random() > 0.5 ? 'orange' : 'gold',
      trend: (Math.random() * 20 - 10).toFixed(1)
    },
    {
      label: 'RAM Usage',
      value: Math.floor(Math.random() * 100),
      unit: '%',
      color: Math.random() > 0.8 ? 'red' : Math.random() > 0.5 ? 'orange' : 'gold'
    },
    {
      label: 'Inference Queue',
      value: Math.floor(Math.random() * 500),
      unit: 'jobs',
      color: 'gold'
    },
    {
      label: 'WS Connections',
      value: Math.floor(Math.random() * 100),
      unit: 'clients',
      color: 'green'
    }
  ]
}

// ─────────────────────────────────────────────────────────────────────
// HELPER: Generate random sparkline data
// ─────────────────────────────────────────────────────────────────────

export function generateSparklineData(length = 15, min = 0, max = 100) {
  const data = []
  let current = Math.random() * max
  for (let i = 0; i < length; i++) {
    current = Math.max(min, Math.min(max, current + (Math.random() - 0.5) * 30))
    data.push(Math.floor(current))
  }
  return data
}
