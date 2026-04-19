import { motion } from 'framer-motion'
import { useStore } from '../store/ascendStore'
import { NeuralNetCanvas } from '../components/NeuralNetCanvas'
import { XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts'

export function LiveFeedback() {
  const { chartData, forgeFeed, moneyFeed, blacklightFeed } = useStore()

  const chartFormatted = chartData.map((d) => ({
    time: new Date(d.ts).toLocaleTimeString(),
    tokens: d.tokens,
    latency: d.latency,
    activity: d.activity,
  }))

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: 28, fontWeight: 700, marginBottom: 20 }} className="metallic-text">
        📡 LIVE FEEDBACK
      </h1>

      {/* Action bar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <button className="btn-outline">⏸ PAUSE ALL</button>
        <button className="btn-outline">⚡ BOOST PRIORITY</button>
        <button className="btn-outline">📤 EXPORT LOGS</button>
      </div>

      {/* Neural canvas */}
      <div className="panel" style={{ marginBottom: 20, overflow: 'hidden' }}>
        <NeuralNetCanvas />
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
        {[
          { key: 'tokens', label: 'TOKEN USAGE' },
          { key: 'latency', label: 'LATENCY' },
          { key: 'activity', label: 'ACTIVITY SCORE' },
        ].map(({ key, label }) => (
          <div key={key} className="panel" style={{ padding: 16 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)', letterSpacing: 1, marginBottom: 12 }}>
              {label}
            </div>
            <ResponsiveContainer width="100%" height={120}>
              <AreaChart data={chartFormatted}>
                <defs>
                  <linearGradient id={`grad-${key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#D4AF37" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#D4AF37" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" hide />
                <YAxis hide />
                <Tooltip
                  contentStyle={{
                    background: '#111',
                    border: '1px solid rgba(205,127,50,0.3)',
                    borderRadius: 6,
                    fontFamily: 'JetBrains Mono',
                    fontSize: 10,
                    color: '#CD7F32',
                  }}
                />
                <Area type="monotone" dataKey={key} stroke="#D4AF37" fill={`url(#grad-${key})`} strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ))}
      </div>

      {/* Activity feed */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        {[
          { label: 'FORGE', feed: forgeFeed, color: 'var(--bronze)' },
          { label: 'MONEY', feed: moneyFeed, color: 'var(--gold)' },
          { label: 'BLACKLIGHT', feed: blacklightFeed, color: 'var(--bronze)' },
        ].map(({ label, feed, color }) => (
          <div key={label} className="panel" style={{ padding: 16, maxHeight: 250, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color, letterSpacing: 1, marginBottom: 8 }}>
              {label}
            </div>
            <div style={{ flex: 1, overflowY: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11, lineHeight: 1.7, color: 'var(--text-secondary)' }}>
              {feed.length === 0 && <div style={{ color: 'var(--text-dim)' }}>Awaiting activity...</div>}
              {feed.map((line, i) => (
                <motion.div key={i} initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
                  {line}
                </motion.div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  )
}
