"""Gemma Local AI Agent — Google open-source model chat interface.

Runs a FastAPI web UI on port 8793 for interactive chat with a Google Gemma
model.  Two backends are supported:

  1. Local via Ollama (default, completely free & private):
       ollama pull gemma3
       ollama serve
     Set GEMMA_VIA_OLLAMA=1 (default) in config.

  2. Google AI Studio free-tier API:
       Get a free key at https://aistudio.google.com/app/apikey
     Set GOOGLE_API_KEY=<key> and GEMMA_VIA_OLLAMA=0 in config.

Web UI: http://127.0.0.1:8793

Configuration (in ~/.ai-employee/config/gemma-agent.env):
    OLLAMA_HOST           — Ollama server URL (default: http://localhost:11434)
    GEMMA_MODEL           — Gemma model for Ollama (default: gemma3)
    GEMMA_VIA_OLLAMA      — "1" to use local Ollama, "0" to use Google AI Studio (default: 1)
    GOOGLE_API_KEY        — Google AI Studio API key (for cloud backend)
    GEMMA_CLOUD_MODEL     — Gemma model via Google AI Studio (default: gemma-3-27b-it)
    GEMMA_AGENT_HOST      — bind address (default: 127.0.0.1)
    GEMMA_AGENT_PORT      — port (default: 8793)
    GEMMA_TIMEOUT         — request timeout in seconds (default: 120)
    ACTIVE_AI_PROVIDER    — set to "gemma" to make all sub-agents use this provider
"""
import json
import logging
import os
import urllib.request
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma3")
GEMMA_VIA_OLLAMA: bool = os.environ.get("GEMMA_VIA_OLLAMA", "1").strip().lower() not in (
    "0", "false", "no"
)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMMA_CLOUD_MODEL = os.environ.get("GEMMA_CLOUD_MODEL", "gemma-3-27b-it")
GEMMA_AGENT_HOST = os.environ.get("GEMMA_AGENT_HOST", "127.0.0.1")
GEMMA_AGENT_PORT = int(os.environ.get("GEMMA_AGENT_PORT", "8793"))
GEMMA_TIMEOUT = int(os.environ.get("GEMMA_TIMEOUT", "120"))
SYSTEM_PROMPT = os.environ.get(
    "GEMMA_SYSTEM_PROMPT",
    "You are a helpful AI assistant powered by Google Gemma, a free open-source model. "
    "You excel at creative writing, reasoning, coding, and general conversation. "
    "Be concise but thorough.",
)

app = FastAPI(title="Gemma AI Agent")
logger = logging.getLogger("gemma_agent")

