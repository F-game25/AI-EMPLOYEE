"""AI Employee Dashboard — Problem Solver UI

Extended dashboard with 5 tabs:
  1. Dashboard  — bot status overview
  2. Chat       — send tasks / view chat log (mirrors WhatsApp tasks)
  3. Scheduler  — create/edit/list scheduled tasks
  4. Workers    — view/adjust enabled bots
  5. Improvements — approve/reject skill/market proposals

State files are read from ~/.ai-employee/state/
Config is read/written in ~/.ai-employee/config/
"""
import json
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_DIR = AI_HOME / "state"
CONFIG_DIR = AI_HOME / "config"
BOTS_DIR = AI_HOME / "bots"
CHATLOG = STATE_DIR / "chatlog.jsonl"
SCHEDULES_FILE = CONFIG_DIR / "schedules.json"
IMPROVEMENTS_FILE = STATE_DIR / "improvements.json"

PORT = int(os.environ.get("PROBLEM_SOLVER_UI_PORT", "8787"))
HOST = os.environ.get("PROBLEM_SOLVER_UI_HOST", "127.0.0.1")

app = FastAPI(title="AI Employee Dashboard")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ai_employee(*args: str) -> tuple:
    try:
        p = subprocess.run(
            [str(AI_HOME / "bin" / "ai-employee"), *args],
            capture_output=True, text=True, timeout=10
        )
        return p.returncode, p.stdout + p.stderr
    except Exception as e:
        return 1, str(e)


