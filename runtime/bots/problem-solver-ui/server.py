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
import logging
import os
import signal
import subprocess
import sys
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
SKILLS_LIBRARY_FILE = CONFIG_DIR / "skills_library.json"
CUSTOM_AGENTS_FILE = CONFIG_DIR / "custom_agents.json"

PORT = int(os.environ.get("PROBLEM_SOLVER_UI_PORT", "8787"))
HOST = os.environ.get("PROBLEM_SOLVER_UI_HOST", "127.0.0.1")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("problem-solver-ui")

# ── AI router (Ollama first, cloud fallback) ──────────────────────────────────

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai as _query_ai  # type: ignore
    _AI_ROUTER_AVAILABLE = True
except ImportError:
    _AI_ROUTER_AVAILABLE = False

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

# ─── HTML Dashboard ────────────────────────────────────────────────────────────

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AI Employee Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root{
      --bg:#080e1a;--surface:#0d1626;--surface2:#111d30;--border:#1e2d45;
      --primary:#6366f1;--primary-dark:#4f46e5;--accent:#22d3ee;
      --success:#10b981;--danger:#ef4444;--warning:#f59e0b;
      --text:#e2e8f0;--text-muted:#64748b;--text-secondary:#94a3b8;
      --radius:12px;--radius-sm:8px;--shadow:0 4px 24px rgba(0,0,0,.4);
    }
    *{box-sizing:border-box;margin:0;padding:0}
    html{scroll-behavior:smooth}
    body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5}

    /* ── Scrollbars ── */
    ::-webkit-scrollbar{width:6px;height:6px}
    ::-webkit-scrollbar-track{background:var(--surface)}
    ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
    ::-webkit-scrollbar-thumb:hover{background:#2a3d5a}

    /* ── Layout ── */
    .app{display:flex;flex-direction:column;min-height:100vh}

    /* ── Header ── */
    header{
      background:linear-gradient(135deg,var(--primary-dark) 0%,#312e81 50%,#1e1b4b 100%);
      padding:16px 28px;display:flex;align-items:center;justify-content:space-between;
      border-bottom:1px solid rgba(99,102,241,.25);
      position:sticky;top:0;z-index:100;backdrop-filter:blur(10px);
    }
    .header-left{display:flex;align-items:center;gap:14px}
    .logo{width:40px;height:40px;background:rgba(255,255,255,.1);border-radius:10px;
      display:flex;align-items:center;justify-content:center;font-size:1.4em;
      border:1px solid rgba(255,255,255,.15)}
    .header-title h1{color:#fff;font-size:1.2em;font-weight:700;letter-spacing:-.02em}
    .header-title .sub{color:rgba(255,255,255,.6);font-size:.8em;margin-top:1px}
    .header-right{display:flex;align-items:center;gap:10px}
    .status-pill{display:flex;align-items:center;gap:6px;background:rgba(255,255,255,.07);
      border:1px solid rgba(255,255,255,.12);border-radius:20px;
      padding:5px 12px;font-size:.8em;color:rgba(255,255,255,.75)}
    .status-dot{width:7px;height:7px;border-radius:50%;background:var(--success);
      box-shadow:0 0 6px var(--success);animation:blink 2s infinite}
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.4}}

    /* ── Navigation ── */
    nav{background:var(--surface);border-bottom:1px solid var(--border);
      padding:0 28px;display:flex;gap:2px;overflow-x:auto}
    nav button{
      background:none;border:none;color:var(--text-secondary);
      padding:12px 16px;cursor:pointer;font-size:.875em;font-weight:500;
      border-bottom:2px solid transparent;transition:all .2s;
      white-space:nowrap;display:flex;align-items:center;gap:6px;
      font-family:inherit;
    }
    nav button:hover{color:var(--text);background:rgba(255,255,255,.03)}
    nav button.active{color:var(--primary);border-bottom-color:var(--primary);background:rgba(99,102,241,.05)}

    /* ── Main content ── */
    main{flex:1;padding:24px 28px;max-width:1280px;margin:0 auto;width:100%}
    @media(max-width:768px){main{padding:16px}}

    /* ── Tab panels ── */
    .tab-content{display:none}
    .tab-content.active{display:block;animation:fadeIn .2s ease}
    @keyframes fadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}

    /* ── Cards ── */
    .card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:16px}
    .card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
    .card-title{font-size:.95em;font-weight:600;color:var(--text);display:flex;align-items:center;gap:8px}
    .card-title .icon{color:var(--primary)}
    .section-title{font-size:.8em;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px}

    /* ── Grid layouts ── */
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
    .grid-stat{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px}
    @media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr}}

    /* ── Stat cards ── */
    .stat-card{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:16px;display:flex;align-items:center;gap:12px}
    .stat-icon{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;
      justify-content:center;font-size:1.1em;flex-shrink:0}
    .stat-icon.green{background:rgba(16,185,129,.15);color:var(--success)}
    .stat-icon.blue{background:rgba(99,102,241,.15);color:var(--primary)}
    .stat-icon.cyan{background:rgba(34,211,238,.15);color:var(--accent)}
    .stat-icon.yellow{background:rgba(245,158,11,.15);color:var(--warning)}
    .stat-body .val{font-size:1.5em;font-weight:700;color:var(--text)}
    .stat-body .lbl{font-size:.78em;color:var(--text-muted);margin-top:1px}

    /* ── Bot rows ── */
    .bot-row{display:flex;align-items:center;gap:10px;padding:9px 0;
      border-bottom:1px solid var(--border)}
    .bot-row:last-child{border:none}
    .dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;transition:background .3s}
    .dot.on{background:var(--success);box-shadow:0 0 8px rgba(16,185,129,.5)}
    .dot.off{background:#374151}
    .dot.unknown{background:var(--warning)}
    .bot-name{flex:1;font-size:.88em;color:var(--text)}

    /* ── Badges ── */
    .badge{display:inline-flex;align-items:center;padding:2px 9px;border-radius:20px;
      font-size:.75em;font-weight:600;letter-spacing:.01em}
    .badge.running,.badge.approved{background:rgba(16,185,129,.12);color:var(--success);border:1px solid rgba(16,185,129,.25)}
    .badge.stopped,.badge.rejected{background:rgba(239,68,68,.12);color:var(--danger);border:1px solid rgba(239,68,68,.25)}
    .badge.pending{background:rgba(245,158,11,.12);color:var(--warning);border:1px solid rgba(245,158,11,.25)}
    .badge.enabled{background:rgba(99,102,241,.12);color:var(--primary);border:1px solid rgba(99,102,241,.25)}
    .badge.disabled{background:rgba(100,116,139,.12);color:var(--text-muted);border:1px solid rgba(100,116,139,.25)}

    /* ── Buttons ── */
    .btn{display:inline-flex;align-items:center;gap:6px;padding:9px 18px;border:none;
      border-radius:var(--radius-sm);cursor:pointer;font-size:.875em;font-weight:500;
      transition:all .2s;font-family:inherit;text-decoration:none;white-space:nowrap}
    .btn-primary{background:var(--primary);color:#fff}
    .btn-primary:hover{background:var(--primary-dark);transform:translateY(-1px);box-shadow:0 4px 12px rgba(99,102,241,.4)}
    .btn-danger{background:rgba(239,68,68,.15);color:var(--danger);border:1px solid rgba(239,68,68,.25)}
    .btn-danger:hover{background:rgba(239,68,68,.25)}
    .btn-success{background:rgba(16,185,129,.15);color:var(--success);border:1px solid rgba(16,185,129,.25)}
    .btn-success:hover{background:rgba(16,185,129,.25)}
    .btn-ghost{background:rgba(255,255,255,.05);color:var(--text-secondary);border:1px solid var(--border)}
    .btn-ghost:hover{background:rgba(255,255,255,.08);color:var(--text)}
    .btn-sm{padding:5px 11px;font-size:.8em}
    .btn:disabled{opacity:.4;cursor:not-allowed;transform:none!important}

    /* ── Form controls ── */
    .form-group{margin-bottom:14px}
    label{display:block;font-size:.82em;font-weight:500;color:var(--text-secondary);margin-bottom:5px}
    input,textarea,select{
      width:100%;background:var(--surface2);border:1px solid var(--border);
      color:var(--text);border-radius:var(--radius-sm);padding:9px 12px;
      font-size:.875em;font-family:inherit;transition:border-color .2s;outline:none}
    input:focus,textarea:focus,select:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(99,102,241,.12)}
    textarea{resize:vertical;min-height:80px}
    select option{background:var(--surface)}

    /* ── Code / pre ── */
    pre{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:14px;overflow:auto;font-size:.82em;max-height:280px;
      white-space:pre-wrap;word-break:break-word;color:var(--text-secondary);
      font-family:'JetBrains Mono','Fira Code',monospace}
    code{background:rgba(99,102,241,.12);color:var(--primary);
      padding:1px 6px;border-radius:4px;font-size:.88em;font-family:monospace}

    /* ── Chat ── */
    #chat-log{max-height:400px;overflow-y:auto;padding:12px;border:1px solid var(--border);
      border-radius:var(--radius-sm);background:var(--bg);margin-bottom:12px}
    .chat-msg{padding:10px 14px;border-radius:10px;margin-bottom:8px;max-width:82%;word-break:break-word}
    .chat-msg.user{background:linear-gradient(135deg,var(--primary),var(--primary-dark));
      margin-left:auto;text-align:right;color:#fff}
    .chat-msg.bot{background:var(--surface2);border:1px solid var(--border);color:var(--text)}
    .chat-msg .ts{font-size:.72em;opacity:.55;margin-top:4px}
    .chat-input-row{display:flex;gap:8px;align-items:flex-end}

    /* ── Improvements ── */
    .improv-row{border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:14px;margin-bottom:10px;background:var(--surface2);transition:border-color .2s}
    .improv-row:hover{border-color:rgba(99,102,241,.3)}
    .improv-row h4{color:var(--text);font-size:.9em;margin-bottom:4px}
    .improv-row p{font-size:.83em;color:var(--text-secondary);margin-bottom:8px;line-height:1.5}

    /* ── Scheduler ── */
    .sched-row{border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:12px 14px;margin-bottom:10px;background:var(--surface2);
      display:flex;align-items:flex-start;gap:12px}
    .sched-info{flex:1}
    .sched-info h4{color:var(--text);font-size:.88em;margin-bottom:3px;display:flex;align-items:center;gap:8px}
    .sched-info p{font-size:.8em;color:var(--text-muted)}

    /* ── Toggle ── */
    .toggle{position:relative;display:inline-block;width:38px;height:22px;flex-shrink:0}
    .toggle input{opacity:0;width:0;height:0}
    .slider{position:absolute;cursor:pointer;inset:0;background:var(--border);border-radius:22px;transition:.3s}
    .slider:before{content:"";position:absolute;width:16px;height:16px;left:3px;top:3px;
      background:#64748b;border-radius:50%;transition:.3s}
    input:checked+.slider{background:var(--primary)}
    input:checked+.slider:before{transform:translateX(16px);background:#fff}

    /* ── Skills ── */
    .skill-card{border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:12px;margin-bottom:8px;cursor:pointer;transition:all .2s;background:var(--surface2)}
    .skill-card:hover{border-color:rgba(99,102,241,.4);background:rgba(99,102,241,.05)}
    .skill-card.selected{border-color:var(--success);background:rgba(16,185,129,.05)}
    .skill-card h5{color:var(--text);font-size:.88em;margin-bottom:3px;font-weight:600}
    .skill-card p{font-size:.8em;color:var(--text-muted);margin:0;line-height:1.4}
    .skill-card .tags{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px}
    .tag{background:rgba(99,102,241,.12);color:var(--primary);border-radius:4px;
      padding:2px 7px;font-size:.72em;font-weight:500}
    .cat-pill{display:inline-block;padding:4px 12px;border-radius:20px;font-size:.8em;
      cursor:pointer;border:1px solid var(--border);color:var(--text-secondary);
      margin:2px;transition:all .2s;font-weight:500}
    .cat-pill:hover{border-color:var(--primary);color:var(--primary)}
    .cat-pill.active{background:var(--primary);color:#fff;border-color:var(--primary)}
    .skill-grid{max-height:500px;overflow-y:auto;padding-right:4px}
    .agent-card{border:1px solid var(--border);border-radius:var(--radius-sm);
      padding:14px;margin-bottom:8px;background:var(--surface2)}
    .agent-card h4{color:var(--text);margin-bottom:4px;font-size:.9em;font-weight:600}
    .agent-card p{font-size:.83em;color:var(--text-muted)}
    #skill-search{margin-bottom:10px}

    /* ── Toast ── */
    #toast{position:fixed;bottom:24px;right:24px;min-width:220px;padding:12px 18px;
      border-radius:var(--radius-sm);color:#fff;opacity:0;
      transition:opacity .3s,transform .3s;pointer-events:none;z-index:9999;
      font-size:.875em;font-weight:500;box-shadow:var(--shadow);
      transform:translateY(10px);display:flex;align-items:center;gap:8px}
    #toast.show{opacity:1;transform:translateY(0)}

    /* ── Empty states ── */
    .empty{text-align:center;padding:32px 16px;color:var(--text-muted)}
    .empty .icon{font-size:2.5em;margin-bottom:10px;opacity:.5}
    .empty p{font-size:.88em}

    /* ── Divider ── */
    hr{border:none;border-top:1px solid var(--border);margin:16px 0}

    /* ── Quick actions bar ── */
    .actions-bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}

    /* ── Cmd reference ── */
    .cmd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}
    .cmd-item{background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 14px}
    .cmd-item code{display:block;margin-bottom:4px;font-size:.82em}
    .cmd-item span{font-size:.78em;color:var(--text-muted)}
  </style>
</head>
<body>
<div class="app">

<!-- ── Header ── -->
<header>
  <div class="header-left">
    <div class="logo">🤖</div>
    <div class="header-title">
      <h1>AI Employee</h1>
      <div class="sub" id="header-sub">Loading…</div>
    </div>
  </div>
  <div class="header-right">
    <div class="status-pill"><div class="status-dot"></div><span id="header-status">Running</span></div>
  </div>
</header>

<!-- ── Navigation ── -->
<nav>
  <button class="active" onclick="switchTab('dashboard',this)">📊 Dashboard</button>
  <button onclick="switchTab('chat',this)">💬 Chat</button>
  <button onclick="switchTab('tasks',this)">🚀 Tasks</button>
  <button onclick="switchTab('swarm',this)">🐝 Swarm</button>
  <button onclick="switchTab('scheduler',this)">📅 Scheduler</button>
  <button onclick="switchTab('workers',this)">👷 Workers</button>
  <button onclick="switchTab('improvements',this)">💡 Improvements</button>
  <button onclick="switchTab('skills',this)">🛠️ Skills</button>
</nav>

<main>

<!-- ── Dashboard ── -->
<div id="tab-dashboard" class="tab-content active">
  <div class="grid-stat" id="stat-cards">
    <div class="stat-card">
      <div class="stat-icon green">🟢</div>
      <div class="stat-body"><div class="val" id="stat-running">–</div><div class="lbl">Bots Running</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon blue">🤖</div>
      <div class="stat-body"><div class="val" id="stat-total">–</div><div class="lbl">Total Bots</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon cyan">📡</div>
      <div class="stat-body"><div class="val" id="stat-gateway">–</div><div class="lbl">Gateway</div></div>
    </div>
    <div class="stat-card">
      <div class="stat-icon yellow">⏱️</div>
      <div class="stat-body"><div class="val" id="stat-uptime">–</div><div class="lbl">Uptime</div></div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🤖</span> Bot Status</div>
        <button class="btn btn-ghost btn-sm" onclick="loadDashboard()">↻ Refresh</button>
      </div>
      <div id="bot-status-list"><div class="empty"><div class="icon">🔍</div><p>Loading bots…</p></div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">⚡</span> Quick Actions</div>
      </div>
      <div class="actions-bar">
        <button class="btn btn-success" onclick="startAll()">▶ Start All</button>
        <button class="btn btn-danger" onclick="stopAll()">■ Stop All</button>
        <a class="btn btn-ghost btn-sm" href="http://localhost:18789" target="_blank">📡 Gateway</a>
      </div>
      <hr>
      <div class="card-title" style="margin-bottom:10px"><span class="icon">🔧</span> System Info</div>
      <pre id="system-info" style="font-size:.78em">Click Refresh on the left to load…</pre>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">💬</span> WhatsApp Commands</div>
    </div>
    <div class="cmd-grid">
      <div class="cmd-item"><code>status</code><span>Get current status report</span></div>
      <div class="cmd-item"><code>workers</code><span>List active workers</span></div>
      <div class="cmd-item"><code>schedule</code><span>List scheduled tasks</span></div>
      <div class="cmd-item"><code>improvements</code><span>List pending proposals</span></div>
      <div class="cmd-item"><code>switch to &lt;agent&gt;</code><span>Switch active agent</span></div>
      <div class="cmd-item"><code>help</code><span>Show all commands</span></div>
    </div>
  </div>
</div>

<!-- ── Chat ── -->
<div id="tab-chat" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">💬</span> Chat / Task Input</div>
      <button class="btn btn-ghost btn-sm" onclick="loadChatLog()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">
      Send tasks here — same as WhatsApp. Tasks are processed by the active agent.
    </p>
    <div id="chat-log"><div class="empty"><div class="icon">💬</div><p>No messages yet.</p></div></div>
    <div class="chat-input-row">
      <div style="flex:1">
        <textarea id="chat-input" placeholder="Type a task or question…" rows="2"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChat()}"></textarea>
      </div>
      <button class="btn btn-primary" onclick="sendChat()" style="height:44px">Send ↗</button>
    </div>
    <p style="font-size:.75em;color:var(--text-muted);margin-top:6px">Press Enter to send · Shift+Enter for new line</p>
  </div>
