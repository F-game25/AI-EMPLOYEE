import type { Experience } from '../../shared/types';

class MemoryEngine {
  shortTerm: Experience[] = [];
  longTerm: Experience[] = [];

  storeShort(term: Experience) {
    this.shortTerm.push(term);
    if (this.shortTerm.length > 100) {
      this.shortTerm.shift();
    }
  }

  consolidate() {
    this.longTerm.push(...this.shortTerm);
    this.shortTerm = [];
    if (this.longTerm.length > 5000) {
      this.longTerm = this.longTerm.slice(-5000);
    }
  }

  findSimilarTask(taskId?: string, metadata: Record<string, any> = {}): Experience | null {
    const all = [...this.shortTerm, ...this.longTerm];
    if (!all.length) return null;
    if (taskId) {
      const exact = all.find((item) => item.taskId === taskId && item.success);
      if (exact) return exact;
    }

    const keys = Object.keys(metadata);
    if (!keys.length) return null;

    const scored = all
      .map((item) => {
        const overlap = keys.reduce((score, key) => {
          return score + (item.metadata?.[key] === metadata[key] ? 1 : 0);
        }, 0);
        return { item, overlap };
      })
      .sort((a, b) => b.overlap - a.overlap);

    return scored[0] && scored[0].overlap > 0 ? scored[0].item : null;
  }

  hydrate(shortTerm: Experience[], longTerm: Experience[]): void {
    this.shortTerm = Array.isArray(shortTerm) ? shortTerm : [];
    this.longTerm = Array.isArray(longTerm) ? longTerm : [];
  }
}

export const memoryEngine = new MemoryEngine();
