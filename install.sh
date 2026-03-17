#!/bin/bash
set -euo pipefail

R='\033[0;31m';G='\033[0;32m';Y='\033[1;33m';C='\033[0;36m';NC='\033[0m'
AI_HOME="$HOME/.ai-employee"

log() { echo -e "${C}▸${NC} $1"; }
ok() { echo -e "${G}✓${NC} $1"; }

input() {
    log "Configuration"
    read -p "WhatsApp (+31624323731): " PHONE
    read -sp "Anthropic API key (optional): " ANTHROPIC_KEY; echo
    read -p "Trading bot path (optional): " BOT_PATH
    TOKEN=$(openssl rand -hex 32)
    ok "Config saved"
}

setup() {
    log "Installing OpenClaw..."
    if ! command -v openclaw &>/dev/null; then
        curl -fsSL https://openclaw.ai/install.sh | bash
        export PATH="$HOME/.local/bin:$PATH"
    fi
    ok "OpenClaw ready"
    
    log "Creating structure..."
    mkdir -p "$AI_HOME"/{workspace,credentials,downloads,logs,ui,backups}
    for a in orchestrator lead-hunter content-master social-guru intel-agent product-scout email-ninja support-bot data-analyst creative-studio crypto-trader bot-dev web-sales; do
        mkdir -p "$AI_HOME/workspace-$a/skills"
    done
    ok "Structure created"
}

install_skills() {
    log "Installing skills..."
    for skill in \
        "lead-hunter:linkedin_scraper" \
        "content-master:blog_writer" \
        "social-guru:viral_finder" \
        "intel-agent:pricing_tracker" \
        "product-scout:arbitrage_finder" \
        "email-ninja:sequence_builder" \
        "support-bot:faq_trainer" \
        "data-analyst:trend_analyzer" \
        "creative-studio:design_brief" \
        "crypto-trader:technical_analysis" \
        "bot-dev:code_review" \
        "web-sales:ux_audit"; do
        IFS=':' read -r agent skill_name <<< "$skill"
        cat > "$AI_HOME/workspace-$agent/skills/${skill_name}.md" << SKILL
---
name: $skill_name
description: AI skill for $agent
---
Use this skill to perform $skill_name tasks.
SKILL
    done
    ok "Skills installed"
}

