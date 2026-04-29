import { useEffect, useRef } from 'react';
import { useAppStore } from '../store/appStore';
import gsap from 'gsap';

/**
 * useOrbitNodeInteraction — Navigate between orbital nodes with camera transitions
 * Clicking a node causes:
 * 1. Camera to dolly toward that node (zoom 35% → full screen)
 * 2. Node expands to become new center of universe
 * 3. Page router dispatches to corresponding subsystem page
 * 4. Orbital children render around new center
 */

export const useOrbitNodeInteraction = () => {
  const { setActiveSection } = useAppStore();
  const cameraRef = useRef(null);

  const nodePageMap = {
    agents: 'agents',
    memory: 'neural-brain',
    models: 'ai-control',
    revenue: 'money-mode',
    security: 'blacklight',
    analytics: 'analytics-bi',
  };

  const handleNodeClick = async (nodeId, camera) => {
    if (!camera) return;

    cameraRef.current = camera;

    // Get node position
    const angle = getNodeAngle(nodeId);
    const orbitRadius = 3.2;
    const nodeX = Math.cos(angle) * orbitRadius;
    const nodeZ = Math.sin(angle) * orbitRadius;

    // Animate camera to node
    const timeline = gsap.timeline();

    // Step 1: Zoom in on node (500ms)
    timeline.to(
      camera.position,
      {
        x: nodeX * 0.5,
        y: 0,
        z: nodeZ * 0.5,
        duration: 0.5,
        ease: 'power2.inOut',
      },
      0
    );

    // Step 2: Dolly further into node (300ms)
    timeline.to(
      camera.position,
      {
        x: 0,
        y: 0,
        z: 2.0,
        duration: 0.3,
        ease: 'back.out',
      },
      0.5
    );

    // Step 3: Fade out core + orbital nodes (during step 2)
    timeline.to(
      { opacity: 1 },
      {
        opacity: 0,
        duration: 0.5,
        onUpdate: function() {
          // Dispatch opacity change to parent Three.js scene
          window.dispatchEvent(
            new CustomEvent('neural-fade', {
              detail: { opacity: this.targets()[0].opacity },
            })
          );
        },
      },
      0.3
    );

    // Step 4: Wait for animation to complete, then switch page
    await new Promise(resolve => setTimeout(resolve, 800));

    // Navigate to subsystem page
    const pageId = nodePageMap[nodeId];
    if (pageId) {
      setActiveSection(pageId);

      // Signal to render subsystem orbital children
      window.dispatchEvent(
        new CustomEvent('orbital-enter', {
          detail: {
            nodeId,
            depth: 1, // Level of detail: 1 = subsystem center
          },
        })
      );
    }
  };

  const handleNodeDoubleClick = async (nodeId, camera) => {
    // Double-click: Enter "deep operational mode"
    // Node becomes full-screen center with its own orbital children
    handleNodeClick(nodeId, camera);
    window.dispatchEvent(
      new CustomEvent('orbital-deep-mode', {
        detail: { nodeId, depth: 2 },
      })
    );
  };

  const exitOrbitalView = (camera) => {
    if (!camera) return;

    // Reverse animation: return to core view
    const timeline = gsap.timeline();

    // Step 1: Dolly out from subsystem (300ms)
    timeline.to(
      camera.position,
      {
        x: 0,
        y: 0,
        z: 3.5,
        duration: 0.3,
        ease: 'power2.inOut',
      },
      0
    );

    // Step 2: Fade in core + orbitals (during step 1)
    timeline.to(
      { opacity: 0 },
      {
        opacity: 1,
        duration: 0.3,
        onUpdate: function() {
          window.dispatchEvent(
            new CustomEvent('neural-fade', {
              detail: { opacity: this.targets()[0].opacity },
            })
          );
        },
      },
      0
    );

    // Step 3: Return to dashboard
    setTimeout(() => {
      setActiveSection('dashboard');
      window.dispatchEvent(
        new CustomEvent('orbital-exit', {
          detail: { returnToDashboard: true },
        })
      );
    }, 300);
  };

  return {
    handleNodeClick,
    handleNodeDoubleClick,
    exitOrbitalView,
  };
};

// Helper: map node IDs to orbital angles
function getNodeAngle(nodeId) {
  const angles = {
    agents: 0,
    memory: Math.PI / 3,
    models: (Math.PI * 2) / 3,
    revenue: Math.PI,
    security: Math.PI + Math.PI / 3,
    analytics: Math.PI + (Math.PI * 2) / 3,
  };
  return angles[nodeId] || 0;
}

/**
 * useOrbitChildNodes — Render child orbital nodes around a subsystem center
 * Used when viewing a subsystem page to show its operational satellites
 */
export const useOrbitChildNodes = (parentNodeId) => {
  const childNodeMap = {
    agents: [
      { id: 'agents-active', label: 'Active Fleet', color: '#22c55e' },
      { id: 'agents-idle', label: 'Idle Pool', color: '#666670' },
      { id: 'agents-health', label: 'Health Monitor', color: '#e5c76b' },
      { id: 'agents-upgrade', label: 'Upgrade Queue', color: '#a855f7' },
    ],
    memory: [
      { id: 'memory-cache', label: 'L1 Cache', color: '#e5c76b' },
      { id: 'memory-vector', label: 'Vector Store', color: '#a855f7' },
      { id: 'memory-graph', label: 'Knowledge Graph', color: '#cd7f32' },
      { id: 'memory-archive', label: 'Archive', color: '#666670' },
    ],
    revenue: [
      { id: 'revenue-live', label: 'Live Revenue', color: '#ffdf00' },
      { id: 'revenue-forecast', label: 'Forecasts', color: '#e5c76b' },
      { id: 'revenue-costs', label: 'Cost Analysis', color: '#cd7f32' },
      { id: 'revenue-billing', label: 'Billing', color: '#a855f7' },
    ],
    security: [
      { id: 'security-threats', label: 'Threat Detection', color: '#8b0000' },
      { id: 'security-auth', label: 'Authentication', color: '#e5c76b' },
      { id: 'security-audit', label: 'Audit Log', color: '#cd7f32' },
      { id: 'security-compliance', label: 'Compliance', color: '#22c55e' },
    ],
    analytics: [
      { id: 'analytics-kpi', label: 'KPIs', color: '#e5c76b' },
      { id: 'analytics-cohorts', label: 'Cohorts', color: '#a855f7' },
      { id: 'analytics-trends', label: 'Trends', color: '#cd7f32' },
      { id: 'analytics-retention', label: 'Retention', color: '#22c55e' },
    ],
    models: [
      { id: 'models-anthropic', label: 'Anthropic', color: '#e5c76b' },
      { id: 'models-openrouter', label: 'OpenRouter', color: '#cd7f32' },
      { id: 'models-ollama', label: 'Ollama', color: '#a855f7' },
      { id: 'models-latency', label: 'Latency Monitor', color: '#666670' },
    ],
  };

  const children = childNodeMap[parentNodeId] || [];

  return {
    children,
    childCount: children.length,
  };
};

export default useOrbitNodeInteraction;
