import type { Edge } from '../models/Edge';
import type { Node } from '../models/Node';

class GraphEngine {
  nodes = new Map<string, Node>();
  edges = new Map<string, Edge>();

  addNode(node: Node) {
    this.nodes.set(node.id, node);
  }

  connect(from: string, to: string) {
    const key = `${from}-${to}`;
    if (!this.edges.has(key)) {
      this.edges.set(key, {
        from,
        to,
        weight: 0.1,
        successRate: 0,
        usageCount: 0,
        lastUsed: Date.now(),
      });
    }
  }

  strengthenEdge(from: string, to: string) {
    const edge = this.edges.get(`${from}-${to}`);
    if (!edge) return;

    edge.weight = Math.min(1, edge.weight + 0.1);
    edge.usageCount += 1;
    edge.successRate = (edge.successRate + 1) / 2;
    edge.lastUsed = Date.now();
  }

  weakenEdge(from: string, to: string) {
    const edge = this.edges.get(`${from}-${to}`);
    if (!edge) return;

    edge.weight = Math.max(0.01, edge.weight * 0.8);
    edge.successRate *= 0.9;
    edge.lastUsed = Date.now();
  }

  getOutgoing(nodeId: string): Edge[] {
    return Array.from(this.edges.values()).filter((edge) => edge.from === nodeId);
  }

  touchPath(path: string[]): void {
    for (let i = 0; i < path.length - 1; i += 1) {
      const edge = this.edges.get(`${path[i]}-${path[i + 1]}`);
      if (!edge) continue;
      edge.usageCount += 1;
      edge.lastUsed = Date.now();
    }
  }

  serialize(): { nodes: Node[]; edges: Edge[] } {
    return {
      nodes: Array.from(this.nodes.values()),
      edges: Array.from(this.edges.values()),
    };
  }

  hydrate(data: { nodes: Node[]; edges: Edge[] }): void {
    this.nodes.clear();
    this.edges.clear();
    data.nodes.forEach((node) => this.nodes.set(node.id, node));
    data.edges.forEach((edge) => this.edges.set(`${edge.from}-${edge.to}`, edge));
  }
}

export const graphEngine = new GraphEngine();
