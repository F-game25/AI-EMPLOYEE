import { useEffect, useMemo, useState } from 'react';
import type { GraphSnapshot } from '../../shared/types';
import { brainAPI } from '../services/brainAPI';

const EMPTY: GraphSnapshot = {
  nodes: [],
  edges: [],
  strategies: [],
  shortTerm: [],
  longTerm: [],
  activePath: [],
  recentlyUsedPaths: [],
  failedPaths: [],
};

export function useNeuralGraph() {
  const [snapshot, setSnapshot] = useState<GraphSnapshot>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let closed = false;

    brainAPI.getState()
      .then((data) => {
        if (!closed) setSnapshot(data);
      })
      .catch((err) => {
        if (!closed) setError(err instanceof Error ? err.message : 'load_failed');
      })
      .finally(() => {
        if (!closed) setLoading(false);
      });

    const stream = new EventSource(brainAPI.streamURL);
    stream.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (parsed?.snapshot) setSnapshot(parsed.snapshot);
      } catch {
        // ignore malformed event payloads
      }
    };
    stream.onerror = () => {
      setError((prev) => prev || 'stream_disconnected');
    };

    return () => {
      closed = true;
      stream.close();
    };
  }, []);

  const stats = useMemo(() => ({
    nodeCount: snapshot.nodes.length,
    edgeCount: snapshot.edges.length,
    strategyCount: snapshot.strategies.length,
    experienceCount: snapshot.longTerm.length + snapshot.shortTerm.length,
  }), [snapshot]);

  return { snapshot, loading, error, stats };
}
