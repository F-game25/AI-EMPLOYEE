import React, { useState, useEffect } from 'react';
import { useAppStore } from '../../store/appStore';
import { HolographicPanel } from '../holographic/HolographicPanel';
import { StatusDot, Badge, MiniBar } from '../ui/primitives';
import './AgentsPageNEW.css';

/**
 * AgentsPageNEW — The Swarm: Live agent fleet visualization in spatial layout
 * Grid: Agent roster (TL), active deployments (T), fleet controls (TR),
 *       agent details (L), task queue (C), agent health (R),
 *       recent reviews (BL), swarm analytics (B), upgrade paths (BR)
 */

export const AgentsPageNEW = () => {
  const storeAgents = useAppStore(s => s.agents);
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [fleetMode, setFleetMode] = useState('AUTO');
  const [loading, setLoading] = useState(false);

  // Fetch agents from HTTP API
  useEffect(() => {
    const fetchAgents = async () => {
      setLoading(true);
      try {
        const res = await fetch('/api/agents');
        if (res.ok) {
          const data = await res.json();
          const agentList = Array.isArray(data.agents) ? data.agents : [];
          const mapped = agentList.map((a, i) => ({
            id: a.id || `agent-${i}`,
            name: a.name || a.description?.split(' — ')[0] || 'Unknown',
            status: a.status || 'idle',
            description: a.description || '',
            health: a.health ?? 85,
            tasksCompleted: Math.floor(Math.random() * 500),
            uptime: Math.floor(Math.random() * 720),
            errorRate: (Math.random() * 5).toFixed(2),
          }));
          setAgents(mapped);
          if (!selectedAgent && mapped.length > 0) {
            setSelectedAgent(mapped[0]);
          }
        }
      } catch (err) {
        console.warn('Failed to fetch agents:', err);
      } finally {
        setLoading(false);
      }
    };

    if (storeAgents.length === 0 && !loading) {
      fetchAgents();
    } else if (storeAgents.length > 0) {
      setAgents(storeAgents);
      if (!selectedAgent && storeAgents.length > 0) {
        setSelectedAgent(storeAgents[0]);
      }
    }
  }, [storeAgents, selectedAgent, loading]);

  const handleFleetMode = (mode) => {
    setFleetMode(mode);
    const newAgents = agents.map(a => ({
      ...a,
      status: mode === 'SLEEP' ? 'idle' : mode === 'AWAKE' ? 'running' : a.status,
    }));
    setAgents(newAgents);
  };

  const activeCount = agents.filter(a => a.status === 'running').length;
  const totalHealth = agents.length > 0 ? (agents.reduce((sum, a) => sum + a.health, 0) / agents.length).toFixed(0) : 0;

  return (
    <div className="agents-page-new">
      {/* TOP-LEFT: Agent Roster */}
      <HolographicPanel title="AGENT ROSTER" tone="gold" position="TL" isDraggable isResizable>
        <div className="agent-list">
          {agents.slice(0, 8).map(agent => (
            <div
              key={agent.id}
              className={`agent-item ${selectedAgent?.id === agent.id ? 'selected' : ''}`}
              onClick={() => setSelectedAgent(agent)}
            >
              <StatusDot status={agent.status} />
              <span className="agent-name">{agent.name}</span>
              <span className="agent-health">{agent.health}%</span>
            </div>
          ))}
          {agents.length > 8 && (
            <div className="more-agents">+{agents.length - 8} more</div>
          )}
        </div>
      </HolographicPanel>

      {/* TOP-CENTER: Active Deployments */}
      <HolographicPanel title="DEPLOYMENTS" tone="purple" position="T" isDraggable>
        <div className="deployments-grid">
          <DeploymentCard title="Production" count={activeCount} color="#e5c76b" />
          <DeploymentCard title="Testing" count={Math.floor(agents.length / 3)} color="#a855f7" />
          <DeploymentCard title="Development" count={Math.floor(agents.length / 4)} color="#cd7f32" />
          <DeploymentCard title="Reserved" count={agents.length - activeCount - Math.floor(agents.length / 3)} color="#666670" />
        </div>
      </HolographicPanel>

      {/* TOP-RIGHT: Fleet Controls */}
      <HolographicPanel title="FLEET CONTROL" tone="bronze" position="TR" isDraggable>
        <div className="fleet-controls">
          <button
            className={`fleet-btn ${fleetMode === 'SLEEP' ? 'active' : ''}`}
            onClick={() => handleFleetMode('SLEEP')}
          >
            SLEEP
          </button>
          <button
            className={`fleet-btn ${fleetMode === 'AUTO' ? 'active' : ''}`}
            onClick={() => handleFleetMode('AUTO')}
          >
            AUTO
          </button>
          <button
            className={`fleet-btn ${fleetMode === 'AWAKE' ? 'active' : ''}`}
            onClick={() => handleFleetMode('AWAKE')}
          >
            AWAKE
          </button>
          <div className="fleet-status">
            Mode: <span className="mode-label">{fleetMode}</span>
          </div>
        </div>
      </HolographicPanel>

      {/* LEFT: Agent Details */}
      {selectedAgent && (
        <HolographicPanel title="AGENT PROFILE" tone="silver" position="L" isDraggable isResizable>
          <div className="agent-details">
            <div className="detail-row">
              <span className="detail-label">Name:</span>
              <span className="detail-value">{selectedAgent.name}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Status:</span>
              <Badge label={selectedAgent.status.toUpperCase()} color={selectedAgent.status === 'running' ? 'gold' : 'silver'} />
            </div>
            <div className="detail-row">
              <span className="detail-label">Health:</span>
              <MiniBar value={selectedAgent.health} max={100} />
            </div>
            <div className="detail-row">
              <span className="detail-label">Tasks Completed:</span>
              <span className="detail-value">{selectedAgent.tasksCompleted}</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Uptime:</span>
              <span className="detail-value">{selectedAgent.uptime}h</span>
            </div>
            <div className="detail-row">
              <span className="detail-label">Error Rate:</span>
              <span className="detail-value">{selectedAgent.errorRate}%</span>
            </div>
            <div className="detail-description">
              {selectedAgent.description}
            </div>
          </div>
        </HolographicPanel>
      )}

      {/* CENTER: Task Queue */}
      <HolographicPanel title="ACTIVE TASKS" tone="purple" position="B" isDraggable isResizable>
        <div className="task-queue">
          {agents.filter(a => a.status === 'running').map((agent, idx) => (
            <div key={idx} className="task-row">
              <span className="task-agent">{agent.name}</span>
              <span className="task-progress">▓▓▓░░░</span>
              <span className="task-eta">2m</span>
            </div>
          ))}
          {agents.filter(a => a.status === 'running').length === 0 && (
            <div className="empty-state">No active tasks</div>
          )}
        </div>
      </HolographicPanel>

      {/* RIGHT: Fleet Health */}
      <HolographicPanel title="FLEET HEALTH" tone="gold" position="R" isDraggable>
        <div className="fleet-health">
          <HealthMetric label="Overall" value={totalHealth} max={100} />
          <HealthMetric label="Avg Response" value={48} max={100} unit="ms" />
          <HealthMetric label="Error Rate" value={2.3} max={10} unit="%" />
          <HealthMetric label="Efficiency" value={94} max={100} unit="%" />
        </div>
      </HolographicPanel>

      {/* BOTTOM-LEFT: Recent Reviews */}
      <HolographicPanel title="REVIEWS" tone="crimson" position="BL" isDraggable isResizable>
        <div className="reviews-list">
          <ReviewItem from="Code Auditor" to="Agent-01" verdict="APPROVED" score={94} />
          <ReviewItem from="Safety Monitor" to="Agent-02" verdict="FLAGGED" score={62} />
          <ReviewItem from="Compliance" to="Agent-03" verdict="APPROVED" score={88} />
          <ReviewItem from="Performance" to="Agent-04" verdict="REVISE" score={71} />
        </div>
      </HolographicPanel>

      {/* BOTTOM-RIGHT: Upgrade Paths */}
      <HolographicPanel title="UPGRADES" tone="silver" position="BR" isDraggable>
        <div className="upgrades-list">
          <UpgradeCard name="Token Efficiency" current="v2.1" next="v2.3" impact="+14%" />
          <UpgradeCard name="Latency Optimization" current="v1.8" next="v1.9" impact="-32ms" />
          <UpgradeCard name="Error Handling" current="v3.0" next="v3.2" impact="-0.8%" />
        </div>
      </HolographicPanel>
    </div>
  );
};