</div>

<!-- ── Scheduler ── -->
<div id="tab-scheduler" class="tab-content">
  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📅</span> Scheduled Tasks</div>
        <button class="btn btn-ghost btn-sm" onclick="loadSchedules()">↻ Refresh</button>
      </div>
      <div id="schedule-list"><div class="empty"><div class="icon">📅</div><p>No tasks yet.</p></div></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">➕</span> Add New Task</div>
      </div>
      <div class="form-group"><label>Task ID (unique)</label><input id="sched-id" placeholder="my_task_1"/></div>
      <div class="form-group"><label>Label</label><input id="sched-label" placeholder="Hourly status report"/></div>
      <div class="form-group">
        <label>Action</label>
        <select id="sched-action">
          <option value="log">Log message</option>
          <option value="start_bot">Start bot</option>
          <option value="stop_bot">Stop bot</option>
          <option value="status_report">Send status report</option>
        </select>
      </div>
      <div class="form-group" id="sched-bot-row" style="display:none">
        <label>Bot name</label><input id="sched-bot" placeholder="status-reporter"/>
      </div>
      <div class="form-group"><label>Message (for log action)</label><input id="sched-msg" placeholder="Task ran"/></div>
      <div class="form-group">
        <label>Schedule type</label>
        <select id="sched-type">
          <option value="interval">Interval (every N minutes)</option>
          <option value="daily">Daily at time (UTC)</option>
        </select>
      </div>
      <div class="form-group" id="sched-interval-row">
        <label>Interval (minutes)</label><input id="sched-interval" type="number" value="60" min="1"/>
      </div>
      <div class="form-group" id="sched-daily-row" style="display:none">
        <label>Run at (HH:MM UTC)</label><input id="sched-daily-time" placeholder="08:00"/>
      </div>
      <button class="btn btn-success" onclick="addSchedule()">➕ Add Task</button>
    </div>
  </div>
