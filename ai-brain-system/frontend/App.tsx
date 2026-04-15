import { useMemo, useState } from 'react';
import type { Node } from '../shared/types';
import { MemoryViewer } from './components/MemoryViewer';
import { NeuralGraph } from './components/NeuralGraph';
import { NodeInspector } from './components/NodeInspector';
import { PathPanel } from './components/PathPanel';
import { useNeuralGraph } from './hooks/useNeuralGraph';

export default function App() {
  const { snapshot, loading, error, stats } = useNeuralGraph();
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  const title = useMemo(() => {
    if (loading) return 'Neural Brain loading…';
    if (error) return `Neural Brain degraded (${error})`;
    return 'Neural Brain live';
  }, [error, loading]);

  return (
    <main style={{ padding: 18, color: '#e5e7eb', background: '#030712', minHeight: '100vh', fontFamily: 'Inter, system-ui, sans-serif' }}>
      <h1>{title}</h1>
      <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
        <div>Nodes: {stats.nodeCount}</div>
        <div>Edges: {stats.edgeCount}</div>
        <div>Strategies: {stats.strategyCount}</div>
        <div>Experiences: {stats.experienceCount}</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
        <NeuralGraph
          nodes={snapshot.nodes}
          edges={snapshot.edges}
          activePath={snapshot.activePath}
          onSelectNode={setSelectedNode}
        />
        <NodeInspector node={selectedNode} edges={snapshot.edges} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
        <PathPanel
          strongest={snapshot.strategies}
          recent={snapshot.recentlyUsedPaths}
          failed={snapshot.failedPaths}
        />
        <MemoryViewer
          strategies={snapshot.strategies}
          shortTerm={snapshot.shortTerm}
          longTerm={snapshot.longTerm}
        />
      </div>
    </main>
  );
}
