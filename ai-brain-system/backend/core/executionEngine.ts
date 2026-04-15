import { graphEngine } from './graphEngine';

class ExecutionEngine {
  private static readonly MAX_PATH_LENGTH = 5;

  findBestPath(start: string): string[] {
    const path = [start];
    let current = start;
    const visited = new Set([start]);

    for (let i = 0; i < ExecutionEngine.MAX_PATH_LENGTH; i += 1) {
      const next = this.getStrongestConnection(current, visited);
      if (!next) break;

      path.push(next);
      current = next;
      visited.add(next);
    }

    return path;
  }

  explorePath(start: string): string[] {
    const path = [start];
    let current = start;
    const visited = new Set([start]);

    for (let i = 0; i < ExecutionEngine.MAX_PATH_LENGTH; i += 1) {
      const options = graphEngine.getOutgoing(current)
        .filter((edge) => !visited.has(edge.to))
        .sort((a, b) => a.usageCount - b.usageCount || a.weight - b.weight);
      const selected = options[0];
      if (!selected) break;
      path.push(selected.to);
      current = selected.to;
      visited.add(current);
    }

    return path;
  }

  getStrongestConnection(nodeId: string, excluded = new Set<string>()): string | null {
    let best: string | null = null;
    let maxWeight = 0;

    graphEngine.edges.forEach((edge) => {
      if (edge.from === nodeId && !excluded.has(edge.to) && edge.weight > maxWeight) {
        maxWeight = edge.weight;
        best = edge.to;
      }
    });

    return best;
  }
}

export const executionEngine = new ExecutionEngine();
