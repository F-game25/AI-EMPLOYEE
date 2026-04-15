export type NodeType = 'agent' | 'task' | 'decision' | 'memory' | 'strategy';

export interface Node {
  id: string;
  type: NodeType;
  label: string;
  metadata: Record<string, any>;
  activation: number;
  confidence: number;
  createdAt: number;
}

export interface Edge {
  from: string;
  to: string;
  weight: number;
  successRate: number;
  usageCount: number;
  lastUsed: number;
}

export interface Strategy {
  id: string;
  path: string[];
  successRate: number;
  usageCount: number;
}

export interface Experience {
  id: string;
  taskId?: string;
  agentId?: string;
  path: string[];
  success?: boolean;
  timestamp: number;
  metadata: Record<string, any>;
}

export interface GraphSnapshot {
  nodes: Node[];
  edges: Edge[];
  strategies: Strategy[];
  shortTerm: Experience[];
  longTerm: Experience[];
  activePath: string[];
  recentlyUsedPaths: string[][];
  failedPaths: string[][];
}
