'use strict';

// pm2 process supervisor config — install with: npm install -g pm2
// Usage:  pm2 start ecosystem.config.js
//         pm2 save && pm2 startup  (auto-restart on boot)
//         pm2 logs                 (tail all logs)
//         pm2 monit                (real-time dashboard)

const path = require('path');
const AI_HOME = process.env.AI_HOME || path.join(require('os').homedir(), '.ai-employee');

module.exports = {
  apps: [
    {
      name: 'ai-employee-node',
      script: path.join(__dirname, 'backend', 'server.js'),
      cwd: __dirname,
      env_file: path.join(AI_HOME, '.env'),
      env: {
        NODE_ENV: 'production',
        PORT: 8787,
        AI_HOME,
      },
      // Restart on crash, cap at 10 restarts in 60s to avoid restart loops
      max_restarts: 10,
      min_uptime: '10s',
      restart_delay: 2000,
      // Log rotation handled by pm2-logrotate; rotate at 50 MB
      error_file: path.join(AI_HOME, 'logs', 'node-error.log'),
      out_file: path.join(AI_HOME, 'logs', 'node-out.log'),
      merge_logs: true,
      time: true,
    },
    {
      name: 'ai-employee-python',
      script: 'uvicorn',
      interpreter: 'python3',
      args: 'runtime.agents.problem-solver-ui.server:app --host 127.0.0.1 --port 18790 --log-level info',
      cwd: __dirname,
      env_file: path.join(AI_HOME, '.env'),
      env: {
        PYTHONUNBUFFERED: '1',
        AI_HOME,
      },
      max_restarts: 10,
      min_uptime: '10s',
      restart_delay: 3000,
      error_file: path.join(AI_HOME, 'logs', 'python-error.log'),
      out_file: path.join(AI_HOME, 'logs', 'python-out.log'),
      merge_logs: true,
      time: true,
    },
  ],
};
