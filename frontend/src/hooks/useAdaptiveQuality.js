/**
 * Adaptive quality hook for Three.js components
 * Adjusts particle counts, animations, and effects based on FPS
 */

import { useEffect, useState, useRef } from 'react';

export function useAdaptiveQuality() {
  const [quality, setQuality] = useState('normal');
  const qualityRef = useRef('normal');
  const fpsRef = useRef(60);
  const frameCountRef = useRef(0);
  const lastTimeRef = useRef(performance.now());
  const animationFrameRef = useRef(null);

  useEffect(() => {
    let consecutiveFrameChecks = 0;

    const checkFPS = () => {
      frameCountRef.current++;
      const now = performance.now();
      const deltaTime = now - lastTimeRef.current;

      if (deltaTime >= 1000) {
        const fps = (frameCountRef.current * 1000) / deltaTime;
        fpsRef.current = fps;

        // Adaptive quality based on FPS
        if (fps > 55) {
          if (qualityRef.current !== 'normal') { qualityRef.current = 'normal'; setQuality('normal'); consecutiveFrameChecks = 0; }
        } else if (fps > 45) {
          if (qualityRef.current !== 'normal') {
            consecutiveFrameChecks++;
            if (consecutiveFrameChecks > 2) { qualityRef.current = 'normal'; setQuality('normal'); consecutiveFrameChecks = 0; }
          }
        } else if (fps > 30) {
          if (qualityRef.current !== 'reduced') { qualityRef.current = 'reduced'; setQuality('reduced'); consecutiveFrameChecks = 0; }
        } else if (fps > 20) {
          if (qualityRef.current !== 'low') { qualityRef.current = 'low'; setQuality('low'); consecutiveFrameChecks = 0; }
        } else {
          if (qualityRef.current !== 'fallback') { qualityRef.current = 'fallback'; setQuality('fallback'); consecutiveFrameChecks = 0; }
        }

        frameCountRef.current = 0;
        lastTimeRef.current = now;
      }

      animationFrameRef.current = requestAnimationFrame(checkFPS);
    };

    animationFrameRef.current = requestAnimationFrame(checkFPS);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, []);

  const qualitySettings = {
    normal: {
      particleCount: 1.0,
      blur: true,
      animations: true,
      shadowQuality: 'high',
    },
    reduced: {
      particleCount: 0.5,
      blur: true,
      animations: true,
      shadowQuality: 'medium',
    },
    low: {
      particleCount: 0.25,
      blur: false,
      animations: true,
      shadowQuality: 'low',
    },
    fallback: {
      particleCount: 0,
      blur: false,
      animations: false,
      shadowQuality: 'none',
    },
  };

  return {
    quality,
    fps: Math.round(fpsRef.current),
    ...qualitySettings[quality],
  };
}
