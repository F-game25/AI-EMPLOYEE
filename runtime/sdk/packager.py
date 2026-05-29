"""Build .aiepkg (zip) from a plugin directory."""
from __future__ import annotations
import hashlib
import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REQUIRED_FILES = ["manifest.json"]
_EXCLUDE_PATTERNS = {".git", "__pycache__", ".DS_Store", "*.pyc", "*.egg-info"}


def _should_exclude(name: str) -> bool:
    for pat in _EXCLUDE_PATTERNS:
        if pat.startswith("*"):
            if name.endswith(pat[1:]):
                return True
        elif name == pat:
            return True
    return False


def build(plugin_dir: str, output_path: Optional[str] = None) -> str:
    """
    Build .aiepkg from plugin_dir.
    Returns path to created package.
    """
    src = Path(plugin_dir).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Plugin directory not found: {src}")

    for req in _REQUIRED_FILES:
        if not (src / req).exists():
            raise FileNotFoundError(f"Required file missing: {req}")

    manifest = json.loads((src / "manifest.json").read_text())
    plugin_id = manifest.get("id", "unknown").replace("/", "_")
    version = manifest.get("version", "0.0.0")

    if output_path is None:
        output_path = str(src.parent / f"{plugin_id}-{version}.aiepkg")

    buf = bytearray()
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(src.rglob("*")):
            if fp.is_file():
                rel = fp.relative_to(src)
                # Skip excluded patterns
                if any(_should_exclude(part) for part in rel.parts):
                    continue
                zf.write(fp, str(rel))

    # Write checksum
    digest = hashlib.sha256(Path(output_path).read_bytes()).hexdigest()
    with zipfile.ZipFile(output_path, "a") as zf:
        zf.writestr("MANIFEST.sha256", digest)

    logger.info("Built %s → %s (sha256: %s)", plugin_id, output_path, digest[:12])
    return output_path


# Optional CLI usage
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python packager.py <plugin_dir> [output.aiepkg]")
        sys.exit(1)
    out = build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(f"Package created: {out}")
