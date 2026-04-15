import { Router, type Request, type Response } from 'express';
import { EventEmitter } from 'node:events';
import type { GraphSnapshot, Node } from '../../shared/types';
import { executionEngine } from '../core/executionEngine';
import { graphEngine } from '../core/graphEngine';
import { learningEngine } from '../core/learningEngine';
import { memoryEngine } from '../core/memoryEngine';
import { graphStore } from '../storage/graphStore';

const bus = new EventEmitter();
let activePath: string[] = [];
let recentlyUsedPaths: string[][] = [];
let failedPaths: string[][] = [];

function hydrate(): void {
  const saved = graphStore.load();
  graphEngine.hydrate({ nodes: saved.nodes, edges: saved.edges });
  learningEngine.hydrate(saved.strategies);
  memoryEngine.hydrate(saved.shortTerm, saved.longTerm);
  activePath = Array.isArray(saved.activePath) ? saved.activePath : [];
  recentlyUsedPaths = Array.isArray(saved.recentlyUsedPaths) ? saved.recentlyUsedPaths : [];
  failedPaths = Array.isArray(saved.failedPaths) ? saved.failedPaths : [];
}

function snapshot(): GraphSnapshot {
  return {
    ...graphEngine.serialize(),
    strategies: learningEngine.topStrategies(20),
    shortTerm: memoryEngine.shortTerm,
    longTerm: memoryEngine.longTerm,
    activePath,
    recentlyUsedPaths,
    failedPaths,
  };
}

function persistAndBroadcast(event: string, payload: Record<string, any> = {}): void {
  const current = snapshot();
  graphStore.save(current);
  bus.emit('update', { event, payload, snapshot: current, ts: Date.now() });
}

hydrate();

const router = Router();

router.get('/state', (_req: Request, res: Response) => {
  res.json(snapshot());
});

router.get('/events', (req: Request, res: Response) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const onUpdate = (data: any) => {
    res.write(`event: ${data.event}\n`);
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  };

  bus.on('update', onUpdate);
  onUpdate({ event: 'state:init', snapshot: snapshot(), ts: Date.now() });

  req.on('close', () => {
    bus.off('update', onUpdate);
    res.end();
  });
});

router.post('/nodes', (req: Request, res: Response) => {
  const node = req.body as Node;
  if (!node?.id || !node?.type) {
    res.status(400).json({ error: 'invalid_node' });
    return;
  }
  graphEngine.addNode({
    ...node,
    createdAt: node.createdAt || Date.now(),
    activation: typeof node.activation === 'number' ? node.activation : 0,
    confidence: typeof node.confidence === 'number' ? node.confidence : 0.5,
    metadata: node.metadata || {},
  });
  persistAndBroadcast('node:added', { nodeId: node.id });
  res.status(201).json({ ok: true });
});

router.post('/agents/sync', (req: Request, res: Response) => {
  const agents = Array.isArray(req.body?.agents) ? req.body.agents : [];
  agents.forEach((agent: any) => {
    if (!agent?.id) return;
    graphEngine.addNode({
      id: String(agent.id),
      type: 'agent',
      label: String(agent.label || agent.id),
      metadata: { source: 'agents/sync', ...agent.metadata },
      activation: Number(agent.activation || 0),
      confidence: Number(agent.confidence || 0.5),
      createdAt: Date.now(),
    });
  });
  persistAndBroadcast('agents:synced', { count: agents.length });
  res.json({ ok: true, count: agents.length });
});

router.post('/connect', (req: Request, res: Response) => {
  const from = String(req.body?.from || '');
  const to = String(req.body?.to || '');
  if (!from || !to) {
    res.status(400).json({ error: 'from_and_to_required' });
    return;
  }
  graphEngine.connect(from, to);
  persistAndBroadcast('edge:connected', { from, to });
  res.status(201).json({ ok: true });
});

router.post('/task/run', (req: Request, res: Response) => {
  const taskId = String(req.body?.taskId || `task-${Date.now()}`);
  const startNodeId = String(req.body?.startNodeId || '');
  const metadata = req.body?.metadata || {};
  if (!startNodeId) {
    res.status(400).json({ error: 'startNodeId_required' });
    return;
  }

  const remembered = memoryEngine.findSimilarTask(taskId, metadata);
  const reused = Boolean(remembered?.path?.length);
  const path = reused
    ? remembered!.path
    : (executionEngine.findBestPath(startNodeId).length > 1
      ? executionEngine.findBestPath(startNodeId)
      : executionEngine.explorePath(startNodeId));

  activePath = path;
  recentlyUsedPaths = [path, ...recentlyUsedPaths].slice(0, 50);
  graphEngine.touchPath(path);
  memoryEngine.storeShort({
    id: `exp-${Date.now()}`,
    taskId,
    path,
    success: undefined,
    timestamp: Date.now(),
    metadata,
  });

  persistAndBroadcast('task:path-selected', { taskId, path, reused });
  res.json({
    taskId,
    path,
    reused,
    reason: reused ? 'memory_match' : 'exploration_or_weighted_greedy',
  });
});

router.post('/task/feedback', (req: Request, res: Response) => {
  const taskId = String(req.body?.taskId || '');
  const success = Boolean(req.body?.success);
  const path = Array.isArray(req.body?.path) ? req.body.path.map(String) : [];
  const metadata = req.body?.metadata || {};
  const agentId = req.body?.agentId ? String(req.body.agentId) : undefined;

  if (!taskId || path.length < 2) {
    res.status(400).json({ error: 'taskId_and_path_required' });
    return;
  }

  learningEngine.reinforcePath(path, success);
  if (!success) {
    learningEngine.penalizePath(path);
    failedPaths = [path, ...failedPaths].slice(0, 50);
  }

  memoryEngine.storeShort({
    id: `exp-${Date.now()}`,
    taskId,
    agentId,
    path,
    success,
    timestamp: Date.now(),
    metadata,
  });

  if (memoryEngine.shortTerm.length >= 25) {
    memoryEngine.consolidate();
  }

  activePath = path;
  persistAndBroadcast('task:feedback-recorded', { taskId, success, path });
  res.json({ ok: true, success });
});

export { router as brainRouter };
