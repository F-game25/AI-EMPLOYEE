"""loop/auto_loop.py — Async orchestration pipeline for the UI-engine.

Pipeline stages (per component):
  [SCAN] → [RENDER] → [CAPTURE] → [ANALYZE] → [OPTIMIZE] → [SCORE]
  → [VALIDATE] → [APPLY/REJECT] → repeat

Features:
  - Incremental processing (only changed components)
  - SHA-256 change detection cache
  - Async concurrent execution via asyncio + ThreadPoolExecutor
  - Configurable mode and dry-run flag
  - Structured JSON progress/result log
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE        = Path(__file__).parent
_ENGINE_DIR  = _HERE.parent
_SCANNER_DIR = _ENGINE_DIR / "scanner"
_VISION_DIR  = _ENGINE_DIR / "vision"
_BRAIN_DIR   = _ENGINE_DIR / "brain"
_REFACTOR_DIR = _ENGINE_DIR / "refactor"
_CONFIG_DIR  = _ENGINE_DIR / "config"

_AI_HOME     = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_STATE_DIR   = _AI_HOME / "state"
_CACHE_FILE  = _STATE_DIR / "ui-engine-cache.json"
_LOG_FILE    = _STATE_DIR / "ui-engine.log.jsonl"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ui_engine.loop")


# ── Module loader helpers ─────────────────────────────────────────────────────

def _add_path(p: Path) -> None:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


def _import_modules() -> tuple[Any, Any, Any, Any, Any]:
    """Import all engine sub-modules and return them."""
    for p in (_SCANNER_DIR, _VISION_DIR, _BRAIN_DIR, _REFACTOR_DIR):
        _add_path(p)

    cp  = importlib.import_module("component_parser")
    sa  = importlib.import_module("style_analyzer")
    vr  = importlib.import_module("vision_runner")
    opt = importlib.import_module("ui_optimizer")
    pg  = importlib.import_module("patch_generator")
    return cp, sa, vr, opt, pg


# ── Cache ─────────────────────────────────────────────────────────────────────

def _load_cache() -> dict[str, str]:
    """Load SHA-256 hash cache {file_path: sha256_hex}."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _file_hash(path: Path) -> str:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def _is_changed(path: Path, cache: dict[str, str]) -> bool:
    key  = str(path)
    h    = _file_hash(path)
    if cache.get(key) != h:
        return True
    return False


# ── JSONL logger ──────────────────────────────────────────────────────────────

