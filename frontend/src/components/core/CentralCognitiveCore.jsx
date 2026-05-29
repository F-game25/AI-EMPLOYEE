import React, { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import gsap from 'gsap';
import { useCognitiveStore } from '../../store/cognitiveStore';
import { useSystemStore } from '../../store/systemStore';
import { useSecurityStore } from '../../store/securityStore';
import { useTaskStore } from '../../store/taskStore';
import { useAdaptiveQuality } from '../../hooks/useAdaptiveQuality';
import { measureComponentRender } from '../../utils/performanceMonitor';
import CoreSphere from '../three/NeuralCore/CoreSphere';

/**
 * CENTRAL COGNITIVE CORE — Reactive Avatar System
 *
 * This is the heart of the UI. A 9-state machine avatar that continuously
 * morphs its visual properties based on system triggers:
 *
 * STATE MACHINE:
 * idle → thinking → planning → executing → learning
 *      ↓
 *      warning → focused
 *      ↓
 *      sleeping, error (independent states)
 *
 * CONTINUOUS REACTIVITY (CSS variable updates, NOT re-renders):
 * - CPU load → orbit speed
 * - RAM usage → particle count
 * - Inference queue depth → glow intensity
 * - Threat level → color tint
 *
 * Component Architecture:
 * 1. Three.js CoreSphere at center (existing component)
 * 2. 3 CSS rotating rings around sphere
 * 3. Data badges positioned around sphere (objective, active task, tool)
 * 4. Particle system (capped 100 particles, orbit pattern)
 */

const CentralCognitiveCore = () => {
  // State subscriptions (granular selectors to avoid re-renders on unrelated updates)
  const avatarState = useCognitiveStore(s => s.avatarState);
  const reasoningSteps = useCognitiveStore(s => s.reasoningSteps);
  const modelCalls = useCognitiveStore(s => s.modelCalls);
  const brainActivity = useCognitiveStore(s => s.brainActivity);
  const wsConnected = useSystemStore(s => s.wsConnected);
  const systemStatus = useSystemStore(s => s.systemStatus);
  const appState = useSystemStore(s => s.appState);
  const securityStatus = useSecurityStore(s => s.securityStatus);
  const workflowState = useTaskStore(s => s.workflowState);
  const chatMessages = useTaskStore(s => s.chatMessages);

  // Adaptive quality for performance optimization
  const adaptiveQuality = useAdaptiveQuality();
  const perfMeasureRef = useRef(null);
  if (perfMeasureRef.current === null) {
    perfMeasureRef.current = measureComponentRender('CentralCognitiveCore');
  }

  // DOM refs for DOM-direct updates (no re-render cost)
  const coreContainerRef = useRef(null);
  const ring1Ref = useRef(null);
  const ring2Ref = useRef(null);
  const ring3Ref = useRef(null);
  const particlesRef = useRef(null);

  // Performance monitoring
  useEffect(() => {
    perfMeasureRef.current.start();
    return () => perfMeasureRef.current.end();
  }, []);

  // State machine implementation
  // Derives current state from reactive triggers
  const computeState = useCallback((triggers) => {
    const {
      wsConnected,
      hasActiveTask,
      hasActiveReasoning,
      threatLevel,
      cpuUsage,
      isError,
    } = triggers;

    // Offline/error takes priority
    if (!wsConnected || isError) return 'error';

    // Threat escalation
    if (threatLevel === 'CRITICAL') return 'warning';
    if (threatLevel === 'ALERT') return 'focused';

    // Active execution
    if (hasActiveTask && hasActiveReasoning) return 'executing';
    if (hasActiveReasoning) return 'thinking';

    // High CPU = focused attention
    if (cpuUsage > 70) return 'planning';

    // Idle by default
    return 'idle';
  }, []);

  // Extract triggers from stores (memoized to prevent excessive recomputation)
  const triggers = useMemo(() => {
    const hasActiveTask = !!workflowState?.active_run;
    const hasActiveReasoning = reasoningSteps.length > 0;
    const threatLevel = securityStatus?.mode || 'NORMAL';
    const cpuUsage = systemStatus?.cpu_usage || 0;
    const memoryUsage = systemStatus?.memory || 0;
    const inferenceQueueDepth = modelCalls.length;
    const isError = appState === 'error';

    return {
      wsConnected,
      hasActiveTask,
      hasActiveReasoning,
      threatLevel,
      cpuUsage,
      memoryUsage,
      inferenceQueueDepth,
      isError,
    };
  }, [
    workflowState,
    reasoningSteps.length,
    securityStatus?.mode,
    systemStatus?.cpu_usage,
    systemStatus?.memory,
    modelCalls.length,
    wsConnected,
    appState,
  ]);

  // Current state
  const currentState = useMemo(() => computeState(triggers), [triggers, computeState]);

  // Avatar properties by state
  // Each state defines base properties; reactivity layer modulates them
  const stateConfig = {
    idle: {
      primaryColor: '#3CE7FF', // cyan
      secondaryColor: '#A855F7', // purple
      orbitSpeed: 12, // seconds per rotation
      glowIntensity: 0.3,
      pulseFrequency: 0.8, // Hz
      particleCount: 15,
      ringOpacity: 0.6,
    },
    thinking: {
      primaryColor: '#FFD97A', // gold
      secondaryColor: '#E5C76B', // gold dim
      orbitSpeed: 8,
      glowIntensity: 0.5,
      pulseFrequency: 1.2,
      particleCount: 40,
      ringOpacity: 0.8,
    },
    planning: {
      primaryColor: '#FFD97A', // gold
      secondaryColor: '#C084FC', // purple bright
      orbitSpeed: 6,
      glowIntensity: 0.6,
      pulseFrequency: 1.5,
      particleCount: 60,
      ringOpacity: 0.9,
    },
    executing: {
      primaryColor: '#22C55E', // green
      secondaryColor: '#FFD97A', // gold
      orbitSpeed: 4,
      glowIntensity: 0.7,
      pulseFrequency: 2.0,
      particleCount: 80,
      ringOpacity: 0.95,
    },
    learning: {
      primaryColor: '#60A5FA', // blue
      secondaryColor: '#A855F7', // purple
      orbitSpeed: 5,
      glowIntensity: 0.6,
      pulseFrequency: 1.3,
      particleCount: 50,
      ringOpacity: 0.85,
    },
    warning: {
      primaryColor: '#F97316', // orange
      secondaryColor: '#EF4444', // red
      orbitSpeed: 3,
      glowIntensity: 0.8,
      pulseFrequency: 2.5,
      particleCount: 90,
      ringOpacity: 1.0,
    },
    focused: {
      primaryColor: '#FBBF24', // amber
      secondaryColor: '#F59E0B', // warning
      orbitSpeed: 5,
      glowIntensity: 0.7,
      pulseFrequency: 1.8,
      particleCount: 70,
      ringOpacity: 0.9,
    },
    sleeping: {
      primaryColor: '#6B7280', // gray
      secondaryColor: '#4B5563', // gray dim
      orbitSpeed: 20, // very slow
      glowIntensity: 0.2,
      pulseFrequency: 0.3,
      particleCount: 5,
      ringOpacity: 0.4,
    },
    error: {
      primaryColor: '#EF4444', // red
      secondaryColor: '#DC2626', // red dark
      orbitSpeed: 2,
      glowIntensity: 0.9,
      pulseFrequency: 3.0,
      particleCount: 100,
      ringOpacity: 1.0,
    },
  };

  const baseProps = stateConfig[currentState] || stateConfig.idle;

  // Continuous reactivity layer
  // Modulates properties based on real-time metrics WITHOUT re-rendering
  const computeAvatarProperties = useCallback(() => {
    const props = { ...baseProps };

    // CPU load → orbit speed (inverse relationship)
    const { cpuUsage } = triggers;
    if (cpuUsage < 30) {
      props.orbitSpeed = baseProps.orbitSpeed * 1.5;
    } else if (cpuUsage > 30 && cpuUsage <= 50) {
      props.orbitSpeed = baseProps.orbitSpeed;
    } else if (cpuUsage > 50 && cpuUsage <= 70) {
      props.orbitSpeed = baseProps.orbitSpeed * 0.8;
    } else if (cpuUsage > 70 && cpuUsage <= 90) {
      props.orbitSpeed = baseProps.orbitSpeed * 0.6;
    } else {
      props.orbitSpeed = baseProps.orbitSpeed * 0.4;
    }

    // RAM usage → particle count (linear scaling)
    const { memoryUsage } = triggers;
    if (memoryUsage < 40) {
      props.particleCount = Math.max(10, baseProps.particleCount * 0.5);
    } else if (memoryUsage > 40 && memoryUsage <= 60) {
      props.particleCount = baseProps.particleCount;
    } else if (memoryUsage > 60 && memoryUsage <= 80) {
      props.particleCount = Math.round(baseProps.particleCount * 1.4);
    } else {
      props.particleCount = Math.min(100, Math.round(baseProps.particleCount * 1.8));
    }

    // Inference queue depth → glow intensity
    const { inferenceQueueDepth } = triggers;
    if (inferenceQueueDepth < 5) {
      props.glowIntensity = baseProps.glowIntensity * 0.6;
    } else if (inferenceQueueDepth >= 5 && inferenceQueueDepth <= 15) {
      props.glowIntensity = baseProps.glowIntensity;
    } else if (inferenceQueueDepth > 15 && inferenceQueueDepth <= 30) {
      props.glowIntensity = baseProps.glowIntensity * 1.3;
    } else {
      props.glowIntensity = baseProps.glowIntensity * 1.6;
    }

    // Threat level → color tint (via CSS filter)
    const { threatLevel } = triggers;
    props.threatTint = {
      NORMAL: 'none',
      ALERT: 'hue-rotate(45deg) saturate(1.2)',
      CRITICAL: 'hue-rotate(0deg) saturate(1.5) brightness(1.1)',
    }[threatLevel] || 'none';

    return props;
  }, [baseProps, triggers]);

  const avatarProps = useMemo(
    () => computeAvatarProperties(),
    [computeAvatarProperties]
  );

  // Update DOM directly on state change (no re-render)
  useEffect(() => {
    if (!coreContainerRef.current) return;

    const container = coreContainerRef.current;

    // Set CSS variables for smooth transitions
    container.style.setProperty('--primary-color', avatarProps.primaryColor);
    container.style.setProperty('--secondary-color', avatarProps.secondaryColor);
    container.style.setProperty('--glow-intensity', avatarProps.glowIntensity.toString());
    container.style.setProperty('--pulse-frequency', avatarProps.pulseFrequency.toString());
    container.style.setProperty('--ring-opacity', avatarProps.ringOpacity.toString());
    container.style.setProperty('--threat-tint', avatarProps.threatTint);

    // Animate orbit speeds
    const ring1 = ring1Ref.current;
    const ring2 = ring2Ref.current;
    const ring3 = ring3Ref.current;

    if (ring1) {
      gsap.to(ring1, {
        '--orbit-speed': `${avatarProps.orbitSpeed}s`,
        duration: 0.8,
        ease: 'power1.inOut',
      });
    }

    if (ring2) {
      gsap.to(ring2, {
        '--orbit-speed': `${avatarProps.orbitSpeed * 1.2}s`,
        duration: 0.8,
        ease: 'power1.inOut',
      });
    }

    if (ring3) {
      gsap.to(ring3, {
        '--orbit-speed': `${avatarProps.orbitSpeed * 0.9}s`,
        duration: 0.8,
        ease: 'power1.inOut',
      });
    }
  }, [avatarProps]);

  // Update particle count dynamically
  useEffect(() => {
    const particlesContainer = particlesRef.current;
    if (!particlesContainer) return;

    const targetCount = Math.min(100, Math.max(5, avatarProps.particleCount));
    const currentCount = particlesContainer.children.length;

    if (currentCount < targetCount) {
      // Add particles
      for (let i = currentCount; i < targetCount; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particlesContainer.appendChild(particle);
      }
    } else if (currentCount > targetCount) {
      // Remove particles
      while (particlesContainer.children.length > targetCount) {
        particlesContainer.removeChild(particlesContainer.lastChild);
      }
    }
  }, [avatarProps.particleCount]);

  // Extract data badges
  const currentObjective = useMemo(() => {
    if (workflowState?.active_run) {
      return workflowState.active_run.substring(0, 20);
    }
    return 'idle';
  }, [workflowState?.active_run]);

  const activeTask = useMemo(() => {
    const lastMsg = chatMessages?.[chatMessages.length - 1];
    if (lastMsg?.content) {
      return lastMsg.content.substring(0, 30);
    }
    return 'none';
  }, [chatMessages]);

  const activeTool = useMemo(() => {
    const lastReason = reasoningSteps?.[reasoningSteps.length - 1];
    if (lastReason?.tool) {
      return lastReason.tool;
    }
    return 'thinking';
  }, [reasoningSteps]);

  // Metrics for CoreSphere shader
  const sphereMetrics = useMemo(
    () => ({
      rotationSpeed: 100 - avatarProps.orbitSpeed * 8,
      taskRate: triggers.hasActiveTask ? 1 : 0.3,
      errorMix: triggers.isError ? 1 : 0,
      load: Math.min(triggers.cpuUsage / 100, 1),
      thinking: reasoningSteps.length > 0 ? 1 : 0,
    }),
    [avatarProps.orbitSpeed, triggers, reasoningSteps.length]
  );

  return (
    <div
      ref={coreContainerRef}
      className="central-cognitive-core"
      data-state={currentState}
    >
      {/* Three.js CoreSphere at center */}
      <div className="core-sphere-container">
        <CoreSphere metrics={sphereMetrics} />
      </div>

      {/* Ring 1: Fast rotation (clockwise) */}
      <div
        ref={ring1Ref}
        className="orbit-ring ring-1"
        style={{
          '--orbit-speed': `${avatarProps.orbitSpeed}s`,
        }}
      >
        <div className="ring-element" />
      </div>

      {/* Ring 2: Medium rotation (counter-clockwise) */}
      <div
        ref={ring2Ref}
        className="orbit-ring ring-2"
        style={{
          '--orbit-speed': `${avatarProps.orbitSpeed * 1.2}s`,
        }}
      >
        <div className="ring-element" />
      </div>

      {/* Ring 3: Slow rotation (clockwise) */}
      <div
        ref={ring3Ref}
        className="orbit-ring ring-3"
        style={{
          '--orbit-speed': `${avatarProps.orbitSpeed * 0.9}s`,
        }}
      >
        <div className="ring-element" />
      </div>

      {/* Particle system (max 100 particles) */}
      <div ref={particlesRef} className="particles-system" />

      {/* Data badges around sphere */}
      <div className="data-badges">
        <div className="badge badge-objective">
          <span className="badge-label">Objective</span>
          <span className="badge-value">{currentObjective}</span>
        </div>

        <div className="badge badge-task">
          <span className="badge-label">Task</span>
          <span className="badge-value">{activeTask}</span>
        </div>

        <div className="badge badge-tool">
          <span className="badge-label">Tool</span>
          <span className="badge-value">{activeTool}</span>
        </div>
      </div>

      {/* State indicator */}
      <div className="state-indicator">
        <span className="state-dot" />
        <span className="state-text">{currentState}</span>
      </div>

    </div>
  );
};

export default CentralCognitiveCore;
