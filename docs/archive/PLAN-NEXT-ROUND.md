# PLAN VAN AANPAK — RONDE 3
## Sidebar Discoverability · Research v2 · Knowledge & Neural Backend · Model Management (echt werkend)

**Datum:** 2026-05-18
**Status:** Voorstel — wacht op goedkeuring per fase voor uitvoering

---

## Context

Vorige rondes zijn opgeleverd (ModelsPage scaffolding, Settings 9 tabs, KnowledgePage/NeuralPage rendering fixes, cinematic eye, EyeStage HUD). De UI ziet er nu uit zoals het hoort, maar **de meeste features achter de UI zijn nog scaffolding** — niet echt functioneel. Deze ronde maakt ze echt.

5 concrete problemen, allemaal teruggeleid naar de ROOT cause met code-paden:

| # | Probleem | Root cause | Impact |
|---|---|---|---|
| 1 | AscendForge en Blacklight niet in sidebar | AscendForgePage bestaat (1052 LOC) + is geregistreerd in Dashboard.jsx, maar niet in `NAV_GROUPS` van Sidebar.jsx. Blacklight zit als tab in SecurityPanel — onvindbaar. | Twee complete features die onbereikbaar zijn voor de gebruiker. |
| 2 | Research engine werkt niet als gevraagd | Bestaat als single-phase pipeline (query → klaar). Heeft geen "discover sources first" endpoint. User wil: candidate websites tonen → selectie → execute. | Onbruikbaar workflow voor echte research. |
| 3 | Neural graph functioneert niet als bedoeld | `/api/brain/graph` faalt vaak (Python timeout 1s) → seed-fallback van 12 hardcoded nodes wordt getoond. brainStore is in-memory only — data weg na reload. Geen live updates. | Lijkt te werken (graph rendert) maar toont nepdata. |
| 4 | Knowledge functioneert niet als bedoeld | Schema-mismatch: `knowledge_store.json` heeft `{topics:{...}}`, frontend verwacht `{entries:[]}`. Search is grep, geen vector search. Upload-endpoint is een stub die niets indexeert. | Knowledge entries komen er in, maar zijn nooit terug te vinden. |
| 5 | Model management is decoratief | `/api/settings/model-routing` PUT slaat op, maar **de orchestrator leest het bestand nooit**. Geen Ollama pull/list. Geen UI om main brain te veranderen. agent_capabilities.json heeft `model_routing` sectie die door niemand gebruikt wordt. | UI suggereert controle die er niet is. |

---

## Fase A — Sidebar discoverability (~30 min)

**Doel:** AscendForge en Blacklight zichtbaar/navigable maken zonder bestaande architectuur te breken.

### A.1 — AscendForge in sidebar

**File:** `frontend/src/components/layout/Sidebar.jsx`

Voeg toe aan de **OPERATIONS** groep (logische plek — forge is een werkbank/IDE workflow):

```js
{
  id: 'ascend-forge',
  label: 'ASCEND FORGE',
  sub: 'Build & deploy',
  icon: <ForgeIcon />,
}
```

Icon: hamer/aambeeld glyph (kan inline SVG zijn, ~12 LOC, of een bestaand symbool uit de huidige sidebar icons hergebruiken).

Route key `'ascend-forge'` matcht al de PAGES map entry in Dashboard.jsx — geen Dashboard.jsx wijziging nodig.

### A.2 — Blacklight als eigen route + bewaar SecurityPanel-tab

Twee strategieën, kies één:

**Optie A (aanbevolen):** Voeg een **standalone** sidebar entry toe die navigeert naar `/security?tab=blacklight` (deeplink naar de bestaande tab). Geen nieuwe page nodig, geen duplicate code. SecurityPanel leest de query-param en opent de juiste tab.

**Optie B:** Maak een echte `BlacklightPage.jsx` die de blacklight-specifieke onderdelen uit SecurityPanel haalt. Meer werk, splitst een mooi geintegreerde flow.

→ **Kies A.** Toevoegen aan SECURITY groep:

