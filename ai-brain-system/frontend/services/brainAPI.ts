import type { GraphSnapshot, Node } from '../../shared/types';

const BASE_URL = (import.meta as any).env?.VITE_BRAIN_API_URL || 'http://localhost:8899';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`brain_api_error:${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const brainAPI = {
  getState: () => request<GraphSnapshot>('/api/brain/state'),
  streamURL: `${BASE_URL}/api/brain/events`,
  addNode: (node: Node) => request('/api/brain/nodes', { method: 'POST', body: JSON.stringify(node) }),
  connect: (from: string, to: string) => request('/api/brain/connect', { method: 'POST', body: JSON.stringify({ from, to }) }),
  runTask: (taskId: string, startNodeId: string, metadata: Record<string, any> = {}) => request('/api/brain/task/run', {
    method: 'POST',
    body: JSON.stringify({ taskId, startNodeId, metadata }),
  }),
  feedback: (taskId: string, path: string[], success: boolean, metadata: Record<string, any> = {}, agentId?: string) => request('/api/brain/task/feedback', {
    method: 'POST',
    body: JSON.stringify({ taskId, path, success, metadata, agentId }),
  }),
};
