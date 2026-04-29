import React, { Suspense, useEffect, useState } from 'react';
import { useAppStore } from '../store/appStore';
import CommandDock from './dock/CommandDock';
import TopStrip from './hud/TopStrip';
import NeuralCore from './three/NeuralCore';
import './DashboardLayout.css';

export const DashboardLayout = ({ children }) => {
  const { coreMetrics = {} } = useAppStore();
  const [coreState, setCoreState] = useState({
    rotationSpeed: 0.05,
    taskRate: 0.5,
    errorMix: 0.0,
    load: 0.5,
    thinking: 0.0,
  });

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

        setCoreState({
          rotationSpeed: Math.min(apiCallRate, 2.0),
          taskRate: Math.min(taskRate, 1.0),
          errorMix: Math.min(errorRate, 0.8),
          load: taskRate,
          thinking: 0.0, // Updated via WS 'core:thinking' event
        });
      } catch (err) {
        console.error('Failed to poll metrics:', err);
      }
    };

    pollMetrics();
    const interval = setInterval(pollMetrics, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className='dashboard-layout'>
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