```js
{
  id: 'blacklight',
  label: 'BLACKLIGHT',
  sub: 'OSINT operations',
  icon: <BlacklightIcon />,
  route: '/security?tab=blacklight',
}
```

**File-edits:** `Sidebar.jsx` (+ ~30 LOC), `Dashboard.jsx` routing-helper (paar regels om query-param naar SecurityPanel door te geven), `SecurityPanel.jsx` (1 useEffect die `?tab=` leest en setActiveTab aanroept).

---

## Fase B — Research engine v2 (~3 uur)

**Doel:** 2-phase workflow — discover sources → user kiest → execute research op selectie.

### B.1 — Nieuwe backend endpoint: source discovery

**File:** `backend/routes/dashboard-api.js` (nieuwe route group)

```
POST /api/research/discover
  body: { query: string, max_sources?: number = 10 }
  response: { sources: [{ id, url, title, snippet, domain, trust_score, source_type }] }
```

Implementatie: roept de Python `AutoResearchAgent.discover_sources(query)` aan via de bestaande proxy naar `localhost:18790`. Python kant gebruikt search_web maar **slaat de stealth fetch + summarize over** — alleen URLs + snippets terug.

### B.2 — Python: nieuwe method `discover_sources`

**File:** `runtime/core/auto_research_agent.py`

Voeg toe naast bestaande `research()`:
```python
async def discover_sources(self, query: str, max_results: int = 10) -> List[SourceCandidate]:
    """Phase 1: return candidate sources without fetching/summarizing."""
    results = await self.search_web(query, num=max_results)
    return [SourceCandidate(
        id=hashlib.md5(r.url.encode()).hexdigest()[:12],
        url=r.url, title=r.title, snippet=r.snippet,
        domain=urlparse(r.url).netloc,
        trust_score=self.source_trust.get(urlparse(r.url).netloc, 0.5),
        source_type=classify_source_type(r.url),  # 'news' | 'docs' | 'forum' | 'social' | 'academic'
    ) for r in results]
```

### B.3 — Nieuwe backend endpoint: execute on selection

```
POST /api/research/execute
  body: { query: string, selected_source_ids: string[], depth?: 'shallow'|'normal'|'deep' = 'normal' }
  response: { session_id: string }   # WS pushes voor progress
```

Implementatie: roept `AutoResearchAgent.research_selected(query, urls, depth)` aan — bestaande pipeline maar geinjecteerde URL list ipv discover.

### B.4 — ResearchPage UI rebuild

**File:** `frontend/src/components/pages/ResearchPage.jsx`

Nieuwe flow met 3 panelen (links→rechts of stacked):

1. **Search panel** — query input + zoeken-knop → POST `/api/research/discover` → toont candidate list
2. **Source selection panel** — kaartjes per source:
   - URL + domein + trust score badge
   - Snippet preview
   - Checkbox om te selecteren
   - "Select all" / "Select high-trust only" quick actions
3. **Execute panel** — toont selectie count, depth-kiezer (shallow=3 hops, normal=6, deep=10), "Run research" knop → POST `/api/research/execute` → live progress via WS events `task:research_started`/`task:research_completed` (deze events bestaan al).

Hergebruik: `useLiveData`, `AsyncPanel`, `Panel`, `KPITile`, `LiveBadge` uit nexus-ui. Geen nieuwe primitives.

### B.5 — Source-trust integratie

`runtime/core/source_trust.py` + `runtime/config/source_trust.json` bestaan al per CLAUDE.md. Hergebruik in `discover_sources` — frontend toont badge per trust tier (>0.8=green, 0.5-0.8=gold, <0.5=red).

---

## Fase C — Neural graph + Knowledge backend echt functioneel maken (~4 uur)

### C.1 — Knowledge schema migratie

**File:** `state/knowledge_store.json` + `backend/routes/dashboard-api.js`

Probleem: store heeft `{topics: {...}}`, search verwacht `{entries: []}`.