</div>

<!-- ── Workers ── -->
<div id="tab-workers" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">👷</span> Manage Workers</div>
      <button class="btn btn-ghost btn-sm" onclick="loadWorkers()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">
      Start or stop individual bots. The problem-solver watchdog auto-restarts enabled bots if they crash.
    </p>
    <div id="worker-list"><div class="empty"><div class="icon">👷</div><p>Loading workers…</p></div></div>
  </div>
</div>

<!-- ── Improvements ── -->
<div id="tab-improvements" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">💡</span> Improvement Proposals</div>
      <button class="btn btn-ghost btn-sm" onclick="loadImprovements()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">
      The discovery bot proposes new skills and markets. Review and approve or reject below.
      <strong style="color:var(--warning)">No changes are applied automatically.</strong>
    </p>
    <div id="improvement-list"><div class="empty"><div class="icon">💡</div><p>No proposals yet. The discovery bot will add proposals over time.</p></div></div>
  </div>
</div>

<!-- ── Skills ── -->
<div id="tab-skills" class="tab-content">
  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🛠️</span> Skills Library <span id="skill-total-badge" style="font-size:.8em;color:var(--text-muted)"></span></div>
      </div>
      <input id="skill-search" placeholder="Search skills…" oninput="filterSkills()" />
      <div id="category-pills" style="margin:10px 0"></div>
      <div id="skill-grid" class="skill-grid"><div class="empty"><div class="icon">🛠️</div><p>Loading skills…</p></div></div>
    </div>
    <div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🤖</span> Create Custom Agent</div>
        </div>
        <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">Select skills from the library, name your agent, then click Create.</p>
        <div class="form-group"><label>Agent Name</label><input id="agent-name-input" placeholder="e.g. My Content Writer"/></div>
        <div class="form-group"><label>Description (optional)</label><input id="agent-desc-input" placeholder="What this agent does"/></div>
        <div class="form-group">
          <label>Selected Skills <span id="selected-count" style="color:var(--primary)">(0)</span></label>
          <div id="selected-skills-list" style="font-size:.82em;color:var(--text-muted);min-height:24px">No skills selected. Click cards on the left.</div>
        </div>
        <button class="btn btn-success" onclick="createAgent()">➕ Create Agent</button>
      </div>
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">👥</span> Custom Agents</div>
          <button class="btn btn-ghost btn-sm" onclick="loadAgents()">↻ Refresh</button>
        </div>
        <div id="agents-list"><div class="empty"><div class="icon">👥</div><p>No agents yet.</p></div></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Tasks ── -->
<div id="tab-tasks" class="tab-content">
  <div class="grid2">
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🚀</span> Submit a Task</div>
      </div>
      <p style="color:var(--text-muted);font-size:.85em;margin-bottom:14px">Describe any goal — the AI will decompose it, pick the right agents, and execute autonomously.</p>
      <div class="form-group">
        <label>Task Description</label>
        <textarea id="task-input" rows="4" placeholder="e.g. Build a SaaS company for remote team management — create business plan, brand identity, hiring plan, financial model, and go-to-market strategy" style="width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);padding:10px;font-family:inherit;resize:vertical"></textarea>
      </div>
      <button class="btn btn-success" onclick="submitTask()" style="width:100%">🚀 Launch Multi-Agent Task</button>
      <div id="task-submit-result" style="margin-top:12px;font-size:.88em;color:var(--text-muted)"></div>
    </div>
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📊</span> Active Task</div>
        <button class="btn btn-ghost btn-sm" onclick="loadTasks()">↻ Refresh</button>
      </div>
      <div id="active-task-panel"><div class="empty"><div class="icon">🚀</div><p>No active task. Submit one on the left.</p></div></div>
    </div>
  </div>
  <div class="card" style="margin-top:16px">
    <div class="card-header">
      <div class="card-title"><span class="icon">📋</span> Recent Tasks</div>
    </div>
    <div id="task-history-list"><div class="empty"><p>No task history yet.</p></div></div>
  </div>
