"""Deployment Panel — apply, review, and rollback Ascend Forge changes.

Panels:
- Pending approvals — list + approve / reject buttons
- Deployed versions — list from VersionControl with rollback action
- Reload history    — recent hot_reload_manager events
- Version summary   — snapshot counts, performance scores
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


def _get_fc() -> Any:
    from core.forge_controller import get_forge_controller
    return get_forge_controller()


def _get_vc() -> Any:
    from runtime.runtime.version_control import get_version_control
    return get_version_control()


def _get_hrm() -> Any:
    from runtime.runtime.hot_reload_manager import get_hot_reload_manager
    return get_hot_reload_manager()


def render_deployment_panel() -> None:
    """Render the deployment panel inside a Streamlit context."""
    if not _HAS_ST:
        print("Streamlit not installed — skipping deployment_panel render.")
        return

    st.subheader("🚦 Deployment Panel")

    # ── Version summary ───────────────────────────────────────────────────────
    try:
        summary = _get_vc().summary()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Snapshots", str(summary.get("total_snapshots", 0)))
        c2.metric("Deployed",        str(summary.get("deployed", 0)))
        c3.metric("Rolled Back",     str(summary.get("rolled_back", 0)))
        avg = summary.get("avg_performance_score")
        c4.metric("Avg Perf Score",  f"{avg:.3f}" if avg is not None else "—")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Version control unavailable: {exc}")

    st.divider()

    # ── Pending approvals ─────────────────────────────────────────────────────
    st.markdown("**⏳ Pending Approvals**")
    try:
        pending = _get_fc().list_pending()
        if pending:
            import pandas as pd

            for rec in pending:
                sid = rec.get("snapshot_id", "")
                col_info, col_approve, col_reject = st.columns([5, 1, 1])
                with col_info:
                    st.markdown(
                        f"**`{rec.get('module', '')}`** — {rec.get('description', '')}  "
                        f"  `{sid}`  |  submitted {rec.get('submitted_at', '')}"
                    )
                with col_approve:
                    if st.button("✅ Approve", key=f"approve_{sid}"):
                        result = _get_fc().approve(sid)
                        if result.get("status") == "deployed":
                            st.success(f"Deployed snapshot `{sid}`")
                        else:
                            st.error(f"Deployment failed: {result.get('reload_result', {}).get('error', '')}")
                        st.rerun()
                with col_reject:
                    if st.button("❌ Reject", key=f"reject_{sid}"):
                        _get_fc().reject(sid, "Rejected via dashboard")
                        st.rerun()
        else:
            st.info("No pending submissions.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load pending: {exc}")

    st.divider()

    # ── Version history ───────────────────────────────────────────────────────
    st.markdown("**📋 Version History**")
    try:
        versions = _get_vc().list_versions(limit=30)
        if versions:
            import pandas as pd

            rows = [
                {
                    "ID": v.get("id", ""),
                    "Module": v.get("module", ""),
                    "Tag": v.get("tag", ""),
                    "Description": (v.get("description") or "")[:60],
                    "Status": v.get("status", ""),
                    "Perf Score": v.get("performance_score", "—"),
                    "Timestamp": v.get("ts", ""),
                }
                for v in versions
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            # Rollback by snapshot ID
            rollback_id = st.text_input(
                "Rollback snapshot ID",
                placeholder="Enter a snapshot ID from the table above",
                key="deploy_rollback_id",
            )
            if st.button("↩️ Rollback", key="deploy_rollback_btn"):
                if rollback_id:
                    result = _get_fc().rollback(rollback_id)
                    if result.get("success"):
                        st.success(f"Rolled back to snapshot `{rollback_id}`")
                    else:
                        st.error(f"Rollback failed: {result.get('error', '')}")
                else:
                    st.warning("Enter a snapshot ID to rollback.")
        else:
            st.info("No versions recorded yet.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load version history: {exc}")

    st.divider()

    # ── Reload history ────────────────────────────────────────────────────────
    st.markdown("**🔄 Recent Hot-Reloads**")
    try:
        history = _get_hrm().reload_history(limit=15)
        if history:
            import pandas as pd

            rows = [
                {
                    "Time": r.get("ts", ""),
                    "Module": r.get("module", ""),
                    "Result": "✅ OK" if r.get("success") else "❌ Failed",
                    "Rolled Back": "Yes" if r.get("rolled_back") else "No",
                    "Error": (r.get("error") or "")[:80],
                }
                for r in reversed(history)
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("No reload history yet.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load reload history: {exc}")


if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="Ascend Forge — Deployment", page_icon="🚦")
    render_deployment_panel()