# ─── HTML Dashboard ────────────────────────────────────────────────────────────

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AI Employee Dashboard</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
    header{background:linear-gradient(135deg,#667eea,#764ba2);padding:20px 30px;display:flex;align-items:center;gap:16px}
    header h1{color:#fff;font-size:1.6em}
    header .sub{color:rgba(255,255,255,.8);font-size:.9em;margin-top:2px}
    nav{background:#1e293b;border-bottom:1px solid #334155;display:flex;gap:0}
    nav button{background:none;border:none;color:#94a3b8;padding:12px 22px;cursor:pointer;font-size:.95em;border-bottom:3px solid transparent;transition:all .2s}
    nav button:hover{color:#e2e8f0;background:#334155}
    nav button.active{color:#667eea;border-bottom-color:#667eea}
    .tab-content{display:none;padding:24px;max-width:1200px;margin:0 auto}
    .tab-content.active{display:block}
    .card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:20px;margin-bottom:16px}
    .card h3{color:#667eea;margin-bottom:12px;font-size:1.05em}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}
    @media(max-width:700px){.grid2,.grid3{grid-template-columns:1fr}}
    .bot-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #334155}
    .bot-row:last-child{border:none}
    .dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
    .dot.on{background:#10b981;box-shadow:0 0 6px #10b981}
    .dot.off{background:#ef4444}
    .dot.unknown{background:#f59e0b}
    .btn{background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;padding:9px 18px;border-radius:8px;cursor:pointer;font-size:.9em;transition:all .2s}
    .btn:hover{opacity:.9;transform:translateY(-1px)}
    .btn.danger{background:linear-gradient(135deg,#ef4444,#b91c1c)}
    .btn.success{background:linear-gradient(135deg,#10b981,#059669)}
    .btn.sm{padding:5px 12px;font-size:.82em}
    textarea,input,select{background:#0f172a;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:8px 12px;font-size:.9em;width:100%}
    textarea{resize:vertical;min-height:80px}
    pre{background:#0f172a;border:1px solid #334155;padding:12px;border-radius:8px;overflow:auto;font-size:.85em;max-height:300px;white-space:pre-wrap;word-break:break-word}
    .chat-msg{padding:8px 12px;border-radius:8px;margin-bottom:8px;max-width:80%}
    .chat-msg.user{background:#3730a3;margin-left:auto;text-align:right}
    .chat-msg.bot{background:#1e293b;border:1px solid #334155}
    .chat-msg .ts{font-size:.75em;opacity:.6;margin-top:4px}
    #chat-log{max-height:380px;overflow-y:auto;padding:8px;border:1px solid #334155;border-radius:8px;background:#0f172a;margin-bottom:12px}
    .badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.8em;font-weight:600}
    .badge.pending{background:#f59e0b22;color:#f59e0b;border:1px solid #f59e0b}
    .badge.approved{background:#10b98122;color:#10b981;border:1px solid #10b981}
    .badge.rejected{background:#ef444422;color:#ef4444;border:1px solid #ef4444}
    .badge.running{background:#10b98122;color:#10b981}
    .badge.stopped{background:#ef444422;color:#ef4444}
    .improv-row{border:1px solid #334155;border-radius:8px;padding:12px;margin-bottom:10px}
    .improv-row h4{color:#e2e8f0;margin-bottom:4px}
    .improv-row p{font-size:.88em;color:#94a3b8;margin-bottom:8px}
    label{display:block;margin-bottom:4px;font-size:.88em;color:#94a3b8}
    .form-row{margin-bottom:12px}
    .sched-row{border:1px solid #334155;border-radius:8px;padding:12px;margin-bottom:10px;display:flex;align-items:flex-start;gap:12px}
    .sched-info{flex:1}
    .sched-info h4{color:#e2e8f0;font-size:.95em;margin-bottom:2px}
    .sched-info p{font-size:.82em;color:#94a3b8}
    .toggle{position:relative;display:inline-block;width:36px;height:20px}
    .toggle input{opacity:0;width:0;height:0}
    .slider{position:absolute;cursor:pointer;inset:0;background:#334155;border-radius:20px;transition:.3s}
    .slider:before{content:"";position:absolute;width:14px;height:14px;left:3px;top:3px;background:#94a3b8;border-radius:50%;transition:.3s}
    input:checked+.slider{background:#667eea}
    input:checked+.slider:before{transform:translateX(16px);background:#fff}
    #toast{position:fixed;bottom:24px;right:24px;background:#10b981;color:#fff;padding:10px 20px;border-radius:8px;opacity:0;transition:opacity .3s;pointer-events:none;z-index:999}
    #toast.show{opacity:1}
  </style>
</head>
<body>
<header>
  <span style="font-size:2em">🤖</span>
  <div><h1>AI Employee</h1><div class="sub" id="header-sub">Loading...</div></div>
</header>
<nav>
  <button class="active" onclick="switchTab('dashboard',this)">📊 Dashboard</button>
  <button onclick="switchTab('chat',this)">💬 Chat</button>
  <button onclick="switchTab('scheduler',this)">📅 Scheduler</button>
  <button onclick="switchTab('workers',this)">👷 Workers</button>
  <button onclick="switchTab('improvements',this)">💡 Improvements</button>
</nav>

<!-- DASHBOARD TAB -->
<div id="tab-dashboard" class="tab-content active">
  <div class="grid2">
    <div class="card">
      <h3>Bot Status</h3>
      <div id="bot-status-list">Loading...</div>
      <br><button class="btn sm" onclick="loadDashboard()">🔄 Refresh</button>
    </div>
    <div class="card">
      <h3>Quick Actions</h3>
      <button class="btn" onclick="startAll()" style="margin:4px">▶ Start All</button>
      <button class="btn danger" onclick="stopAll()" style="margin:4px">■ Stop All</button>
      <button class="btn sm" onclick="window.open('http://localhost:18789','_blank')" style="margin:4px">📡 Gateway</button>
      <br><br>
      <h3>System Info</h3>
      <pre id="system-info">Click Refresh to load</pre>
    </div>
  </div>
  <div class="card">
    <h3>WhatsApp Commands Reference</h3>
    <p style="color:#94a3b8;font-size:.88em;line-height:1.8">
      Send these to your WhatsApp number:<br>
      <code style="color:#10b981">status</code> — get current status report &nbsp;|&nbsp;
      <code style="color:#10b981">workers</code> — list active workers &nbsp;|&nbsp;
      <code style="color:#10b981">schedule</code> — list scheduled tasks &nbsp;|&nbsp;
      <code style="color:#10b981">improvements</code> — list pending improvements &nbsp;|&nbsp;
      <code style="color:#10b981">switch to &lt;agent&gt;</code> — switch active agent &nbsp;|&nbsp;
      <code style="color:#10b981">help</code> — show all commands
    </p>
  </div>
</div>

<!-- CHAT TAB -->
<div id="tab-chat" class="tab-content">
  <div class="card">
    <h3>Chat / Task Input</h3>
    <p style="color:#94a3b8;font-size:.85em;margin-bottom:12px">
      Send tasks here — same as WhatsApp. Tasks are logged and can be picked up by agents.
    </p>
    <div id="chat-log"></div>
    <div style="display:flex;gap:8px;align-items:flex-end">
      <div style="flex:1">
        <textarea id="chat-input" placeholder="Type a task or question..." rows="2"></textarea>
      </div>
      <button class="btn" onclick="sendChat()" style="flex-shrink:0">Send</button>
    </div>
  </div>
</div>

<!-- SCHEDULER TAB -->
<div id="tab-scheduler" class="tab-content">
  <div class="grid2">
    <div class="card">
      <h3>Scheduled Tasks</h3>
      <div id="schedule-list">Loading...</div>
      <br><button class="btn sm" onclick="loadSchedules()">🔄 Refresh</button>
    </div>
    <div class="card">
      <h3>Add New Task</h3>
      <div class="form-row"><label>Task ID (unique)</label><input id="sched-id" placeholder="my_task_1"/></div>
      <div class="form-row"><label>Label</label><input id="sched-label" placeholder="Hourly status report"/></div>
      <div class="form-row">
        <label>Action</label>
        <select id="sched-action">
          <option value="log">Log message</option>
          <option value="start_bot">Start bot</option>
          <option value="stop_bot">Stop bot</option>
          <option value="status_report">Send status report</option>
        </select>
      </div>
      <div class="form-row" id="sched-bot-row" style="display:none">
        <label>Bot name</label>
        <input id="sched-bot" placeholder="status-reporter"/>
      </div>
      <div class="form-row"><label>Message (for log action)</label><input id="sched-msg" placeholder="Task ran"/></div>
      <div class="form-row">
        <label>Schedule type</label>
        <select id="sched-type">
          <option value="interval">Interval (every N minutes)</option>
          <option value="daily">Daily at time (UTC)</option>
        </select>
      </div>
      <div class="form-row" id="sched-interval-row">
        <label>Interval (minutes)</label>
        <input id="sched-interval" type="number" value="60" min="1"/>
      </div>
      <div class="form-row" id="sched-daily-row" style="display:none">
        <label>Run at (HH:MM UTC)</label>
        <input id="sched-daily-time" placeholder="08:00"/>
      </div>
      <button class="btn success" onclick="addSchedule()">+ Add Task</button>
    </div>
  </div>
</div>

<!-- WORKERS TAB -->
<div id="tab-workers" class="tab-content">
  <div class="card">
    <h3>Manage Workers / Bots</h3>
    <p style="color:#94a3b8;font-size:.85em;margin-bottom:12px">
      Start or stop individual bots. The problem-solver watchdog will auto-restart
      enabled bots if they crash.
    </p>
    <div id="worker-list">Loading...</div>
    <br><button class="btn sm" onclick="loadWorkers()">🔄 Refresh</button>
  </div>
</div>

<!-- IMPROVEMENTS TAB -->
<div id="tab-improvements" class="tab-content">
  <div class="card">
    <h3>Skill &amp; Market Improvement Proposals</h3>
    <p style="color:#94a3b8;font-size:.85em;margin-bottom:12px">
      The discovery bot proposes new skills and markets. Review and approve/reject below.
      <strong>No changes are made automatically.</strong>
    </p>
    <div id="improvement-list">Loading...</div>
    <br><button class="btn sm" onclick="loadImprovements()">🔄 Refresh</button>
  </div>
</div>

<div id="toast"></div>

<script>
let currentTab = 'dashboard';

function switchTab(tab, btn) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  btn.classList.add('active');
  currentTab = tab;
  if (tab === 'dashboard') loadDashboard();
  if (tab === 'chat') loadChatLog();
  if (tab === 'scheduler') loadSchedules();
  if (tab === 'workers') loadWorkers();
  if (tab === 'improvements') loadImprovements();
}

function toast(msg, color='#10b981') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.background = color;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

async function api(path, opts={}) {
  const r = await fetch(path, opts);
  return r.json();
}

// ── Dashboard ──
async function loadDashboard() {
  const d = await api('/api/status');
  const bots = d.bots || [];
  const el = document.getElementById('bot-status-list');
  if (!bots.length) { el.innerHTML = '<p style="color:#94a3b8">No bot state data yet.</p>'; return; }
  el.innerHTML = bots.map(b => {
    const cls = b.running ? 'on' : 'off';
    const lbl = b.running ? 'running' : 'stopped';
    return `<div class="bot-row"><div class="dot ${cls}"></div><span style="flex:1">${b.bot}</span><span class="badge ${lbl}">${lbl}</span></div>`;
  }).join('');
  document.getElementById('header-sub').textContent = `${bots.filter(b=>b.running).length}/${bots.length} bots running`;

  const sys = await api('/api/doctor');
  document.getElementById('system-info').textContent = sys.output || '';
}

async function startAll() {
  await api('/api/bots/start-all', {method:'POST'});
  toast('Starting all bots...');
  setTimeout(loadDashboard, 2000);
}

async function stopAll() {
  if (!confirm('Stop all bots?')) return;
  await api('/api/bots/stop-all', {method:'POST'});
  toast('Stopping all bots...', '#ef4444');
  setTimeout(loadDashboard, 2000);
}

// ── Chat ──
async function loadChatLog() {
  const data = await api('/api/chat');
  const log = document.getElementById('chat-log');
  const msgs = data.messages || [];
  if (!msgs.length) { log.innerHTML = '<p style="color:#94a3b8;padding:8px">No messages yet.</p>'; return; }
  log.innerHTML = msgs.slice(-50).map(m => {
    const type = m.type === 'user' ? 'user' : 'bot';
    const text = m.message || m.question || JSON.stringify(m);
    return `<div class="chat-msg ${type}"><div>${text}</div><div class="ts">${m.ts||''}</div></div>`;
  }).join('');
  log.scrollTop = log.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  const r = await api('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({message: q})});
  loadChatLog();
}

// ── Scheduler ──
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('sched-action').addEventListener('change', function() {
    document.getElementById('sched-bot-row').style.display = (this.value==='start_bot'||this.value==='stop_bot') ? '' : 'none';
  });
  document.getElementById('sched-type').addEventListener('change', function() {
    document.getElementById('sched-interval-row').style.display = this.value==='interval' ? '' : 'none';
    document.getElementById('sched-daily-row').style.display = this.value==='daily' ? '' : 'none';
  });
});

async function loadSchedules() {
  const data = await api('/api/schedules');
  const tasks = data.tasks || [];
  const el = document.getElementById('schedule-list');
  if (!tasks.length) { el.innerHTML = '<p style="color:#94a3b8">No scheduled tasks yet.</p>'; return; }
  el.innerHTML = tasks.map(t => {
    const info = t.type==='interval' ? `every ${t.interval_minutes||60}m` : `daily at ${t.run_at_utc||'?'} UTC`;
    return `<div class="sched-row">
      <div class="sched-info">
        <h4>${t.label||t.id} <span class="badge ${t.enabled!==false?'approved':'rejected'}">${t.enabled!==false?'enabled':'disabled'}</span></h4>
        <p>${t.action} | ${info}</p>
      </div>
      <button class="btn sm danger" onclick="deleteSchedule('${t.id}')">✕</button>
    </div>`;
  }).join('');
}

async function addSchedule() {
  const id = document.getElementById('sched-id').value.trim();
  const label = document.getElementById('sched-label').value.trim();
  const action = document.getElementById('sched-action').value;
  const bot = document.getElementById('sched-bot').value.trim();
  const msg = document.getElementById('sched-msg').value.trim();
  const type = document.getElementById('sched-type').value;
  const interval = parseInt(document.getElementById('sched-interval').value) || 60;
  const dailyTime = document.getElementById('sched-daily-time').value.trim();

  if (!id || !label) { toast('ID and label are required', '#ef4444'); return; }

  const task = {id, label, action, type, enabled: true,
    ...(bot && {bot}),
    ...(msg && {message: msg}),
    ...(type==='interval' && {interval_minutes: interval}),
    ...(type==='daily' && {run_at_utc: dailyTime||'08:00'}),
  };

  const r = await api('/api/schedules', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(task)});
  if (r.ok) { toast('Task added!'); loadSchedules(); }
  else { toast(r.error||'Error', '#ef4444'); }
}

async function deleteSchedule(id) {
  if (!confirm(`Delete task ${id}?`)) return;
  const r = await api(`/api/schedules/${id}`, {method:'DELETE'});
  if (r.ok) { toast('Deleted'); loadSchedules(); }
}

// ── Workers ──
async function loadWorkers() {
  const data = await api('/api/workers');
  const bots = data.bots || [];
  const el = document.getElementById('worker-list');
  el.innerHTML = bots.map(b => {
    const cls = b.running ? 'on' : 'off';
    const lbl = b.running ? 'running' : 'stopped';
    const startBtn = b.running ? '' : `<button class="btn sm success" onclick="startBot('${b.name}')">▶ Start</button>`;
    const stopBtn = b.running ? `<button class="btn sm danger" onclick="stopBot('${b.name}')">■ Stop</button>` : '';
    return `<div class="sched-row">
      <div class="dot ${cls}" style="margin-top:4px"></div>
      <div class="sched-info"><h4>${b.name}</h4><p class="badge ${lbl}">${lbl}</p></div>
      <div style="display:flex;gap:6px">${startBtn}${stopBtn}</div>
    </div>`;
  }).join('') || '<p style="color:#94a3b8">No bots found.</p>';
}

async function startBot(name) {
  await api('/api/bots/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot: name})});
  toast(`Starting ${name}...`);
  setTimeout(loadWorkers, 1500);
}

async function stopBot(name) {
  if (!confirm(`Stop ${name}?`)) return;
  await api('/api/bots/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot: name})});
  toast(`Stopping ${name}...`, '#ef4444');
  setTimeout(loadWorkers, 1500);
}

// ── Improvements ──
async function loadImprovements() {
  const data = await api('/api/improvements');
  const items = data.improvements || [];
  const el = document.getElementById('improvement-list');
  if (!items.length) { el.innerHTML = '<p style="color:#94a3b8">No proposals yet. The discovery bot will add proposals over time.</p>'; return; }
  el.innerHTML = items.map(imp => `
    <div class="improv-row">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <h4>${imp.title||imp.id} <span class="badge ${imp.status||'pending'}">${imp.status||'pending'}</span></h4>
        ${imp.status==='pending' ? `<div style="display:flex;gap:6px">
          <button class="btn sm success" onclick="reviewImprovement('${imp.id}','approved')">✓ Approve</button>
          <button class="btn sm danger" onclick="reviewImprovement('${imp.id}','rejected')">✕ Reject</button>
        </div>` : ''}
      </div>
      <p>${imp.description||''}</p>
      ${imp.agent ? `<p style="font-size:.8em;color:#667eea;margin-top:4px">Agent: ${imp.agent} | Type: ${imp.type||'?'} | Effort: ${imp.effort||'?'}</p>` : ''}
    </div>`).join('');
}

async function reviewImprovement(id, decision) {
  const r = await api(`/api/improvements/${id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status: decision})});
  if (r.ok) { toast(decision==='approved' ? '✓ Approved' : '✕ Rejected', decision==='approved'?'#10b981':'#ef4444'); loadImprovements(); }
}

// Initial load
loadDashboard();
</script>
</body>
</html>"""


# ─── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


@app.get("/api/status")
def get_status():
    state_file = STATE_DIR / "problem-solver.state.json"
    if state_file.exists():
        try:
            return JSONResponse(json.loads(state_file.read_text()))
        except Exception:
            pass
    return JSONResponse({"ts": None, "bots": [], "note": "No state yet. Start problem-solver."})


@app.get("/api/doctor")
def get_doctor():
    rc, out = ai_employee("doctor")
    return JSONResponse({"output": out, "rc": rc})


@app.post("/api/bots/start-all")
def start_all_bots():
    rc, out = ai_employee("start", "--all")
    return JSONResponse({"ok": rc == 0, "output": out})


@app.post("/api/bots/stop-all")
def stop_all_bots():
    rc, out = ai_employee("stop", "--all")
    return JSONResponse({"ok": rc == 0, "output": out})


@app.post("/api/bots/start")
def start_bot(payload: dict):
    bot = payload.get("bot", "")
    if not bot:
        raise HTTPException(400, "bot name required")
    rc, out = ai_employee("start", bot)
    return JSONResponse({"ok": rc == 0, "output": out})


@app.post("/api/bots/stop")
def stop_bot(payload: dict):
    bot = payload.get("bot", "")
    if not bot:
        raise HTTPException(400, "bot name required")
    rc, out = ai_employee("stop", bot)
    return JSONResponse({"ok": rc == 0, "output": out})


@app.get("/api/workers")
def get_workers():
    bots = []
    if BOTS_DIR.exists():
        for d in sorted(BOTS_DIR.iterdir()):
            if d.is_dir():
                pid_file = AI_HOME / "run" / f"{d.name}.pid"
                running = False
                if pid_file.exists():
                    try:
                        pid = int(pid_file.read_text().strip())
                        os.kill(pid, 0)
                        running = True
                    except Exception:
                        pass
                bots.append({"name": d.name, "running": running})
    return JSONResponse({"bots": bots})


# ─── Chat ─────────────────────────────────────────────────────────────────────

@app.get("/api/chat")
def get_chat():
    messages = []
    if CHATLOG.exists():
        try:
            for line in CHATLOG.read_text().splitlines():
                if line.strip():
                    messages.append(json.loads(line))
        except Exception:
            pass
    return JSONResponse({"messages": messages[-100:]})


@app.post("/api/chat")
def post_chat(payload: dict):
    message = (payload or {}).get("message", "").strip()
    if not message:
        raise HTTPException(400, "message required")

    entry = {"ts": now_iso(), "type": "user", "message": message}
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Simple command handling
    response = handle_command(message)
    resp_entry = {"ts": now_iso(), "type": "bot", "message": response}
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(resp_entry) + "\n")

    return JSONResponse({"ok": True, "response": response})


def handle_command(message: str) -> str:
    msg_lower = message.lower().strip()

    if msg_lower in ("status", "s"):
        rc, out = ai_employee("status")
        return f"Bot status:\n{out}" if out.strip() else "No status data."

    if msg_lower in ("workers", "w"):
        rc, out = ai_employee("status")
        return f"Workers:\n{out}"

    if msg_lower.startswith("start "):
        bot = message[6:].strip()
        rc, out = ai_employee("start", bot)
        return f"Started {bot}. {out}"

    if msg_lower.startswith("stop "):
        bot = message[5:].strip()
        rc, out = ai_employee("stop", bot)
        return f"Stopped {bot}. {out}"

    if msg_lower == "help":
        return (
            "Available commands:\n"
            "  status — bot status\n"
            "  workers — list workers\n"
            "  start <bot> — start a bot\n"
            "  stop <bot> — stop a bot\n"
            "  schedule — list schedules\n"
            "  improvements — pending proposals\n"
            "  help — this help"
        )

    if msg_lower in ("schedule", "schedules"):
        if SCHEDULES_FILE.exists():
            tasks = json.loads(SCHEDULES_FILE.read_text())
            if tasks:
                lines = [f"• {t.get('label',t.get('id'))} ({t.get('action')})" for t in tasks[:10]]
                return "Scheduled tasks:\n" + "\n".join(lines)
        return "No scheduled tasks."

    if msg_lower in ("improvements", "i"):
        if IMPROVEMENTS_FILE.exists():
            items = json.loads(IMPROVEMENTS_FILE.read_text())
            pending = [i for i in items if i.get("status") == "pending"]
            if pending:
                lines = [f"• {i.get('title', i.get('id'))}" for i in pending[:5]]
                return f"{len(pending)} pending proposals:\n" + "\n".join(lines) + "\nGo to UI > Improvements to approve."
        return "No pending improvements."

    # Default: queue as task
    return (
        f"Task queued: '{message}'\n"
        "Tip: use 'start <bot>', 'stop <bot>', 'status', 'help' for commands."
    )


# ─── Schedules ────────────────────────────────────────────────────────────────

@app.get("/api/schedules")
def get_schedules():
    if SCHEDULES_FILE.exists():
        try:
            return JSONResponse({"tasks": json.loads(SCHEDULES_FILE.read_text())})
        except Exception:
            pass
    return JSONResponse({"tasks": []})


@app.post("/api/schedules")
def add_schedule(task: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tasks = []
    if SCHEDULES_FILE.exists():
        try:
            tasks = json.loads(SCHEDULES_FILE.read_text())
        except Exception:
            pass

    task_id = task.get("id", "")
    if not task_id:
        raise HTTPException(400, "id required")

    # Replace if exists
    tasks = [t for t in tasks if t.get("id") != task_id]
    tasks.append(task)
    SCHEDULES_FILE.write_text(json.dumps(tasks, indent=2))
    return JSONResponse({"ok": True})


@app.delete("/api/schedules/{task_id}")
def delete_schedule(task_id: str):
    if not SCHEDULES_FILE.exists():
        return JSONResponse({"ok": True})
    try:
        tasks = json.loads(SCHEDULES_FILE.read_text())
        tasks = [t for t in tasks if t.get("id") != task_id]
        SCHEDULES_FILE.write_text(json.dumps(tasks, indent=2))
    except Exception as e:
        raise HTTPException(500, str(e))
    return JSONResponse({"ok": True})


# ─── Improvements ─────────────────────────────────────────────────────────────

@app.get("/api/improvements")
def get_improvements():
    if IMPROVEMENTS_FILE.exists():
        try:
            return JSONResponse({"improvements": json.loads(IMPROVEMENTS_FILE.read_text())})
        except Exception:
            pass
    return JSONResponse({"improvements": []})


@app.patch("/api/improvements/{improvement_id}")
def review_improvement(improvement_id: str, payload: dict):
    status = payload.get("status", "")
    if status not in ("approved", "rejected"):
        raise HTTPException(400, "status must be 'approved' or 'rejected'")

    if not IMPROVEMENTS_FILE.exists():
        raise HTTPException(404, "no improvements found")

    items = json.loads(IMPROVEMENTS_FILE.read_text())
    found = False
    for item in items:
        if item.get("id") == improvement_id:
            item["status"] = status
            item["reviewed_at"] = now_iso()
            found = True
            break

    if not found:
        raise HTTPException(404, f"improvement {improvement_id!r} not found")

    IMPROVEMENTS_FILE.write_text(json.dumps(items, indent=2))
    return JSONResponse({"ok": True, "id": improvement_id, "status": status})


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
