"""Profit Visualizer — ROI trends and monetization pipeline dashboard (V4).

Displays:
- System-wide profit over time
- Per-agent profit contribution chart
- Forge ROI suggestions ranked by impact
- Money Mode tool pipeline (builder_agent activity)
- Optimizer scan history
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


def _get_fc() -> Any:
    from core.forge_controller import get_forge_controller
    return get_forge_controller()


def _get_opt() -> Any:
    from agents.optimizer_agent import get_optimizer_agent
    return get_optimizer_agent()


def render_profit_visualizer() -> None:
    """Render the profit visualizer inside a Streamlit context."""
    if not _HAS_ST:
        return

    st.subheader("📈 Profit Visualizer")
    st.caption(
        "Tracks value generated vs cost across all agents and actions. "
        "Drives forge optimization priority."
    )

    try:
        eco = _get_eco()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Economy engine unavailable: {exc}")
        return

    summary = eco.system_summary()

    # ── Top KPIs ──────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("System Profit",  f"${summary.get('global_profit', 0):.2f}")
    c2.metric("System ROI",     f"{summary.get('global_roi', 0):.3f}x")
    c3.metric("Agent Budget Pool", f"${summary.get('total_agent_budget', 0):.0f}")

    st.divider()

    # ── Per-agent profit bar chart ─────────────────────────────────────────────
    st.markdown("**💼 Agent Profit Contributions**")
    top = eco.top_agents(limit=15)
    if top:
        try:
            import pandas as pd
            df = pd.DataFrame([
                {"Agent": a["name"], "Profit": round(a.get("profit", 0), 2), "ROI": round(a.get("roi", 0), 3)}
                for a in top
            ]).sort_values("Profit", ascending=False)
            st.bar_chart(df.set_index("Agent")["Profit"])
            st.caption("Profit = Value Generated − Cost.  Sorted highest to lowest.")
        except Exception:  # noqa: BLE001
            st.info("Chart unavailable — install pandas.")
    else:
        st.info("No agent data yet.")

    st.divider()

    # ── Forge ROI suggestions ─────────────────────────────────────────────────
    st.markdown("**🔨 Forge ROI Opportunity Pipeline**")
    try:
        fc = _get_fc()
        suggestions = fc.roi_suggestions(limit=8)
        if suggestions:
            import pandas as pd
            rows = [
                {
                    "Priority": s.get("priority", s.get("roi_analysis", {}).get("priority", "?")),
                    "Agent / Module": s.get("agent", "?"),
                    "Reason": (s.get("reason") or "")[:70],
                    "ROI Score": round(
                        s.get("roi_analysis", {}).get("roi_score", s.get("roi_impact", 0)), 3
                    ),
                    "Rev +%": s.get("roi_analysis", {}).get("expected_revenue_increase", "?"),
                    "Eff +%": s.get("roi_analysis", {}).get("efficiency_gain", "?"),
                    "Risk %": s.get("roi_analysis", {}).get("stability_risk", "?"),
                    "Auto-Deploy": "✅" if s.get("roi_analysis", {}).get("auto_deploy_eligible") else "❌",
                }
                for s in suggestions
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.success("No high-ROI improvement opportunities identified.")
    except Exception:  # noqa: BLE001
        st.info("ROI suggestions unavailable.")

    st.divider()

    # ── Profit impact analysis (on-demand) ────────────────────────────────────
    st.markdown("**🔬 On-Demand Profit Impact Analysis**")
    st.caption("Enter a module and describe a proposed change to get an ROI estimate.")
    col_mod, col_type = st.columns(2)
    with col_mod:
        pmod = st.text_input("Module", placeholder="agents/email_ninja.py", key="pv_module")
    with col_type:
        ptype = st.selectbox(
            "Change type",
            ["optimization", "new_agent", "memory", "ui", "tool"],
            key="pv_type",
        )
    pdesc = st.text_input("Description", placeholder="Improve prompt routing logic", key="pv_desc")
    if st.button("📊 Analyse ROI", key="pv_analyse"):
        if pmod:
            try:
                result = _get_fc().profit_impact_analysis(
                    module=pmod, description=pdesc, change_type=ptype
                )
                col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                col_r1.metric("ROI Score",      f"{result['roi_score']:.3f}")
                col_r2.metric("Revenue +%",     f"{result['expected_revenue_increase']}%")
                col_r3.metric("Efficiency +%",  f"{result['efficiency_gain']}%")
                col_r4.metric("Stability Risk", f"{result['stability_risk']}%")
                pcolor = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "⚪"}.get(
                    result["priority"], "⚪"
                )
                st.markdown(f"**Priority:** {pcolor} {result['priority'].upper()}")
                if result.get("auto_deploy_eligible"):
                    st.success("✅ This change is eligible for auto-deployment after sandbox validation.")
                else:
                    st.warning("⚠️ Manual approval required before deployment.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Analysis error: {exc}")
        else:
            st.warning("Enter a module path.")

    st.divider()

    # ── Optimizer agent status ────────────────────────────────────────────────
    st.markdown("**🤖 Optimizer Agent**")
    try:
        opt = _get_opt()
        status = opt.status()
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Scan Count",       str(status.get("scan_count", 0)))
        sc2.metric("Pending Proposals",str(status.get("pending_proposals", 0)))
        sc3.metric("Loop Running",     "✅" if status.get("running") else "⏸")
        if status.get("last_scan"):
            st.caption(f"Last scan: {status['last_scan']}")
        if st.button("▶️ Run Optimization Scan Now", key="pv_opt_scan"):
            findings = opt.analyze()
            st.success(
                f"Scan #{findings['scan_id']} complete — "
                f"{findings['total_proposals']} proposals, "
                f"{len(findings['forge_suggestions'])} forge suggestions."
            )
    except Exception:  # noqa: BLE001
        st.info("Optimizer agent unavailable.")


if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="Profit Visualizer", page_icon="📈")
    render_profit_visualizer()
