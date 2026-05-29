'use strict';

/**
 * WebSocket Upgrade Handlers
 * Routes upgrade requests to appropriate channels
 */

const { WebSocketServer } = require('ws');
const { CHANNELS, createMessage } = require('./channels');
const { authenticateWebSocketUpgrade, attachTenantContext } = require('../middleware/ws-auth');

/**
 * Create upgrade request handler for specific channels
 * @param {ConnectionManager} connManager - Connection manager
 * @param {string} jwtSecret - JWT secret for auth
 * @returns {Function} Handler function for server.on('upgrade')
 */
function createUpgradeHandler(connManager, jwtSecret) {
  return (req, socket, head) => {
    try {
      const url = new URL(req.url || '/', 'http://localhost');
      const pathname = url.pathname;

      // Route-based channel handlers
      if (pathname.startsWith('/ws/tasks')) {
        handleChannelUpgrade(req, socket, head, CHANNELS.TASKS_UPDATED, connManager, jwtSecret);
      } else if (pathname.startsWith('/ws/agents')) {
        handleChannelUpgrade(req, socket, head, CHANNELS.AGENTS_STATUS, connManager, jwtSecret);
      } else if (pathname.startsWith('/ws/execution-trace')) {
        handleChannelUpgrade(req, socket, head, CHANNELS.EXECUTION_TRACE, connManager, jwtSecret);
      } else if (pathname.startsWith('/ws/logs')) {
        handleChannelUpgrade(req, socket, head, CHANNELS.LOGS_STREAM, connManager, jwtSecret);
      } else {
        socket.destroy();
      }
    } catch (err) {
      console.error('[WS] Upgrade error:', err.message);
      socket.destroy();
    }
  };
}

/**
 * Handle WebSocket upgrade for a specific channel
 */
function handleChannelUpgrade(req, socket, head, channel, connManager, jwtSecret) {
  const wss = new WebSocketServer({ noServer: true, maxPayload: 1024 * 1024 });

  wss.handleUpgrade(req, socket, head, (ws) => {
    // Authenticate connection
    const jwtPayload = authenticateWebSocketUpgrade(req, jwtSecret);
    if (!jwtPayload) {
      ws.close(4401, 'Unauthorized');
      return;
    }

    // Attach tenant context
    attachTenantContext(ws, jwtPayload);

    // Subscribe to channel
    connManager.subscribe(channel, ws, ws.tenantId, {
      channel,
      subscribedAt: Date.now(),
    });

    // Send subscription confirmation
    ws.send(JSON.stringify({
      type: 'subscription',
      channel,
      status: 'subscribed',
      tenantId: ws.tenantId,
      timestamp: Date.now(),
    }));

    // Cleanup on close
    ws.on('close', () => {
      connManager.unsubscribe(channel, ws);
    });
  });
}

module.exports = {
  createUpgradeHandler,
};
