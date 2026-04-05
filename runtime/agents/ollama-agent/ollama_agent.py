"""Ollama Local AI Agent — privacy-first local LLM chat interface.

Runs a FastAPI web UI on port 8789 for interactive chat with a local Ollama
model.  All processing happens on your machine; no data ever leaves.

Accessible via WhatsApp: send `switch to ollama-agent` to activate.
Web UI: http://127.0.0.1:8789

Configuration (in ~/.ai-employee/config/ollama-agent.env):
    OLLAMA_HOST         — Ollama server URL (default: http://localhost:11434)
    OLLAMA_MODEL        — model name       (default: llama3.2)
    OLLAMA_AGENT_HOST   — bind address     (default: 127.0.0.1)
    OLLAMA_AGENT_PORT   — port             (default: 8789)
"""
import os
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_AGENT_HOST = os.environ.get("OLLAMA_AGENT_HOST", "127.0.0.1")
OLLAMA_AGENT_PORT = int(os.environ.get("OLLAMA_AGENT_PORT", "8789"))
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
SYSTEM_PROMPT = os.environ.get(
    "OLLAMA_SYSTEM_PROMPT",
    "You are a helpful AI assistant running locally on the user's machine. "
    "You excel at reasoning, analysis, coding, and creative tasks. "
    "All processing happens locally — no data leaves the user's device. "
    "Be concise but thorough.",
)

app = FastAPI(title="Ollama Local AI Agent")

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Ollama Local AI Agent</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:24px}
    h1{color:#34d399;margin-bottom:4px;font-size:1.6em}
    .badge{display:inline-block;background:#064e3b;color:#6ee7b7;padding:4px 14px;border-radius:20px;font-size:.85em;margin-bottom:20px}
    .chat-wrap{max-width:860px;margin:0 auto}
    #chat-log{min-height:200px;max-height:460px;overflow-y:auto;border:1px solid #334155;border-radius:10px;padding:12px;background:#0a1628;margin-bottom:14px}
    .msg{padding:10px 14px;border-radius:8px;margin-bottom:10px;max-width:85%;line-height:1.5;white-space:pre-wrap;word-break:break-word}
    .msg.user{background:#1e3a5f;margin-left:auto;text-align:right}
    .msg.bot{background:#0d2a1e;border:1px solid #164e35}
    .msg .ts{font-size:.72em;opacity:.55;margin-top:4px}
    .input-row{display:flex;gap:10px;align-items:flex-end}
    textarea{flex:1;background:#1e293b;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:10px 14px;font-size:.95em;resize:vertical;min-height:72px}
    button{background:linear-gradient(135deg,#059669,#065f46);color:#fff;border:none;padding:10px 22px;border-radius:8px;cursor:pointer;font-size:.9em;white-space:nowrap}
    button:hover{opacity:.88}
    button.clear{background:#1e293b;border:1px solid #334155;color:#94a3b8;margin-top:8px}
    .status-bar{font-size:.82em;color:#64748b;margin-top:8px;min-height:18px}
    .info-row{display:flex;gap:12px;font-size:.82em;color:#4ade80;margin-bottom:14px;flex-wrap:wrap}
  </style>
</head>
<body>
<div class="chat-wrap">
  <h1>&#x1F999; Ollama Local AI Agent</h1>
  <div class="badge" id="badge">Checking Ollama...</div>
  <div class="info-row" id="info-row"></div>
  <div id="chat-log"><p style="color:#4b5563;padding:4px">No messages yet. Start a conversation!</p></div>
  <div class="input-row">
    <textarea id="q" placeholder="Ask anything — runs entirely on your machine, no data leaves!"></textarea>
    <button onclick="ask()" id="send-btn">&#x1F680; Send</button>
  </div>
  <div class="status-bar" id="status"></div>
  <button class="clear" onclick="clearHistory()">&#x1F5D1; Clear History</button>
</div>
<script>
const log = document.getElementById('chat-log');
let empty = true;
function addMsg(role, text, ts){
  if(empty){ log.innerHTML=''; empty=false; }
  const d=document.createElement('div');
  d.className='msg '+role;
  const safeText=text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
  const safeTs=(ts||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  d.innerHTML='<div>'+safeText+'</div><div class="ts">'+safeTs+'</div>';
  log.appendChild(d);
  log.scrollTop=log.scrollHeight;
}
async function ask(){
  const q=document.getElementById('q').value.trim();
  if(!q) return;
  document.getElementById('q').value='';
  document.getElementById('status').textContent='Processing locally...';
  document.getElementById('send-btn').disabled=true;
  addMsg('user', q, new Date().toLocaleTimeString());
  const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
  const d=await r.json();
  document.getElementById('send-btn').disabled=false;
  if(d.answer){
    addMsg('bot', d.answer, new Date().toLocaleTimeString());
    document.getElementById('status').textContent='Model: '+d.model+' (local, private)';
  } else {
    addMsg('bot', '⚠️ '+(d.error||'Unknown error'), new Date().toLocaleTimeString());
    document.getElementById('status').textContent='Error';
  }
}
async function clearHistory(){
  await fetch('/api/clear',{method:'POST'});
  log.innerHTML='<p style="color:#4b5563;padding:4px">History cleared.</p>';
  empty=false;
  document.getElementById('status').textContent='';
}
async function loadInfo(){
  const r=await fetch('/api/info');
  const d=await r.json();
  document.getElementById('badge').textContent='Model: '+d.model+' | Ready: '+(d.ready?'✅ Yes':'❌ No');
  if(!d.ready){
    document.getElementById('info-row').innerHTML='<span style="color:#f87171">Ollama not reachable at '+d.host+'. Run: <code>ollama serve</code> &amp; <code>ollama pull '+d.model+'</code></span>';
  } else {
    document.getElementById('info-row').innerHTML='<span>Host: '+d.host+'</span><span>&#x1F512; Private — nothing leaves your machine</span>';
  }
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}});
loadInfo();
</script>
</body>
</html>"""

_history: list = []


def _ollama_ready() -> bool:
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/api/info")
def info() -> JSONResponse:
    return JSONResponse({
        "model": OLLAMA_MODEL,
        "host": OLLAMA_HOST,
        "ready": _ollama_ready(),
    })


@app.post("/api/ask")
def ask(payload: dict) -> JSONResponse:
    q = (payload or {}).get("question", "").strip()
    if not q:
        return JSONResponse({"error": "Empty question"}, status_code=400)

    _history.append({"role": "user", "content": q})
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + _history
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("message", {}).get("content", "No response").strip()
        _history.append({"role": "assistant", "content": answer})
        return JSONResponse({"question": q, "answer": answer, "model": OLLAMA_MODEL})
    except requests.exceptions.ConnectionError:
        _history.pop()
        return JSONResponse({
            "error": (
                f"Cannot connect to Ollama at {OLLAMA_HOST}. "
                "Is Ollama running? Run: ollama serve"
            ),
            "hint": f"Then pull your model: ollama pull {OLLAMA_MODEL}",
        }, status_code=503)
    except Exception as exc:
        _history.pop()
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/clear")
def clear_history() -> JSONResponse:
    global _history
    _history = []
    return JSONResponse({"status": "cleared"})


if __name__ == "__main__":
    print(f"[ollama-agent] Starting on http://{OLLAMA_AGENT_HOST}:{OLLAMA_AGENT_PORT}")
    print(f"[ollama-agent] Ollama host: {OLLAMA_HOST}  model: {OLLAMA_MODEL}")
    uvicorn.run(app, host=OLLAMA_AGENT_HOST, port=OLLAMA_AGENT_PORT)