</div>

<!-- ── Swarm ── -->
<div id="tab-swarm" class="tab-content">
  <div class="card">
    <div class="card-header">
      <div class="card-title"><span class="icon">🐝</span> Agent Swarm Overview</div>
      <button class="btn btn-ghost btn-sm" onclick="loadSwarm()">↻ Refresh</button>
    </div>
    <p style="color:var(--text-muted);font-size:.85em;margin-bottom:16px">All 20 AI agents — their capabilities, current status, and workload.</p>
    <div id="swarm-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px"><div class="empty"><div class="icon">🐝</div><p>Loading agents…</p></div></div>
  </div>
</div>

</main>
</div><!-- .app -->

<div id="toast"></div>

<script>
let currentTab = 'dashboard';
const _startTime = Date.now();

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
  if (tab === 'skills') loadSkills();
  if (tab === 'tasks') loadTasks();
  if (tab === 'swarm') loadSwarm();
}

function toast(msg, color='#10b981') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.background = color;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

async function api(path, opts={}) {
  try {
    const r = await fetch(path, opts);
    return r.json();
  } catch(e) {
    return {error: String(e)};
  }
}

// ── Dashboard ──────────────────────────────────────────────────────────────
async function loadDashboard() {
  const d = await api('/api/status');
  const bots = d.bots || [];
  const running = bots.filter(b => b.running).length;
  const total = bots.length;

  document.getElementById('stat-running').textContent = running;
  document.getElementById('stat-total').textContent = total;
  document.getElementById('header-sub').textContent = `${running}/${total} bots running`;

  // Uptime
  const secs = Math.floor((Date.now() - _startTime) / 1000);
  document.getElementById('stat-uptime').textContent =
    secs < 60 ? secs + 's' : secs < 3600 ? Math.floor(secs/60) + 'm' : Math.floor(secs/3600) + 'h';

  // Gateway status (try to ping)
  fetch('http://localhost:18789', {mode:'no-cors',signal:AbortSignal.timeout(1500)})
    .then(() => document.getElementById('stat-gateway').textContent = 'Online')
    .catch(() => document.getElementById('stat-gateway').textContent = 'Offline');

  const el = document.getElementById('bot-status-list');
  if (!bots.length) {
    el.innerHTML = '<div class="empty"><div class="icon">🤖</div><p>No bot state data yet. Start the bots first.</p></div>';
  } else {
    el.innerHTML = bots.map(b => {
      const cls = b.running ? 'on' : 'off';
      const lbl = b.running ? 'running' : 'stopped';
      return `<div class="bot-row">
        <div class="dot ${cls}"></div>
        <span class="bot-name">${b.bot}</span>
        <span class="badge ${lbl}">${lbl}</span>
      </div>`;
    }).join('');
  }

  const sys = await api('/api/doctor');
  document.getElementById('system-info').textContent = sys.output || '(no output)';
}

async function startAll() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '…';
  await api('/api/bots/start-all', {method:'POST'});
  toast('Starting all bots…');
  setTimeout(() => { loadDashboard(); btn.disabled=false; btn.textContent='▶ Start All'; }, 2500);
}

async function stopAll() {
  if (!confirm('Stop all running bots?')) return;
  await api('/api/bots/stop-all', {method:'POST'});
  toast('Stopping all bots…', '#ef4444');
  setTimeout(loadDashboard, 2000);
}

// ── Chat ────────────────────────────────────────────────────────────────────
async function loadChatLog() {
  const data = await api('/api/chat');
  const log = document.getElementById('chat-log');
  const msgs = data.messages || [];
  if (!msgs.length) {
    log.innerHTML = '<div class="empty"><div class="icon">💬</div><p>No messages yet.</p></div>';
    return;
  }
  log.innerHTML = msgs.slice(-60).map(m => {
    const type = m.type === 'user' ? 'user' : 'bot';
    const raw = m.message || m.question || JSON.stringify(m);
    // HTML-escape to prevent XSS, then convert newlines to <br>
    const text = raw.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                    .replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/\n/g,'<br>');
    const ts = (m.ts||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    return `<div class="chat-msg ${type}"><div>${text}</div><div class="ts">${ts}</div></div>`;
  }).join('');
  log.scrollTop = log.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  await api('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({message: q})});
  loadChatLog();
}

// ── Scheduler ───────────────────────────────────────────────────────────────
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
  if (!tasks.length) { el.innerHTML = '<div class="empty"><div class="icon">📅</div><p>No scheduled tasks yet.</p></div>'; return; }
  el.innerHTML = tasks.map(t => {
    const info = t.type==='interval' ? `every ${t.interval_minutes||60}m` : `daily at ${t.run_at_utc||'?'} UTC`;
    const enabled = t.enabled !== false;
    return `<div class="sched-row">
      <div class="sched-info">
        <h4>${t.label||t.id} <span class="badge ${enabled?'enabled':'disabled'}">${enabled?'enabled':'disabled'}</span></h4>
        <p>${t.action} · ${info}</p>
      </div>
      <button class="btn btn-danger btn-sm" onclick="deleteSchedule('${t.id}')">✕</button>
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
    ...(bot && {bot}), ...(msg && {message: msg}),
    ...(type==='interval' && {interval_minutes: interval}),
    ...(type==='daily' && {run_at_utc: dailyTime||'08:00'}),
  };

  const r = await api('/api/schedules', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(task)});
  if (r.ok) { toast('Task added!'); loadSchedules(); }
  else { toast(r.error||'Error', '#ef4444'); }
}

async function deleteSchedule(id) {
  if (!confirm(`Delete task "${id}"?`)) return;
  const r = await api(`/api/schedules/${id}`, {method:'DELETE'});
  if (r.ok) { toast('Task deleted'); loadSchedules(); }
}

// ── Workers ─────────────────────────────────────────────────────────────────
async function loadWorkers() {
  const data = await api('/api/workers');
  const bots = data.bots || [];
  const el = document.getElementById('worker-list');
  if (!bots.length) { el.innerHTML = '<div class="empty"><div class="icon">👷</div><p>No bots found.</p></div>'; return; }
  el.innerHTML = bots.map(b => {
    const cls = b.running ? 'on' : 'off';
    const lbl = b.running ? 'running' : 'stopped';
    const startBtn = b.running ? '' : `<button class="btn btn-success btn-sm" onclick="startBot('${b.name}')">▶ Start</button>`;
    const stopBtn = b.running ? `<button class="btn btn-danger btn-sm" onclick="stopBot('${b.name}')">■ Stop</button>` : '';
    return `<div class="sched-row">
      <div class="dot ${cls}" style="margin-top:4px;flex-shrink:0"></div>
      <div class="sched-info"><h4>${b.name} <span class="badge ${lbl}">${lbl}</span></h4></div>
      <div style="display:flex;gap:6px">${startBtn}${stopBtn}</div>
    </div>`;
  }).join('');
}

async function startBot(name) {
  await api('/api/bots/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot: name})});
  toast(`Starting ${name}…`);
  setTimeout(loadWorkers, 1800);
}

async function stopBot(name) {
  if (!confirm(`Stop ${name}?`)) return;
  await api('/api/bots/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({bot: name})});
  toast(`Stopping ${name}…`, '#ef4444');
  setTimeout(loadWorkers, 1800);
}

// ── Improvements ────────────────────────────────────────────────────────────
async function loadImprovements() {
  const data = await api('/api/improvements');
  const items = data.improvements || [];
  const el = document.getElementById('improvement-list');
  if (!items.length) { el.innerHTML = '<div class="empty"><div class="icon">💡</div><p>No proposals yet. The discovery bot will add them over time.</p></div>'; return; }
  el.innerHTML = items.map(imp => `
    <div class="improv-row">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
        <h4>${imp.title||imp.id} <span class="badge ${imp.status||'pending'}">${imp.status||'pending'}</span></h4>
        ${imp.status==='pending' ? `<div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn btn-success btn-sm" onclick="reviewImprovement('${imp.id}','approved')">✓ Approve</button>
          <button class="btn btn-danger btn-sm" onclick="reviewImprovement('${imp.id}','rejected')">✕ Reject</button>
        </div>` : ''}
      </div>
      <p>${imp.description||''}</p>
      ${imp.agent ? `<p style="font-size:.78em;color:var(--primary);margin-top:4px">Agent: ${imp.agent} · Type: ${imp.type||'?'} · Effort: ${imp.effort||'?'}</p>` : ''}
    </div>`).join('');
}

async function reviewImprovement(id, decision) {
  const r = await api(`/api/improvements/${id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status: decision})});
  if (r.ok) { toast(decision==='approved' ? '✓ Approved' : '✕ Rejected', decision==='approved'?'#10b981':'#ef4444'); loadImprovements(); }
}

