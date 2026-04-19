"""neural_brain_tab.py — Streamlit live monitor tab for the Central Brain.

Launch standalone:
    PYTHONPATH=runtime streamlit run runtime/ui/neural_brain_tab.py

Embed in an existing Streamlit app:
    from ui.neural_brain_tab import render_brain_tab
    with st.tabs(["...", "🧠 Neural Brain"])[-1]:
        render_brain_tab()
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import torch

# ── Path bootstrap ────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve()
_RUNTIME = _HERE.parents[1]   # runtime/
_ROOT    = _HERE.parents[2]   # repo root

for _p in [str(_RUNTIME), str(_ROOT)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st  # noqa: E402

from brain.brain import get_brain, Brain  # noqa: E402


# ── Singleton brain via session state ─────────────────────────────────────────

def _get_brain() -> Brain:
    if "central_brain" not in st.session_state:
        st.session_state["central_brain"] = get_brain()
    return st.session_state["central_brain"]


def _init_history() -> None:
    for key in ("brain_loss_hist", "brain_reward_hist"):
        if key not in st.session_state:
            st.session_state[key] = []
    if "brain_last_action" not in st.session_state:
        st.session_state["brain_last_action"] = None
    if "brain_last_conf" not in st.session_state:
        st.session_state["brain_last_conf"] = None
    if "brain_last_state_preview" not in st.session_state:
        st.session_state["brain_last_state_preview"] = None


def _append_history(brain: Brain) -> None:
    s = brain.stats()
    st.session_state["brain_loss_hist"].append(s["last_loss"])
    st.session_state["brain_reward_hist"].append(s["avg_reward"])
    for key in ("brain_loss_hist", "brain_reward_hist"):
        if len(st.session_state[key]) > 500:
            st.session_state[key] = st.session_state[key][-500:]


# ═════════════════════════════════════════════════════════════════════════════
def render_brain_tab() -> None:
    """Render the Neural Brain live tab."""
    _init_history()
    brain = _get_brain()
    stats = brain.stats()
    cfg   = brain.cfg

    st.header("🧠 Neural Brain — Central Intelligence")
    st.caption(
        "The single neural intelligence driving every decision in AI Employee. "
        "All agents route through this brain in real time."
    )

    # ── Status banner ─────────────────────────────────────────────────────────
    mode_icon = "🟢 Online" if stats["is_online"] else "🔴 Offline"
    bg_icon   = "⚙️ Running" if stats["bg_running"] else "⏸ Stopped"
    st.info(f"**Learning mode:** {mode_icon}   |   **Background loop:** {bg_icon}   |   **Device:** {stats['device'].upper()}")

    st.divider()

    # ── Top metrics ───────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Learn Steps",   f"{stats['learn_step']:,}")
    c2.metric("Experiences",   f"{stats['experience_count']:,}")
    c3.metric("Buffer",        f"{stats['buffer_size']:,} / {stats['buffer_capacity']:,}")
    c4.metric("Avg Reward",    f"{stats['avg_reward']:.4f}")
    c5.metric("Learning Rate", f"{stats['lr']:.2e}")

    st.divider()

    # ── Action & state panel ──────────────────────────────────────────────────
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("🎯 Last Action")
        if st.session_state["brain_last_action"] is not None:
            st.write(f"**Action index:** `{st.session_state['brain_last_action']}`")
            st.write(f"**Confidence:**   `{st.session_state['brain_last_conf']:.1%}`")
        else:
            st.info("No action taken yet in this session.")

        st.subheader("💰 Last Reward")
        st.write(f"**Last reward:** `{stats['last_reward']:.2f}`")
        st.write(
            f"**Avg reward (last {cfg['ui']['reward_window']}):** "
            f"`{stats['avg_reward']:.4f}`"
        )

    with col_r:
        st.subheader("📡 Current State Features")
        if st.session_state["brain_last_state_preview"] is not None:
            preview = st.session_state["brain_last_state_preview"]
            st.code(f"[{', '.join(f'{v:.3f}' for v in preview)}, ...]  (first 8 dims)")
        else:
            st.info("Run a synthetic inference to see state features here.")

    st.divider()

    # ── Live charts ───────────────────────────────────────────────────────────
    loss_col, rew_col = st.columns(2)

    with loss_col:
        st.subheader("📉 Loss History")
        loss_hist = st.session_state["brain_loss_hist"]
        if loss_hist:
            st.line_chart(pd.DataFrame({"Loss": loss_hist}), use_container_width=True)
        else:
            st.info("Loss chart appears after the first learn step.")

    with rew_col:
        st.subheader("📈 Avg Reward History")
        rew_hist = st.session_state["brain_reward_hist"]
        if rew_hist:
            st.line_chart(pd.DataFrame({"Avg Reward": rew_hist}), use_container_width=True)
        else:
            st.info("Reward chart appears after the first experience is stored.")

    st.divider()

    # ── Model stats ───────────────────────────────────────────────────────────
    st.subheader("⚙️ Model Configuration")
    ms1, ms2, ms3 = st.columns(3)
    ms1.write(f"**Input size:**     `{cfg['model']['input_size']}`")
    ms1.write(f"**Output size:**    `{cfg['model']['output_size']}`")
    ms1.write(f"**Hidden layers:**  `{cfg['model']['hidden_sizes']}`")
    ms2.write(f"**Dropout:**        `{cfg['model']['dropout']}`")
    ms2.write(f"**Batch size:**     `{cfg['training']['batch_size']}`")
    ms2.write(f"**Update freq:**    `{cfg['training']['update_frequency']}`")
    ms3.write(f"**PER α:**          `{cfg['training']['per_alpha']}`")
    ms3.write(f"**PER β:**          `{cfg['training']['per_beta']}`")
    ms3.write(f"**Last loss:**      `{stats['last_loss']:.6f}`")

    st.write(f"**Model path:** `{stats['model_path']}`")

    st.divider()

    # ── Control buttons ───────────────────────────────────────────────────────
    st.subheader("🕹️ Controls")
    b1, b2, b3, b4, b5 = st.columns(5)

    with b1:
        if st.button("🎓 Manual Learn"):
            loss = brain.learn()
            _append_history(brain)
            st.success(f"Learn done — loss: {loss:.6f}")

    with b2:
        if st.button("🔌 Force Offline Learn"):
            n = brain.force_offline_learn()
            _append_history(brain)
            st.success(f"Offline learn: {n} experiences collected.")

    with b3:
        if st.button("🗑️ Clear Buffer"):
            brain.replay_buffer.clear()
            st.warning("Replay buffer cleared.")

    with b4:
        if st.button("💾 Save Brain"):
            brain.save()
            st.success("Brain saved to disk.")

    with b5:
        if st.button("🔄 Refresh"):
            _append_history(brain)
            st.rerun()

    # ── Synthetic inference demo ───────────────────────────────────────────────
    st.divider()
    st.subheader("🧪 Synthetic Inference Demo")
    if st.button("▶ Run Synthetic Inference"):
        state = torch.randn(cfg["model"]["input_size"])
        action, confidence = brain.get_action(state)
        st.session_state["brain_last_action"]        = action
        st.session_state["brain_last_conf"]          = confidence
        st.session_state["brain_last_state_preview"] = state[:8].tolist()

        reward     = 1.0
        next_state = torch.randn(cfg["model"]["input_size"])
        brain.store_experience(state, action, reward, next_state)
        _append_history(brain)
        st.success(f"Action={action}  Confidence={confidence:.1%}  Reward=+1.0")
        st.rerun()

    # ── Auto-refresh toggle ───────────────────────────────────────────────────
    update_interval = cfg["ui"].get("update_interval", 3)
    if cfg["ui"].get("show_graphs", True):
        auto_refresh = st.toggle(
            f"⏱️ Auto-refresh every {update_interval}s",
            value=False,
            key="brain_auto_refresh",
            help="Enable continuous live refresh of all charts and metrics.",
        )
        if auto_refresh:
            import time
            time.sleep(update_interval)
            _append_history(brain)
            st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# Standalone entry point
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    st.set_page_config(
        page_title="AI Employee — Neural Brain",
        page_icon="🧠",
        layout="wide",
    )
    render_brain_tab()
