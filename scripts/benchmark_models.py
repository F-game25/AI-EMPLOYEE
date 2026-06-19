#!/usr/bin/env python3
"""Benchmark installed Ollama models → real tok/s + VRAM + GPU/CPU split.

Writes ``state/model_benchmarks.json``. Only benchmarks models actually present
in ``ollama list`` (never pulls). These measured numbers are meant to replace
the research seeds in ``runtime/config/model_quant_profiles.json`` (Phase A0 of
docs/LOCAL_QUANTIZATION_AND_MODEL_ORCHESTRATION_PLAN.md). Honest: a model that
times out is recorded as ``status: "timeout"``, never a fabricated number.

Usage:
    python3 scripts/benchmark_models.py [--models a,b] [--num-predict 48]
        [--timeout 180] [--max-weights-mb 8000] [--include-heavy]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from engine.compute import hardware_profiler as hp  # noqa: E402

OLLAMA = "http://localhost:11434"
_PROMPT = "Write one concise sentence about the ocean."
# Models never worth a local quick-bench on an 8GB box (huge CPU-offload).
_ALWAYS_SKIP = {"llama3.3:latest", "llama3.3"}


def _post(path: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        OLLAMA + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _installed() -> list[str]:
    inv = hp.ollama_inventory() or []
    return [m.get("name") or m.get("model") for m in inv
            if (m.get("name") or m.get("model"))]


def _loaded_entry(model: str) -> dict:
    for p in (hp.ollama_loaded() or []):
        if (p.get("name") or p.get("model")) == model:
            return p
    return {}


def _profile_weights_mb(model: str) -> int | None:
    try:
        prof = json.loads((ROOT / "runtime/config/model_quant_profiles.json").read_text())
        quants = (prof.get(model) or {}).get("quants") or {}
        return min(quants.values()) if quants else None
    except Exception:
        return None


def benchmark(model: str, num_predict: int, timeout: float) -> dict:
    rec: dict = {"model": model,
                 "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        t0 = time.time()
        _post("/api/generate",
              {"model": model, "prompt": "hi", "stream": False,
               "options": {"num_predict": 1}}, timeout)
        rec["load_ms"] = int((time.time() - t0) * 1000)

        resp = _post("/api/generate",
                     {"model": model, "prompt": _PROMPT, "stream": False,
                      "options": {"num_predict": num_predict}}, timeout)
        n = resp.get("eval_count") or 0
        dur_ns = resp.get("eval_duration") or 0
        rec["tokens_per_s"] = round(n / (dur_ns / 1e9), 2) if dur_ns else None
        rec["eval_count"] = n

        ps = _loaded_entry(model)
        rec["vram_mb"] = ps.get("vram_mb")
        rec["cpu_mb"] = ps.get("cpu_mb")
        rec["gpu_fraction"] = ps.get("gpu_fraction")  # 1.0 = fully on GPU
        rec["context_length"] = ps.get("context_length")
        rec["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 — timeouts/errors are recorded honestly
        rec["status"] = "timeout" if "timed out" in str(exc).lower() else "error"
        rec["error"] = str(exc)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="", help="comma list; default = all installed")
    ap.add_argument("--num-predict", type=int, default=48)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--max-weights-mb", type=int, default=8000,
                    help="skip models whose smallest quant exceeds this (unless --include-heavy)")
    ap.add_argument("--include-heavy", action="store_true")
    args = ap.parse_args()

    if hp.ollama_inventory() is None:
        print("Ollama not reachable on", OLLAMA, "— start it (ollama serve).")
        return 1

    installed = _installed()
    targets = [m.strip() for m in args.models.split(",") if m.strip()] or installed
    targets = [m for m in targets if m in installed and m not in _ALWAYS_SKIP]

    snap = hp.snapshot()
    results: list[dict] = []
    for m in targets:
        w = _profile_weights_mb(m)
        if not args.include_heavy and w is not None and w > args.max_weights_mb:
            print(f"skip (heavy, {w}MB > {args.max_weights_mb}): {m}")
            results.append({"model": m, "status": "skipped_heavy", "weights_mb": w})
            continue
        print(f"benchmarking {m} ...", flush=True)
        rec = benchmark(m, args.num_predict, args.timeout)
        print(f"  -> {rec.get('status')} tok/s={rec.get('tokens_per_s')} "
              f"vram_mb={rec.get('vram_mb')} gpu_frac={rec.get('gpu_fraction')}")
        results.append(rec)

    out = {
        "_meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "host": {"free_vram_mb": snap.get("vram_free_mb"),
                     "total_vram_mb": snap.get("vram_total_mb"),
                     "ram_available_mb": snap.get("ram_available_mb"),
                     "cpu_threads": snap.get("cpu_threads")},
            "num_predict": args.num_predict,
            "note": "tok/s from Ollama eval_count/eval_duration; vram_bytes from /api/ps size_vram",
        },
        "results": results,
    }
    # Write to the canonical state dir ($STATE_DIR → ~/.ai-employee/state) so the
    # Models page / /api/models/benchmarks reads the same file the stack runs against.
    try:
        from core.state_paths import canonical_state_dir
        out_path = canonical_state_dir() / "model_benchmarks.json"
    except Exception:  # noqa: BLE001 — fall back to repo-local state if helper unavailable
        out_path = ROOT / "state" / "model_benchmarks.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\nbenchmark results written ({len([r for r in results if r.get('status') == 'ok'])} measured)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
