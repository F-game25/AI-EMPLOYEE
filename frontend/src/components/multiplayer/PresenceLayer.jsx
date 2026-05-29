import React, { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../../store/appStore';
import { useWebSocketStore } from '../../store/webSocketStore';
import './PresenceLayer.css';

/**
 * PresenceLayer — Live cursors, avatars, focus rings for multiplayer awareness
 * Shows all connected operators in real-time with smooth cursor tracking
 */

export const PresenceLayer = () => {
  const userId = useAppStore(s => s.userId);
  const userName = useAppStore(s => s.userName);
  const wsConnected = useWebSocketStore(s => s.isConnected);
  const [remoteUsers, setRemoteUsers] = useState(new Map());
  const [localMousePos, setLocalMousePos] = useState({ x: 0, y: 0 });
  const [broadcastInterval, setBroadcastInterval] = useState(null);

  // Broadcast local cursor position every 100ms
  useEffect(() => {
    const handleMouseMove = (e) => {
      setLocalMousePos({ x: e.clientX, y: e.clientY });

      // Broadcast via WebSocket every 100ms
      if (broadcastInterval) clearInterval(broadcastInterval);
      setBroadcastInterval(
        setInterval(() => {
          if (wsConnected) {
            window.dispatchEvent(
              new CustomEvent('presence-update', {
                detail: {
                  userId,
                  userName,
                  x: e.clientX,
                  y: e.clientY,
                  timestamp: Date.now(),
                },
              })
            );
          }
        }, 100)
      );
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      if (broadcastInterval) clearInterval(broadcastInterval);
    };
  }, [userId, userName, wsConnected, broadcastInterval]);

  // Listen for remote user presence updates
  useEffect(() => {
    const handlePresenceUpdate = (e) => {
      const { userId: remoteId, userName: remoteName, x, y, timestamp } = e.detail;

      if (remoteId === userId) return; // Ignore self

      setRemoteUsers(prev => {
        const updated = new Map(prev);
        updated.set(remoteId, {
          id: remoteId,
          name: remoteName,
          x,
          y,
          timestamp,
          color: getColorForUser(remoteId),
        });
        return updated;
      });
    };

    window.addEventListener('presence-update', handlePresenceUpdate);

    // Prune stale users (no update for > 5s)
    const pruneInterval = setInterval(() => {
      setRemoteUsers(prev => {
        const updated = new Map(prev);
        const now = Date.now();
        for (const [id, user] of updated) {
          if (now - user.timestamp > 5000) {
            updated.delete(id);
          }
        }
        return updated;
      });
    }, 1000);

    return () => {
      window.removeEventListener('presence-update', handlePresenceUpdate);
      clearInterval(pruneInterval);
    };
  }, [userId]);

  return (
    <div className="presence-layer">
      {/* Local cursor (always shown) */}
      <LocalCursor x={localMousePos.x} y={localMousePos.y} name={userName} />

      {/* Remote cursors */}
      {Array.from(remoteUsers.values()).map(user => (
        <RemoteCursor
          key={user.id}
          user={user}
        />
      ))}

      {/* User count indicator */}
      {remoteUsers.size > 0 && (
        <div className="user-count-badge">
          {remoteUsers.size + 1} online
        </div>
      )}
    </div>
  );
};

/**
 * LocalCursor — Current user's cursor with glow and label
 */
const LocalCursor = ({ x, y, name }) => {
  return (
    <div className="cursor local-cursor" style={{ left: x, top: y }}>
      <div className="cursor-pointer" />
      <div className="cursor-glow" />
      <div className="cursor-label">{name || 'You'}</div>
    </div>
  );
};

/**
 * RemoteCursor — Remote user's cursor with avatar and trail
 */
const RemoteCursor = ({ user }) => {
  const cursorRef = useRef();
  const [trailPoints, setTrailPoints] = useState([]);

  useEffect(() => {
    // Smooth cursor movement with easing
    if (cursorRef.current) {
      cursorRef.current.style.left = user.x + 'px';
      cursorRef.current.style.top = user.y + 'px';
    }

    // Add trail point
    setTrailPoints(prev => {
      const updated = [...prev, { x: user.x, y: user.y, id: Date.now() }];
      // Keep only last 5 trail points
      return updated.slice(-5);
    });
  }, [user.x, user.y]);

  return (
    <div className="cursor remote-cursor" ref={cursorRef} style={{ color: user.color }}>
      {/* Trail */}
      <svg className="cursor-trail">
        {trailPoints.map((point, idx) => (
          <circle
            key={point.id}
            cx={point.x}
            cy={point.y}
            r={3 - (idx * 0.5)}
            fill={user.color}
            opacity={(idx + 1) / trailPoints.length * 0.3}
          />
        ))}
      </svg>

      {/* Cursor pointer */}
      <div className="cursor-pointer" style={{ borderColor: user.color }} />

      {/* User avatar */}
      <div className="cursor-avatar" style={{ backgroundColor: user.color }}>
        {user.name[0]?.toUpperCase() || '?'}
      </div>

      {/* User label */}
      <div className="cursor-label" style={{ color: user.color }}>
        {user.name}
      </div>
    </div>
  );
};

/**
 * FocusRing — Shows which panel/element a remote user is focused on
 */
export const FocusRing = ({ userId, elementId }) => {
  const [targetElement, setTargetElement] = useState(null);
  const [position, setPosition] = useState(null);

  useEffect(() => {
    const el = document.getElementById(elementId);
    if (!el) return;

    setTargetElement(el);

    // Update position on resize
    const updatePosition = () => {
      const rect = el.getBoundingClientRect();
      setPosition({
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      });
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);

    return () => window.removeEventListener('resize', updatePosition);
  }, [elementId]);

  if (!position) return null;

  return (
    <div
      className="focus-ring"
      style={{
        top: position.top,
        left: position.left,
        width: position.width,
        height: position.height,
      }}
    />
  );
};

/**
 * Utility: Generate consistent color for user ID
 */
function getColorForUser(userId) {
  const colors = [
    '#e5c76b', // gold
    '#a855f7', // purple
    '#cd7f32', // bronze
    '#00ff88', // green
    '#00d4ff', // cyan
    '#ff6b6b', // red
    '#ffd97a', // light gold
  ];

  const hash = userId.split('').reduce((acc, char) => {
    return ((acc << 5) - acc) + char.charCodeAt(0);
  }, 0);

  return colors[Math.abs(hash) % colors.length];
}

export default PresenceLayer;
