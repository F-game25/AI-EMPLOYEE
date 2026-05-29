#!/usr/bin/env python3
"""Verify that enterprise core Python dependencies are importable.

This is intentionally offline-only: it never installs or downloads anything.
The launcher/startup path uses it to fail clearly when a packaged build is
missing a dependency that is part of the core system contract.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "runtime" / "config" / "core_dependency_manifest.json"


def load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def verify(manifest: dict, include_connectors: bool = False) -> dict:
    groups = ["core"]
    if include_connectors:
        groups.append("connectors")

    checked = []
    missing = []
    for group in groups:
        for item in manifest.get(group, []):
            import_name = item.get("import")
            if not import_name:
                continue
            row = {
                "group": group,
                "pip": item.get("pip", ""),
                "import": import_name,
                "purpose": item.get("purpose", ""),
            }
            try:
                importlib.import_module(import_name)
                row["ok"] = True
            except Exception as exc:  # noqa: BLE001 - report import failure exactly
                row["ok"] = False
                row["error"] = str(exc)
                missing.append(row)
            checked.append(row)

    return {
        "ok": not missing,
        "checked": checked,
        "missing": missing,
        "manifest": str(DEFAULT_MANIFEST),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--include-connectors", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    result = verify(load_manifest(manifest_path), include_connectors=args.include_connectors)
    result["manifest"] = str(manifest_path)

    if args.json:
        print(json.dumps(result, indent=2), flush=True)
    elif result["ok"]:
        print(f"[✓] Core dependency imports OK ({len(result['checked'])} checked)", flush=True)
    else:
        print("[✗] Missing enterprise core dependencies:", flush=True)
        for row in result["missing"]:
            print(f"  - {row['pip']}  import={row['import']}  purpose={row['purpose']}  error={row.get('error', '')}", flush=True)
        print("Rebuild the downloadable app with the offline wheelhouse/vendor bundle; do not download on first boot.", flush=True)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