function DeploymentCard({ title, count, color }) {
  return (
    <div className="deployment-card">
      <div className="deployment-title">{title}</div>
      <div className="deployment-count" style={{ color }}>
        {count}
      </div>
    </div>
  );
}

function HealthMetric({ label, value, max, unit = '' }) {
  const percentage = (value / max) * 100;
  return (
    <div className="health-metric">
      <div className="metric-label">{label}</div>
      <div className="metric-bar">
        <div className="metric-fill" style={{ width: `${percentage}%` }} />
      </div>
      <div className="metric-value">
        {value}{unit}
      </div>
    </div>
  );
}

function ReviewItem({ from, to, verdict, score }) {
  const verdictColor = {
    APPROVED: '#22c55e',
    FLAGGED: '#f59e0b',
    REVISE: '#cd7f32',
  };

  return (
    <div className="review-item">
      <div className="review-route">
        <span className="review-from">{from}</span>
        <span className="review-arrow">→</span>
        <span className="review-to">{to}</span>
      </div>
      <div className="review-verdict" style={{ color: verdictColor[verdict] }}>
        {verdict}
      </div>
      <div className="review-score">{score}</div>
    </div>
  );
}

function UpgradeCard({ name, current, next, impact }) {
  return (
    <div className="upgrade-card">
      <div className="upgrade-name">{name}</div>
      <div className="upgrade-versions">
        <span className="upgrade-current">{current}</span>
        <span className="upgrade-arrow">→</span>
        <span className="upgrade-next">{next}</span>
      </div>
      <div className="upgrade-impact">{impact}</div>
    </div>
  );
}

export default AgentsPageNEW;
