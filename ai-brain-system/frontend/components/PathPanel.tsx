import type { Strategy } from '../../shared/types';

interface PathPanelProps {
  strongest: Strategy[];
  recent: string[][];
  failed: string[][];
}

function PathList({ title, rows }: { title: string; rows: string[] }) {
  return (
    <section style={{ border: '1px solid #1f2937', borderRadius: 12, padding: 12, background: '#0b1020' }}>
      <h4 style={{ marginTop: 0 }}>{title}</h4>
      {rows.length === 0 ? <div style={{ color: '#94a3b8' }}>No data</div> : rows.map((path, idx) => <div key={`${title}-${idx}`}>{path}</div>)}
    </section>
  );
}

export function PathPanel({ strongest, recent, failed }: PathPanelProps) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
      <PathList
        title="Top Strongest Paths"
        rows={strongest.slice(0, 5).map((strategy) => `${strategy.path.join(' → ')} (${(strategy.successRate * 100).toFixed(0)}%)`)}
      />
      <PathList title="Recently Used Paths" rows={recent.slice(0, 5).map((path) => path.join(' → '))} />
      <PathList title="Failed Paths" rows={failed.slice(0, 5).map((path) => path.join(' → '))} />
    </div>
  );
}
