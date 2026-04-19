"""Agent Monitor — Streamlit panel showing running agents and their stats.

Renders:
- A table of known agents with their success rates and weight vectors
- Recent outcome history (last N actions)
- A live suggestions panel (which agent would be chosen for a given context)

Can be run standalone::

    PYTHONPATH=runtime streamlit run runtime/ui/dashboard/agent_monitor.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ── Path bootstrap ────────────────────────────────────────────────────────────
_RUNTIME = Path(__file__).resolve().parents[2]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


def _load_agent_data() -> dict[str, Any]:
    """Load agent stats from brain_model and learning_engine."""
    try:
        import core.brain_model as _bm
        from core.learning_engine import LearningEngine
        le = LearningEngine()
        model = _bm.get_agent_model()
        agents = []
        for name, weights in model.items():
            agents.append({
                "name": name,
                "success_rate": round(le.agent_success_rate(name), 3),
                "task_match": round(float(weights.get("task_match", 0.5)), 3),
                "speed": round(float(weights.get("speed", 0.5)), 3),
                "complexity_fit": round(float(weights.get("complexity_fit", 0.5)), 3),
                "success_history": round(float(weights.get("success_history", 0.5)), 3),
            })
        return {"agents": agents}
    except Exception:  # noqa: BLE001
        return {"agents": []}


def _load_recent_outcomes(limit: int = 15) -> list[dict[str, Any]]:
    try:
        from core.self_learning_brain import get_self_learning_brain
        return get_self_learning_brain().recent_outcomes(limit=limit)
    except Exception:  # noqa: BLE001
        return []


def render_agent_monitor() -> None:
    """Render the agent monitor panel inside a Streamlit context."""
    if not _HAS_ST:
        print("Streamlit not installed — dashboard rendering skipped.")
        return

    st.subheader("🤖 Agent Monitor")

    data = _load_agent_data()
    agents = data.get("agents", [])

    if agents:
        import pandas as pd

        df = pd.DataFrame(agents).rename(columns={
            "name": "Agent",
            "success_rate": "Success Rate",
            "task_match": "Task Match",
            "speed": "Speed",
            "complexity_fit": "Complexity Fit",
            "success_history": "History Score",
        })

        st.markdown("**Known Agents & Weights**")
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info("No agent data available yet.")

    st.divider()

    # ── Recent outcomes ───────────────────────────────────────────────────────
    st.markdown("**Recent Outcomes**")
    outcomes = _load_recent_outcomes()
    if outcomes:
        import pandas as pd

        rows = []
        for o in reversed(outcomes):
            rows.append({
                "Time": o.get("ts", ""),
                "Agent": o.get("action", ""),
                "Result": "✅ Success" if o.get("success") else "❌ Failed",
                "Strategy": o.get("strategy", ""),
                "Duration (ms)": o.get("duration_ms", 0),
                "Context": o.get("context_snippet", "")[:60],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No outcomes recorded yet.")

    st.divider()

    # ── Live suggestion ───────────────────────────────────────────────────────
    st.markdown("**Live Agent Suggestion**")
    query = st.text_input(
        "Describe a task to see which agent the brain recommends:",
        placeholder="e.g. write a marketing email for our new product",
        key="agent_monitor_query",
    )
    if query:
        try:
            from core.self_learning_brain import get_self_learning_brain
            suggestion = get_self_learning_brain().suggest_action(context=query)
            st.success(
                f"**Recommended agent:** `{suggestion['agent']}`  \n"
                f"**Strategy:** `{suggestion['strategy']}`  \n"
                f"**Confidence:** {suggestion['confidence']:.1%}  \n"
                f"**Reasoning:** {suggestion['reasoning']}"
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Suggestion failed: {exc}")


# ── Standalone entry ──────────────────────────────────────────────────────────

if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="AI Employee — Agent Monitor", page_icon="🤖")
    render_agent_monitor()
