import fs from 'node:fs';
import path from 'node:path';

export interface VectorEntry {
  id: string;
  vector: number[];
  metadata: Record<string, any>;
}

export class VectorStore {
  private readonly filePath: string;
  private entries = new Map<string, VectorEntry>();

  constructor(filePath = path.resolve(process.cwd(), 'state', 'neural-vectors.json')) {
    this.filePath = filePath;
    this.restore();
  }

  upsert(entry: VectorEntry): void {
    this.entries.set(entry.id, entry);
    this.persist();
  }

  nearest(vector: number[], topK = 3): VectorEntry[] {
    return Array.from(this.entries.values())
      .map((entry) => ({
        entry,
        score: cosineSimilarity(vector, entry.vector),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
      .map((x) => x.entry);
  }

  private restore(): void {
    try {
      if (!fs.existsSync(this.filePath)) return;
      const raw = fs.readFileSync(this.filePath, 'utf-8');
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return;
      parsed.forEach((entry) => {
        if (entry && typeof entry.id === 'string' && Array.isArray(entry.vector)) {
          this.entries.set(entry.id, entry as VectorEntry);
        }
      });
    } catch {
      this.entries.clear();
    }
  }

  private persist(): void {
    const dir = path.dirname(this.filePath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(this.filePath, JSON.stringify(Array.from(this.entries.values()), null, 2), 'utf-8');
  }
}

function cosineSimilarity(a: number[], b: number[]): number {
  const n = Math.max(a.length, b.length);
  if (!n) return 0;
  let dot = 0;
  let magA = 0;
  let magB = 0;
  for (let i = 0; i < n; i += 1) {
    const av = a[i] || 0;
    const bv = b[i] || 0;
    dot += av * bv;
    magA += av * av;
    magB += bv * bv;
  }
  if (!magA || !magB) return 0;
  return dot / (Math.sqrt(magA) * Math.sqrt(magB));
}

export const vectorStore = new VectorStore();
