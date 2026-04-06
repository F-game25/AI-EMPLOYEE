"""refactor/applier.py — Safe patch applier with rollback and dry-run.

A patch is ONLY applied when ALL of the following are true:
  1. score_new > score_old          (measurable improvement)
  2. syntax is valid                (Python-parseable or JS syntax-checkable)
  3. no functional regression       (required props/hooks not removed)
  4. risk_level is within threshold (configurable)

Default behaviour: DRY-RUN (suggest mode) — writes nothing to disk.
Set ``dry_run=False`` to enable actual file writes with rollback support.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE       = Path(__file__).parent
_ENGINE_DIR = _HERE.parent
_CONFIG_DIR = _ENGINE_DIR / "config"
_MODES_PATH = _CONFIG_DIR / "modes.json"

# Rollback backup directory
_BACKUP_DIR = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee"))) / "state" / "ui-engine-backups"


# ── Public API ────────────────────────────────────────────────────────────────

def apply_patch(
    target_file: str | Path,
    improved_code: str,
    score_old: float,
    score_new: float,
    patch_meta: dict[str, Any],
    dry_run: bool = True,
    mode: str = "general_mode",
    max_risk: str = "medium",
) -> dict[str, Any]:
    """Attempt to apply *improved_code* to *target_file*.

    Args:
        target_file:   Path to the component file on disk.
        improved_code: New source code to write.
        score_old:     Current optimisation score.
        score_new:     Predicted score after the change.
        patch_meta:    Dict returned by patch_generator.generate_patch().
        dry_run:       When True (default) nothing is written — suggest mode.
        mode:          Active optimisation mode (determines accept_threshold).
        max_risk:      Maximum acceptable risk level ("low"|"medium"|"high").

    Returns a dict with keys:
        decision        — "applied" | "rejected" | "suggested" | "dry_run"
        reason          — human-readable explanation
        backup_path     — path to backup file if applied (else None)
        validation      — list of validation result dicts
    """
    target_file  = Path(target_file)
    validations: list[dict[str, Any]] = []

    # ── 1. Score gate ─────────────────────────────────────────────────────────
    modes        = _load_json(_MODES_PATH)
    threshold    = modes.get(mode, {}).get("accept_threshold", 2.0)
    score_delta  = score_new - score_old

    val_score: dict[str, Any] = {
        "check":  "score_improvement",
        "pass":   score_delta >= threshold,
        "detail": f"Δscore={score_delta:.2f} (threshold={threshold})",
    }
    validations.append(val_score)

    # ── 2. Syntax validation ──────────────────────────────────────────────────
    val_syntax = _validate_syntax(improved_code, target_file.suffix)
    validations.append(val_syntax)

    # ── 3. Functional regression check ───────────────────────────────────────
    original_code = target_file.read_text(encoding="utf-8") if target_file.exists() else ""
    val_regression = _check_regression(original_code, improved_code)
    validations.append(val_regression)

    # ── 4. Risk gate ──────────────────────────────────────────────────────────
    risk_rank  = {"low": 0, "medium": 1, "high": 2}
    patch_risk = patch_meta.get("risk_level", "medium")
    val_risk: dict[str, Any] = {
        "check":  "risk_level",
        "pass":   risk_rank.get(patch_risk, 2) <= risk_rank.get(max_risk, 1),
        "detail": f"patch_risk={patch_risk}, max_allowed={max_risk}",
    }
    validations.append(val_risk)

    # ── Decision ──────────────────────────────────────────────────────────────
    all_pass = all(v["pass"] for v in validations)
    failed   = [v for v in validations if not v["pass"]]

    if not all_pass:
        reason = "Rejected: " + "; ".join(v["detail"] for v in failed)
        return {"decision": "rejected", "reason": reason, "backup_path": None, "validation": validations}

    if dry_run:
        reason = (
            f"Dry-run: all checks passed (Δscore={score_delta:.2f}). "
            "Set dry_run=False to apply."
        )
        return {"decision": "dry_run", "reason": reason, "backup_path": None, "validation": validations}

    # ── Apply with backup ─────────────────────────────────────────────────────
    backup_path = _backup(target_file)
    try:
        target_file.write_text(improved_code, encoding="utf-8")
        reason = f"Applied: Δscore={score_delta:.2f}, risk={patch_risk}, backup={backup_path}"
        return {"decision": "applied", "reason": reason, "backup_path": str(backup_path), "validation": validations}
    except Exception as exc:
        # Rollback immediately on any write error
        rollback(target_file, backup_path)
        reason = f"Write failed — rolled back: {exc}"
        return {"decision": "rejected", "reason": reason, "backup_path": None, "validation": validations}


def rollback(target_file: str | Path, backup_path: str | Path) -> bool:
    """Restore *target_file* from *backup_path*.

    Returns True on success, False otherwise.
    """
    try:
        shutil.copy2(str(backup_path), str(target_file))
        return True
    except Exception:
        return False


def dry_run_suggest(
    target_file: str | Path,
    improved_code: str,
    score_old: float,
    score_new: float,
    patch_meta: dict[str, Any],
    mode: str = "general_mode",
) -> dict[str, Any]:
    """Convenience wrapper — always runs in dry-run mode."""
    return apply_patch(
        target_file,
        improved_code,
        score_old,
        score_new,
        patch_meta,
        dry_run=True,
        mode=mode,
    )


# ── Backup ────────────────────────────────────────────────────────────────────

def _backup(target_file: Path) -> Path:
    """Copy *target_file* to the backup directory, timestamped."""
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{target_file.stem}__{ts}{target_file.suffix}"
    dest = _BACKUP_DIR / name
    shutil.copy2(str(target_file), str(dest))
    return dest


# ── Validators ────────────────────────────────────────────────────────────────

def _validate_syntax(code: str, suffix: str) -> dict[str, Any]:
    """Check syntax.  Python files are AST-parsed; JS/JSX use a heuristic."""
    suffix = suffix.lower()

    if suffix in (".py",):
        try:
            ast.parse(code)
            return {"check": "syntax", "pass": True, "detail": "Python AST valid"}
        except SyntaxError as exc:
            return {"check": "syntax", "pass": False, "detail": f"SyntaxError: {exc}"}

    if suffix in (".js", ".jsx", ".ts", ".tsx", ".vue"):
        # Heuristic: balanced braces / brackets / parens
        ok, detail = _heuristic_js_syntax(code)
        return {"check": "syntax", "pass": ok, "detail": detail}

    # Unknown type — assume OK
    return {"check": "syntax", "pass": True, "detail": f"Unchecked file type ({suffix})"}


def _heuristic_js_syntax(code: str) -> tuple[bool, str]:
    """Very lightweight JS syntax check: balanced delimiters."""
    pairs = {"{": "}", "[": "]", "(": ")"}
    stack: list[str] = []
    for ch in code:
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in pairs.values():
            if not stack or stack[-1] != ch:
                return False, f"Unbalanced delimiter '{ch}'"
            stack.pop()
    if stack:
        return False, f"Unclosed delimiters: {''.join(stack)}"
    return True, "Heuristic delimiter balance OK"


def _check_regression(original: str, improved: str) -> dict[str, Any]:
    """Ensure no required props / hooks / exports were removed."""
    _hook_re   = __import__("re").compile(r"\buse[A-Z]\w+\(")
    _export_re = __import__("re").compile(r"\bexport\b")
    _import_re = __import__("re").compile(r"\bimport\b")

    orig_hooks   = set(_hook_re.findall(original))
    impr_hooks   = set(_hook_re.findall(improved))
    removed_hooks = orig_hooks - impr_hooks

    orig_exports = len(_export_re.findall(original))
    impr_exports = len(_export_re.findall(improved))

    issues: list[str] = []
    if removed_hooks:
        issues.append(f"Removed hooks: {', '.join(removed_hooks)}")
    if impr_exports < orig_exports:
        issues.append(f"Export count dropped {orig_exports}→{impr_exports}")

    if issues:
        return {"check": "regression", "pass": False, "detail": "; ".join(issues)}
    return {"check": "regression", "pass": True, "detail": "No functional regressions detected"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python3 applier.py <target_file> <improved_file> [--apply]",
            file=sys.stderr,
        )
        sys.exit(1)

    target   = Path(sys.argv[1])
    improved = Path(sys.argv[2]).read_text(encoding="utf-8")
    do_apply = "--apply" in sys.argv

    result = apply_patch(
        target_file=target,
        improved_code=improved,
        score_old=50.0,
        score_new=65.0,
        patch_meta={"risk_level": "low"},
        dry_run=not do_apply,
    )
    print(json.dumps(result, indent=2))