Stap 1: schrijf migratie-script `scripts/migrate_knowledge_store.py`:
```python
old = json.load(open('state/knowledge_store.json'))
entries = []
for topic, items in old.get('topics', {}).items():
    for item in items:
        entries.append({
            'id': uuid.uuid4().hex[:12],
            'topic': topic,
            'content': item.get('content') or item.get('summary'),
            'source': item.get('source', 'migrated'),
            'importance': item.get('importance', 0.5),
            'ts': item.get('ts', time.time()),
        })
json.dump({'entries': entries, '_migrated': True}, open('state/knowledge_store.json', 'w'), indent=2)
```

Stap 2: search endpoint `/api/knowledge/search` aanpassen — werkt al op `entries` als die er is; alleen filter + grep verbeteren naar fuzzy match (Python `difflib.SequenceMatcher` of `rapidfuzz` als dep).

### C.2 — Vector search endpoint (knowledge)

**File:** `backend/routes/dashboard-api.js` + nieuw Python endpoint

```
POST /api/knowledge/search/semantic
  body: { query: string, top_k?: number = 10 }
  response: { entries: [{ ...entry, score: 0..1 }] }
```

Backend proxied naar Python `/api/knowledge/semantic_search` die de bestaande `memory_router.py` vector store gebruikt (CLAUDE.md noemt deze al). Als geen vector store actief: graceful fallback naar text-search met header `X-Search-Mode: text`.

Frontend: KnowledgePage krijgt toggle "semantic / keyword".

### C.3 — Knowledge upload echt indexeren

**File:** `runtime/agents/problem-solver-ui/server.py` (FastAPI op 18790)

Endpoint `/api/knowledge/upload` bestaat als stub. Maak echt:
1. Accepteer multipart upload
2. Detecteer type (txt/md/pdf/docx via mimetype)
3. Extract text (gebruik bestaande extractors of `pypdf`/`python-docx` — al in requirements-test.txt waarschijnlijk; check `requirements.txt`)
4. Chunk + embed via `engine/api.py:embed()` (al beschikbaar per CLAUDE.md)
5. Persist in vector store + append entry naar `knowledge_store.json`
6. Return `{ status: 'indexed', id, chunks_count }`

Frontend: upload progress state (al gepland, klein fixje in KnowledgePage).

### C.4 — Neural graph persistente backend

**File:** `runtime/neural_brain/graph_exporter.py` (nieuw, ~150 LOC)

Probleem: `/api/neural-brain/graph` is dood (1s timeout). brainStore is in-memory only.

Stap 1: nieuwe exporter die periodiek (elke 5s) een snapshot maakt van:
- Cognitive nodes uit `runtime/neural_brain/` LangGraph state
- Memory edges uit vector store recents
- Agent connections uit agent activity logs

Snapshot wordt geschreven naar `state/neural_graph_snapshot.json` (atomic via file_lock).

Stap 2: backend endpoint `/api/brain/graph` leest **eerst** snapshot file (snel, lokaal, geen Python timeout). Faalt alleen als file niet bestaat → start exporter on-demand.

Stap 3: WebSocket push `brain:graph` elke 5s wanneer snapshot bijgewerkt — frontend brainStore subscribet en updatet zonder polling.

Stap 4: NeuralNetworkPage's `isStaleFallback` blijft als safety net, maar zou nu vrijwel nooit moeten triggeren omdat lokale file read snel is.

### C.5 — Graph seed data wegnemen of duidelijk markeren

Als snapshot file leeg is op een verse install: NeuralNetworkPage toont nu het hardcoded seed graph. **Markeer dat expliciet** met een badge "DEMO DATA — start de Python brain om live data te zien". Niet stil tonen alsof het echt is.

---

## Fase D — Model management echt functioneel (~5 uur, grootste blok)

**Doel:** alles in de ModelsPage doet wat het belooft.

### D.1 — Ollama integratie: list + pull + delete

**File:** `backend/services/ollama_admin.js` (nieuw)

