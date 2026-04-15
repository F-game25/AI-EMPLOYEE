import { useMemo, useState } from 'react';
import type { Experience, Strategy } from '../../shared/types';

interface MemoryViewerProps {
  strategies: Strategy[];
  shortTerm: Experience[];
  longTerm: Experience[];
}

export function MemoryViewer({ strategies, shortTerm, longTerm }: MemoryViewerProps) {
  const [filter, setFilter] = useState('');

  const experiences = useMemo(() => {
    const text = filter.trim().toLowerCase();
    const merged = [...shortTerm, ...longTerm].sort((a, b) => b.timestamp - a.timestamp);
    if (!text) return merged;
    return merged.filter((exp) => {
      const task = String(exp.taskId || '').toLowerCase();
      const agent = String(exp.agentId || '').toLowerCase();
      return task.includes(text) || agent.includes(text);
    });
  }, [filter, longTerm, shortTerm]);

  return (
    <section style={{ border: '1px solid #1f2937', borderRadius: 12, padding: 12, background: '#0b1020' }}>
      <h4 style={{ marginTop: 0 }}>Memory Viewer</h4>
      <input
        placeholder="Filter by agent/task"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ width: '100%', marginBottom: 10, background: '#111827', color: '#e5e7eb', border: '1px solid #374151', borderRadius: 8, padding: 8 }}
      />
      <div style={{ marginBottom: 10 }}>
        <strong>Learned Strategies</strong>
        {strategies.length === 0 ? <div style={{ color: '#94a3b8' }}>No strategies yet</div> : strategies.slice(0, 5).map((strategy) => (
          <div key={strategy.id}>{strategy.path.join(' → ')} | success {(strategy.successRate * 100).toFixed(0)}% | used {strategy.usageCount}</div>
        ))}
      </div>
      <div>
        <strong>Stored Experiences</strong>
        {experiences.length === 0 ? <div style={{ color: '#94a3b8' }}>No experiences yet</div> : experiences.slice(0, 8).map((exp) => (
          <div key={exp.id}>{new Date(exp.timestamp).toLocaleTimeString()} | {(exp.taskId || 'task')} | {exp.path.join(' → ')} | {String(exp.success)}</div>
        ))}
      </div>
    </section>
  );
}
