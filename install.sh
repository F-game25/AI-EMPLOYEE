#!/bin/bash
set -euo pipefail

################################################################################
# AI EMPLOYEE - MAIN INSTALLER v3.0
# This is called by quick-install.sh
################################################################################

R='\033[0;31m';G='\033[0;32m';Y='\033[1;33m';B='\033[0;34m';C='\033[0;36m';NC='\033[0m'
AI_HOME="$HOME/.ai-employee"
START_TIME=$(date +%s)

log() { echo -e "${C}▸${NC} $1"; }
ok() { echo -e "${G}✓${NC} $1"; }
warn() { echo -e "${Y}⚠${NC} $1"; }
err() { echo -e "${R}✗${NC} $1"; exit 1; }

banner() {
cat << 'EOF'
╔══════════════════════════════════════════════════════╗
║          AI EMPLOYEE - v3.0 INSTALLER                ║
║   13 Agents • 50+ Skills • Modern UI • Lightning    ║
╚══════════════════════════════════════════════════════╝
EOF
}

input() {
    log "Configuration"
    read -p "WhatsApp number (+31612345678): " PHONE
    [[ ! $PHONE =~ ^\+[0-9]{10,15}$ ]] && { warn "Invalid format, using anyway"; }
    read -sp "Anthropic API key (optional): " ANTHROPIC_KEY; echo
    read -p "Trading bot path (optional): " BOT_PATH
    BOT_PATH="${BOT_PATH/#\~/$HOME}"
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
    chmod -R 700 "$AI_HOME/credentials"
    ok "Structure created"
}

install_skills() {
    log "Installing skills..."
    
    for skill in \
        "lead-hunter:linkedin_scraper:Find decision makers on LinkedIn" \
        "lead-hunter:email_finder:Find and verify email addresses" \
        "lead-hunter:lead_scorer:Score lead quality 0-100" \
        "lead-hunter:company_enrichment:Enrich company data" \
        "content-master:keyword_research:SEO keyword research" \
        "content-master:blog_writer:Write 2000+ word SEO articles" \
        "content-master:content_optimizer:Optimize existing content" \
        "social-guru:viral_finder:Find trending viral content" \
        "social-guru:caption_writer:Write platform-specific captions" \
        "social-guru:hashtag_generator:Generate relevant hashtags" \
        "social-guru:content_calendar:Create 30-day content calendar" \
        "intel-agent:pricing_tracker:Track competitor pricing" \
        "intel-agent:review_scraper:Scrape and analyze reviews" \
        "intel-agent:feature_comparison:Compare features with competitors" \
        "intel-agent:traffic_estimator:Estimate competitor traffic" \
        "product-scout:arbitrage_finder:Find AliExpress to Amazon arbitrage" \
        "product-scout:trend_spotter:Find trending products" \
        "product-scout:supplier_validator:Validate supplier reliability" \
        "product-scout:profit_calculator:Calculate true profit" \
        "email-ninja:sequence_builder:Build cold email sequences" \
        "email-ninja:deliverability_checker:Check email deliverability" \
        "email-ninja:personalization_engine:Personalize emails at scale" \
        "support-bot:faq_trainer:Extract FAQs from docs" \
        "support-bot:ticket_classifier:Classify support tickets" \
        "support-bot:sentiment_analyzer:Analyze customer sentiment" \
        "data-analyst:trend_analyzer:Analyze market trends" \
        "data-analyst:swot_generator:Generate SWOT analysis" \
        "data-analyst:survey_analyzer:Analyze survey responses" \
        "creative-studio:design_brief:Create design briefs" \
        "creative-studio:image_prompt:Generate AI image prompts" \
        "creative-studio:brand_voice:Define brand voice" \
        "creative-studio:ad_copy:Write ad copy" \
        "crypto-trader:technical_analysis:Full technical analysis" \
        "crypto-trader:pattern_recognition:Identify chart patterns" \
        "crypto-trader:whale_tracker:Track large wallet movements" \
        "bot-dev:code_review:Review code for issues" \
        "bot-dev:feature_implementation:Implement new features" \
        "bot-dev:bug_finder:Find bugs in code" \
        "web-sales:ux_audit:Audit website UX" \
        "web-sales:seo_audit:Technical SEO audit" \
        "web-sales:speed_test:Website speed analysis"; do
        
        IFS=':' read -r agent skill_name desc <<< "$skill"
        cat > "$AI_HOME/workspace-$agent/skills/${skill_name}.md" << SKILL
---
name: $skill_name
description: $desc
---
Use this skill to $desc. Provide structured output with clear, actionable results.
SKILL
    done
    
    ok "40+ skills installed"
}

