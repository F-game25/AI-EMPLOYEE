"""Main Dashboard — AI Employee Streamlit dashboard entrypoint.

Assembles all dashboard tabs into a single multi-tab Streamlit application:

  🏠 System Status    — overall health, memory summary, brain KPIs
  🧠 Brain Visualizer  — node/edge graph of learning paths
  🤖 Agent Monitor     — per-agent stats, recent outcomes, live suggestions
  🗄️ Memory Viewer     — semantic search, recent entries, write panel
  🔨 Ascend Forge      — live code editor, module builder, deployment panel

Launch::

    PYTHONPATH=runtime streamlit run runtime/ui/dashboard/main_dashboard.py

Or programmatically::

    from ui.dashboard.main_dashboard import run_dashboard
    run_dashboard()
"""
from __future__ import annotations

import sys
import time
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


def _ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_system_status() -> dict[str, Any]:
    status: dict[str, Any] = {"ts": _ts()}
    try:
        from memory.memory_router import get_memory_router
        status["memory"] = get_memory_router().health()
    except Exception:
        status["memory"] = {}

    try:
        from core.self_learning_brain import get_self_learning_brain
        m = get_self_learning_brain().metrics()
        status["brain"] = {
            "avg_reward": m.get("avg_reward_recent", 0.0),
            "total_outcomes": m.get("total_outcomes_recorded", 0),
            "agent_count": len(m.get("agent_weights", {})),
        }
    except Exception:
        status["brain"] = {}

    try:
        from engine.api import process_input
        _ = process_input("health check")
        status["engine"] = "ok"
    except Exception:
        status["engine"] = "unavailable"

    return status


def render_system_status() -> None:
    """Render the System Status overview tab."""
    st.subheader("🏠 System Status")

    status = _load_system_status()

    # ── Top-level status row ──────────────────────────────────────────────────
    engine_ok = status.get("engine") == "ok"
    col1, col2, col3 = st.columns(3)
    col1.metric("Internal Engine", "✅ Online" if engine_ok else "⚠️ Check logs")
    col1.caption("engine/api.py")

    brain = status.get("brain", {})
    col2.metric("Self-Learning Brain", "✅ Active" if brain else "⚠️ Initialising")
    col2.caption(f"Avg reward: {brain.get('avg_reward', 0.0):.3f}")

    mem = status.get("memory", {})
    col3.metric("Memory Router", "✅ Active" if mem else "⚠️ Initialising")
    col3.caption(f"Cache: {mem.get('cache_live_entries', 0)} live entries")

    st.divider()

    # ── Memory detail ─────────────────────────────────────────────────────────
    st.markdown("**Memory Store Breakdown**")
    ve = mem.get("vector_entries", {})
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total Vector", str(ve.get("total", 0)))
    mc2.metric("Episodic", str(ve.get("episodic", 0)))
    mc3.metric("Semantic",  str(ve.get("semantic",  0)))
    mc4.metric("Procedural", str(ve.get("procedural", 0)))

    st.divider()

    # ── Brain detail ──────────────────────────────────────────────────────────
    st.markdown("**Learning Brain Summary**")
    bc1, bc2 = st.columns(2)
    bc1.metric("Outcomes Recorded", str(brain.get("total_outcomes", 0)))
    bc2.metric("Known Agents",       str(brain.get("agent_count", 0)))

    try:
        from core.self_learning_brain import get_self_learning_brain
        metrics = get_self_learning_brain().metrics()
        best = metrics.get("best_strategies", [])
        if best:
            st.markdown("**Top Strategies**")
            import pandas as pd
            rows = [
                {
                    "ID": s.get("strategy_id", ""),
                    "Success Rate": round(float(s.get("success_rate", 0)), 3),
                    "Uses": int(s.get("use_count", 0)),
                }
                for s in best[:5]
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    except Exception:
        pass

    st.caption(f"Last refreshed: {status.get('ts', '—')}")


def run_dashboard() -> None:
    """Assemble and render the full multi-tab AI Employee dashboard."""
    if not _HAS_ST:
        print(
            "Streamlit is not installed. Install it with:\n"
            "  pip install streamlit pandas\n\n"
            "Then run:\n"
            "  PYTHONPATH=runtime streamlit run runtime/ui/dashboard/main_dashboard.py"
        )
        return

    st.set_page_config(
        page_title="AI Employee — OS Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.title("🤖 AI Employee")
        st.caption("Autonomous AI Operating System")
        st.divider()
        st.markdown("**Navigation**")
        tab_choice = st.radio(
            "Select view",
            [
                "🏠 System Status",
                "🧠 Brain Visualizer",
                "🤖 Agent Monitor",
                "🗄️ Memory Viewer",
                "🔨 Ascend Forge",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("🔄 Refresh"):
            st.rerun()
        st.caption(f"v{_ts()}")

    # ── Main content ──────────────────────────────────────────────────────────
    if tab_choice == "🏠 System Status":
        render_system_status()
    elif tab_choice == "🧠 Brain Visualizer":
        from ui.dashboard.brain_visualizer import render_brain_visualizer
        render_brain_visualizer()
    elif tab_choice == "🤖 Agent Monitor":
        from ui.dashboard.agent_monitor import render_agent_monitor
        render_agent_monitor()
    elif tab_choice == "🗄️ Memory Viewer":
        from ui.dashboard.memory_viewer import render_memory_viewer
        render_memory_viewer()
    elif tab_choice == "🔨 Ascend Forge":
        _render_ascend_forge()


def _render_ascend_forge() -> None:
    """Render the Ascend Forge multi-sub-tab panel."""
    st.header("🔨 Ascend Forge")
    st.caption(
        "Internal AI-powered development environment. "
        "Build, test, and deploy modules — all under controlled execution rules."
    )

    forge_tab = st.radio(
        "Forge section",
        ["✏️ Code Editor", "🧩 Module Builder", "🔬 Live Preview", "🚦 Deployment"],
        horizontal=True,
        label_visibility="collapsed",
        key="forge_sub_tab",
    )

    if forge_tab == "✏️ Code Editor":
        from ui.ascend_forge.forge_editor import render_forge_editor
        render_forge_editor()
    elif forge_tab == "🧩 Module Builder":
        from ui.ascend_forge.module_builder import render_module_builder
        render_module_builder()
    elif forge_tab == "🔬 Live Preview":
        from ui.ascend_forge.live_preview import render_live_preview
        render_live_preview()
    elif forge_tab == "🚦 Deployment":
        from ui.ascend_forge.deployment_panel import render_deployment_panel
        render_deployment_panel()


# ── Direct entry ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_dashboard()
