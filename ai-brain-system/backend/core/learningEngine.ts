import type { Strategy } from '../models/Strategy';
import { graphEngine } from './graphEngine';

class LearningEngine {
  private strategies = new Map<string, Strategy>();

  reinforcePath(path: string[], success: boolean) {
    for (let i = 0; i < path.length - 1; i += 1) {
      if (success) {
        graphEngine.strengthenEdge(path[i], path[i + 1]);
      } else {
        graphEngine.weakenEdge(path[i], path[i + 1]);
      }
    }
    this.detectStrategy([path], success);
  }

  detectStrategy(paths: string[][], successOnly = true) {
    paths.forEach((path) => {
      if (!path.length) return;
      const id = path.join('>');
      const strategy = this.strategies.get(id) || {
        id,
        path,
        successRate: 0,
        usageCount: 0,
      };
      strategy.usageCount += 1;
      if (!successOnly) {
        strategy.successRate = Math.max(0, strategy.successRate * 0.95);
      } else {
        strategy.successRate = (strategy.successRate + 1) / 2;
      }
      this.strategies.set(id, strategy);
    });
  }

  penalizePath(path: string[]) {
    this.detectStrategy([path], false);
  }

  topStrategies(limit = 10): Strategy[] {
    return Array.from(this.strategies.values())
      .sort((a, b) => {
        const scoreA = a.successRate * (1 + Math.log1p(a.usageCount));
        const scoreB = b.successRate * (1 + Math.log1p(b.usageCount));
        return scoreB - scoreA;
      })
      .slice(0, limit);
  }

  hydrate(strategies: Strategy[]) {
    this.strategies.clear();
    strategies.forEach((strategy) => this.strategies.set(strategy.id, strategy));
  }
}

export const learningEngine = new LearningEngine();
