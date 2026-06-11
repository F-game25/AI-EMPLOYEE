"""Hybrid recursive retrieval over the context tree — with a mandatory trace.

Retrieval lanes
---------------
- **BM25** — reuses ``runtime/memory/bm25.py`` AS-IS (its corpus→scores API
  fits exactly); ranked over node ``summary + content``.
- **Vector** — reuses the existing vector store's embedding primitives
  (``core.memory_index.embed_text`` / ``cosine_similarity``) applied to the
  same candidate texts. We deliberately do NOT mirror tree nodes into the
  global ``vector_store.json`` singleton: that would create a second
  persistent index of the same data (forbidden by Module 2's "no 2nd store"
  rule). Defensive import — when the embedding layer is unavailable or
  ``CONTEXT_DB_VECTOR=0``, retrieval degrades honestly to BM25-only and the
  trace says so.
- **Fusion** — reciprocal rank fusion (RRF, k=60) over both ranked lists.

Recursive descent (OpenViking): the initial candidate pass covers file nodes
up to ``_INITIAL_DEPTH`` logical segments plus directory pseudo-docs (name +
child names/summaries). When a directory ranks inside the fused top_k, its
children are pulled in one level deeper (bounded to ``_MAX_DESCENTS`` dirs)
and the whole pool is re-fused.

Trace (the OpenViking signature feature): EVERY call returns ``trace`` — an
ordered list of ``{step, action, query|path, candidates_considered, chosen,
reason}`` — including error and empty-tree paths, so wrong context is always
debuggable.

Scope filters (turbovec allowlist): ``filters={tenant, allowed_scopes:[...]}``
are enforced via ``context_permissions.check`` BEFORE any scoring.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from memory.bm25 import BM25
from memory.context_db import context_permissions as perms
from memory.context_db.context_loader import build_view
from memory.context_db.context_tree import ContextTree

logger = logging.getLogger("context_db.retriever")

_RRF_K = 60
_INITIAL_DEPTH = 3      # logical segments, e.g. /project/goals/q3
_MAX_DESCENTS = 3       # directories descended per query
_DOC_TEXT_CAP = 4000    # chars of node text scored per lane
_RICH_VIEWS = 3         # top results served at the richer level


def _vector_fns():
    """Defensive access to the existing embedding primitives."""
    if os.environ.get("CONTEXT_DB_VECTOR", "1") == "0":
        return None
    try:
        from core.memory_index import cosine_similarity, embed_text
        return embed_text, cosine_similarity
    except Exception as exc:  # noqa: BLE001 — degrade, never crash retrieval
        logger.info("vector lane unavailable: %s", exc)
        return None


def _doc_text(node: dict[str, Any]) -> str:
    return (str(node.get("summary", "")) + " "
            + str(node.get("content", "")))[:_DOC_TEXT_CAP]


def _rrf(ranked_lists: list[list[int]], n: int) -> list[tuple[int, float]]:
    """Reciprocal rank fusion over index-ranked lists → (idx, score) desc."""
    scores = [0.0] * n
    for ranking in ranked_lists:
        for rank, idx in enumerate(ranking):
            scores[idx] += 1.0 / (_RRF_K + rank + 1)
    order = sorted(range(n), key=lambda i: scores[i], reverse=True)
    return [(i, scores[i]) for i in order if scores[i] > 0.0]


def _rank_pool(query: str, texts: list[str],
               trace: list[dict], step_offset: int) -> list[tuple[int, float]]:
    """BM25 + (optional) vector ranking over *texts*, RRF-fused. Traces lanes."""
    bm25_scores = BM25(texts).scores(query)
    bm25_rank = sorted(range(len(texts)), key=lambda i: bm25_scores[i],
                       reverse=True)
    bm25_rank = [i for i in bm25_rank if bm25_scores[i] > 0.0]
    trace.append({"step": step_offset, "action": "bm25_rank", "query": query,
                  "candidates_considered": len(texts),
                  "chosen": bm25_rank[:5],
                  "reason": "lexical lane (runtime/memory/bm25.py reused)"})

    lists = [bm25_rank]
    fns = _vector_fns()
    if fns:
        embed, cosine = fns
        q_emb = embed(query)
        sims = [cosine(q_emb, embed(t)) for t in texts]
        vec_rank = sorted(range(len(texts)), key=lambda i: sims[i], reverse=True)
        vec_rank = [i for i in vec_rank if sims[i] > 0.0]
        lists.append(vec_rank)
        trace.append({"step": step_offset + 1, "action": "vector_rank",
                      "query": query, "candidates_considered": len(texts),
                      "chosen": vec_rank[:5],
                      "reason": "semantic lane (core.memory_index embeddings)"})
    else:
        trace.append({"step": step_offset + 1, "action": "vector_unavailable",
                      "query": query, "candidates_considered": 0, "chosen": [],
                      "reason": "embedding layer disabled/unimportable — BM25-only"})

    fused = _rrf(lists, len(texts))
    trace.append({"step": step_offset + 2, "action": "rrf_fuse", "query": query,
                  "candidates_considered": len(texts),
                  "chosen": [i for i, _ in fused[:8]],
                  "reason": f"reciprocal rank fusion over {len(lists)} lane(s), k={_RRF_K}"})
    return fused


def retrieve(query: str, project_id: str = "default",
             levels: tuple[str, ...] = ("L0", "L1"),
             filters: dict[str, Any] | None = None, top_k: int = 8,
             tree: ContextTree | None = None) -> dict[str, Any]:
    """Hybrid recursive retrieval. ALWAYS returns ``{nodes, trace}``; never raises."""
    trace: list[dict[str, Any]] = []
    try:
        return _retrieve(query, project_id, levels, filters, top_k, tree, trace)
    except Exception as exc:  # noqa: BLE001 — retrieval must stay debuggable
        logger.warning("retrieve failed: %s", exc)
        trace.append({"step": len(trace) + 1, "action": "error", "query": query,
                      "candidates_considered": 0, "chosen": [],
                      "reason": f"retrieval error: {exc}"})
        return {"nodes": [], "trace": trace, "query": query}


def _retrieve(query: str, project_id: str, levels: tuple[str, ...],
              filters: dict[str, Any] | None, top_k: int,
              tree: ContextTree | None,
              trace: list[dict[str, Any]]) -> dict[str, Any]:
    query = str(query or "").strip()
    filters = filters if isinstance(filters, dict) else {}
    tenant = str(filters.get("tenant") or "default")
    scopes = filters.get("allowed_scopes")
    if scopes is not None and not isinstance(scopes, (list, tuple)):
        scopes = []  # malformed allowlist → fail closed (deny all)
    levels = tuple(levels) or ("L0",)
    top_k = max(1, min(int(top_k or 8), 50))
    tree = tree or ContextTree(tenant=tenant)

    if not query:
        trace.append({"step": 1, "action": "reject", "query": query,
                      "candidates_considered": 0, "chosen": [],
                      "reason": "empty query"})
        return {"nodes": [], "trace": trace, "query": query}

    # 1. Candidates + allowlist filter BEFORE scoring (turbovec pattern).
    all_nodes = list(tree.walk_nodes("/"))
    allowed = [n for n in all_nodes
               if perms.check(str(n.get("path", "")), tenant,
                              list(scopes) if scopes is not None else None)]
    trace.append({"step": 1, "action": "scope_filter", "query": query,
                  "candidates_considered": len(all_nodes),
                  "chosen": len(allowed),
                  "reason": ("allowlist excluded "
                             f"{len(all_nodes) - len(allowed)} node(s) pre-scoring"
                             if scopes is not None else "no scope allowlist set")})
    if not allowed:
        trace.append({"step": 2, "action": "empty", "query": query,
                      "candidates_considered": 0, "chosen": [],
                      "reason": "no permitted nodes in tree"})
        return {"nodes": [], "trace": trace, "query": query}

    # 2. Initial pool: shallow file nodes + directory pseudo-docs.
    def _depth(n: dict) -> int:
        return len(str(n.get("path", "")).strip("/").split("/"))

    shallow = [n for n in allowed if _depth(n) <= _INITIAL_DEPTH]
    deep = [n for n in allowed if _depth(n) > _INITIAL_DEPTH]
    by_dir: dict[str, list[dict]] = {}
    for n in deep:
        parent = "/".join(str(n["path"]).split("/")[:-1])
        by_dir.setdefault(parent, []).append(n)

    pool: list[dict[str, Any]] = list(shallow)
    texts = [_doc_text(n) for n in pool]
    dir_docs: list[tuple[str, int]] = []  # (dir_path, pool index)
    for dpath, children in sorted(by_dir.items()):
        child_bits = " ".join(
            f"{str(c.get('path','')).rsplit('/',1)[-1]} {str(c.get('summary',''))[:80]}"
            for c in children[:20])
        pool.append({"id": f"dir:{dpath}", "path": dpath, "summary": "",
                     "content": "", "_dir": True})
        texts.append(f"{dpath.replace('/', ' ')} {child_bits}"[:_DOC_TEXT_CAP])
        dir_docs.append((dpath, len(pool) - 1))
    trace.append({"step": 2, "action": "candidate_pool", "query": query,
                  "candidates_considered": len(pool),
                  "chosen": [n["path"] for n in pool[:8]],
                  "reason": (f"{len(shallow)} file node(s) ≤ depth {_INITIAL_DEPTH} "
                             f"+ {len(dir_docs)} directory doc(s)")})

    # 3. Rank lanes + fuse.
    fused = _rank_pool(query, texts, trace, step_offset=3)

    # 4. Recursive descent: high-scoring directories pull in children (1 level).
    step = len(trace) + 1
    descended = 0
    top_idx = {i for i, _ in fused[:top_k]}
    for dpath, idx in dir_docs:
        if descended >= _MAX_DESCENTS or idx not in top_idx:
            continue
        children = by_dir.get(dpath, [])
        new = [c for c in children if all(c["path"] != p["path"] for p in pool)]
        for c in new:
            pool.append(c)
            texts.append(_doc_text(c))
        trace.append({"step": step, "action": "descend", "path": dpath,
                      "candidates_considered": len(children),
                      "chosen": [c["path"] for c in new[:8]],
                      "reason": "directory ranked in fused top_k — one level down"})
        step += 1
        descended += 1
    if descended:
        fused = _rank_pool(query, texts, trace, step_offset=step)
        step = len(trace) + 1

    # 5. Final selection (file nodes only) + tiered views.
    rich_level = levels[-1] if levels[-1] in ("L0", "L1", "L2") else "L0"
    base_level = levels[0] if levels[0] in ("L0", "L1", "L2") else "L0"
    nodes: list[dict[str, Any]] = []
    for idx, score in fused:
        node = pool[idx]
        if node.get("_dir"):
            continue
        level = rich_level if len(nodes) < _RICH_VIEWS else base_level
        view = build_view(node, level)
        view["score"] = round(score, 6)
        nodes.append(view)
        if len(nodes) >= top_k:
            break
    trace.append({"step": step, "action": "select", "query": query,
                  "candidates_considered": len(pool),
                  "chosen": [v["path"] for v in nodes],
                  "reason": (f"top {len(nodes)} file node(s); first {_RICH_VIEWS} "
                             f"at {rich_level}, rest at {base_level}")})
    return {"nodes": nodes, "trace": trace, "query": query}
