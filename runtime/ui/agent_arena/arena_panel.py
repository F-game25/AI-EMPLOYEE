"""Agent Arena — real-time competitive agent visualization (V4).

Displays:
- Live performance ranking board
- Agent score cards with competition history
- Challenge simulator (head-to-head comparison)
- Reward/penalty event stream
- Rewrite proposal panel
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


def _get_ce() -> Any:
    from core.agent_competition_engine import get_competition_engine
    return get_competition_engine()


def _get_eco() -> Any:
    from core.economy_engine import get_economy_engine
    return get_economy_engine()


def render_agent_arena() -> None:
    """Render the Agent Arena panel inside a Streamlit context."""
    if not _HAS_ST:
        return

    st.subheader("⚔️ Agent Arena")
    st.caption(
        "Agents compete continuously. Best performers are reinforced with resources; "
        "worst performers are candidates for forge rewrite."
    )

    try:
        ce = _get_ce()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Competition engine unavailable: {exc}")
        return

    # ── Competition summary ───────────────────────────────────────────────────
    summary = ce.competition_summary()
    eco_s = summary.get("economy", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Global ROI",       f"{eco_s.get('global_roi', 0):.3f}")
    c2.metric("Action Events",    str(summary.get("action_events", 0)))
    c3.metric("Rewrite Proposals",str(summary.get("rewrite_proposals", 0)))
    c4.metric("Total Tasks",      str(eco_s.get("global_tasks", 0)))

    st.divider()

    # ── Leaderboard ───────────────────────────────────────────────────────────
    st.markdown("**🏆 Live Competition Leaderboard**")
    board = ce.leaderboard(limit=15)
    if board:
        import pandas as pd
        rows = [
            {
                "Rank": f"#{r['rank']}",
                "Agent": r["name"],
                "Score": f"{r['performance_score']:.3f}",
                "ROI": f"{r['roi']:.3f}",
                "Profit": f"{r['profit']:.1f}",
                "Tasks Won": r.get("tasks_won", 0),
                "Challenges Won": r.get("challenges_won", 0),
                "Budget": f"{r.get('budget', 0):.0f}",
                "Status": "🥇" if r["rank"] == 1 else ("⚠️" if r["performance_score"] < 0.25 else "✅"),
            }
            for r in board
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        # Highlight champion + underperformers
        if board:
            champion = board[0]
            st.success(f"🥇 Champion: **{champion['name']}** — score {champion['performance_score']:.3f}")
        underperf = [a for a in board if a.get("performance_score", 1) < 0.25]
        if underperf:
            names = ", ".join(a["name"] for a in underperf)
            st.warning(f"⚠️ Underperformers (rewrite candidates): {names}")
    else:
        st.info("No agents in the arena yet. Record some task outcomes to start the competition.")

    st.divider()

    # ── Challenge simulator ───────────────────────────────────────────────────
    st.markdown("**🥊 Challenge Simulator**")
    st.caption("Trigger a head-to-head score comparison between any two agents.")
    all_agents = [a["name"] for a in board] if board else []
    if len(all_agents) >= 2:
        col_a, col_b, col_run = st.columns([2, 2, 1])
        with col_a:
            challenger = st.selectbox("Challenger", all_agents, key="arena_challenger")
        with col_b:
            opts = [a for a in all_agents if a != challenger]
            defender = st.selectbox("Defender", opts, key="arena_defender")
        with col_run:
            st.write("")
            st.write("")
            if st.button("⚔️ Challenge", key="arena_challenge_btn"):
                result = ce.challenge(challenger=challenger, defender=defender)
                st.json(result)
    else:
        st.info("Need at least 2 agents to run a challenge.")

    st.divider()

    # ── Rewrite proposals ─────────────────────────────────────────────────────
    st.markdown("**🔧 Rewrite Proposals**")
    proposals = ce.propose_rewrites(limit=3)
    if proposals:
        for p in proposals:
            st.warning(
                f"⚙️ **{p.get('agent', '?')}** — score {p.get('score', 0):.3f}  \n"
                f"{p.get('description', '')}"
            )
    else:
        st.success("No rewrite proposals — all agents performing adequately.")

    st.divider()

    # ── Recent actions ────────────────────────────────────────────────────────
    st.markdown("**📡 Recent Competition Events**")
    recent = ce.recent_actions(limit=15)
    if recent:
        import pandas as pd
        rows = [
            {
                "Time": r.get("ts", ""),
                "Agent": r.get("agent", ""),
                "Result": "✅" if r.get("success") else "❌",
                "Value": f"{r.get('value', 0):.1f}",
                "Cost": f"{r.get('cost', 0):.1f}",
                "Actions": ", ".join(a.get("action", "") for a in r.get("actions", [])),
            }
            for r in reversed(recent)
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No competition events yet.")


if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="Agent Arena", page_icon="⚔️")
    render_agent_arena()