// ── Skills ───────────────────────────────────────────────────────────────────
let allSkills = [];
let selectedSkillIds = new Set();
let activeCategory = '';

const CAT_COLORS = {
  'Content & Writing':'#f472b6','Research & Analysis':'#60a5fa',
  'Trading & Finance':'#34d399','Social Media':'#fb923c',
  'Lead Generation & Sales':'#a78bfa','Customer Support':'#fbbf24',
  'Development & Technical':'#22d3ee','Data Analysis':'#4ade80',
  'E-commerce & Product':'#f87171','Marketing & SEO':'#c084fc',
  'Automation & Productivity':'#e2e8f0',
};

async function loadSkills() {
  const data = await api('/api/skills');
  allSkills = data.skills || [];
  document.getElementById('skill-total-badge').textContent = `(${allSkills.length})`;
  renderCategoryPills(data.categories || []);
  renderSkillGrid(allSkills);
  loadAgents();
}

function renderCategoryPills(cats) {
  const el = document.getElementById('category-pills');
  el.innerHTML = `<span class="cat-pill active" onclick="setCat('',this)">All</span>` +
    cats.map(c => `<span class="cat-pill" onclick="setCat(${JSON.stringify(c)},this)">${c}</span>`).join('');
}

function setCat(cat, btn) {
  activeCategory = cat;
  document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  filterSkills();
}

function filterSkills() {
  const q = (document.getElementById('skill-search').value || '').toLowerCase();
  const filtered = allSkills.filter(s => {
    const catMatch = !activeCategory || s.category === activeCategory;
    const textMatch = !q || s.id.includes(q) || s.name.toLowerCase().includes(q) ||
                      s.description.toLowerCase().includes(q) ||
                      (s.tags||[]).some(t => t.toLowerCase().includes(q));
    return catMatch && textMatch;
  });
  renderSkillGrid(filtered);
}

function renderSkillGrid(skills) {
  const el = document.getElementById('skill-grid');
  if (!skills.length) { el.innerHTML = '<div class="empty"><div class="icon">🔍</div><p>No skills match.</p></div>'; return; }
  el.innerHTML = skills.map(s => {
    const color = CAT_COLORS[s.category] || '#94a3b8';
    const sel = selectedSkillIds.has(s.id);
    const tags = (s.tags||[]).slice(0,4).map(t=>`<span class="tag">${t}</span>`).join('');
    return `<div class="skill-card${sel?' selected':''}" onclick="toggleSkill(${JSON.stringify(s.id)},this)">
      <h5>${s.name} <span style="color:${color};font-size:.72em;font-weight:500">${s.category}</span></h5>
      <p>${s.description.slice(0,110)}${s.description.length>110?'…':''}</p>
      <div class="tags">${tags}</div>
    </div>`;
  }).join('');
}

function toggleSkill(id, card) {
  if (selectedSkillIds.has(id)) { selectedSkillIds.delete(id); card.classList.remove('selected'); }
  else { selectedSkillIds.add(id); card.classList.add('selected'); }
  updateSelectedPanel();
}

function updateSelectedPanel() {
  const count = selectedSkillIds.size;
  document.getElementById('selected-count').textContent = `(${count})`;
  const el = document.getElementById('selected-skills-list');
  if (!count) { el.textContent = 'No skills selected. Click cards on the left.'; return; }
  el.innerHTML = [...selectedSkillIds].map(id => {
    const s = allSkills.find(x => x.id === id);
    return `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 4px 2px 0;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.8em">
      ${s ? s.name : id}
      <span onclick="selectedSkillIds.delete(${JSON.stringify(id)});updateSelectedPanel();filterSkills();"
        style="cursor:pointer;color:var(--danger);font-weight:bold;margin-left:2px">×</span>
    </span>`;
  }).join('');
}

async function createAgent() {
  const name = document.getElementById('agent-name-input').value.trim();
  const desc = document.getElementById('agent-desc-input').value.trim();
  if (!name) { toast('Agent name is required', '#ef4444'); return; }
  if (!selectedSkillIds.size) { toast('Select at least one skill', '#ef4444'); return; }
  const r = await api('/api/agents/custom', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, description: desc, skills: [...selectedSkillIds]}),
  });
  if (r.ok) {
    toast(`Agent "${name}" created with ${r.skill_count} skills!`);
    document.getElementById('agent-name-input').value = '';
    document.getElementById('agent-desc-input').value = '';
    selectedSkillIds.clear();
    updateSelectedPanel();
    filterSkills();
    loadAgents();
  } else { toast(r.error || 'Error creating agent', '#ef4444'); }
}

async function loadAgents() {
  const data = await api('/api/agents/custom');
  const agents = data.agents || [];
  const el = document.getElementById('agents-list');
  if (!agents.length) { el.innerHTML = '<div class="empty"><div class="icon">👥</div><p>No agents yet. Create one above.</p></div>'; return; }
  el.innerHTML = agents.map(a => `
    <div class="agent-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <h4>${a.name}</h4>
        <button class="btn btn-danger btn-sm" onclick="deleteAgent('${a.id}')">🗑</button>
      </div>
      <p>${a.description || 'No description'}</p>
      <p style="margin-top:6px;color:var(--primary);font-size:.78em">${a.skill_count} skills: ${(a.skills||[]).slice(0,5).join(', ')}${a.skill_count>5?'…':''}</p>
    </div>`).join('');
}

async function deleteAgent(id) {
  if (!confirm('Delete this agent?')) return;
  const r = await api('/api/agents/custom/' + id, {method:'DELETE'});
  if (r.ok) { toast('Agent deleted', '#ef4444'); loadAgents(); }
}

// ── Tasks ────────────────────────────────────────────────────────────────────
async function submitTask() {
  const desc = document.getElementById('task-input').value.trim();
  if (!desc) { toast('Please enter a task description', '#ef4444'); return; }
  const resultEl = document.getElementById('task-submit-result');
  resultEl.textContent = '⏳ Submitting task to orchestrator…';
  const r = await api('/api/task/submit', {method:'POST', body: JSON.stringify({description: desc})});
  if (r.ok) {
    const d = await r.json();
    resultEl.innerHTML = '<span style="color:var(--success)">✅ Task submitted! ID: <code>' + (d.task_id||'?') + '</code></span>';
    document.getElementById('task-input').value = '';
    setTimeout(loadTasks, 2000);
  } else {
    resultEl.innerHTML = '<span style="color:var(--danger)">❌ Failed to submit task. Is task-orchestrator running?</span>';
  }
}

