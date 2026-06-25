'use strict';

/**
 * WebSocket Authentication Middleware
 * Extracts and verifies JWT token from query parameters
 */

const jwt = require('jsonwebtoken');

/**
 * Authenticate WebSocket upgrade request
 * Extracts JWT from query param: ws://localhost:8787/ws/tasks?token=xxx
 * @param {http.IncomingMessage} req - Upgrade request
 * @param {string} jwtSecret - JWT secret key
 * @returns {object|null} Token payload if valid, null otherwise
 */
function authenticateWebSocketUpgrade(req, jwtSecret) {
  try {
    const url = new URL(req.url || '', 'http://localhost');
    const token = url.searchParams.get('token');

    if (!token) {
      return null;
    }

    const payload = jwt.verify(token, jwtSecret, { algorithms: ['HS256'] });
    return payload;
  } catch (err) {
    return null;
  }
}

/**
 * Attach tenantId to socket after successful auth
 * @param {WebSocket} socket - WebSocket instance
 * @param {object} payload - JWT payload
 */
function attachTenantContext(socket, payload) {
  socket.tenantId = payload.tenant_id || payload.tenantId;
  socket.userId = payload.sub || payload.userId;
  socket.email = payload.email;
  socket.authenticated = true;
}

module.exports = {
  authenticateWebSocketUpgrade,
  attachTenantContext,
};