_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Gemma AI Agent</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:24px}
    h1{color:#60a5fa;margin-bottom:4px;font-size:1.6em}
    .badge{display:inline-block;background:#1e3a5f;color:#93c5fd;padding:4px 14px;border-radius:20px;font-size:.85em;margin-bottom:20px}
    .chat-wrap{max-width:860px;margin:0 auto}
    #chat-log{min-height:200px;max-height:460px;overflow-y:auto;border:1px solid #334155;border-radius:10px;padding:12px;background:#0a1628;margin-bottom:14px}
    .msg{padding:10px 14px;border-radius:8px;margin-bottom:10px;max-width:85%;line-height:1.5;white-space:pre-wrap;word-break:break-word}
    .msg.user{background:#1e3a5f;margin-left:auto;text-align:right}
    .msg.bot{background:#0d1f3e;border:1px solid #1e40af}
    .msg .ts{font-size:.72em;opacity:.55;margin-top:4px}
    .input-row{display:flex;gap:10px;align-items:flex-end}
    textarea{flex:1;background:#1e293b;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:10px 14px;font-size:.95em;resize:vertical;min-height:72px}
    button{background:linear-gradient(135deg,#2563eb,#1d4ed8);color:#fff;border:none;padding:10px 22px;border-radius:8px;cursor:pointer;font-size:.9em;white-space:nowrap}
    button:hover{opacity:.88}
    button.clear{background:#1e293b;border:1px solid #334155;color:#94a3b8;margin-top:8px}
    .status-bar{font-size:.82em;color:#64748b;margin-top:8px;min-height:18px}
    .info-row{display:flex;gap:12px;font-size:.82em;color:#60a5fa;margin-bottom:14px;flex-wrap:wrap}
    .tag{background:#1e3a5f;border-radius:12px;padding:2px 10px;font-size:.8em}
  </style>
</head>
<body>
<div class="chat-wrap">
  <h1>&#x1F4A1; Gemma AI Agent</h1>
  <div class="badge" id="badge">Checking Gemma...</div>
  <div class="info-row" id="info-row"></div>
  <div id="chat-log"><p style="color:#4b5563;padding:4px">No messages yet. Start a conversation!</p></div>
  <div class="input-row">
    <textarea id="q" placeholder="Ask anything — powered by Google Gemma (free &amp; open-source)"></textarea>
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
  const safeText=text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/\n/g,'<br>');
  const safeTs=(ts||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  d.innerHTML='<div>'+safeText+'</div><div class="ts">'+safeTs+'</div>';
  log.appendChild(d);
  log.scrollTop=log.scrollHeight;
}
async function ask(){
  const q=document.getElementById('q').value.trim();
  if(!q) return;
  document.getElementById('q').value='';
  document.getElementById('status').textContent='Thinking...';
  document.getElementById('send-btn').disabled=true;
  addMsg('user', q, new Date().toLocaleTimeString());
  const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
  const d=await r.json();
  document.getElementById('send-btn').disabled=false;
  if(d.answer){
    addMsg('bot', d.answer, new Date().toLocaleTimeString());
    document.getElementById('status').textContent='Model: '+d.model+' | Backend: '+d.backend;
  } else {
    addMsg('bot', '\u26a0\ufe0f '+(d.error||'Unknown error'), new Date().toLocaleTimeString());
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
  document.getElementById('badge').textContent='Gemma | Model: '+d.model+' | Ready: '+(d.ready?'\u2705 Yes':'\u274c No');
  if(!d.ready){
    document.getElementById('info-row').innerHTML='<span style="color:#f87171">'+d.status_message+'</span>';
  } else {
    document.getElementById('info-row').innerHTML=
      '<span class="tag">Backend: '+d.backend+'</span>'+
      '<span class="tag">&#x1F194; Free &amp; Open Source</span>'+
      (d.backend==='ollama' ? '<span class="tag">&#x1F512; Local &amp; Private</span>' : '<span class="tag">&#x2601; Google AI Studio Free Tier</span>');
  }
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}});
loadInfo();
</script>
</body>
</html>"""

_history: list = []


def _gemma_ready() -> tuple[bool, str, str]:
    """Check if Gemma is available. Returns (ready, backend, status_message)."""
    if GEMMA_VIA_OLLAMA:
        try:
            r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
            if r.status_code == 200:
                tags = r.json().get("models", [])
                has_gemma = any(
                    m.get("name", "").split(":")[0] == GEMMA_MODEL.split(":")[0]
                    for m in tags
                )
                if has_gemma:
                    return True, "ollama", "ready"
                return (
                    False,
                    "ollama",
                    f"Gemma model not found. Run: ollama pull {GEMMA_MODEL}",
                )
            return False, "ollama", f"Ollama returned status {r.status_code}"
        except Exception:
            return (
                False,
                "ollama",
                f"Cannot connect to Ollama at {OLLAMA_HOST}. Run: ollama serve",
            )
    # Google AI Studio backend
    if GOOGLE_API_KEY:
        return True, "google_ai_studio", "ready"
    return False, "google_ai_studio", "Set GOOGLE_API_KEY in ~/.ai-employee/.env"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML


@app.get("/api/info")
def info() -> JSONResponse:
    ready, backend, status_message = _gemma_ready()
    model = GEMMA_MODEL if GEMMA_VIA_OLLAMA else GEMMA_CLOUD_MODEL
    return JSONResponse({
        "model": model,
        "backend": backend,
        "ready": ready,
        "status_message": status_message,
        "via_ollama": GEMMA_VIA_OLLAMA,
    })


def _ask_ollama(messages: list) -> tuple[str, str]:
    """Query Gemma via local Ollama. Returns (answer, model)."""
    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json={"model": GEMMA_MODEL, "messages": messages, "stream": False},
        timeout=GEMMA_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    answer = data.get("message", {}).get("content", "No response").strip()
    return answer, GEMMA_MODEL


def _ask_google_ai_studio(messages: list) -> tuple[str, str]:
    """Query Gemma via Google AI Studio free-tier API. Returns (answer, model)."""
    contents = []
    for msg in messages:
        role = msg["role"]
        if role == "system":
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            contents.append({"role": "model", "parts": [{"text": "Understood."}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": msg["content"]}]})
        else:
            contents.append({"role": "user", "parts": [{"text": msg["content"]}]})

    payload = json.dumps({"contents": contents}).encode("utf-8")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMMA_CLOUD_MODEL}:generateContent?key={GOOGLE_API_KEY}"
    )
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "AI-Employee/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=GEMMA_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))

    answer = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "No response")
        .strip()
    )
    return answer, GEMMA_CLOUD_MODEL


@app.post("/api/ask")
def ask(payload: dict) -> JSONResponse:
    q = (payload or {}).get("question", "").strip()
    if not q:
        return JSONResponse({"error": "Empty question"}, status_code=400)

    _history.append({"role": "user", "content": q})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + _history

    try:
        if GEMMA_VIA_OLLAMA:
            answer, model = _ask_ollama(messages)
            backend = "ollama"
        elif GOOGLE_API_KEY:
            answer, model = _ask_google_ai_studio(messages)
            backend = "google_ai_studio"
        else:
            _history.pop()
            return JSONResponse(
                {
                    "error": (
                        "No Gemma backend configured. "
                        "Either start Ollama and run `ollama pull gemma3`, "
                        "or set GOOGLE_API_KEY in ~/.ai-employee/.env"
                    )
                },
                status_code=503,
            )

        _history.append({"role": "assistant", "content": answer})
        return JSONResponse({"question": q, "answer": answer, "model": model, "backend": backend})

    except requests.exceptions.ConnectionError:
        _history.pop()
        return JSONResponse(
            {
                "error": (
                    f"Cannot connect to Ollama at {OLLAMA_HOST}. "
                    "Is Ollama running? Run: ollama serve"
                ),
                "hint": f"Then pull the model: ollama pull {GEMMA_MODEL}",
            },
            status_code=503,
        )
    except Exception:
        _history.pop()
        logger.exception("gemma-agent: unexpected error processing request")
        return JSONResponse({"error": "An internal error occurred. Check server logs."}, status_code=500)


@app.post("/api/clear")
def clear_history() -> JSONResponse:
    global _history
    _history = []
    return JSONResponse({"status": "cleared"})


@app.get("/api/set_active_provider")
def set_active_provider(provider: str = "") -> JSONResponse:
    """Convenience endpoint: set ACTIVE_AI_PROVIDER so sub-agents inherit this provider.

    Call with ?provider=gemma to make all sub-agents use Gemma.
    Call with ?provider= (empty) to restore auto-routing.
    """
    import os as _os
    _os.environ["ACTIVE_AI_PROVIDER"] = provider.strip().lower()
    return JSONResponse({"active_ai_provider": _os.environ.get("ACTIVE_AI_PROVIDER", "")})


if __name__ == "__main__":
    print(f"[gemma-agent] Starting on http://{GEMMA_AGENT_HOST}:{GEMMA_AGENT_PORT}")
    print(f"[gemma-agent] Backend: {'Ollama' if GEMMA_VIA_OLLAMA else 'Google AI Studio'}")
    model_display = GEMMA_MODEL if GEMMA_VIA_OLLAMA else GEMMA_CLOUD_MODEL
    print(f"[gemma-agent] Model: {model_display}")
    uvicorn.run(app, host=GEMMA_AGENT_HOST, port=GEMMA_AGENT_PORT)
