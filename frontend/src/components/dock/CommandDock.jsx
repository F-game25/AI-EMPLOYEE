import React, { useState } from 'react';
import { useAppStore } from '../../store/appStore';
import './CommandDock.css';

const dockItems = [
  { id: 'dashboard', icon: '◎', label: 'Mission Control' },
  { id: 'agents', icon: '⬢', label: 'The Swarm' },
  { id: 'neural-brain', icon: '◉', label: 'The Mind' },
  { id: 'money-mode', icon: '◆', label: 'Revenue Forge' },
  { id: 'history', icon: '⟲', label: 'Chronicle' },
  { id: 'ai-control', icon: '⚙', label: 'AI Control' },
  { id: 'hermes', icon: '✉', label: 'Hermes' },
  { id: 'operations', icon: '▦', label: 'Operations' },
  { id: 'evolution', icon: '⟳', label: 'Evolution' },
  { id: 'voice', icon: '◐', label: 'Voice' },
  { id: 'workspace', icon: '⌗', label: 'Workspace' },
  { id: 'learning-ladder', icon: '⬆', label: 'Learning' },
  { id: 'training', icon: '⬜', label: 'Training' },
  { id: 'ascend-forge', icon: '⬢', label: 'Ascend Forge' },
  { id: 'blacklight', icon: '⚡', label: 'Blacklight' },
  { id: 'fairness', icon: '◈', label: 'Fairness' },
  { id: 'doctor', icon: '✚', label: 'Doctor' },
  { id: 'control-center', icon: '⊞', label: 'Control Center' },
  { id: 'prompt-inspector', icon: '◁', label: 'Prompt Inspector' },
  { id: 'system', icon: '⊕', label: 'System' },
];

export const CommandDock = () => {
  const { activeSection, setActiveSection, wsConnected } = useAppStore();
  const [hoveredId, setHoveredId] = useState(null);

  return (
    <div className='command-dock'>
      {/* Operator sigil */}
      <div className='dock-sigil'>
        <div className='sigil-icon'>AI</div>
        <div className='sigil-pulse' />
      </div>

      {/* Nav divider */}
      <div className='dock-divider' />

      {/* Nav items */}
      <div className='dock-nav'>
        {dockItems.map((item) => (
          <button
            key={item.id}
            className={`dock-item ${activeSection === item.id ? 'active' : ''}`}
            onClick={() => setActiveSection(item.id)}
            onMouseEnter={() => setHoveredId(item.id)}
            onMouseLeave={() => setHoveredId(null)}
            title={item.label}
          >
            <span className='item-icon'>{item.icon}</span>
            {hoveredId === item.id && (
              <div className='item-tooltip'>{item.label}</div>
            )}
            {activeSection === item.id && (
              <div className='item-active-bar' />
            )}
          </button>
        ))}
      </div>

      {/* Footer status */}
      <div className='dock-footer'>
        <div className={`status-dot ${wsConnected ? 'connected' : 'offline'}`} />
        <div className='status-label'>
          {wsConnected ? 'ONLINE' : 'OFFLINE'}
        </div>
      </div>
    </div>
  );
};

export default CommandDock;