Wrappers rond Ollama HTTP API (`localhost:11434`):
```js
async function listLocalModels() {
  const r = await fetch(`${OLLAMA_HOST}/api/tags`)
  return r.json()  // { models: [{name, size, modified_at, digest}] }
}
async function pullModel(name, onProgress) {
  // POST /api/pull met name + stream:true — pipe progress events via SSE/WS
}
async function deleteModel(name) {
  return fetch(`${OLLAMA_HOST}/api/delete`, { method: 'DELETE', body: JSON.stringify({name}) })
}
async function showModel(name) {
  return fetch(`${OLLAMA_HOST}/api/show`, { method: 'POST', body: JSON.stringify({name}) })
}
```

Endpoints in `backend/routes/dashboard-api.js`:
- `GET /api/ollama/models` — list lokaal
- `POST /api/ollama/pull` — start pull, returnt session_id, progress via WS `ollama:pull_progress`
- `DELETE /api/ollama/models/:name`
- `GET /api/ollama/models/:name` — show details

### D.2 — Provider configuration page (echte add/remove)

**File:** `frontend/src/components/pages/ModelsPage.jsx` — PROVIDERS tab uitbreiden

Nieuwe sectie per provider:
- **Ollama**: lijst van geinstalleerde modellen (uit `/api/ollama/models`), per model: size, last-used, "delete" knop. Onderaan: input + "Pull new model" knop → toont progress bar via WS.
- **Anthropic**: input voor API key (al deels in settings), test-knop, **lijst beschikbare modellen** (statisch — claude-opus-4-7, sonnet-4-6, haiku-4-5). Toggle per model = "available for routing".
- **OpenAI**: idem als Anthropic. Voeg ook **echte runtime support** toe in `runtime/core/orchestrator.py` (`_call_openai`) — bestaat nu alleen in de UI, niet in Python.
- **OpenRouter**: idem, modellijst dynamisch via `https://openrouter.ai/api/v1/models`.
- **+ Add custom provider** knop voor zelf-gehoste OpenAI-compatible endpoints.

### D.3 — Maak routing-rules ECHT functioneel

**File:** `runtime/core/llm_router.py` (nieuw, ~120 LOC) + `runtime/core/orchestrator.py` (edit)

Probleem: `/api/settings/model-routing` slaat op maar wordt nooit gelezen.

Stap 1: nieuwe `LLMRouter` class:
```python
class LLMRouter:
    def __init__(self, routing_file='~/.ai-employee/model-routing.json'):
        self.routing_file = expand(routing_file)
        self._cache = None; self._mtime = 0
    
    def get_model_for(self, agent_id: str, default: str) -> tuple[str, str]:
        """Returns (provider, model) tuple."""
        config = self._load()  # reload als mtime nieuwer
        rule = config.get(agent_id) or config.get('_default')
        if not rule: return ('anthropic', default)
        return (rule['provider'], rule['model'])
```

Stap 2: `LLMClient` in orchestrator.py constructor neemt optioneel `agent_id` en gebruikt router:
```python
def __init__(self, agent_id: str | None = None):
    self.router = LLMRouter()
    self.agent_id = agent_id
    provider, model = self.router.get_model_for(agent_id, default_model_for_backend())
    self.provider = provider
    self.model = model
```

Stap 3: alle call-sites die `LLMClient()` aanroepen passen agent_id mee. Dit raakt veel files — gebruik grep `LLMClient(` om alle 15-20 sites te vinden en pas systematisch aan.

Stap 4: per-agent override schema voor `model-routing.json`:
```json
{
  "_default": { "provider": "anthropic", "model": "claude-sonnet-4-6" },
  "blacklight": { "provider": "anthropic", "model": "claude-opus-4-7" },
  "ascend-forge": { "provider": "anthropic", "model": "claude-sonnet-4-6" },
  "money-mode": { "provider": "ollama", "model": "llama3.2" }
}
```

### D.4 — Main AI brain switcher

**File:** ModelsPage PROVIDERS tab + nieuwe endpoint

Nieuwe section: "**MAIN AI BRAIN**" — dropdown van alle beschikbare modellen (uit alle providers) + "Apply" knop.

Endpoint:
```
PUT /api/settings/main-model
  body: { provider: string, model: string }
  → schrijft naar model-routing.json als `_default`
  → hot-reload: notify alle running LLMClient instances via in-process event
```

