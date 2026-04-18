"""Live Preview — sandbox test panel for Ascend Forge.

Lets the user paste code and immediately run it through the
SandboxExecutor to see validation results before submitting to the
ForgeController.

No code is written to disk here — this is a pure validation preview.
"""
from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[2]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


def render_live_preview() -> None:
    """Render the live sandbox preview panel inside a Streamlit context."""
    if not _HAS_ST:
        print("Streamlit not installed — skipping live_preview render.")
        return

    st.subheader("🔬 Live Sandbox Preview")
    st.caption(
        "Paste code here to instantly validate it in the sandbox. "
        "No code is written to disk — this is a pure dry-run."
    )

    code = st.text_area(
        "Code to test",
        height=320,
        placeholder="# Paste your Python code here\ndef my_function():\n    return 42",
        key="live_preview_code",
    )

    col_run, col_module = st.columns([1, 2])
    with col_module:
        module_name = st.text_input(
            "Module name (for error messages)",
            value="preview_module",
            key="live_preview_module",
        )
    with col_run:
        run = st.button("▶️ Run Sandbox", key="live_preview_run")

    if run:
        if not code.strip():
            st.warning("Enter some code first.")
            return

        try:
            from runtime.runtime.sandbox_executor import get_sandbox_executor
            result = get_sandbox_executor().run(code, module_name=module_name)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Sandbox executor error: {exc}")
            return

        st.divider()
        if result["safe"]:
            st.success(
                f"✅ Sandbox PASSED in {result['duration_ms']} ms  |  "
                f"Exports: {', '.join(result['exports']) or '(none)'}"
            )
        else:
            st.error(f"❌ Sandbox FAILED in {result['duration_ms']} ms")

        if result["errors"]:
            st.markdown("**Errors**")
            for err in result["errors"]:
                st.code(err, language="text")

        if result["warnings"]:
            st.markdown("**Warnings**")
            for w in result["warnings"]:
                st.warning(w)

        if result["safe"] and result["exports"]:
            st.markdown("**Detected exports**")
            for exp in result["exports"]:
                st.code(exp, language="python")


if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="Ascend Forge — Live Preview", page_icon="🔬")
    render_live_preview()