def _log(entry: dict[str, Any]) -> None:
    entry["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    with _LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# ── Single-component pipeline ─────────────────────────────────────────────────

def _process_component(
    component_path: Path,
    mode: str = "general_mode",
    dry_run: bool = True,
    screenshot_dir: str | None = None,
) -> dict[str, Any]:
    """Run the full pipeline for one component.  Blocking (run in thread pool)."""
    cp, sa, vr, opt, pg = _import_modules()
    _add_path(_REFACTOR_DIR)
    applier = importlib.import_module("applier")

    result: dict[str, Any] = {
        "file":    str(component_path),
        "mode":    mode,
        "dry_run": dry_run,
        "stages":  {},
    }

    # [SCAN] ──────────────────────────────────────────────────────────────────
    try:
        parsed = cp.parse_file(component_path)
        result["stages"]["scan"] = {"ok": True, "type": parsed.get("type")}
    except Exception as exc:
        result["stages"]["scan"] = {"ok": False, "error": str(exc)}
        result["decision"] = "error"
        _log({"event": "scan_error", "file": str(component_path), "error": str(exc)})
        return result

    # [ANALYZE] ───────────────────────────────────────────────────────────────
    try:
        style_report = sa.analyze(parsed)
        result["stages"]["analyze"] = {
            "ok": True,
            "debt_score": style_report["debt_score"],
            "violations": style_report["summary"]["total"],
        }
    except Exception as exc:
        result["stages"]["analyze"] = {"ok": False, "error": str(exc)}
        style_report = {"debt_score": 0, "violations": [], "summary": {}}

    # [CAPTURE] — optional (requires screenshot_dir) ──────────────────────────
    vision_report: dict[str, Any] = {"ux_score": 60, "issues": [], "directives": [], "source": "skipped"}
    if screenshot_dir:
        stem         = component_path.stem
        screenshot   = Path(screenshot_dir) / f"screen_{stem}_1280x800.png"
        if screenshot.exists():
            try:
                vision_report = vr.analyze_screenshot(screenshot)
                result["stages"]["capture"] = {
                    "ok": True,
                    "ux_score": vision_report.get("ux_score"),
                    "issues":   len(vision_report.get("issues", [])),
                }
            except Exception as exc:
                result["stages"]["capture"] = {"ok": False, "error": str(exc)}
        else:
            result["stages"]["capture"] = {"ok": True, "note": "No screenshot found — vision skipped"}
    else:
        result["stages"]["capture"] = {"ok": True, "note": "Screenshot dir not configured"}

    # [OPTIMIZE] ──────────────────────────────────────────────────────────────
    try:
        opt_result = opt.optimize(parsed, style_report, vision_report, mode=mode)
        result["stages"]["optimize"] = {
            "ok":              True,
            "current_score":   opt_result["current_score"],
            "predicted_score": opt_result["predicted_score"],
        }
    except Exception as exc:
        result["stages"]["optimize"] = {"ok": False, "error": str(exc)}
        result["decision"] = "error"
        _log({"event": "optimize_error", "file": str(component_path), "error": str(exc)})
        return result

    # [SCORE] — already embedded in opt_result ────────────────────────────────
    current_score   = opt_result["current_score"]
    predicted_score = opt_result["predicted_score"]
    improved_code   = opt_result["improved_code"]
    result["stages"]["score"] = {
        "ok":        True,
        "current":   current_score,
        "predicted": predicted_score,
        "delta":     round(predicted_score - current_score, 2),
    }

    # [VALIDATE + APPLY/REJECT] ───────────────────────────────────────────────
    try:
        original_code = component_path.read_text(encoding="utf-8")
        patch         = pg.generate_patch(original_code, improved_code, filename=str(component_path))

        apply_result = applier.apply_patch(
            target_file=component_path,
            improved_code=improved_code,
            score_old=current_score,
            score_new=predicted_score,
            patch_meta=patch,
            dry_run=dry_run,
            mode=mode,
        )
        result["stages"]["apply"] = {
            "ok":       True,
            "decision": apply_result["decision"],
            "reason":   apply_result["reason"],
        }
        result["decision"] = apply_result["decision"]
    except Exception as exc:
        result["stages"]["apply"] = {"ok": False, "error": str(exc)}
        result["decision"] = "error"

    _log({"event": "component_processed", **result})
    return result


# ── Multi-component orchestrator ──────────────────────────────────────────────

async def run_loop(
    component_paths: list[str | Path],
    mode: str = "general_mode",
    dry_run: bool = True,
    screenshot_dir: str | None = None,
    max_workers: int = 4,
    force_reprocess: bool = False,
) -> list[dict[str, Any]]:
    """Orchestrate the full pipeline for a list of component paths.

    Skips components whose source has not changed since the last run
    (unless *force_reprocess* is True).

    Returns a list of result dicts (one per component processed).
    """
    cache  = _load_cache()
    paths  = [Path(p) for p in component_paths]

    # Filter to changed components only
    to_process: list[Path] = []
    skipped: list[Path]    = []
    for p in paths:
        if not p.exists():
            logger.warning("Skipping missing file: %s", p)
            continue
        if not force_reprocess and not _is_changed(p, cache):
            skipped.append(p)
        else:
            to_process.append(p)

    logger.info(
        "UI-Engine loop: %d to process, %d unchanged / skipped",
        len(to_process), len(skipped),
    )

    results: list[dict[str, Any]] = []

    if not to_process:
        return results

    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=max_workers)

    futures = {
        loop.run_in_executor(
            executor,
            _process_component,
            path, mode, dry_run, screenshot_dir,
        ): path
        for path in to_process
    }

    done, _ = await asyncio.wait(list(futures.keys()))
    for fut in done:
        try:
            res = fut.result()
            results.append(res)
            # Update cache only if successfully processed
            if res.get("decision") != "error":
                cache[str(Path(res["file"]))] = _file_hash(Path(res["file"]))
        except Exception as exc:
            logger.error("Pipeline error: %s", exc)

    _save_cache(cache)
    executor.shutdown(wait=False)

    # Summary
    counts: dict[str, int] = {}
    for r in results:
        counts[r.get("decision", "unknown")] = counts.get(r.get("decision", "unknown"), 0) + 1
    logger.info("Loop complete: %s", counts)

    return results


# ── Convenience sync wrapper ──────────────────────────────────────────────────

def run_loop_sync(
    component_paths: list[str | Path],
    mode: str = "general_mode",
    dry_run: bool = True,
    screenshot_dir: str | None = None,
    max_workers: int = 4,
    force_reprocess: bool = False,
) -> list[dict[str, Any]]:
    """Synchronous wrapper around :func:`run_loop` for non-async callers."""
    return asyncio.run(
        run_loop(
            component_paths,
            mode=mode,
            dry_run=dry_run,
            screenshot_dir=screenshot_dir,
            max_workers=max_workers,
            force_reprocess=force_reprocess,
        )
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AscendForge UI-Engine auto loop")
    parser.add_argument("paths", nargs="+", help="Component file paths")
    parser.add_argument("--mode", default="general_mode",
                        choices=["money_mode", "general_mode", "blacklight_mode"],
                        help="Optimisation mode")
    parser.add_argument("--apply", action="store_true",
                        help="Actually apply patches (default: dry-run / suggest)")
    parser.add_argument("--screenshots", default=None,
                        help="Directory containing pre-captured screenshots")
    parser.add_argument("--workers", type=int, default=4,
                        help="Max concurrent worker threads")
    parser.add_argument("--force", action="store_true",
                        help="Reprocess even unchanged files")

    args = parser.parse_args()

    results = run_loop_sync(
        component_paths=args.paths,
        mode=args.mode,
        dry_run=not args.apply,
        screenshot_dir=args.screenshots,
        max_workers=args.workers,
        force_reprocess=args.force,
    )

    for r in results:
        decision = r.get("decision", "?")
        score    = r.get("stages", {}).get("score", {})
        print(
            f"[{decision.upper():10s}] {Path(r['file']).name}"
            f"  score={score.get('current', '?')}→{score.get('predicted', '?')}"
            f"  (Δ{score.get('delta', '?')})"
        )

    print(f"\nTotal: {len(results)} components processed.")
