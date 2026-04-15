import type { Edge, Node } from '../../shared/types';

interface NodeInspectorProps {
  node: Node | null;
  edges: Edge[];
}

export function NodeInspector({ node, edges }: NodeInspectorProps) {
  if (!node) {
    return <aside style={{ padding: 16, border: '1px solid #1f2937', borderRadius: 12 }}>Select a node</aside>;
  }

  const outgoing = edges.filter((edge) => edge.from === node.id);
  const incoming = edges.filter((edge) => edge.to === node.id);
  const usageCount = outgoing.reduce((sum, edge) => sum + edge.usageCount, 0);
  const avgSuccess = outgoing.length
    ? outgoing.reduce((sum, edge) => sum + edge.successRate, 0) / outgoing.length
    : 0;
  const lastUsed = outgoing.length
    ? new Date(Math.max(...outgoing.map((edge) => edge.lastUsed))).toLocaleString()
    : 'never';

  return (
    <aside style={{ padding: 16, border: '1px solid #1f2937', borderRadius: 12, background: '#0b1020' }}>
      <h3 style={{ marginTop: 0 }}>{node.label}</h3>
      <div>Type: {node.type}</div>
      <div>Confidence: {(node.confidence * 100).toFixed(1)}%</div>
      <div>Connections: {incoming.length + outgoing.length}</div>
      <div>Success Rate: {(avgSuccess * 100).toFixed(1)}%</div>
      <div>Usage Count: {usageCount}</div>
      <div>Last Used: {lastUsed}</div>
    </aside>
  );
}
