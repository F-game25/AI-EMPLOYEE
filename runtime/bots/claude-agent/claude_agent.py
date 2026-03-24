"""Claude AI Agent — Anthropic Claude cloud chat interface.

Runs a FastAPI web UI on port 8788 for multi-turn conversations with
Anthropic Claude.  Used as a cloud fallback when local Ollama cannot
handle a task.

Accessible via WhatsApp: send `switch to claude-agent` to activate.
Web UI: http://127.0.0.1:8788

Configuration (in ~/.ai-employee/config/claude-agent.env):
    ANTHROPIC_API_KEY   — your Anthropic key (also in ~/.ai-employee/.env)
    CLAUDE_MODEL        — model name (default: claude-opus-4-5)
    CLAUDE_AGENT_HOST   — bind address (default: 127.0.0.1)
    CLAUDE_AGENT_PORT   — port (default: 8788)
    CLAUDE_MAX_TOKENS   — max tokens per response (default: 4096)
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")
CLAUDE_AGENT_HOST = os.environ.get("CLAUDE_AGENT_HOST", "127.0.0.1")
CLAUDE_AGENT_PORT = int(os.environ.get("CLAUDE_AGENT_PORT", "8788"))
MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "4096"))
SYSTEM_PROMPT = os.environ.get(
    "CLAUDE_SYSTEM_PROMPT",
    "You are a highly capable AI assistant powered by Anthropic Claude. "
    "You excel at reasoning, analysis, creative writing, and code. "
    "Be concise but thorough. Always be helpful, honest, and harmless.",
)

try:
    import anthropic as _anthropic_module
    _client = _anthropic_module.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except ImportError:
    _client = None
    _anthropic_module = None

app = FastAPI(title="Claude AI Agent")

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Claude AI Agent</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:24px}
    h1{color:#a78bfa;margin-bottom:4px;font-size:1.6em}
    .badge{display:inline-block;background:#312e81;color:#a5b4fc;padding:4px 14px;border-radius:20px;font-size:.85em;margin-bottom:20px}
    .chat-wrap{max-width:860px;margin:0 auto}
    #chat-log{min-height:200px;max-height:460px;overflow-y:auto;border:1px solid #334155;border-radius:10px;padding:12px;background:#0a0a1a;margin-bottom:14px}
    .msg{padding:10px 14px;border-radius:8px;margin-bottom:10px;max-width:85%;line-height:1.5;white-space:pre-wrap;word-break:break-word}
    .msg.user{background:#312e81;margin-left:auto;text-align:right}
    .msg.bot{background:#1e1b4b;border:1px solid #3730a3}
    .msg .ts{font-size:.72em;opacity:.55;margin-top:4px}
    .input-row{display:flex;gap:10px;align-items:flex-end}
    textarea{flex:1;background:#1e293b;border:1px solid #334155;color:#e2e8f0;border-radius:8px;padding:10px 14px;font-size:.95em;resize:vertical;min-height:72px}
    button{background:linear-gradient(135deg,#7c3aed,#4f46e5);color:#fff;border:none;padding:10px 22px;border-radius:8px;cursor:pointer;font-size:.9em;white-space:nowrap}
    button:hover{opacity:.88}
    button.clear{background:#1e293b;border:1px solid #334155;color:#94a3b8;margin-top:8px}
    .status-bar{font-size:.82em;color:#64748b;margin-top:8px;min-height:18px}
    .info-row{font-size:.82em;color:#818cf8;margin-bottom:14px}
  </style>
</head>
<body>
<div class="chat-wrap">
  <h1>&#x1F916; Claude AI Agent</h1>
  <div class="badge" id="badge">Loading...</div>
  <div class="info-row" id="info-row"></div>
  <div id="chat-log"><p style="color:#4b5563;padding:4px">No messages yet. Start a conversation!</p></div>
  <div class="input-row">
    <textarea id="q" placeholder="Ask Claude anything — complex reasoning, analysis, code, creative writing..."></textarea>
    <button onclick="ask()" id="send-btn">&#x2728; Send</button>
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
  document.getElementById('status').textContent='Thinking...';
  document.getElementById('send-btn').disabled=true;
  addMsg('user', q, new Date().toLocaleTimeString());
  const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
  const d=await r.json();
  document.getElementById('send-btn').disabled=false;
  if(d.answer){
    addMsg('bot', d.answer, new Date().toLocaleTimeString());
    const u=d.usage||{};
    document.getElementById('status').textContent='Model: '+d.model+' | In: '+(u.input_tokens||'?')+' | Out: '+(u.output_tokens||'?')+' tokens';
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
    document.getElementById('info-row').innerHTML='<span style="color:#f87171">ANTHROPIC_API_KEY not set. Add it to ~/.ai-employee/.env and restart.</span>';
  } else {
    document.getElementById('info-row').innerHTML='Model: '+d.model+' | Max tokens: '+d.max_tokens;
  }
}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}});
loadInfo();
</script>
</body>
</html>"""

_history: list = []


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/api/info")
def info() -> JSONResponse:
    return JSONResponse({
        "model": CLAUDE_MODEL,
        "ready": _client is not None,
        "api_key_set": bool(ANTHROPIC_API_KEY),
        "max_tokens": MAX_TOKENS,
    })


@app.post("/api/ask")
def ask(payload: dict) -> JSONResponse:
    global _history
    q = (payload or {}).get("question", "").strip()
    if not q:
        return JSONResponse({"error": "Empty question"}, status_code=400)
    if not _client:
        return JSONResponse({
            "error": (
                "Anthropic client not available. "
                "Set ANTHROPIC_API_KEY in ~/.ai-employee/.env and restart claude-agent."
            ),
            "hint": "Add: ANTHROPIC_API_KEY=sk-ant-... to ~/.ai-employee/.env",
        }, status_code=503)

    _history.append({"role": "user", "content": q})
    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=_history,
        )
        answer = response.content[0].text
        _history.append({"role": "assistant", "content": answer})
        return JSONResponse({
            "question": q,
            "answer": answer,
            "model": CLAUDE_MODEL,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        })
    except Exception as exc:
        _history.pop()
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/clear")
def clear_history() -> JSONResponse:
    global _history
    _history = []
    return JSONResponse({"status": "cleared"})


if __name__ == "__main__":
    print(f"[claude-agent] Starting on http://{CLAUDE_AGENT_HOST}:{CLAUDE_AGENT_PORT}")
    print(f"[claude-agent] Model: {CLAUDE_MODEL}  API key set: {bool(ANTHROPIC_API_KEY)}")
    uvicorn.run(app, host=CLAUDE_AGENT_HOST, port=CLAUDE_AGENT_PORT)
