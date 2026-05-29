/**
 * Database client wrapper for Node.js
 * Calls Python FastAPI backend for database queries
 */

const http = require('http');
const PYTHON_BACKEND = `http://localhost:${process.env.PYTHON_BACKEND_PORT || 18790}`;

class DatabaseClient {
  async query(sql, params = [], tenantId = null) {
    return this._request('POST', '/api/db/query', { sql, params, tenant_id: tenantId });
  }

  async insert(table, data, tenantId = null) {
    return this._request('POST', '/api/db/insert', { table, data, tenant_id: tenantId });
  }

  async update(table, data, where, params = [], tenantId = null) {
    return this._request('POST', '/api/db/update', { table, data, where, params, tenant_id: tenantId });
  }

  async delete(table, where, params = [], tenantId = null) {
    return this._request('POST', '/api/db/delete', { table, where, params, tenant_id: tenantId });
  }

  async findById(table, id, tenantId = null) {
    return this._request('POST', '/api/db/query', {
      sql: `SELECT * FROM ${table} WHERE id = %s`,
      params: [id],
      tenant_id: tenantId
    });
  }

  async _request(method, path, body) {
    return new Promise((resolve, reject) => {
      const payload = JSON.stringify(body);
      const options = {
        hostname: 'localhost',
        port: process.env.PYTHON_BACKEND_PORT || 18790,
        path,
        method,
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(payload)
        },
        timeout: 10000
      };

      const req = http.request(options, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(new Error(`Invalid JSON response: ${data}`));
          }
        });
      });

      req.on('error', reject);
      req.on('timeout', () => {
        req.destroy();
        reject(new Error('Database request timeout'));
      });

      req.write(payload);
      req.end();
    });
  }
}

module.exports = new DatabaseClient();
