import React, { useState, useEffect } from 'react';
import { useAppStore } from '../../store/appStore';
import './TopStrip.css';

export const TopStrip = () => {
  const {
    activeSection,
    sampleSystemStatus,
  } = useAppStore();
  const [time, setTime] = useState(new Date());
  const [metrics, setMetrics] = useState({
    cpu: 0,
    ram: 0,
    gpu: 0,
    latency: 0,
    tokens: 0,
  });

  // Update clock
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Poll metrics
  useEffect(() => {
    const pollMetrics = async () => {
      try {
        const status = sampleSystemStatus();
        setMetrics({
          cpu: status.cpuUsage || 0,
          ram: status.memoryUsage || 0,
          gpu: status.gpuUsage || 0,
          latency: status.latency || 0,
          tokens: status.tokensPerSecond || 0,
        });
      } catch (err) {
        console.error('Failed to poll metrics:', err);
      }
    };

    pollMetrics();
    const interval = setInterval(pollMetrics, 8000);
    return () => clearInterval(interval);
  }, [sampleSystemStatus]);

  const sectionLabel = {
    dashboard: 'MISSION CONTROL',
    agents: 'THE SWARM',
    'neural-brain': 'THE MIND',
    'money-mode': 'REVENUE FORGE',
    history: 'CHRONICLE',
    'ai-control': 'AI CONTROL',
    hermes: 'HERMES',
    operations: 'OPERATIONS',
    evolution: 'EVOLUTION',
    voice: 'VOICE',
    workspace: 'WORKSPACE',
    'learning-ladder': 'LEARNING',
    training: 'TRAINING',
    'ascend-forge': 'ASCEND FORGE',
    blacklight: 'BLACKLIGHT',
    fairness: 'FAIRNESS',
    doctor: 'DOCTOR',
    'control-center': 'CONTROL CENTER',
    'prompt-inspector': 'PROMPT INSPECTOR',
    system: 'SYSTEM',
  };

  const hours = time.getUTCHours().toString().padStart(2, '0');
  const mins = time.getUTCMinutes().toString().padStart(2, '0');
  const secs = time.getUTCSeconds().toString().padStart(2, '0');

  return (
    <div className='top-strip'>
      {/* Left: Breadcrumb */}
      <div className='strip-breadcrumb'>
        NEXUS · {sectionLabel[activeSection] || 'UNKNOWN'}
      </div>

      {/* Center: Spacer */}
      <div className='strip-spacer' />

      {/* Right: Telemetry meters */}
      <div className='strip-telemetry'>
        <div className='telemetry-meter'>
          <span className='meter-label'>CPU</span>
          <span className='meter-value'>{metrics.cpu.toFixed(1)}%</span>
        </div>
        <div className='telemetry-meter'>
          <span className='meter-label'>RAM</span>
          <span className='meter-value'>{metrics.ram.toFixed(1)}%</span>
        </div>
        <div className='telemetry-meter'>
          <span className='meter-label'>GPU</span>
          <span className='meter-value'>{metrics.gpu.toFixed(1)}%</span>
        </div>
        <div className='telemetry-meter'>
          <span className='meter-label'>LAT</span>
          <span className='meter-value'>{metrics.latency.toFixed(0)}ms</span>
        </div>
        <div className='telemetry-meter'>
          <span className='meter-label'>TOK</span>
          <span className='meter-value'>{metrics.tokens.toFixed(0)}/s</span>
        </div>
      </div>

      {/* Right: Clock */}
      <div className='strip-clock'>
        <div className='clock-time'>
          {hours}:{mins}:{secs}
        </div>
        <div className='clock-date'>UTC</div>
      </div>

      {/* Operator avatar placeholder */}
      <div className='strip-avatar'>
        <div className='avatar-circle'>OP</div>
        <div className='avatar-status' />
      </div>
    </div>
  );
};

export default TopStrip;
