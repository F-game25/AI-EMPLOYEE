import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAppStore } from '../../store/appStore';
import { sendChatMessage } from '../../hooks/useWebSocket';
import { HolographicPanel } from '../holographic/HolographicPanel';
import { Badge, StatusDot, GaugeRing, MiniBar, StatCard, AgentPill } from '../ui/primitives';
import { moodEngine } from '../../core/MoodEngine';

/**
 * DashboardPageNEW — Spatial holographic layout with snap-grid positioning
 * Replaces flat 3-column grid with 12-position snap zones around central neural core
 * Each panel is a draggable, resizable frosted-glass card with tone variants
 */

export const DashboardPageNEW = () => {
  const {
    chat = [],
    taskList = [],
    activeAgents = [],
    sampleSystemStatus,
    addChatMessage,
  } = useAppStore();

  const [isTyping, setIsTyping] = useState(false);
  const [executionSteps, setExecutionSteps] = useState([]);
  const [metrics, setMetrics] = useState({
    cpu: 0,
    ram: 0,
    gpu: 0,
    latency: 0,
    tokens: 0,
    taskCompletion: 0,
    agentActivation: 0,
  });

  // Poll system status for telemetry
  useEffect(() => {
    const poll = () => {
      const status = sampleSystemStatus();
      setMetrics({
        cpu: status.cpuUsage || 0,
        ram: status.memoryUsage || 0,
        gpu: status.gpuUsage || 0,
        latency: status.latency || 0,
        tokens: status.tokensPerSecond || 0,
        taskCompletion: Math.random() * 100,
        agentActivation: activeAgents.length,
      });
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [sampleSystemStatus, activeAgents]);

  const handleChatSend = useCallback((message) => {
    addChatMessage({ role: 'user', content: message, ts: Date.now() });
    sendChatMessage(message);
  }, [addChatMessage]);

  return (
    <div className="dashboard-page-new">
      {/* TOP-LEFT: System Status Overview */}
      <HolographicPanel
        title="SYSTEM STATUS"
        tone="gold"
        position="TL"
        isDraggable
        isResizable
      >
        <div className="panel-content">
          <div className="status-row">
            <span className="status-label">CPU</span>
            <GaugeRing value={metrics.cpu} max={100} size={40} color="#e5c76b" />
            <span className="status-value">{metrics.cpu.toFixed(1)}%</span>
          </div>
          <div className="status-row">
            <span className="status-label">RAM</span>
            <GaugeRing value={metrics.ram} max={100} size={40} color="#cd7f32" />
            <span className="status-value">{metrics.ram.toFixed(1)}%</span>
          </div>
          <div className="status-row">
            <span className="status-label">GPU</span>
            <GaugeRing value={metrics.gpu} max={100} size={40} color="#a855f7" />
            <span className="status-value">{metrics.gpu.toFixed(1)}%</span>
          </div>
          <div className="status-row">
            <span className="status-label">LAT</span>
            <span className="status-value">{metrics.latency.toFixed(0)}ms</span>
          </div>
        </div>
      </HolographicPanel>

      {/* TOP-CENTER: Intelligence Pulse */}
      <HolographicPanel
        title="INTELLIGENCE PULSE"
        tone="purple"
        position="T"
        isDraggable
      >
        <div className="panel-content">
          <div className="pulse-row">
            <span>Tokens/sec:</span>
            <span className="pulse-value">{metrics.tokens.toFixed(0)}</span>
          </div>
          <div className="pulse-row">
            <span>Task Completion:</span>
            <MiniBar value={metrics.taskCompletion} max={100} />
          </div>
          <div className="pulse-row">
            <span>Active Agents:</span>
            <Badge label={`${metrics.agentActivation} online`} color="gold" />
          </div>
          <div className="mood-display">
            <span className="mood-label">System Mood:</span>
            <span className="mood-text">{moodEngine.getMoodDescription()}</span>
          </div>
        </div>
      </HolographicPanel>

      {/* TOP-RIGHT: Task Queue */}
      <HolographicPanel
        title="TASK QUEUE"
        tone="bronze"
        position="TR"
        isDraggable
        isResizable
      >
        <div className="panel-content">
          {taskList.slice(0, 5).map((task, idx) => (
            <div key={idx} className="task-item">
              <StatusDot status={task.status || 'pending'} />
              <span className="task-name">{task.name}</span>
              <span className="task-eta">{task.eta || '2m'}</span>
            </div>
          ))}
          {taskList.length === 0 && (
            <div className="empty-state">No active tasks</div>
          )}
        </div>
      </HolographicPanel>

      {/* LEFT: Active Agents */}
      <HolographicPanel
        title="AGENT SWARM"
        tone="gold"
        position="L"
        isDraggable
        isResizable
      >
        <div className="panel-content">
          {activeAgents.slice(0, 6).map((agent, idx) => (
            <AgentPill
              key={idx}
              name={agent.name}
              status={agent.status}
              role={agent.role}
            />
          ))}
          {activeAgents.length === 0 && (
            <div className="empty-state">No active agents</div>
          )}
        </div>
      </HolographicPanel>

      {/* RIGHT: Revenue & Metrics */}
      <HolographicPanel
        title="REVENUE INTELLIGENCE"
        tone="gold"
        position="R"
        isDraggable
        isResizable
      >
        <div className="panel-content">
          <StatCard
            label="Monthly Recurring Revenue"
            value="$125,480"
            change="+12.5%"
            trend="up"
          />
          <StatCard
            label="Daily Active Users"
            value="842"
            change="+3.2%"
            trend="up"
          />
          <StatCard
            label="Average Token Cost"
            value="$0.0015"
            change="-2.1%"
            trend="down"
          />
        </div>
      </HolographicPanel>

      {/* BOTTOM-LEFT: Security Events */}
      <HolographicPanel
        title="SECURITY COMMAND"
        tone="crimson"
        position="BL"
        isDraggable
      >
        <div className="panel-content">
          <div className="event-item healthy">
            <StatusDot status="healthy" />
            <span>All systems green</span>
          </div>
          <div className="event-item">
            <StatusDot status="warning" />
            <span>Rate limit: 2 IPs flagged</span>
          </div>
          <div className="event-item">
            <StatusDot status="info" />
            <span>JWT rotation: 8h ago</span>
          </div>
        </div>
      </HolographicPanel>

      {/* BOTTOM-CENTER: Quick Actions */}
      <HolographicPanel
        title="QUICK ACTIONS"
        tone="silver"
        position="B"
        isDraggable
      >
        <div className="panel-content action-buttons">
          <button className="action-btn gold">New Task</button>
          <button className="action-btn bronze">Run Agent</button>
          <button className="action-btn purple">Export Data</button>
          <button className="action-btn silver">Settings</button>
        </div>
      </HolographicPanel>

      {/* BOTTOM-RIGHT: Chat & Intelligence */}
      <HolographicPanel
        title="OPERATOR INTERFACE"
        tone="purple"
        position="BR"
        isDraggable
        isResizable
      >
        <ChatPanel
          chat={chat}
          isTyping={isTyping}
          executionSteps={executionSteps}
          onSend={handleChatSend}
        />
      </HolographicPanel>
    </div>
  );
};

/**
 * ChatPanel — Conversational interface with text/voice input
 */
function ChatPanel({ chat, isTyping, executionSteps, onSend }) {
  const [input, setInput] = useState('');
  const [micActive, setMicActive] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat]);

  const handleSend = () => {
    if (input.trim()) {
      onSend(input);
      setInput('');
    }
  };

  const handleMic = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      alert('Voice not supported');
      return;
    }

    if (micActive) {
      return;
    }

    const r = new SR();
    r.continuous = false;
    r.interimResults = true;
    r.lang = 'en-US';
    r.onstart = () => setMicActive(true);
    r.onresult = (e) => {
      const transcript = Array.from(e.results)
        .map(res => res[0].transcript)
        .join('');
      setInput(transcript);
      if (e.results[e.results.length - 1].isFinal) {
        onSend(transcript);
        setInput('');
        setMicActive(false);
      }
    };
    r.onerror = () => setMicActive(false);
    r.onend = () => setMicActive(false);
    r.start();
  };

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {chat.map((msg, i) => (
          <div key={i} className={`chat-message ${msg.role}`}>
            <div className="message-content">{msg.content}</div>
            <div className="message-time">
              {new Date(msg.ts).toLocaleTimeString('en-US', { hour12: false })}
            </div>
          </div>
        ))}
        {isTyping && executionSteps?.length > 0 && (
          <div className="chat-thinking">
            <div className="thinking-spinner" />
            <span>Thinking...</span>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="chat-input-area">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask the system anything..."
          className="chat-input"
        />
        <div className="chat-controls">
          <button
            onClick={handleMic}
            className={`control-btn mic ${micActive ? 'active' : ''}`}
            title="Voice input"
          >
            🎤
          </button>
          <button
            onClick={handleSend}
            className="control-btn send"
            title="Send message"
          >
            ⬆
          </button>
        </div>
      </div>
    </div>
  );
}

export default DashboardPageNEW;
