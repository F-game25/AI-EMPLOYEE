'use strict';

/**
 * WebSocket Connection Manager
 * Manages subscriptions per channel with tenant isolation
 */

const WebSocket = require('ws');

class ConnectionManager {
  constructor() {
    // Map: channelId => Map<socket, metadata>
    this.channels = new Map();
    // Map: socket => Set<channelId>
    this.socketChannels = new Map();
  }

  /**
   * Subscribe socket to channel
   * @param {string} channelId - Channel identifier
   * @param {WebSocket} socket - WebSocket instance
   * @param {string} tenantId - Tenant ID for isolation
   * @param {object} metadata - Optional subscription metadata
   */
  subscribe(channelId, socket, tenantId, metadata = {}) {
    if (!this.channels.has(channelId)) {
      this.channels.set(channelId, new Map());
    }
    const subs = this.channels.get(channelId);
    subs.set(socket, { tenantId, ...metadata, subscribedAt: Date.now() });

    if (!this.socketChannels.has(socket)) {
      this.socketChannels.set(socket, new Set());
    }
    this.socketChannels.get(socket).add(channelId);
  }

  /**
   * Unsubscribe socket from channel
   * @param {string} channelId - Channel identifier
   * @param {WebSocket} socket - WebSocket instance
   */
  unsubscribe(channelId, socket) {
    const subs = this.channels.get(channelId);
    if (!subs) return;
    subs.delete(socket);
    if (subs.size === 0) this.channels.delete(channelId);

    const channels = this.socketChannels.get(socket);
    if (channels) {
      channels.delete(channelId);
      if (channels.size === 0) this.socketChannels.delete(socket);
    }
  }

  /**
   * Unsubscribe socket from all channels
   * @param {WebSocket} socket - WebSocket instance
   */
  unsubscribeAll(socket) {
    const channels = this.socketChannels.get(socket);
    if (!channels) return;
    channels.forEach(ch => this.unsubscribe(ch, socket));
    this.socketChannels.delete(socket);
  }

  /**
   * Broadcast message to all subscribed sockets on channel
   * @param {string} channelId - Channel identifier
   * @param {object} message - Message to send (will be JSON.stringify'd)
   */
  broadcast(channelId, message) {
    const subs = this.channels.get(channelId);
    if (!subs) return;
    const payload = JSON.stringify({ ...message, channel: channelId });
    subs.forEach((meta, socket) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(payload);
      }
    });
  }

  /**
   * Broadcast message to all subscribed sockets on channel, filtered by tenantId
   * @param {string} tenantId - Tenant ID
   * @param {string} channelId - Channel identifier
   * @param {object} message - Message to send
   */
  broadcastToTenant(tenantId, channelId, message) {
    const subs = this.channels.get(channelId);
    if (!subs) return;
    const payload = JSON.stringify({ ...message, channel: channelId, tenantId });
    subs.forEach((meta, socket) => {
      if (meta.tenantId === tenantId && socket.readyState === WebSocket.OPEN) {
        socket.send(payload);
      }
    });
  }

  /**
   * Get subscription count for channel
   * @param {string} channelId - Channel identifier
   */
  getSubscriptionCount(channelId) {
    const subs = this.channels.get(channelId);
    return subs ? subs.size : 0;
  }

  /**
   * Get all channels socket is subscribed to
   * @param {WebSocket} socket - WebSocket instance
   */
  getSocketChannels(socket) {
    const channels = this.socketChannels.get(socket);
    return channels ? Array.from(channels) : [];
  }

  /**
   * Get stats for all channels
   */
  getStats() {
    const stats = {};
    this.channels.forEach((subs, ch) => {
      stats[ch] = { subscriptions: subs.size };
    });
    return stats;
  }
}

module.exports = ConnectionManager;
