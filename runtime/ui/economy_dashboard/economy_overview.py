"""Economy Overview — AI Employee internal economy dashboard panel (V4).

Displays:
- Global economy KPIs (profit, ROI, cost, value)
- Per-agent budget / efficiency table
- ROI-ranked improvement suggestions
- Recent task log
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_RUNTIME = Path(__file__).resolve().parents[2]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


def _get_eco() -> Any:
    from core.economy_engine import get_economy_engine
    return get_economy_engine()


def render_economy_overview() -> None:
    """Render the economy overview panel inside a Streamlit context."""
    if not _HAS_ST:
        return

    st.subheader("💰 Internal Economy Overview")
    st.caption(
        "Every agent action has a cost and a value. "
        "ROI drives evolution priority — low-ROI agents are candidates for forge rewrite."
    )

    try:
        eco = _get_eco()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Economy engine unavailable: {exc}")
        return

    # ── Global KPIs ───────────────────────────────────────────────────────────
    summary = eco.system_summary()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Global Profit",  f"{summary.get('global_profit', 0):.1f}")
    c2.metric("Global ROI",     f"{summary.get('global_roi', 0):.3f}")
    c3.metric("Total Value",    f"{summary.get('global_value', 0):.1f}")
    c4.metric("Total Cost",     f"{summary.get('global_cost', 0):.1f}")
    c5.metric("Tasks Run",      str(summary.get("global_tasks", 0)))

    st.divider()

    # ── Agent leaderboard ─────────────────────────────────────────────────────
    st.markdown("**🏆 Agent Performance Leaderboard**")
    top = eco.top_agents(limit=20)
    if top:
        import pandas as pd
        rows = [
            {
                "Agent": a["name"],
                "Score": f"{a['performance_score']:.3f}",
                "ROI": f"{a['roi']:.3f}",
                "Profit": f"{a['profit']:.1f}",
                "Efficiency": f"{a['efficiency']:.3f}",
                "✅ Tasks": a["tasks_completed"],
                "❌ Tasks": a["tasks_failed"],
                "Budget": f"{a['budget']:.1f}",
            }
            for a in top
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No agent data yet. Run some tasks to populate the leaderboard.")

    st.divider()

    # ── Improvement suggestions ───────────────────────────────────────────────
    st.markdown("**🔧 Economy-Driven Improvement Suggestions**")
    try:
        suggestions = eco.suggest_improvements(limit=5)
        if suggestions:
            for s in suggestions:
                priority_color = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(
                    s.get("priority", "low"), "⚪"
                )
                st.markdown(
                    f"{priority_color} **{s.get('type', '').title()}** · `{s.get('agent', 'system')}` — "
                    f"{s.get('reason', '')} _(ROI impact: +{s.get('roi_impact', 0):.3f})_"
                )
        else:
            st.success("No critical improvement suggestions — system is healthy!")
    except Exception:  # noqa: BLE001
        st.info("Suggestions unavailable.")

    st.divider()

    # ── Recent tasks ──────────────────────────────────────────────────────────
    st.markdown("**📋 Recent Tasks**")
    recent = eco.recent_tasks(limit=15)
    if recent:
        import pandas as pd
        rows = [
            {
                "Time": t.get("ts", ""),
                "Agent": t.get("agent", ""),
                "Task": (t.get("task_id") or "")[:30],
                "Value": f"{t.get('value', 0):.1f}",
                "Cost": f"{t.get('cost', 0):.1f}",
                "ROI": f"{(t.get('value', 0) - t.get('cost', 0)) / max(t.get('cost', 1), 1):.2f}",
                "✓": "✅" if t.get("success") else "❌",
            }
            for t in reversed(recent)
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No task history yet.")


if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="Economy Dashboard", page_icon="💰")
    render_economy_overview()
