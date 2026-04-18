"""Memory Viewer — Streamlit panel for inspecting stored memories.

Features:
- Memory health summary (cache size, vector store counts by type)
- Search memories by query text with optional type filter
- View recent entries from the vector store
- Filterable by memory_type: episodic / semantic / procedural

Can be run standalone::

    PYTHONPATH=runtime streamlit run runtime/ui/dashboard/memory_viewer.py
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


def _get_router() -> Any:
    from memory.memory_router import get_memory_router
    return get_memory_router()


def render_memory_viewer() -> None:
    """Render the memory viewer panel inside a Streamlit context."""
    if not _HAS_ST:
        print("Streamlit not installed — dashboard rendering skipped.")
        return

    st.subheader("🗄️ Memory Viewer")

    # ── Health summary ────────────────────────────────────────────────────────
    try:
        router = _get_router()
        health = router.health()
        ve = health.get("vector_entries", {})
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Cache (live)", str(health.get("cache_live_entries", 0)))
        col2.metric("Episodic", str(ve.get("episodic", 0)))
        col3.metric("Semantic",  str(ve.get("semantic",  0)))
        col4.metric("Procedural", str(ve.get("procedural", 0)))
    except Exception as exc:  # noqa: BLE001
        st.error(f"Memory health unavailable: {exc}")
        return

    st.divider()

    # ── Search ────────────────────────────────────────────────────────────────
    st.markdown("**Search Memory**")
    search_col, type_col = st.columns([3, 1])
    with search_col:
        query = st.text_input(
            "Search query",
            placeholder="e.g. email marketing best practices",
            key="memory_search_query",
        )
    with type_col:
        mem_type = st.selectbox(
            "Type",
            ["all", "episodic", "semantic", "procedural"],
            key="memory_type_filter",
        )

    if query:
        try:
            mt_filter = mem_type if mem_type != "all" else None
            results = router.retrieve(query, memory_type=mt_filter, top_k=10)
            if results:
                import pandas as pd

                rows = [
                    {
                        "Key": r.get("key", ""),
                        "Type": r.get("metadata", {}).get("memory_type", ""),
                        "Score": round(float(r.get("_score", 0)), 4),
                        "Source": r.get("metadata", {}).get("source", ""),
                        "Text": (r.get("text") or "")[:120],
                    }
                    for r in results
                ]
                st.dataframe(
                    pd.DataFrame(rows),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No matching memories found.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Search failed: {exc}")

    st.divider()

    # ── Recent entries ────────────────────────────────────────────────────────
    st.markdown("**Recent Entries (Vector Store)**")
    type_snap = st.selectbox(
        "Filter by type",
        ["all", "episodic", "semantic", "procedural"],
        key="memory_snap_type",
    )
    try:
        from memory.vector_store import get_vector_store
        vs = get_vector_store()
        entries = vs.snapshot(limit=50)
        if type_snap != "all":
            entries = [e for e in entries if e.get("metadata", {}).get("memory_type") == type_snap]

        if entries:
            import pandas as pd

            rows = [
                {
                    "Key": e.get("key", ""),
                    "Type": e.get("metadata", {}).get("memory_type", ""),
                    "Importance": round(float(e.get("importance", 0)), 3),
                    "Accesses": int(e.get("access_count", 0)),
                    "Last Accessed": e.get("last_accessed", ""),
                    "Text": (e.get("text") or "")[:100],
                }
                for e in entries
            ]
            st.dataframe(
                pd.DataFrame(rows),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No entries in vector store yet.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load entries: {exc}")

    st.divider()

    # ── Write a memory entry ──────────────────────────────────────────────────
    with st.expander("➕ Store a new memory"):
        new_key = st.text_input("Key", key="new_mem_key")
        new_text = st.text_area("Text", key="new_mem_text")
        new_type = st.selectbox(
            "Memory type",
            ["semantic", "episodic", "procedural"],
            key="new_mem_type",
        )
        new_importance = st.slider("Importance", 0.0, 1.0, 0.5, 0.05, key="new_mem_imp")
        if st.button("Store", key="new_mem_btn"):
            if new_key and new_text:
                try:
                    result = router.store(
                        new_key,
                        new_text,
                        memory_type=new_type,
                        source="dashboard",
                        importance=new_importance,
                    )
                    st.success(
                        f"Stored ✓  (vector={result.get('vector_stored')}, "
                        f"type={result.get('memory_type')})"
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Store failed: {exc}")
            else:
                st.warning("Key and Text are required.")


# ── Standalone entry ──────────────────────────────────────────────────────────

if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="AI Employee — Memory Viewer", page_icon="🗄️")
    render_memory_viewer()
