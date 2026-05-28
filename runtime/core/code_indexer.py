"""Code indexer for AscendForge (WS4) — gives the builder real understanding.

Walks a project, chunks source by symbol (functions/classes) where it can, embeds
chunks into a *dedicated* per-project vector store (no pollution of agent memory),
extracts a symbol + import map, and produces an architecture summary. Query returns
the most relevant file chunks for a goal so codegen is grounded in the actual repo.

Isolated store path: state/code_index/{project_id}.json
Summary path:        state/code_index/{project_id}.summary.json
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
    "env", ".forge_snapshots", ".cache", "coverage", ".next", ".turbo",
    "site-packages", ".pytest_cache", ".mypy_cache", "vendor",
}
_CODE_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript",
    ".tsx": "tsx", ".go": "go", ".rs": "rust", ".java": "java", ".css": "css",
    ".html": "html", ".json": "json", ".md": "markdown", ".sh": "bash",
    ".yml": "yaml", ".yaml": "yaml", ".sql": "sql", ".toml": "toml",
}
_ENTRY_HINTS = ("main.py", "server.js", "index.js", "app.py", "App.jsx", "__main__.py", "start.sh")
_MAX_FILES = 400
_MAX_CHUNK_LINES = 80
_MAX_FILE_BYTES = 200_000

_PY_SYMBOL = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", re.M)
_JS_SYMBOL = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|class\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\()", re.M)
_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
_JS_IMPORT = re.compile(r"""(?:import[^'"]*['"]([^'"]+)['"]|require\(['"]([^'"]+)['"]\))""")
_SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


def _safe_project_id(project_id: str) -> str:
    if not _SAFE_PROJECT_ID.fullmatch(project_id):
        raise ValueError("invalid project id")
    return project_id


def _safe_project_root(root: str) -> Path:
    allowed_root = os.path.realpath(os.environ.get("ASCENDFORGE_ALLOWED_ROOT", os.getcwd()))
    if root in {"", "."}:
        return Path(allowed_root)
    absolute_candidate = os.path.realpath(root)
    if os.path.commonpath([allowed_root, absolute_candidate]) == allowed_root:
        return Path(absolute_candidate)
    project_dir = os.path.basename(root.rstrip(os.sep))
    if project_dir in {"", ".", ".."}:
        raise ValueError("invalid project root")
    candidate = os.path.normpath(os.path.join(allowed_root, project_dir))
    if os.path.commonpath([allowed_root, candidate]) != allowed_root:
        raise ValueError("project root is outside allowed workspace")
    return Path(candidate)


def _state_dir() -> Path:
    home = Path(os.environ.get("AI_EMPLOYEE_HOME") or os.environ.get("AI_HOME") or Path.home() / ".ai-employee")
    return Path(os.environ.get("STATE_DIR") or home / "state").resolve()


def _index_dir() -> Path:
    d = _state_dir() / "code_index"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _store_for(project_id: str):
    from memory.vector_store import VectorStore
    safe_project = _safe_project_id(project_id)
    return VectorStore(path=_index_dir() / f"{safe_project}.json")


def _summary_path(project_id: str) -> Path:
    safe_project = _safe_project_id(project_id)
    base = os.path.realpath(_index_dir())
    fullpath = os.path.normpath(os.path.join(base, f"{safe_project}.summary.json"))
    if os.path.commonpath([base, fullpath]) != base:
        raise ValueError("summary path escapes index directory")
    return Path(fullpath)


def _chunk(text: str, lang: str) -> list[tuple[str, str]]:
    """Return [(symbol_label, chunk_text)]. Symbol-aware for py/js; else line windows."""
    lines = text.split("\n")
    pat = _PY_SYMBOL if lang == "python" else (_JS_SYMBOL if lang in ("javascript", "jsx", "typescript", "tsx") else None)
    if pat is None or len(lines) <= _MAX_CHUNK_LINES:
        out = []
        for i in range(0, len(lines), _MAX_CHUNK_LINES):
            seg = "\n".join(lines[i:i + _MAX_CHUNK_LINES]).strip()
            if seg:
                out.append((f"L{i + 1}", seg))
        return out or [("L1", text[:2000])]
    # split at symbol boundaries
    bounds = [m.start() for m in pat.finditer(text)]
    if not bounds:
        return [("L1", text[:2000])]
    bounds = [0] + [b for b in bounds if b > 0]
    chunks = []
    for i, start in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else len(text)
        seg = text[start:end].strip()
        if not seg:
            continue
        m = pat.search(seg)
        name = next((g for g in (m.groups() if m else ()) if g), f"chunk{i}") if m else f"chunk{i}"
        chunks.append((name, seg[:4000]))
    return chunks


def _symbols(text: str, lang: str) -> list[str]:
    pat = _PY_SYMBOL if lang == "python" else _JS_SYMBOL
    names = []
    for m in pat.finditer(text):
        names.extend(g for g in m.groups() if g)
    return names[:40]


def _imports(text: str, lang: str) -> list[str]:
    out = []
    if lang == "python":
        for m in _PY_IMPORT.finditer(text):
            out.append(m.group(1) or m.group(2))
    else:
        for m in _JS_IMPORT.finditer(text):
            out.append(m.group(1) or m.group(2))
    return [i for i in out if i][:40]


def index_project(root: str, project_id: str, *, max_files: int = _MAX_FILES) -> dict:
    """Index a project tree into its own vector store + write an architecture summary."""
    try:
        project_id = _safe_project_id(project_id)
        root_p = _safe_project_root(root)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    if not root_p.is_dir():
        return {"ok": False, "error": f"not a directory: {root}"}
    store = _store_for(project_id)
    t0 = time.time()
    files = 0
    chunks = 0
    total_lines = 0
    langs: dict[str, int] = {}
    symbol_map: dict[str, list[str]] = {}
    import_edges = 0
    entry_points = []

    for dirpath, dirnames, filenames in os.walk(root_p):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS and not d.startswith(".")]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            lang = _CODE_EXT.get(ext)
            if not lang:
                continue
            if files >= max_files:
                break
            fpath = Path(dirpath) / fn
            try:
                if fpath.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(fpath.relative_to(root_p))
            files += 1
            total_lines += text.count("\n") + 1
            langs[lang] = langs.get(lang, 0) + 1
            if fn in _ENTRY_HINTS:
                entry_points.append(rel)
            syms = _symbols(text, lang)
            if syms:
                symbol_map[rel] = syms
            import_edges += len(_imports(text, lang))
            for i, (label, body) in enumerate(_chunk(text, lang)):
                store.store(
                    key=f"{project_id}:{rel}:{i}",
                    text=f"# {rel} :: {label}\n{body}",
                    metadata={"memory_type": "code", "project_id": project_id, "path": rel,
                              "lang": lang, "symbol": label},
                    importance=0.6,
                )
                chunks += 1

    top_modules = sorted(symbol_map.items(), key=lambda kv: len(kv[1]), reverse=True)[:15]
    summary = {
        "project_id": project_id, "root": str(root_p), "indexed_at": time.time(),
        "files": files, "chunks": chunks, "lines": total_lines,
        "languages": dict(sorted(langs.items(), key=lambda kv: kv[1], reverse=True)),
        "entry_points": entry_points[:10],
        "top_modules": [{"path": p, "symbol_count": len(s), "symbols": s[:12]} for p, s in top_modules],
        "import_edges": import_edges,
        "duration_s": round(time.time() - t0, 2),
    }
    _summary_path(project_id).write_text(json.dumps(summary, indent=2))
    logger.info("indexed %s: %d files, %d chunks in %.1fs", project_id, files, chunks, summary["duration_s"])
    return {"ok": True, **summary}


def query_context(project_id: str, query: str, *, k: int = 6) -> dict:
    """Return the most relevant code chunks for a goal/query."""
    try:
        store = _store_for(project_id)
        hits = store.search(query, top_k=k * 3, memory_type="code") or []
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "results": []}
    results = []
    seen_paths = set()
    for h in hits:
        meta = h.get("metadata") or {}
        if meta.get("project_id") != project_id:
            continue
        path = meta.get("path", "?")
        results.append({
            "path": path, "symbol": meta.get("symbol"), "lang": meta.get("lang"),
            "score": round(float(h.get("score", 0) or 0), 4),
            "snippet": (h.get("text") or "")[:1200],
        })
        seen_paths.add(path)
        if len(results) >= k:
            break
    return {"ok": True, "query": query, "count": len(results),
            "files": sorted(seen_paths), "results": results}


def get_summary(project_id: str) -> dict:
    try:
        project_id = _safe_project_id(project_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "project_id": project_id}
    try:
        p = _summary_path(project_id)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "project_id": project_id}
    if not p.exists():
        return {"ok": False, "error": "not indexed yet", "project_id": project_id}
    try:
        return {"ok": True, **json.loads(p.read_text())}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