async function loadTasks() {
  const r = await api('/api/task/list');
  if (!r.ok) return;
  const d = await r.json();
  const plans = d.plans || [];

  // Active task panel
  const activePanel = document.getElementById('active-task-panel');
  const active = plans.find(p => p.status === 'running' || p.status === 'planning');
  if (active) {
    const subtasks = active.subtasks || [];
    const done = subtasks.filter(s => s.status === 'done').length;
    const pct = subtasks.length ? Math.round(done/subtasks.length*100) : 0;
    const statusEmoji = {running:'⏳',planning:'🧠',done:'✅',failed:'❌'}[active.status]||'?';
    activePanel.innerHTML = `
      <div style="margin-bottom:12px">
        <div style="font-weight:600;margin-bottom:4px">${statusEmoji} ${escHtml(active.title||active.id)}</div>
        <div style="font-size:.82em;color:var(--text-muted)">ID: ${active.id} | ${done}/${subtasks.length} subtasks</div>
        <div style="background:var(--border);border-radius:4px;height:6px;margin:8px 0">
          <div style="background:var(--primary);height:100%;width:${pct}%;border-radius:4px;transition:width .3s"></div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${subtasks.map(st => {
          const e = {done:'✅',running:'⏳',pending:'⏸️',failed:'❌'}[st.status]||'?';
          return `<div style="display:flex;align-items:center;gap:8px;font-size:.85em">
            <span>${e}</span>
            <span style="color:var(--accent);min-width:120px">[${escHtml(st.agent_id||'')}]</span>
            <span style="color:var(--text-secondary)">${escHtml(st.title||st.subtask_id||'')}</span>
          </div>`;
        }).join('')}
      </div>
      <button class="btn btn-ghost btn-sm" style="margin-top:12px;color:var(--danger)" onclick="cancelTask()">🛑 Cancel Task</button>
    `;
    setTimeout(loadTasks, 5000);
  } else {
    activePanel.innerHTML = '<div class="empty"><div class="icon">🚀</div><p>No active task. Submit one on the left.</p></div>';
  }

  // History list
  const histEl = document.getElementById('task-history-list');
  const history = plans.filter(p => !['running','planning'].includes(p.status)).slice(0,10);
  if (!history.length) {
    histEl.innerHTML = '<div class="empty"><p>No task history yet.</p></div>';
    return;
  }
  histEl.innerHTML = history.map(p => {
    const e = {done:'✅',failed:'❌',cancelled:'🛑',timed_out:'⏰'}[p.status]||'?';
    const subs = (p.subtasks||[]).length;
    const agents = [...new Set((p.subtasks||[]).map(s=>s.agent_id))].join(', ');
    return `<div style="padding:10px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
      <div>
        <div style="font-weight:500">${e} ${escHtml(p.title||p.id)}</div>
        <div style="font-size:.78em;color:var(--text-muted)">${subs} subtasks | Agents: ${escHtml(agents)} | ${p.created_at||''}</div>
      </div>
      <span style="font-size:.78em;background:var(--surface2);padding:2px 8px;border-radius:4px;color:var(--text-secondary)">${p.status}</span>
    </div>`;
  }).join('');
}

async function cancelTask() {
  const r = await api('/api/task/cancel', {method:'POST'});
  if (r.ok) { toast('Task cancelled', '#f59e0b'); loadTasks(); }
}

// ── Swarm ────────────────────────────────────────────────────────────────────
async function loadSwarm() {
  const r = await api('/api/agents');
  if (!r.ok) return;
  const d = await r.json();
  const agents = d.agents || [];
  const grid = document.getElementById('swarm-grid');
  if (!agents.length) {
    grid.innerHTML = '<div class="empty"><div class="icon">🐝</div><p>No agent data. Ensure agent_capabilities.json is loaded.</p></div>';
    return;
  }
  const categoryColors = {
    coordination:'#6366f1', sales:'#10b981', content:'#22d3ee', social:'#f59e0b',
    research:'#3b82f6', ecommerce:'#ec4899', analytics:'#8b5cf6', creative:'#ef4444',
    trading:'#f97316', development:'#14b8a6', hr:'#84cc16', finance:'#eab308',
    marketing:'#06b6d4', growth:'#a855f7', management:'#64748b', crypto:'#f59e0b',
    strategy:'#6366f1'
  };
  grid.innerHTML = agents.map(a => {
    const color = categoryColors[a.category] || '#64748b';
    const dotColor = a.running ? '#10b981' : '#ef4444';
    const runningDot = `<span style="width:8px;height:8px;border-radius:50%;background:${dotColor};display:inline-block;margin-left:6px"></span>`;
    const skills = (a.skills||[]).slice(0,4).map(s => `<span style="background:var(--surface);padding:2px 6px;border-radius:3px;font-size:.73em;color:var(--text-secondary)">${escHtml(s)}</span>`).join('');
    return `<div style="background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);padding:14px;border-top:3px solid ${color}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div style="font-weight:600;font-size:.95em">${escHtml(a.id)}</div>
        ${runningDot}
      </div>
      <div style="font-size:.8em;color:var(--text-secondary);margin-bottom:10px;line-height:1.4">${escHtml(a.description||'')}</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">${skills}${(a.skills||[]).length > 4 ? `<span style="font-size:.73em;color:var(--text-muted)">+${(a.skills||[]).length-4} more</span>` : ''}</div>
      <div style="margin-top:8px;font-size:.75em;color:var(--text-muted)">Category: ${escHtml(a.category||'')}</div>
    </div>`;
  }).join('');
}

