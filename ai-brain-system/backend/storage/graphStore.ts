import fs from 'node:fs';
import path from 'node:path';
import type { Edge } from '../models/Edge';
import type { Node } from '../models/Node';
import type { Strategy } from '../models/Strategy';

export interface PersistedGraph {
  nodes: Node[];
  edges: Edge[];
  strategies: Strategy[];
  shortTerm: any[];
  longTerm: any[];
  recentlyUsedPaths: string[][];
  failedPaths: string[][];
  activePath: string[];
}

const DEFAULT_STATE: PersistedGraph = {
  nodes: [],
  edges: [],
  strategies: [],
  shortTerm: [],
  longTerm: [],
  recentlyUsedPaths: [],
  failedPaths: [],
  activePath: [],
};

export class GraphStore {
  private readonly filePath: string;

  constructor(filePath = path.resolve(process.cwd(), 'state', 'neural-graph.json')) {
    this.filePath = filePath;
  }

  load(): PersistedGraph {
    try {
      if (!fs.existsSync(this.filePath)) return { ...DEFAULT_STATE };
      const raw = fs.readFileSync(this.filePath, 'utf-8');
      const parsed = JSON.parse(raw);
      return {
        ...DEFAULT_STATE,
        ...parsed,
        nodes: Array.isArray(parsed.nodes) ? parsed.nodes : [],
        edges: Array.isArray(parsed.edges) ? parsed.edges : [],
        strategies: Array.isArray(parsed.strategies) ? parsed.strategies : [],
        shortTerm: Array.isArray(parsed.shortTerm) ? parsed.shortTerm : [],
        longTerm: Array.isArray(parsed.longTerm) ? parsed.longTerm : [],
        recentlyUsedPaths: Array.isArray(parsed.recentlyUsedPaths) ? parsed.recentlyUsedPaths : [],
        failedPaths: Array.isArray(parsed.failedPaths) ? parsed.failedPaths : [],
        activePath: Array.isArray(parsed.activePath) ? parsed.activePath : [],
      };
    } catch {
      return { ...DEFAULT_STATE };
    }
  }

  save(data: PersistedGraph): void {
    const dir = path.dirname(this.filePath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(this.filePath, JSON.stringify(data, null, 2), 'utf-8');
  }
}

export const graphStore = new GraphStore();