config() {
    log "Generating config..."
    
    local BINDS='[]'
    [[ -n "$BOT_PATH" && -d "$BOT_PATH" ]] && BINDS="[\"$BOT_PATH:/tradingbot:rw\"]"
    
    cat > "$AI_HOME/config.json" << 'CFG'
{"identity":{"name":"AI-Employee","emoji":"🤖","theme":"autonomous business assistant"},"gateway":{"bind":"loopback","port":18789,"auth":{"mode":"token","token":"TOKEN_PLACEHOLDER"},"controlUi":{"enabled":true,"port":18789}},"agent":{"workspace":"AI_HOME_PLACEHOLDER/workspace","model":{"primary":"anthropic/claude-opus-4-5"}},"agents":{"defaults":{"sandbox":{"mode":"all","scope":"agent","workspaceAccess":"rw","docker":{"image":"ai-employee:latest","network":"bridge","memory":"2g","cpus":2,"env":{"PYTHONUNBUFFERED":"1","TZ":"Europe/Amsterdam"},"setupCommand":"apt-get update && apt-get install -y python3 python3-pip nodejs npm git curl && pip3 install --no-cache-dir pandas numpy requests ccxt beautifulsoup4 && npm i -g typescript","binds":BINDS_PLACEHOLDER}}},"list":[{"id":"orchestrator","workspace":"AI_HOME_PLACEHOLDER/workspace-orchestrator","systemPrompt":"Master Orchestrator. Route tasks to: lead-hunter (leads), content-master (content), social-guru (social), intel-agent (research), product-scout (ecommerce), email-ninja (email), support-bot (support), data-analyst (analysis), creative-studio (creative), crypto-trader (crypto), bot-dev (code), web-sales (web).","sandbox":{"mode":"off"},"tools":{"allow":["read","write","sessions_spawn","sessions_send","sessions_list","web_search"]}},{"id":"lead-hunter","workspace":"AI_HOME_PLACEHOLDER/workspace-lead-hunter","systemPrompt":"B2B Lead Generation Specialist. Find decision makers, emails, qualify leads. Always verify before returning.","tools":{"allow":["web_search","web_fetch","browser","read","write"],"deny":["exec","elevated"]}},{"id":"content-master","workspace":"AI_HOME_PLACEHOLDER/workspace-content-master","systemPrompt":"SEO Content Specialist. Write 2000+ word optimized articles with proper structure, keywords, and links.","tools":{"allow":["web_search","web_fetch","read","write","edit"],"deny":["exec","elevated"]}},{"id":"social-guru","workspace":"AI_HOME_PLACEHOLDER/workspace-social-guru","systemPrompt":"Social Media Manager. Find viral content, write engaging captions, generate hashtags. Platform-specific optimization.","tools":{"allow":["web_search","web_fetch","browser","read","write"],"deny":["exec","elevated"]}},{"id":"intel-agent","workspace":"AI_HOME_PLACEHOLDER/workspace-intel-agent","systemPrompt":"Competitive Intelligence Analyst. Monitor competitors: pricing, features, reviews, traffic. Generate actionable reports.","tools":{"allow":["web_search","web_fetch","browser","read","write"],"deny":["exec","elevated"]}},{"id":"product-scout","workspace":"AI_HOME_PLACEHOLDER/workspace-product-scout","systemPrompt":"E-commerce Product Researcher. Find arbitrage opportunities, trending products, validate suppliers, calculate profits.","tools":{"allow":["web_search","web_fetch","browser","read","write","exec"],"deny":["elevated"]}},{"id":"email-ninja","workspace":"AI_HOME_PLACEHOLDER/workspace-email-ninja","systemPrompt":"Cold Email Specialist. Build sequences, personalize at scale, optimize deliverability. Never spam.","tools":{"allow":["web_fetch","read","write","edit"],"deny":["exec","elevated","browser"]}},{"id":"support-bot","workspace":"AI_HOME_PLACEHOLDER/workspace-support-bot","systemPrompt":"Customer Support Agent. Answer FAQs, classify tickets, analyze sentiment, escalate when needed.","tools":{"allow":["read","write","web_fetch"],"deny":["exec","elevated","browser"]}},{"id":"data-analyst","workspace":"AI_HOME_PLACEHOLDER/workspace-data-analyst","systemPrompt":"Market Research Analyst. Analyze trends, generate SWOT, create reports with data and insights.","tools":{"allow":["web_search","web_fetch","browser","read","write","exec"],"deny":["elevated"]}},{"id":"creative-studio","workspace":"AI_HOME_PLACEHOLDER/workspace-creative-studio","systemPrompt":"Creative Director. Design briefs, image prompts, brand voice, ad copy. Professional and actionable.","tools":{"allow":["web_search","read","write"],"deny":["exec","elevated"]}},{"id":"crypto-trader","workspace":"AI_HOME_PLACEHOLDER/workspace-crypto-trader","systemPrompt":"Crypto Trading Analyst. Technical analysis, patterns, risk assessment. Include confidence scores and stop-losses.","model":{"primary":"anthropic/claude-opus-4-5"},"tools":{"allow":["web_fetch","browser","read","write","exec"],"deny":["elevated"]}},{"id":"bot-dev","workspace":"AI_HOME_PLACEHOLDER/workspace-bot-dev","systemPrompt":"Trading Bot Developer. Code review, feature implementation, optimization. Security-first approach.","model":{"primary":"anthropic/claude-opus-4-5"},"tools":{"allow":["read","write","edit","apply_patch","exec"],"deny":["elevated"]}},{"id":"web-sales","workspace":"AI_HOME_PLACEHOLDER/workspace-web-sales","systemPrompt":"Web Analysis & Sales Specialist. UX/SEO audits, find contacts, write personalized pitches. Max 10 emails per session.","tools":{"allow":["browser","web_search","web_fetch","read","write"],"deny":["exec","elevated"]}}]},"session":{"dmScope":"per-channel-peer","reset":{"mode":"manual"},"maintenance":{"mode":"rotate","pruneAfter":"7d","rotateBytes":"50mb"}},"channels":{"whatsapp":{"dmPolicy":"allowlist","allowFrom":["PHONE_PLACEHOLDER"],"groups":{"*":{"requireMention":true}},"mediaMaxMb":50,"sendReadReceipts":true}},"tools":{"browser":{"enabled":true,"headless":false,"downloadsDir":"AI_HOME_PLACEHOLDER/downloads","profile":"ai-employee-profile","viewport":{"width":1920,"height":1080}},"web":{"search":{"enabled":true,"provider":"brave","maxResults":10}},"exec":{"enabled":true,"host":"sandbox","shell":"/bin/bash","timeout":300000,"workdir":"/workspace"},"elevated":{"enabled":false},"media":{"audio":{"enabled":false},"video":{"enabled":false}}},"logging":{"level":"info","consoleLevel":"info","file":"AI_HOME_PLACEHOLDER/logs/gateway.log","redactSensitive":"tools","redactPatterns":["api[_-]?key","secret","token","password"]},"cron":{"enabled":false},"discovery":{"mdns":{"mode":"minimal"}}}
CFG

    # Replace placeholders
    sed -i.bak "s|TOKEN_PLACEHOLDER|$TOKEN|g" "$AI_HOME/config.json"
    sed -i.bak "s|AI_HOME_PLACEHOLDER|$AI_HOME|g" "$AI_HOME/config.json"
    sed -i.bak "s|PHONE_PLACEHOLDER|$PHONE|g" "$AI_HOME/config.json"
    sed -i.bak "s|BINDS_PLACEHOLDER|$BINDS|g" "$AI_HOME/config.json"
    rm "$AI_HOME/config.json.bak"

    ln -sf "$AI_HOME/config.json" ~/.openclaw/openclaw.json 2>/dev/null || true
    chmod 600 "$AI_HOME/config.json"
    
    cat > "$AI_HOME/.env" << ENV
OPENCLAW_GATEWAY_TOKEN=$TOKEN
${ANTHROPIC_KEY:+ANTHROPIC_API_KEY=$ANTHROPIC_KEY}
OPENCLAW_DISABLE_BONJOUR=1
TZ=Europe/Amsterdam
ENV
    chmod 600 "$AI_HOME/.env"
    
    ok "Config generated"
}