// Initial load
loadDashboard();
// Auto-refresh dashboard every 30s
setInterval(() => { if (currentTab === 'dashboard') loadDashboard(); }, 30000);
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
            "  status / workers — bot status\n"
            "  start <bot> / stop <bot> — control bots\n"
            "  schedule / improvements — view tasks & proposals\n"
            "  skills / agents — skills library & custom agents\n"
            "  research <query> — web research\n"
            "  find <topic> / web search <query> / latest news <topic>\n"
            "  social <brief> — full social media content package\n"
            "  social plan <brief> — strategy plan only\n"
            "  content <brief> — same as social\n"
            "  leads <niche> <location> — local business lead generation\n"
            "  leads real-estate <location> — real estate leads\n"
            "  leads status / leads pipeline / leads followup\n"
            "  recruit <role> <requirements> — find candidates\n"
            "  recruit screen <cv_text> — AI CV screening\n"
            "  recruit candidates / recruit status\n"
            "  ecom research <niche> — trending product research\n"
            "  ecom listing <product> — generate full product listing\n"
            "  ecom email <type> <product> — email marketing flow\n"
            "  ecom trends / ecom ads <product>\n"
            "  creator plan <topic> — 30-day content calendar\n"
            "  creator dm-funnel <style> — DM funnel sequence\n"
            "  creator upsell <tier> — upsell scripts\n"
            "  creator brand <name> <niche> — full brand kit\n"
            "  signals — current trading signals (Telegram/Discord)\n"
            "  signal daily — daily market summary\n"
            "  signal post <analysis> — post a manual signal\n"
            "  community update — community newsletter\n"
            "  prospect <niche> <location> — appointment setter prospects\n"
            "  outreach <campaign> — generate outreach campaign\n"
            "  pipeline / setter followup / setter scripts\n"
            "  newsletter create <topic> — generate newsletter issue\n"
            "  newsletter subscribe <email> — add subscriber\n"
            "  newsletter send <issue_id> — send newsletter\n"
            "  chatbot create <niche> — build niche chatbot\n"
            "  chatbot flow <niche> — conversation flow\n"
            "  chatbot scripts <niche> — response scripts\n"
            "  video <topic> — faceless video full pipeline\n"
            "  video script <topic> — video script only\n"
            "  video seo <topic> — YouTube SEO pack\n"
            "  video tiktok <topic> — TikTok short-form\n"
            "  pod research <niche> — print-on-demand trends\n"
            "  pod design <niche> — AI design prompts\n"
            "  pod listing <product> — full POD listing\n"
            "  pod ads <product> — ad copy\n"
            "  course create <topic> — full course package\n"
            "  course outline <topic> — course structure\n"
            "  course lesson <module> <title> — lesson content\n"
            "  course market <topic> — marketing pack\n"
            "  arb scan <product> — arbitrage scan\n"
            "  arb trends — hot arbitrage categories\n"
            "  arb opportunities / arb watchlist\n"
            "  task <description> — multi-agent orchestration\n"
            "  task status / task list / task cancel\n"
            "  agents — list all 20 AI agents\n"
            "  assign <agent> <subtask> — manual agent dispatch\n"
            "  company build <idea> — build a company from scratch\n"
            "  company validate / plan / simulate / gtm / pitch / org / swot\n"
            "  memecoin create <concept> — full token launch package\n"
            "  memecoin name / tokenomics / whitepaper / community / viral\n"
            "  hr hire <role> — full hiring package\n"
            "  hr jd / screen / interview / onboard / review / org / culture\n"
            "  finance model <business> — full financial model\n"
            "  finance pl / runway / raise / unit / pricing / pitch / valuation\n"
            "  brand identity <company> — full brand system\n"
            "  brand name / position / voice / messaging / story / audit\n"
            "  growth loop <product> — viral growth loop\n"
            "  growth funnel / abtests / retention / referral / plg / experiments\n"
            "  pm start <project> — kick off a project\n"
            "  pm breakdown / sprint / roadmap / risks / raci / gantt / retro\n"
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

    # ── Skills commands (pass-through; skills-manager processes these) ──
    if (msg_lower.startswith("skills") or msg_lower.startswith("agents")
            or msg_lower.startswith("agent ") or msg_lower.startswith("create agent")
            or msg_lower.startswith("add skill") or msg_lower.startswith("remove skill")
            or msg_lower.startswith("delete agent")):
        if SKILLS_LIBRARY_FILE.exists():
            try:
                lib = json.loads(SKILLS_LIBRARY_FILE.read_text())
                total = len(lib.get("skills", []))
                cats = len(lib.get("categories", []))
                return (
                    f"📚 Skills Library: {total} skills in {cats} categories.\n"
                    "The skills-manager is processing your command — check the chat in a moment.\n"
                    "Tip: open the *🛠️ Skills* tab in the dashboard for the full interactive UI."
                )
            except (json.JSONDecodeError, OSError):
                pass
        return "Skills library not loaded yet. Ensure skills-manager is running."

    # ── Research commands (pass-through; web-researcher processes these) ──
    if (msg_lower.startswith("research ") or msg_lower.startswith("find ")
            or msg_lower.startswith("web search ") or msg_lower.startswith("search web ")
            or msg_lower.startswith("latest news ") or msg_lower.startswith("news about ")
            or msg_lower.startswith("lookup ")):
        web_bot_state = STATE_DIR / "web-researcher.state.json"
        if web_bot_state.exists():
            try:
                st = json.loads(web_bot_state.read_text())
                if st.get("status") == "running":
                    return (
                        "🔍 Research request queued — web-researcher bot is processing it.\n"
                        "The answer will appear in the chat shortly."
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return (
            "🔍 Research request noted — ensure web-researcher bot is running.\n"
            "Start it: `start web-researcher`"
        )

    # ── Social media commands (pass-through; social-media-manager processes these) ──
    if (msg_lower.startswith("social ") or msg_lower.startswith("content ")
            or msg_lower.startswith("create content ") or msg_lower.startswith("create social ")):
        social_bot_state = STATE_DIR / "social-media-manager.state.json"
        if social_bot_state.exists():
            try:
                st = json.loads(social_bot_state.read_text())
                if st.get("status") == "running":
                    return (
                        "🎨 Content creation request queued — social-media-manager bot is processing it.\n"
                        "Full content package will appear in the chat shortly (30-90 seconds)."
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return (
            "🎨 Content request noted — ensure social-media-manager bot is running.\n"
            "Start it: `start social-media-manager`"
        )

    # ── Pass-through routing helper ───────────────────────────────────────────
    def _bot_passthrough(prefixes: list, bot_name: str, emoji: str, desc: str) -> str | None:
        """Return a pass-through ack if msg matches any prefix, else None."""
        if not any(msg_lower.startswith(p) for p in prefixes):
            return None
        st_file = STATE_DIR / f"{bot_name}.state.json"
        if st_file.exists():
            try:
                st = json.loads(st_file.read_text())
                if st.get("status") == "running":
                    return (
                        f"{emoji} Request queued — {bot_name} bot is processing it.\n"
                        f"Result will appear in chat shortly."
                    )
            except (json.JSONDecodeError, OSError):
                pass
        return f"{emoji} {desc}\nStart it: `start {bot_name}`"

    for _prefixes, _bot, _emoji, _desc in [
        (["leads ", "outreach "], "lead-generator", "📋", "Lead generator not running."),
        (["recruit "], "recruiter", "👔", "Recruiter not running."),
        (["ecom "], "ecom-agent", "🛒", "Ecom agent not running."),
        (["creator "], "creator-agency", "🎭", "Creator agency not running."),
        (["signals", "signal ", "community update"], "signal-community", "📊", "Signal community not running."),
        (["prospect ", "pipeline", "setter "], "appointment-setter", "📅", "Appointment setter not running."),
        (["newsletter "], "newsletter-bot", "📧", "Newsletter bot not running."),
        (["chatbot "], "chatbot-builder", "🤖", "Chatbot builder not running."),
        (["video "], "faceless-video", "🎬", "Faceless video bot not running."),
        (["pod "], "print-on-demand", "👕", "Print-on-demand bot not running."),
        (["course "], "course-creator", "🎓", "Course creator not running."),
        (["arb "], "arbitrage-bot", "💹", "Arbitrage bot not running."),
        (["task ", "orchestrate "], "task-orchestrator", "🚀", "Task orchestrator not running. Start it: `start task-orchestrator`"),
        (["company "], "company-builder", "🏢", "Company builder not running. Start it: `start company-builder`"),
        (["memecoin "], "memecoin-creator", "🪙", "Memecoin creator not running. Start it: `start memecoin-creator`"),
        (["hr "], "hr-manager", "👔", "HR manager not running. Start it: `start hr-manager`"),
        (["finance "], "finance-wizard", "💰", "Finance wizard not running. Start it: `start finance-wizard`"),
        (["brand "], "brand-strategist", "🎨", "Brand strategist not running. Start it: `start brand-strategist`"),
        (["growth "], "growth-hacker", "🚀", "Growth hacker not running. Start it: `start growth-hacker`"),
        (["pm "], "project-manager", "📋", "Project manager not running. Start it: `start project-manager`"),
    ]:
        _reply = _bot_passthrough(_prefixes, _bot, _emoji, _desc)
        if _reply is not None:
            return _reply

    # Default: try AI router (Ollama first, then cloud) before falling back to queued message
    if _AI_ROUTER_AVAILABLE:
        try:
            result = _query_ai(
                message,
                system_prompt=(
                    "You are an AI employee assistant. "
                    "Help the user with their task or question concisely and practically. "
                    "If the task requires running a specific bot command, suggest the right command."
                ),
            )
            if result.get("answer"):
                provider = result.get("provider", "ai")
                suffix = f"\n_[{provider}]_" if provider not in ("error",) else ""
                return result["answer"] + suffix
        except Exception as exc:
            logger.debug("handle_command: AI router error — %s", exc)

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


# ─── Skills Library ────────────────────────────────────────────────────────────

@app.get("/api/skills")
def get_skills(category: str = "", q: str = ""):
    lib = {}
    if SKILLS_LIBRARY_FILE.exists():
        try:
            lib = json.loads(SKILLS_LIBRARY_FILE.read_text())
        except Exception:
            pass
    skills = lib.get("skills", [])
    categories = lib.get("categories", sorted({s["category"] for s in skills}))
    if category:
        skills = [s for s in skills if s["category"].lower() == category.lower()]
    if q:
        ql = q.lower()
        skills = [
            s for s in skills
            if (ql in s["id"].lower() or ql in s["name"].lower()
                or ql in s["description"].lower()
                or any(ql in t.lower() for t in s.get("tags", [])))
        ]
    return JSONResponse({"skills": skills, "categories": categories, "total": len(skills)})


# ─── Custom Agents ─────────────────────────────────────────────────────────────

def _load_library():
    if SKILLS_LIBRARY_FILE.exists():
        try:
            return json.loads(SKILLS_LIBRARY_FILE.read_text())
        except Exception:
            pass
    return {"skills": []}


def _load_custom_agents() -> dict:
    if CUSTOM_AGENTS_FILE.exists():
        try:
            return json.loads(CUSTOM_AGENTS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_custom_agents(agents: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOM_AGENTS_FILE.write_text(json.dumps(agents, indent=2))


def _build_system_prompt(name: str, skill_ids: list, library: dict) -> str:
    skills_map = {s["id"]: s for s in library.get("skills", [])}
    lines = [f"You are {name}, a specialised AI assistant with the following expertise:", ""]
    for sid in skill_ids:
        s = skills_map.get(sid)
        if s:
            lines.append(f"- **{s['name']}** ({s['category']}): {s['description']}")
        else:
            lines.append(f"- {sid}")
    lines += ["", "Apply your full expertise when responding. Be precise, actionable, and thorough."]
    return "\n".join(lines)


@app.get("/api/agents/custom")
def list_custom_agents():
    agents = _load_custom_agents()
    result = []
    for a in agents.values():
        result.append({
            "id": a["id"],
            "name": a["name"],
            "description": a.get("description", ""),
            "skills": a.get("skills", []),
            "skill_count": len(a.get("skills", [])),
            "created_at": a.get("created_at", ""),
            "updated_at": a.get("updated_at", ""),
        })
    return JSONResponse({"agents": result})


@app.post("/api/agents/custom")
def create_custom_agent(payload: dict):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    skill_ids = [str(s).strip() for s in (payload.get("skills") or []) if str(s).strip()]
    description = (payload.get("description") or "").strip()

    library = _load_library()
    known_ids = {s["id"] for s in library.get("skills", [])}
    valid_ids = [s for s in skill_ids if s in known_ids][:20]
    unknown = [s for s in skill_ids if s not in known_ids]

    import re as _re
    agent_id = _re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    agents = _load_custom_agents()
    ts = now_iso()
    agent = {
        "id": agent_id,
        "name": name,
        "description": description,
        "skills": valid_ids,
        "created_at": agents.get(agent_id, {}).get("created_at", ts),
        "updated_at": ts,
        "system_prompt": _build_system_prompt(name, valid_ids, library),
    }
    agents[agent_id] = agent
    _save_custom_agents(agents)
    return JSONResponse({
        "ok": True,
        "id": agent_id,
        "skill_count": len(valid_ids),
        "unknown_skills": unknown,
    })


@app.delete("/api/agents/custom/{agent_id}")
def delete_custom_agent(agent_id: str):
    agents = _load_custom_agents()
    if agent_id not in agents:
        raise HTTPException(404, f"agent '{agent_id}' not found")
    del agents[agent_id]
    _save_custom_agents(agents)
    return JSONResponse({"ok": True})


@app.get("/api/agents/custom/{agent_id}")
def get_custom_agent(agent_id: str):
    agents = _load_custom_agents()
    if agent_id not in agents:
        raise HTTPException(404, f"agent '{agent_id}' not found")
    return JSONResponse(agents[agent_id])


# ─── Task Orchestration API ────────────────────────────────────────────────────

AGENT_CAPS_FILE = CONFIG_DIR / "agent_capabilities.json"
TASK_PLANS_FILE = CONFIG_DIR / "task_plans.json"
AGENT_TASKS_DIR = STATE_DIR / "agent_tasks"


def _load_agent_capabilities() -> dict:
    if not AGENT_CAPS_FILE.exists():
        return {}
    try:
        return json.loads(AGENT_CAPS_FILE.read_text())
    except Exception:
        return {}


def _load_task_plans() -> list:
    if not TASK_PLANS_FILE.exists():
        return []
    try:
        return json.loads(TASK_PLANS_FILE.read_text())
    except Exception:
        return []


def _save_task_plans(plans: list) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TASK_PLANS_FILE.write_text(json.dumps(plans, indent=2))


@app.post("/api/task/submit")
def submit_task(payload: dict):
    """Submit a task for multi-agent orchestration via chatlog."""
    description = (payload.get("description") or "").strip()
    if not description:
        raise HTTPException(400, "description required")

    # Write to chatlog so task-orchestrator picks it up
    task_msg = f"task {description}"
    entry = {"ts": now_iso(), "type": "user", "message": task_msg}
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    import re as _re
    task_id = _re.sub(r"[^a-z0-9]", "", description[:8].lower())
    return JSONResponse({"ok": True, "task_id": task_id, "message": f"Task submitted: {description[:60]}"})


@app.post("/api/task/cancel")
def cancel_task():
    """Cancel the currently running task plan."""
    plans = _load_task_plans()
    for p in plans:
        if p.get("status") in ("running", "planning"):
            p["status"] = "cancelled"
            p["completed_at"] = now_iso()
            _save_task_plans(plans)
            return JSONResponse({"ok": True, "cancelled_id": p["id"]})
    return JSONResponse({"ok": False, "message": "No active task found"})


@app.get("/api/task/list")
def list_tasks():
    """List all task plans (active and history)."""
    plans = _load_task_plans()
    return JSONResponse({"plans": plans[:20]})


@app.get("/api/task/status/{task_id}")
def get_task_status(task_id: str):
    """Get status of a specific task plan."""
    plans = _load_task_plans()
    for p in plans:
        if p.get("id") == task_id:
            return JSONResponse(p)
    raise HTTPException(404, f"task '{task_id}' not found")


@app.get("/api/agents")
def get_all_agents():
    """Get all 20 agents with capabilities and running status."""
    capabilities = _load_agent_capabilities()
    agents_config = capabilities.get("agents", {})

    result = []
    for agent_id, info in agents_config.items():
        pid_file = AI_HOME / "run" / f"{agent_id}.pid"
        running = False
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                running = True
            except Exception:
                pass

        # Get current state if available
        state_file = STATE_DIR / f"{agent_id}.state.json"
        current_task = None
        if state_file.exists():
            try:
                st = json.loads(state_file.read_text())
                current_task = st.get("active_plan_title") or st.get("current_task")
            except Exception:
                pass

        result.append({
            "id": agent_id,
            "description": info.get("description", ""),
            "category": info.get("category", ""),
            "skills": info.get("skills", []),
            "commands": info.get("commands", []),
            "specialties": info.get("specialties", []),
            "parallel_capable": info.get("parallel_capable", True),
            "running": running,
            "current_task": current_task,
        })

    return JSONResponse({"agents": result, "total": len(result)})


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
