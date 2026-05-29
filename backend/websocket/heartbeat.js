'use strict';

/**
 * WebSocket Heartbeat Manager
 * Maintains keep-alive pings with exponential backoff on unresponsive clients
 */

const WebSocket = require('ws');

const HEARTBEAT_INTERVAL_MS = 30000; // 30 seconds
const PING_TIMEOUT_MS = 5000; // 5s to respond
const MAX_MISSED_PONGS = 2;

class HeartbeatManager {
  constructor() {
    this.interval = null;
    this.socketTimers = new WeakMap();
  }

  /**
   * Start heartbeat manager
   * @param {WebSocket.Server} wss - WebSocket server
   * @param {ConnectionManager} connManager - Connection manager for cleanup
   */
  start(wss, connManager) {
    if (this.interval) return;

    this.interval = setInterval(() => {
      if (!wss || !wss.clients) return;
      const now = Date.now();

      wss.clients.forEach(socket => {
        if (socket.readyState !== WebSocket.OPEN) return;

        // Initialize or check pong tracking
        if (!socket.isAlive) socket.isAlive = true;
        if (socket.missedPongs === undefined) socket.missedPongs = 0;

        if (socket.isAlive === false) {
          socket.missedPongs += 1;
          if (socket.missedPongs >= MAX_MISSED_PONGS) {
            // Client unresponsive — close connection and cleanup
            connManager.unsubscribeAll(socket);
            socket.close(1000, 'Heartbeat timeout');
            return;
          }
        } else {
          socket.isAlive = false;
          socket.missedPongs = 0;
        }

        // Send ping
        socket.ping();
      });
    }, HEARTBEAT_INTERVAL_MS);
  }

  /**
   * Stop heartbeat manager
   */
  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }

  /**
   * Mark socket as alive (called on pong)
   * @param {WebSocket} socket
   */
  markAlive(socket) {
    socket.isAlive = true;
    socket.missedPongs = 0;
  }
}

module.exports = HeartbeatManager;
