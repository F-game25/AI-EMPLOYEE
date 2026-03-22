import os
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "run" / "problem-solver.state.json"
PORT = int(os.environ.get("PROBLEM_SOLVER_UI_PORT", "8787"))
HOST = os.environ.get("PROBLEM_SOLVER_UI_HOST", "127.0.0.1")

app = FastAPI()

INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Problem Solver UI</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; max-width: 1000px; }
    textarea { width: 100%; height: 90px; }
    pre { background:#f6f8fa; padding:12px; overflow:auto; }
    .row { display:flex; gap:12px; align-items:flex-start; }
    .col { flex:1; }
  </style>
</head>
<body>
  <h1>Problem Solver UI</h1>
  <p>Status + ask. (Improvements tab comes in the next rewrite after your AII signal.)</p>

  <div class="row">
    <div class="col">
      <h3>Ask</h3>
      <textarea id="q" placeholder="Describe the problem..."></textarea>
      <button onclick="ask()">Send</button>
      <h3>Answer</h3>
      <pre id="a"></pre>
    </div>
    <div class="col">
      <h3>System status</h3>
      <button onclick="refresh()">Refresh</button>
      <pre id="s"></pre>
    </div>
  </div>

<script>
async function refresh(){
  const r = await fetch('/api/status');
  document.getElementById('s').textContent = JSON.stringify(await r.json(), null, 2);
}
async function ask(){
  const q = document.getElementById('q').value;
  const r = await fetch('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:q})});
  document.getElementById('a').textContent = JSON.stringify(await r.json(), null, 2);
}
refresh();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML

@app.get("/api/status")
def status():
    if STATE_FILE.exists():
        return JSONResponse(json.loads(STATE_FILE.read_text()))
    return JSONResponse({"ts": None, "bots": [], "note": "No state file yet. Start problem-solver."})

@app.post("/api/ask")
def ask(payload: dict):
    q = (payload or {}).get("question", "").strip()
    if not q:
        return JSONResponse({"error": "Empty question"}, status_code=400)
    return JSONResponse({
        "question": q,
        "note": "Stub response. After your AII signal, this will use local Ollama first, bridge as fallback."
    })

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
