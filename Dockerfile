# Multi-stage build: Python AI backend + Node.js server in a single image
# Stage 1 — Python deps
FROM python:3.11-slim AS py-deps
WORKDIR /app
COPY runtime/agents/problem-solver-ui/requirements.txt ./py-requirements.txt
RUN pip install --no-cache-dir -r py-requirements.txt

# Stage 2 — Node deps
FROM node:20-slim AS node-deps
WORKDIR /app/backend
COPY backend/package*.json ./
RUN npm ci --omit=dev

# Stage 3 — Frontend build
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 4 — Final runtime image
FROM python:3.11-slim
WORKDIR /app

# System packages needed by better-sqlite3 (pre-built binary shipped in node_modules)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

# Python packages
COPY --from=py-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=py-deps /usr/local/bin /usr/local/bin

# Node packages
COPY --from=node-deps /app/backend/node_modules ./backend/node_modules

# Built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Application source
COPY backend/ ./backend/
COPY runtime/ ./runtime/
COPY ecosystem.config.js ./

# State directory (mounted as volume in production)
RUN mkdir -p /app/state /app/logs

ENV NODE_ENV=production \
    PORT=8787 \
    PYTHON_BACKEND_PORT=18790 \
    AI_HOME=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8787 18790

# Startup: launch Python AI backend in background, then Node server in foreground
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh
CMD ["./docker-entrypoint.sh"]
