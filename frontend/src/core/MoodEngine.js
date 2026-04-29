/**
 * MoodEngine — system mood state machine driven by live metrics
 * Maps normalized metrics → one of 7 moods with associated visual + audio state
 */

const MOODS = {
  SERENE: {
    id: 'serene',
    color: '#a855f7',
    core_spin: 0.02,
    particle_count: 0.3,
    edge_glow: 0.1,
    bloom_intensity: 0.4,
    ambient_pad_freq: 110, // A2 deep
  },
  OPERATIONAL: {
    id: 'operational',
    color: '#e5c76b',
    core_spin: 0.05,
    particle_count: 0.6,
    edge_glow: 0.3,
    bloom_intensity: 0.6,
    ambient_pad_freq: 220, // A3
  },
  HEAVY_LOAD: {
    id: 'heavy_load',
    color: '#ffdf00',
    core_spin: 0.12,
    particle_count: 1.0,
    edge_glow: 0.6,
    bloom_intensity: 0.85,
    ambient_pad_freq: 330, // A4
  },
  ALERT: {
    id: 'alert',
    color: '#8b0000',
    core_spin: 0.2,
    particle_count: 0.8,
    edge_glow: 0.8,
    bloom_intensity: 1.0,
    ambient_pad_freq: 440, // A5 (bright warning)
  },
  TRIUMPH: {
    id: 'triumph',
    color: '#00ff88',
    core_spin: 0.08,
    particle_count: 0.9,
    edge_glow: 0.7,
    bloom_intensity: 0.9,
    ambient_pad_freq: 293.66, // D4
  },
  LEARNING: {
    id: 'learning',
    color: '#00d4ff',
    core_spin: 0.07,
    particle_count: 0.7,
    edge_glow: 0.5,
    bloom_intensity: 0.7,
    ambient_pad_freq: 246.94, // B3
  },
  IDLE_SLEEP: {
    id: 'idle_sleep',
    color: '#1a2a4e',
    core_spin: 0.005,
    particle_count: 0.05,
    edge_glow: 0.05,
    bloom_intensity: 0.2,
    ambient_pad_freq: 82.41, // E2 (deep sub)
  },
};

export class MoodEngine {
  constructor() {
    this.currentMood = MOODS.SERENE;
    this.previousMood = MOODS.SERENE;
    this.transitionProgress = 0;
    this.transitionDuration = 800; // ms
    this.idleTimer = null;
    this.idleThreshold = 180000; // 3 minutes
    this.lastActivityTime = Date.now();
    this.metrics = {};
  }

  /**
   * Update metrics and determine mood
   * @param {object} metrics — normalized values: taskRate [0-1], errorRate [0-1], cpuUsage [0-100], etc.
   */
  updateMetrics(metrics) {
    this.metrics = metrics;
    this.lastActivityTime = Date.now(); // Reset idle timer on any metric change
    this.determineMood(metrics);
  }

  /**
   * Register user activity (mouse move, key press, etc.)
   */
  recordActivity() {
    this.lastActivityTime = Date.now();
    if (this.currentMood === MOODS.IDLE_SLEEP) {
      this.transitionMood(MOODS.OPERATIONAL);
    }
  }

  determineMood(metrics) {
    const { taskRate = 0, errorRate = 0, cpuUsage = 0, agentCount = 0 } = metrics;

    // Idle detection
    const timeSinceActivity = Date.now() - this.lastActivityTime;
    if (timeSinceActivity > this.idleThreshold) {
      this.transitionMood(MOODS.IDLE_SLEEP);
      return;
    }

    // Error state dominates everything
    if (errorRate > 0.5) {
      this.transitionMood(MOODS.ALERT);
      return;
    }

    // Load-based moods
    if (taskRate > 0.8 || cpuUsage > 80) {
      this.transitionMood(MOODS.HEAVY_LOAD);
      return;
    }

    // Task completion success (learning/triumph state)
    if (taskRate > 0.6 && errorRate < 0.1) {
      this.transitionMood(MOODS.TRIUMPH);
      return;
    }

    // Normal operational
    if (taskRate > 0.3) {
      this.transitionMood(MOODS.OPERATIONAL);
      return;
    }

    // Idle but not sleeping (light activity)
    if (taskRate > 0.05) {
      this.transitionMood(MOODS.LEARNING);
      return;
    }

    // Default: serene
    this.transitionMood(MOODS.SERENE);
  }

  transitionMood(newMood) {
    if (this.currentMood.id === newMood.id) return; // No change needed

    this.previousMood = this.currentMood;
    this.currentMood = newMood;
    this.transitionProgress = 0;

    // Log mood change
    console.log(`[MoodEngine] Mood: ${this.previousMood.id} → ${newMood.id}`);
  }

  /**
   * Get interpolated mood state during transition
   * Call this every frame to smoothly blend between old and new mood
   */
  getBlendedMood() {
    // Update transition progress
    this.transitionProgress = Math.min(this.transitionProgress + 16 / this.transitionDuration, 1);

    const p = this.easeInOutCubic(this.transitionProgress);

    return {
      color: this.lerpColor(this.previousMood.color, this.currentMood.color, p),
      core_spin: this.lerp(this.previousMood.core_spin, this.currentMood.core_spin, p),
      particle_count: this.lerp(this.previousMood.particle_count, this.currentMood.particle_count, p),
      edge_glow: this.lerp(this.previousMood.edge_glow, this.currentMood.edge_glow, p),
      bloom_intensity: this.lerp(this.previousMood.bloom_intensity, this.currentMood.bloom_intensity, p),
      ambient_pad_freq: this.lerp(this.previousMood.ambient_pad_freq, this.currentMood.ambient_pad_freq, p),
      moodId: this.currentMood.id,
    };
  }

  // Utility: linear interpolation
  lerp(a, b, t) {
    return a + (b - a) * t;
  }

  // Utility: color interpolation (hex string)
  lerpColor(colorA, colorB, t) {
    const c1 = parseInt(colorA.slice(1), 16);
    const c2 = parseInt(colorB.slice(1), 16);

    const r1 = (c1 >> 16) & 0xff;
    const g1 = (c1 >> 8) & 0xff;
    const b1 = c1 & 0xff;

    const r2 = (c2 >> 16) & 0xff;
    const g2 = (c2 >> 8) & 0xff;
    const b2 = c2 & 0xff;

    const r = Math.round(this.lerp(r1, r2, t));
    const g = Math.round(this.lerp(g1, g2, t));
    const b = Math.round(this.lerp(b1, b2, t));

    return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
  }

  // Utility: easing function
  easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  getMoodDescription() {
    const moodTexts = {
      serene: 'System serene. All quiet.',
      operational: 'Operational mode. Ready.',
      heavy_load: 'Heavy load detected. Working hard.',
      alert: 'ALERT: Error state triggered.',
      triumph: 'Triumph! Tasks completed successfully.',
      learning: 'Learning mode. Analyzing.',
      idle_sleep: 'System idle. Resting.',
    };
    return moodTexts[this.currentMood.id] || 'Unknown mood';
  }
}

export const moodEngine = new MoodEngine();