Hot reload: pubsub via bestaande `runtime/core/bus.py` SimpleMessageBus, kanaal `system:config_reload`. LLMClient subscribet en herinitialiseert provider+model.

### D.5 — Subsystems UI (AscendForge / Blacklight / MoneyMode model assignment)

**File:** ModelsPage ROUTING RULES tab — nieuw sectie "**SUBSYSTEMS**"

Lijst van bekende subsystems uit een nieuwe `runtime/config/subsystems.json`:
```json
[
  { "id": "ascend-forge", "label": "Ascend Forge", "description": "Build & deploy workflow agent" },
  { "id": "blacklight", "label": "Blacklight", "description": "OSINT & security automation" },
  { "id": "money-mode", "label": "Money Mode", "description": "Revenue pipelines" }
]
```

Per subsystem: dropdown met beschikbare modellen + Save → schrijft naar `model-routing.json` onder `subsystems.<id>`.

Subsystem-code (`runtime/agents/blacklight/blacklight.py`, etc.) leest via `LLMRouter` met agent_id = subsystem id.

### D.6 — MoneyMode bestaat niet als agent

Per exploration: `MoneyMode` wordt genoemd maar bestaat niet als subdirectory in `runtime/agents/`. Twee opties:
- **A:** Het is de `money_mode.py` orchestrator-pipeline in `runtime/core/money_mode.py`. Behandel als subsystem in subsystems.json, geen nieuwe agent nodig.
- **B:** Bouw een echte `money-mode` agent als de gebruiker dat wil.

→ **Kies A** voor deze ronde. Markeer B als toekomst.

---

## Fase E — Verificatie

1. **Sidebar:** /  → klik ASCEND FORGE → AscendForgePage rendert; klik BLACKLIGHT → SecurityPanel met blacklight-tab actief
2. **Research:** /research → query "X" → toont 10 candidate URLs → vink 3 aan → "Run" → live progress events → resultaten verschijnen
3. **Knowledge:** /knowledge → toont echte entries (na migratie); upload PDF → status 'indexed' → entry vindbaar in search; semantic toggle werkt
4. **Neural graph:** /neural-graph → toont LIVE data uit snapshot (geen "DEMO DATA" badge als python loopt); update zichtbaar als nieuwe reasoning chain start
5. **Models:**
   - Pull `llama3.2:1b` via UI → progress bar → verschijnt in lokale lijst
   - Stel routing: blacklight → claude-opus → start blacklight task → Python backend log toont gekozen model "claude-opus-4-7" voor die call
   - Wissel main brain naar ollama → nieuwe chat gebruikt Ollama (zichtbaar in /api/intelligence/llm-calls)

---

## Volgorde + tijdsinschatting

| Fase | Wat | Tijd | Kan parallel? |
|---|---|---|---|
| A | Sidebar 2 entries + deeplink | 30 min | Solo |
| B | Research v2 (3 endpoints + UI) | 3 uur | ✓ Agent 1 |
| C | Knowledge schema + vector + Neural snapshot | 4 uur | ✓ Agent 2 |
| D | Model management (5 sub-fases) | 5 uur | ✓ Agent 3 + 4 (split tussen Ollama-stuff en routing-stuff) |
| E | Smoke test + fixes | 1 uur | Solo |

**Totaal:** ~13 uur sequentieel, ~5-6 uur met 4 parallel agents.

---

## Risico's / aandachtspunten

1. **Migratie van knowledge_store.json is destructief** — eerst backup naar `.bak` voordat schema gewijzigd wordt
2. **Ollama pull is groot** (modellen van 2-30 GB) — UI moet niet timeouten, gebruik WS streaming progress
3. **Hot-reload van LLMClient** kan races geven als een call midden in execution zit — implementeer "drain & swap" pattern: nieuwe calls krijgen nieuw model, lopende calls maken af met oud
4. **OpenRouter API key** is gevoelig — moet door dezelfde gateway-secret encryption als andere secrets (zie `backend/security/`)
5. **Vector store dependency** — als pinecone/chroma/weaviate niet draait, semantic search faalt. Fallback naar text moet duidelijk gecommuniceerd via header