config() {
    log "Generating config..."
    cat > "$AI_HOME/config.json" << 'CFG'
{"identity":{"name":"AI-Employee","emoji":"🤖"},"gateway":{"bind":"loopback","port":18789,"auth":{"mode":"token","token":"TOKEN_PLACEHOLDER"}},"agent":{"workspace":"AI_HOME_PLACEHOLDER/workspace","model":{"primary":"anthropic/claude-opus-4-5"}},"agents":{"defaults":{"sandbox":{"mode":"all","scope":"agent"}},"list":[{"id":"orchestrator","workspace":"AI_HOME_PLACEHOLDER/workspace-orchestrator","systemPrompt":"Master Orchestrator.","sandbox":{"mode":"off"}},{"id":"lead-hunter","workspace":"AI_HOME_PLACEHOLDER/workspace-lead-hunter","systemPrompt":"Lead Generation Specialist."},{"id":"content-master","workspace":"AI_HOME_PLACEHOLDER/workspace-content-master","systemPrompt":"Content Specialist."},{"id":"social-guru","workspace":"AI_HOME_PLACEHOLDER/workspace-social-guru","systemPrompt":"Social Media Manager."},{"id":"intel-agent","workspace":"AI_HOME_PLACEHOLDER/workspace-intel-agent","systemPrompt":"Intelligence Analyst."},{"id":"product-scout","workspace":"AI_HOME_PLACEHOLDER/workspace-product-scout","systemPrompt":"Product Researcher."},{"id":"email-ninja","workspace":"AI_HOME_PLACEHOLDER/workspace-email-ninja","systemPrompt":"Email Specialist."},{"id":"support-bot","workspace":"AI_HOME_PLACEHOLDER/workspace-support-bot","systemPrompt":"Support Agent."},{"id":"data-analyst","workspace":"AI_HOME_PLACEHOLDER/workspace-data-analyst","systemPrompt":"Data Analyst."},{"id":"creative-studio","workspace":"AI_HOME_PLACEHOLDER/workspace-creative-studio","systemPrompt":"Creative Director."},{"id":"crypto-trader","workspace":"AI_HOME_PLACEHOLDER/workspace-crypto-trader","systemPrompt":"Trading Analyst."},{"id":"bot-dev","workspace":"AI_HOME_PLACEHOLDER/workspace-bot-dev","systemPrompt":"Bot Developer."},{"id":"web-sales","workspace":"AI_HOME_PLACEHOLDER/workspace-web-sales","systemPrompt":"Web Analyst."}]},"channels":{"whatsapp":{"dmPolicy":"allowlist","allowFrom":["PHONE_PLACEHOLDER"]}},"tools":{"elevated":{"enabled":false}}}
CFG
    sed -i "s|TOKEN_PLACEHOLDER|$TOKEN|g" "$AI_HOME/config.json"
    sed -i "s|AI_HOME_PLACEHOLDER|$AI_HOME|g" "$AI_HOME/config.json"
    sed -i "s|PHONE_PLACEHOLDER|$PHONE|g" "$AI_HOME/config.json"
    ln -sf "$AI_HOME/config.json" ~/.openclaw/openclaw.json 2>/dev/null || true
    cat > "$AI_HOME/.env" << ENV
OPENCLAW_GATEWAY_TOKEN=$TOKEN
${ANTHROPIC_KEY:+ANTHROPIC_API_KEY=$ANTHROPIC_KEY}
ENV
    ok "Config generated"
}

docker_build() {
    log "Building Docker sandbox..."
    cat > /tmp/ai.dockerfile << 'DOCKER'
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y python3 python3-pip nodejs npm git curl && \
    pip3 install pandas numpy requests ccxt && npm i -g typescript && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
DOCKER
    docker build -qt ai-employee:latest -f /tmp/ai.dockerfile /tmp 2>&1 | grep -q "Successfully built" && ok "Sandbox built" || echo "⚠ Check manually"
    rm /tmp/ai.dockerfile
}

webui() {
    log "Installing Web UI..."
    cat > "$AI_HOME/ui/index.html" << 'HTML'
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>AI Employee</title>
<style>body{background:#0f172a;color:#e2e8f0;font-family:sans-serif;padding:20px}h1{color:#667eea}</style>
</head><body><h1>🤖 AI Employee Dashboard</h1><p>Status: Online</p><p>Open: http://localhost:3000</p></body></html>
HTML
    cat > "$AI_HOME/ui/serve.sh" << 'SERVE'
#!/bin/bash
cd "$(dirname "$0")"
python3 -m http.server 3000 2>/dev/null
SERVE
    chmod +x "$AI_HOME/ui/serve.sh"
    ok "Web UI installed"
}

scripts() {
    log "Creating scripts..."
    cat > "$AI_HOME/start.sh" << 'START'
#!/bin/bash
openclaw gateway &
cd ~/.ai-employee/ui && ./serve.sh &
echo "✅ Started! UI: http://localhost:3000"
trap "pkill -f 'openclaw gateway';pkill -f 'http.server'" EXIT
wait
START
    cat > "$AI_HOME/stop.sh" << 'STOP'
#!/bin/bash
pkill -f "openclaw gateway"
pkill -f "http.server"
echo "✅ Stopped"
STOP
    chmod +x "$AI_HOME"/{start,stop}.sh
    ok "Scripts created"
}

input
setup
install_skills
config
docker_build
webui
scripts
echo ""
ok "Installation complete!"
echo "Next: cd ~/.ai-employee && ./start.sh"
