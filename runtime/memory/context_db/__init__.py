"""Context Database Layer (Module 2 — MASTER_PLAN_V3 Reference-Capability Layers).

Filesystem-style, tenant-scoped context tree with tiered loading (L0/L1/L2),
hybrid recursive retrieval (BM25 + vector, RRF-fused) that ALWAYS returns a
visible retrieval trace, session compression into durable memory nodes, and
fail-closed path/scope permissions.

Reference patterns (rebuilt natively, no code copied):
  - OpenViking — filesystem context paradigm, L0/L1/L2 tiered loading,
    visible retrieval trajectories.
  - turbovec  — hybrid retrieval, stable node IDs, allowlist scope filters.

This layer sits ON TOP of the existing retrieval stores. It reuses
``runtime/memory/bm25.py`` as-is for lexical ranking and the vector store's
own embedding primitives (``core.memory_index``) for the semantic lane.
It does NOT replace ``vector_store.py`` / ``memory_router.py`` and creates
no second persistent vector index.

Modules
-------
- ``context_tree``         — persisted node tree under ``CONTEXT_DB_DIR``
- ``context_loader``       — tiered L0/L1/L2 views with a char budget
- ``recursive_retriever``  — hybrid retrieve() with mandatory trace
- ``session_compressor``   — conversation → durable decision/memory nodes
- ``context_permissions``  — fail-closed tenant + scope allowlist checks
"""
