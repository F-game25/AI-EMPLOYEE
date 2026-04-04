# _legacy/

Dead code archived here for one release cycle before permanent deletion.
Do **not** import from this directory in production code.

| File | Archived from | Reason |
|------|---------------|--------|
| `query_ai_for_agent_v1.py` | `ai-router/ai_router.py` | Superseded by the `agent_type` variant (v2). Both had the same function name so Python silently discarded v1 at import time. |