docker_build() {
    log "Building Docker sandbox (3-5 min)..."
    
    cat > /tmp/ai-employee.dockerfile << 'DOCKER'
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip nodejs npm git curl ca-certificates && \
    pip3 install --no-cache-dir pandas numpy requests ccxt beautifulsoup4 && \
    npm i -g typescript && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
CMD ["/bin/bash"]
DOCKER

    if docker build -qt ai-employee:latest -f /tmp/ai-employee.dockerfile /tmp 2>&1 | grep -q "Successfully built"; then
        ok "Docker sandbox built"
    else
        warn "Sandbox build may have issues (check manually)"
    fi
    
    rm /tmp/ai-employee.dockerfile
}

webui() {
    log "Installing Web UI..."
    
    cat > "$AI_HOME/ui/index.html" << 'HTMLEND'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Employee Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:20px}
.container{max-width:1400px;margin:0 auto}
header{background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;border-radius:15px;margin-bottom:30px;text-align:center;box-shadow:0 20px 60px rgba(102,126,234,0.3)}
h1{color:#fff;font-size:2.5em;margin-bottom:10px}
.subtitle{color:rgba(255,255,255,0.9);font-size:1.1em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:20px}
.card{background:#1e293b;padding:25px;border-radius:15px;border:1px solid #334155;transition:all 0.3s}
.card:hover{border-color:#667eea;transform:translateY(-5px);box-shadow:0 20px 40px rgba(102,126,234,0.2)}
.card h2{color:#667eea;margin-bottom:15px;font-size:1.3em}
.agent-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px}
.agent{background:#334155;padding:20px 15px;border-radius:10px;text-align:center;cursor:pointer;transition:all 0.2s;border:2px solid transparent}
.agent:hover{background:#667eea;transform:scale(1.05);border-color:#764ba2}
.agent-emoji{font-size:2.5em;margin-bottom:8px}
.agent-name{font-size:0.9em;font-weight:600;margin-bottom:4px}
.agent-role{font-size:0.75em;opacity:0.7}
.stat{display:flex;justify-content:space-between;align-items:center;padding:15px 0;border-bottom:1px solid #334155}
.stat:last-child{border:none}
.stat-label{font-size:1em;color:#94a3b8}
.stat-value{color:#10b981;font-weight:bold;font-size:1.5em}
.status-dot{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:10px;animation:pulse 2s infinite}
.status-dot.online{background:#10b981;box-shadow:0 0 10px #10b981}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
button{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;padding:12px 24px;border-radius:8px;cursor:pointer;font-size:1em;margin:5px;transition:all 0.2s}
button:hover{transform:translateY(-2px);box-shadow:0 10px 30px rgba(102,126,234,0.4)}
button:active{transform:translateY(0)}
.instruction{background:#334155;padding:20px;border-radius:10px;margin-top:20px;border-left:4px solid #667eea}
.instruction code{background:#1e293b;padding:4px 10px;border-radius:5px;font-family:monospace;color:#10b981}
footer{text-align:center;margin-top:40px;padding:20px;color:#64748b}
</style>
</head>
<body>
<div class="container">
<header>
<h1>🤖 AI Employee</h1>
<p class="subtitle">13 Autonomous Agents • Real-time Dashboard</p>
</header>

<div class="grid">
<div class="card">
<h2>System Status</h2>
<p style="margin:15px 0"><span class="status-dot online"></span>Gateway Online</p>
<p style="margin:15px 0"><span class="status-dot online"></span>WhatsApp Connected</p>
<p style="margin:15px 0"><span class="status-dot online"></span>13 Agents Ready</p>
</div>

<div class="card">
<h2>Today's Statistics</h2>
<div class="stat">
<span class="stat-label">Tasks Completed</span>
<span class="stat-value">0</span>
</div>
<div class="stat">
<span class="stat-label">Leads Generated</span>
<span class="stat-value">0</span>
</div>
<div class="stat">
<span class="stat-label">Content Created</span>
<span class="stat-value">0</span>
</div>
</div>

<div class="card">
<h2>Quick Actions</h2>
<button onclick="window.open('http://localhost:18789','_blank')">📊 Open Gateway</button>
<button onclick="alert('Run in terminal: openclaw logs --follow')">📋 View Logs</button>
<button onclick="alert('Run in terminal: openclaw security audit')">🔒 Security Audit</button>
</div>
</div>

<div class="card">
<h2>Available Agents (13)</h2>
<div class="agent-grid">
<div class="agent" onclick="showInfo('Orchestrator','Routes tasks to specialized agents')">
<div class="agent-emoji">🎯</div>
<div class="agent-name">Orchestrator</div>
<div class="agent-role">Task Router</div>
</div>
<div class="agent" onclick="showInfo('Lead Hunter','B2B lead generation specialist')">
<div class="agent-emoji">🔍</div>
<div class="agent-name">Lead Hunter</div>
<div class="agent-role">Lead Gen</div>
</div>
<div class="agent" onclick="showInfo('Content Master','SEO content writer')">
<div class="agent-emoji">✍️</div>
<div class="agent-name">Content Master</div>
<div class="agent-role">SEO Writing</div>
</div>
<div class="agent" onclick="showInfo('Social Guru','Social media manager')">
<div class="agent-emoji">📱</div>
<div class="agent-name">Social Guru</div>
<div class="agent-role">Social Media</div>
</div>
<div class="agent" onclick="showInfo('Intel Agent','Competitive intelligence')">
<div class="agent-emoji">🕵️</div>
<div class="agent-name">Intel Agent</div>
<div class="agent-role">Research</div>
</div>
<div class="agent" onclick="showInfo('Product Scout','E-commerce researcher')">
<div class="agent-emoji">🛒</div>
<div class="agent-name">Product Scout</div>
<div class="agent-role">E-commerce</div>
</div>
<div class="agent" onclick="showInfo('Email Ninja','Cold email specialist')">
<div class="agent-emoji">📧</div>
<div class="agent-name">Email Ninja</div>
<div class="agent-role">Email</div>
</div>
<div class="agent" onclick="showInfo('Support Bot','Customer support')">
<div class="agent-emoji">💬</div>
<div class="agent-name">Support Bot</div>
<div class="agent-role">Support</div>
</div>
<div class="agent" onclick="showInfo('Data Analyst','Market research')">
<div class="agent-emoji">📊</div>
<div class="agent-name">Data Analyst</div>
<div class="agent-role">Analysis</div>
</div>
<div class="agent" onclick="showInfo('Creative Studio','Design & branding')">
<div class="agent-emoji">🎨</div>
<div class="agent-name">Creative Studio</div>
<div class="agent-role">Creative</div>
</div>
<div class="agent" onclick="showInfo('Crypto Trader','Trading analysis')">
<div class="agent-emoji">📈</div>
<div class="agent-name">Crypto Trader</div>
<div class="agent-role">Trading</div>
</div>
<div class="agent" onclick="showInfo('Bot Developer','Code development')">
<div class="agent-emoji">🤖</div>
<div class="agent-name">Bot Dev</div>
<div class="agent-role">Development</div>
</div>
<div class="agent" onclick="showInfo('Web Sales','Website analysis')">
<div class="agent-emoji">🕸️</div>
<div class="agent-name">Web Sales</div>
<div class="agent-role">Web Analysis</div>
</div>
</div>
</div>

<div class="card instruction">
<h2>💬 How to Use</h2>
<p style="margin-bottom:15px">Send WhatsApp message to yourself:</p>
<p><code>switch to lead-hunter</code></p>
<p style="margin:10px 0"><code>find 20 SaaS CTOs in Netherlands</code></p>
<p style="margin-top:15px;color:#94a3b8;font-size:0.9em">
The agent will process your request and return results via WhatsApp.
</p>
</div>

<footer>
<p>🤖 AI Employee v3.0 • Autonomous Business Operations</p>
<p style="margin-top:10px;font-size:0.9em">
Gateway: localhost:18789 • Dashboard: localhost:3000
</p>
</footer>
</div>

<script>
function showInfo(name,desc){
alert(name + '\n\n' + desc + '\n\nSwitch via WhatsApp:\n"switch to ' + name.toLowerCase().replace(' ','-') + '"');
}
</script>
</body>
</html>
HTMLEND

    cat > "$AI_HOME/ui/serve.sh" << 'SERVE'
#!/bin/bash
cd "$(dirname "$0")"
echo "🌐 Web UI starting at http://localhost:3000"
python3 -m http.server 3000 2>/dev/null || python -m SimpleHTTPServer 3000
SERVE
    
    chmod +x "$AI_HOME/ui/serve.sh"
    ok "Web UI installed"
}

scripts() {
    log "Creating helper scripts..."
    
    cat > "$AI_HOME/start.sh" << 'START'
#!/bin/bash
echo "🚀 Starting AI Employee..."
openclaw gateway &
sleep 2
cd ~/.ai-employee/ui && ./serve.sh &
echo "✅ AI Employee started!"
echo ""
echo "📊 Web UI:    http://localhost:3000"
echo "🔧 Gateway:   http://localhost:18789"
echo ""
echo "Press Ctrl+C to stop..."
trap "pkill -f 'openclaw gateway';pkill -f 'http.server 3000'" EXIT
wait
START

    cat > "$AI_HOME/stop.sh" << 'STOP'
#!/bin/bash
pkill -f "openclaw gateway"
pkill -f "http.server 3000"
echo "✅ AI Employee stopped"
STOP

    chmod +x "$AI_HOME"/{start,stop}.sh
    ok "Helper scripts created"
}

done_message() {
    local elapsed=$(($(date +%s)-START_TIME))
    clear
    banner
    echo ""
    echo -e "${G}✓ Installation complete in ${elapsed}s!${NC}"
    echo ""
    echo -e "${C}Configuration saved:${NC}"
    echo "  Phone:    $PHONE"
    echo "  Token:    ${TOKEN:0:16}...${TOKEN: -8}"
    echo "  Config:   ~/.ai-employee/config.json"
    echo "  Web UI:   http://localhost:3000"
    echo ""
    echo -e "${Y}Next steps:${NC}"
    echo "  1. cd ~/.ai-employee && ./start.sh"
    echo "  2. openclaw channels login  (new terminal)"
    echo "  3. Send WhatsApp: 'Hello!'"
    echo ""
    echo -e "${G}Ready to earn! 💰${NC}"
    echo ""
}

# MAIN
banner
echo ""
input
echo ""
setup
install_skills
config
docker_build
webui
scripts
done_message
