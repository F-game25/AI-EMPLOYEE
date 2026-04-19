"""Forge Editor — Streamlit code-editor panel for Ascend Forge.

Allows the user to:
- Browse and open existing system modules
- Edit code in a text area
- Submit the change through ForgeController (which validates before deploying)
- See validation results and warnings inline

All writes go through ``forge_controller.submit_change()`` — never direct to disk.
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

# ── Module catalogue ──────────────────────────────────────────────────────────

_EDITABLE_MODULES: list[str] = [
    "agents/hermes.py",
    "core/research_agent.py",
    "core/money_mode.py",
    "core/planner.py",
    "core/validator.py",
    "core/task_engine.py",
    "memory/memory_router.py",
    "memory/vector_store.py",
    "memory/short_term_cache.py",
]


def _read_module(module: str) -> str:
    """Read current source of *module* from disk."""
    try:
        path = _RUNTIME / module
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return f"# New module: {module}\n"


def render_forge_editor() -> None:
    """Render the code-editor panel inside a Streamlit context."""
    if not _HAS_ST:
        print("Streamlit not installed — skipping forge_editor render.")
        return

    st.subheader("✏️ Forge Editor")
    st.caption(
        "Edit system modules and submit changes for sandbox validation. "
        "All changes go through ForgeController before touching the live system."
    )

    col_sel, col_tag = st.columns([3, 1])
    with col_sel:
        module = st.selectbox(
            "Select module to edit",
            _EDITABLE_MODULES,
            key="forge_editor_module",
        )
    with col_tag:
        tag = st.text_input("Version tag", placeholder="v1.4", key="forge_editor_tag")

    description = st.text_input(
        "Change description",
        placeholder="Briefly describe what you changed",
        key="forge_editor_desc",
    )

    current_code = _read_module(module)
    new_code = st.text_area(
        "Source code",
        value=current_code,
        height=400,
        key=f"forge_code_{module}",
    )

    auto_deploy = st.checkbox(
        "Auto-deploy if sandbox passes (non-critical modules only)",
        value=False,
        key="forge_auto_deploy",
    )

    col_submit, col_clear = st.columns([2, 1])
    with col_submit:
        if st.button("🚀 Submit for Validation", key="forge_submit_btn"):
            if not new_code.strip():
                st.error("Code cannot be empty.")
            else:
                _submit_change(module, new_code, description, tag, auto_deploy)

    with col_clear:
        if st.button("↩️ Reset to Current", key="forge_reset_btn"):
            st.rerun()


def _submit_change(
    module: str,
    code: str,
    description: str,
    tag: str,
    auto_deploy: bool,
) -> None:
    """Submit the change through ForgeController and display results."""
    try:
        from core.forge_controller import get_forge_controller
        fc = get_forge_controller()
        result = fc.submit_change(
            module=module,
            code=code,
            description=description,
            tag=tag,
            author="dashboard:forge_editor",
            auto_deploy=auto_deploy,
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"ForgeController error: {exc}")
        return

    status = result.get("status", "unknown")

    if status == "rejected":
        st.error(f"❌ Rejected: {result.get('reason', '')}")
        val = result.get("validation", {})
        for err in val.get("errors", []):
            st.code(err, language="text")
    elif status == "awaiting_approval":
        st.warning(
            f"⏳ Awaiting approval — snapshot ID: `{result.get('snapshot_id')}`\n\n"
            f"{result.get('reason', '')}"
        )
        _show_warnings(result.get("validation", {}))
    elif status == "deployed":
        st.success(
            f"✅ Deployed successfully — snapshot ID: `{result.get('snapshot_id')}`"
        )
        _show_warnings(result.get("validation_warnings", []))
    elif status == "failed":
        st.error(
            f"❌ Deployment failed — snapshot ID: `{result.get('snapshot_id')}`\n\n"
            + str(result.get("reload_result", {}).get("error", ""))
        )
    else:
        st.json(result)


def _show_warnings(validation: Any) -> None:
    if isinstance(validation, dict):
        warnings = validation.get("warnings", [])
    elif isinstance(validation, list):
        warnings = validation
    else:
        warnings = []
    for w in warnings:
        st.warning(f"⚠️ {w}")


if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="Ascend Forge — Editor", page_icon="✏️")
    render_forge_editor()
