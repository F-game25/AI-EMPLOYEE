"""Brain Visualizer — Streamlit panel that renders learning-path graphs.

Shows nodes (agents, strategies, memory entries) connected by edges whose
thickness corresponds to the reinforcement weight of each path.

Rendered by ``main_dashboard.py``.  Can also be run standalone::

    PYTHONPATH=runtime streamlit run runtime/ui/dashboard/brain_visualizer.py

The panel never accesses brain internals directly; it reads from the
UI API server (``/brain/metrics``) or falls back to direct Python
imports when running embedded in the same process.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ── Path bootstrap ────────────────────────────────────────────────────────────
_RUNTIME = Path(__file__).resolve().parents[2]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

# ── Streamlit (optional — graceful degradation) ───────────────────────────────
try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


def _load_metrics() -> dict[str, Any]:
    """Load brain metrics from the self-learning brain singleton."""
    try:
        from core.self_learning_brain import get_self_learning_brain
        return get_self_learning_brain().metrics()
    except Exception:  # noqa: BLE001
        return {}


def _build_graph_data(metrics: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Convert brain metrics into node/edge lists for visualisation.

    Returns:
        (nodes, edges) where each node is ``{"id", "label", "weight"}``
        and each edge is ``{"from", "to", "weight"}``.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(node_id: str, label: str, weight: float, group: str = "default") -> None:
        if node_id not in seen_ids:
            nodes.append({"id": node_id, "label": label, "weight": round(weight, 3), "group": group})
            seen_ids.add(node_id)

    # Central orchestrator node
    add_node("orchestrator", "🧠 Orchestrator", 1.0, "core")

    # Agent nodes
    agent_weights: dict[str, Any] = metrics.get("agent_weights", {})
    for agent_name, weights in agent_weights.items():
        if not isinstance(weights, dict):
            continue
        avg_w = sum(weights.values()) / max(len(weights), 1)
        add_node(f"agent:{agent_name}", f"🤖 {agent_name}", avg_w, "agent")
        edges.append({
            "from": "orchestrator",
            "to": f"agent:{agent_name}",
            "weight": round(avg_w, 3),
        })

    # Strategy nodes
    for strat in metrics.get("best_strategies", [])[:5]:
        sid = strat.get("strategy_id", "unknown")
        sr = float(strat.get("success_rate", 0.5))
        label = f"✅ {sid[:12]}"
        add_node(f"strat:{sid}", label, sr, "strategy")
        agent = strat.get("chosen_agent") or ""
        from_node = f"agent:{agent}" if agent and f"agent:{agent}" in seen_ids else "orchestrator"
        edges.append({"from": from_node, "to": f"strat:{sid}", "weight": round(sr, 3)})

    for strat in metrics.get("worst_strategies", [])[:3]:
        sid = strat.get("strategy_id", "unknown")
        sr = float(strat.get("success_rate", 0.0))
        label = f"⚠️ {sid[:12]}"
        add_node(f"strat:{sid}", label, sr, "weak")
        edges.append({
            "from": "orchestrator",
            "to": f"strat:{sid}",
            "weight": round(sr, 3),
        })

    return nodes, edges


def render_brain_visualizer() -> None:
    """Render the brain visualisation panel inside a Streamlit context."""
    if not _HAS_ST:
        print("Streamlit not installed — dashboard rendering skipped.")
        return

    st.subheader("🧠 Brain Visualizer")
    st.caption(
        "Nodes = agents / strategies.  "
        "Edge weight = learned reinforcement strength (thicker = stronger path)."
    )

    metrics = _load_metrics()
    if not metrics:
        st.warning("Brain metrics unavailable — is the system initialised?")
        return

    # ── Summary KPIs ─────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("Avg Reward (recent)", f"{metrics.get('avg_reward_recent', 0.0):.3f}")
    col2.metric("Outcomes Recorded",   str(metrics.get("total_outcomes_recorded", 0)))
    col3.metric("Active Agents",       str(len(metrics.get("agent_weights", {}))))

    st.divider()

    # ── Node / Edge tables ────────────────────────────────────────────────────
    nodes, edges = _build_graph_data(metrics)

    col_n, col_e = st.columns(2)
    with col_n:
        st.markdown("**Nodes**")
        if nodes:
            import pandas as pd
            st.dataframe(
                pd.DataFrame(nodes)[["label", "weight", "group"]].rename(
                    columns={"label": "Node", "weight": "Strength", "group": "Group"}
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No nodes yet.")

    with col_e:
        st.markdown("**Connections (edges)**")
        if edges:
            import pandas as pd
            st.dataframe(
                pd.DataFrame(edges).rename(
                    columns={"from": "From", "to": "To", "weight": "Weight"}
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No connections yet.")

    st.divider()

    # ── Decision weights ─────────────────────────────────────────────────────
    st.markdown("**Decision Engine Weights**")
    dw = metrics.get("decision_weights", {})
    if dw:
        import pandas as pd
        st.dataframe(
            pd.DataFrame([{"Dimension": k, "Weight": round(v, 4)} for k, v in dw.items()]),
            hide_index=True,
            use_container_width=True,
        )


# ── Standalone entry ──────────────────────────────────────────────────────────

if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="AI Employee — Brain Visualizer", page_icon="🧠")
    render_brain_visualizer()
