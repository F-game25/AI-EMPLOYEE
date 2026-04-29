import React, { Suspense, useEffect, useState } from 'react';
import { useAppStore } from '../store/appStore';
import CommandDock from './dock/CommandDock';
import TopStrip from './hud/TopStrip';
import NeuralCore from './three/NeuralCore';
import AwakeningScene from './boot/AwakeningScene';
import PresenceLayer from './multiplayer/PresenceLayer';
import { moodEngine } from '../core/MoodEngine';
import './DashboardLayout.css';

export const DashboardLayout = ({ children }) => {
  const { coreMetrics = {} } = useAppStore();
  const [bootComplete, setBootComplete] = useState(false);
  const [coreState, setCoreState] = useState({
    rotationSpeed: 0.05,
    taskRate: 0.5,
    errorMix: 0.0,
    load: 0.5,
    thinking: 0.0,
  });

  // Boot sequence check (show once per session)
  useEffect(() => {
    const bootShown = localStorage.getItem('bootSequenceShown');
    if (!bootShown) {
      setBootComplete(false);
      localStorage.setItem('bootSequenceShown', 'true');
    } else {
      setBootComplete(true);
    }

    const handleBootComplete = () => {
      setBootComplete(true);
    };

    window.addEventListener('boot-complete', handleBootComplete);
    return () => window.removeEventListener('boot-complete', handleBootComplete);
  }, []);

  // Poll metrics to drive core visualization
  useEffect(() => {
    const pollMetrics = async () => {
      try {
        const res = await fetch('/api/metrics');
        const text = await res.text();

        // Parse Prometheus text format
        const lines = text.split('\n');
        const metrics = {};

        lines.forEach((line) => {
          if (line.startsWith('#')) return;
          const [key, value] = line.split(' ');
          if (key && value) {
            metrics[key] = parseFloat(value);
          }
        });

        // Map to core state
        const apiCallRate = (metrics['ai_employee_api_calls_total'] || 0) / 100;
        const errorRate = (metrics['ai_employee_errors_total'] || 0) / 5;
        const taskRate = (metrics['ai_employee_tasks_completed'] || 0) / 100;
        const cpuUsage = (metrics['process_cpu_percent'] || 0);
        const agentCount = (metrics['ai_employee_agents_active'] || 0);

        const newState = {
          rotationSpeed: Math.min(apiCallRate, 2.0),
          taskRate: Math.min(taskRate, 1.0),
          errorMix: Math.min(errorRate, 0.8),
          load: taskRate,
          thinking: 0.0, // Updated via WS 'core:thinking' event
        };

        setCoreState(newState);

        // Update mood engine
        moodEngine.updateMetrics({
          taskRate: newState.taskRate,
          errorRate: newState.errorMix,
          cpuUsage,
          agentCount,
        });
      } catch (err) {
        console.error('Failed to poll metrics:', err);
      }
    };

    if (bootComplete) {
      pollMetrics();
      const interval = setInterval(pollMetrics, 3000);
      return () => clearInterval(interval);
    }
  }, [bootComplete]);

  // Record user activity for mood engine
  useEffect(() => {
    const recordActivity = () => {
      moodEngine.recordActivity();
    };

    window.addEventListener('mousemove', recordActivity);
    window.addEventListener('keypress', recordActivity);

    return () => {
      window.removeEventListener('mousemove', recordActivity);
      window.removeEventListener('keypress', recordActivity);
    };
  }, []);

  if (!bootComplete) {
    return <AwakeningScene />;
  }

  return (
    <div className='dashboard-layout'>
      {/* Multiplayer presence layer (live cursors, avatars, focus rings) */}
      <PresenceLayer />

      {/* Command dock */}
      <CommandDock />

      {/* Top HUD strip */}
      <TopStrip />

      {/* Neural core canvas — center stage */}
      <div className='core-container'>
        <Suspense fallback={<div className='core-loading'>Initializing Neural Core...</div>}>
          <NeuralCore metrics={coreState} />
        </Suspense>
      </div>

      {/* Main content area (panels rendered by page components) */}
      <div className='pages-container'>{children}</div>
    </div>
  );
};

export default DashboardLayout;
