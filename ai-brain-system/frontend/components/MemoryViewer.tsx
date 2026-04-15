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
        {strategies.length === 0 ? <div style={{ color: '#94a3b8' }}>No strategies yet</div> : (
          <ul aria-label="Learned strategy list">
            {strategies.slice(0, 5).map((strategy) => (
              <li key={strategy.id}>
                {strategy.path.join(' → ')} | <span aria-label="strategy success rate">success {(strategy.successRate * 100).toFixed(0)}%</span> | <span aria-label="strategy usage count">used {strategy.usageCount}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <strong>Stored Experiences</strong>
        {experiences.length === 0 ? <div style={{ color: '#94a3b8' }}>No experiences yet</div> : (
          <ul aria-label="Stored experience list">
            {experiences.slice(0, 8).map((exp) => (
              <li key={exp.id}>
                <span aria-label="experience timestamp">{new Date(exp.timestamp).toLocaleTimeString()}</span> | <span aria-label="experience task">{exp.taskId || 'task'}</span> | <span aria-label="experience path">{exp.path.join(' → ')}</span> | <span aria-label="experience success">{String(exp.success)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
