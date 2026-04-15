import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from 'd3-force';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { Edge, Node } from '../../shared/types';

type PositionedNode = Node & { x: number; y: number };

interface NeuralGraphProps {
  nodes: Node[];
  edges: Edge[];
  activePath: string[];
  onSelectNode: (node: Node) => void;
}

const WIDTH = 980;
const HEIGHT = 620;

function edgeColor(weight: number): string {
  if (weight > 0.7) return '#22c55e';
  if (weight > 0.35) return '#eab308';
  return '#ef4444';
}

export function NeuralGraph({ nodes, edges, activePath, onSelectNode }: NeuralGraphProps) {
  const [time, setTime] = useState(Date.now());
  const [layout, setLayout] = useState<PositionedNode[]>([]);
  const nodeMap = useMemo(() => new Map(layout.map((node) => [node.id, node])), [layout]);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const ticker = window.setInterval(() => setTime(Date.now()), 16);
    return () => window.clearInterval(ticker);
  }, []);

  useEffect(() => {
    if (!nodes.length) {
      setLayout([]);
      return;
    }
    const simNodes = nodes.map((node) => ({ ...node, x: Math.random() * WIDTH, y: Math.random() * HEIGHT }));
    const simLinks = edges.map((edge) => ({ source: edge.from, target: edge.to }));

    const simulation = forceSimulation(simNodes as any)
      .force('charge', forceManyBody().strength(-170))
      .force('center', forceCenter(WIDTH / 2, HEIGHT / 2))
      .force('link', forceLink(simLinks).id((d: any) => d.id).distance(90))
      .force('collide', forceCollide(28))
      .stop();

    for (let i = 0; i < 120; i += 1) simulation.tick();
    setLayout(simNodes.map((node: any) => ({ ...node, x: node.x ?? WIDTH / 2, y: node.y ?? HEIGHT / 2 })));
  }, [nodes, edges]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, WIDTH, HEIGHT);

    edges.forEach((edge) => {
      const from = nodeMap.get(edge.from);
      const to = nodeMap.get(edge.to);
      if (!from || !to) return;
      ctx.beginPath();
      ctx.strokeStyle = edgeColor(edge.weight);
      ctx.lineWidth = 1 + edge.weight * 5;
      ctx.moveTo(from.x, from.y);
      ctx.lineTo(to.x, to.y);
      ctx.stroke();

      const isActive = activePath.some((id, idx) => id === edge.from && activePath[idx + 1] === edge.to);
      if (isActive) {
        const progress = ((time / 900) % 1);
        const px = from.x + (to.x - from.x) * progress;
        const py = from.y + (to.y - from.y) * progress;
        ctx.beginPath();
        ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#22d3ee';
        ctx.shadowBlur = 16;
        ctx.shadowColor = '#22d3ee';
        ctx.fill();
        ctx.shadowBlur = 0;
      }
    });

    layout.forEach((node) => {
      const active = activePath.includes(node.id);
      const radius = active ? 11 : 7;
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = active ? '#22d3ee' : '#6366f1';
      if (active) {
        ctx.shadowBlur = 14;
        ctx.shadowColor = '#22d3ee';
      }
      ctx.fill();
      ctx.shadowBlur = 0;
    });
  }, [activePath, edges, layout, nodeMap, time]);

  const handleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const selected = layout.find((node) => Math.hypot(node.x - x, node.y - y) < 12);
    if (selected) onSelectNode(selected);
  };

  return (
    <canvas
      ref={canvasRef}
      width={WIDTH}
      height={HEIGHT}
      onClick={handleClick}
      style={{ width: '100%', maxWidth: WIDTH, borderRadius: 14, background: '#0b1020', border: '1px solid #1f2937' }}
    />
  );
}
