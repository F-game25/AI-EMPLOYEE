#!/usr/bin/env python3
"""Build and verify the offline Python core runtime bundle.

This script is for release/build machines. It creates a platform-specific
wheelhouse, records hashes/license metadata, then proves the bundle works by
installing into a disposable venv with --no-index.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import venv
import zipfile
from email.parser import Parser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = REPO_ROOT / "runtime" / "requirements-core.txt"
DEFAULT_MANIFEST = REPO_ROOT / "runtime" / "config" / "core_dependency_manifest.json"
DEFAULT_WHEELHOUSE_ROOT = REPO_ROOT / "runtime" / "wheelhouse"
DEFAULT_BROWSER_ROOT = REPO_ROOT / "runtime" / "browsers" / "playwright"
DEFAULT_BUILD_ROOT = REPO_ROOT / ".build" / "python-core"


def target_tag() -> str:
    system = platform.system().lower() or "unknown"
    machine = platform.machine().lower() or "unknown"
    py_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    return f"{system}-{machine}-{py_tag}"


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd or REPO_ROOT), env=env, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_wheel_metadata(path: Path) -> dict:
    if path.suffix != ".whl":
        return {}
    try:
        with zipfile.ZipFile(path) as archive:
            metadata_name = next(
                name for name in archive.namelist()
                if name.endswith(".dist-info/METADATA")
            )
            metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8", errors="replace"))
            wheel_name = next(
                (name for name in archive.namelist() if name.endswith(".dist-info/WHEEL")),
                None,
            )
            tags: list[str] = []
            if wheel_name:
                wheel_meta = Parser().parsestr(archive.read(wheel_name).decode("utf-8", errors="replace"))
                tags = wheel_meta.get_all("Tag") or []
            return {
                "name": metadata.get("Name", ""),
                "version": metadata.get("Version", ""),
                "summary": metadata.get("Summary", ""),
                "license": metadata.get("License-Expression") or metadata.get("License", ""),
                "home_page": metadata.get("Home-page", ""),
                "project_url": metadata.get_all("Project-URL") or [],
                "tags": tags,
            }
    except Exception as exc:  # noqa: BLE001 - metadata is advisory
        return {"metadata_error": str(exc)}


def write_wheelhouse_manifest(wheelhouse: Path, requirements: Path, core_manifest: Path) -> Path:
    files = []
    for path in sorted(wheelhouse.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        if path.suffix not in {".whl", ".gz", ".zip"}:
            continue
        row = {
            "file": path.name,
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        row.update(read_wheel_metadata(path))
        files.append(row)

    data = {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": target_tag(),
        "python": sys.version.split()[0],
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "requirements": str(requirements.relative_to(REPO_ROOT)),
        "requirements_sha256": sha256(requirements),
        "core_dependency_manifest": str(core_manifest.relative_to(REPO_ROOT)),
        "core_dependency_manifest_sha256": sha256(core_manifest),
        "wheelhouse": str(wheelhouse.relative_to(REPO_ROOT)),
        "files": files,
        "security": {
            "install_mode": "offline-no-index",
            "first_boot_network_downloads_allowed": False,
            "source_builds_allowed": False,
        },
    }

    output = wheelhouse / "manifest.json"
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[ok] wrote {output}", flush=True)
    return output


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def verify_offline_install(wheelhouse: Path, requirements: Path, venv_dir: Path) -> Path:
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    python = venv_python(venv_dir)
    run([
        str(python),
        "-m",
        "pip",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        "-r",
        str(requirements),
    ])
    run([str(python), str(REPO_ROOT / "scripts" / "verify_core_dependencies.py")])
    return python


def write_browser_manifest(browser_root: Path) -> Path:
    files = []
    for path in sorted(browser_root.rglob("*")):
        if not path.is_file():
            continue
        files.append({
            "file": str(path.relative_to(browser_root)),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
    data = {
        "schema": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": target_tag(),
        "browser_root": str(browser_root.relative_to(REPO_ROOT)),
        "files": files,
        "security": {
            "runtime_downloads_allowed": False,
            "env": "PLAYWRIGHT_BROWSERS_PATH",
        },
    }
    output = browser_root / "manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[ok] wrote {output}", flush=True)
    return output


def install_playwright_browsers(python: Path, browser_root: Path, browsers: list[str]) -> None:
    browser_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_root)
    run([str(python), "-m", "playwright", "install", *browsers], env=env)
    write_browser_manifest(browser_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build offline Python core wheelhouse")
    parser.add_argument("--requirements", default=str(DEFAULT_REQUIREMENTS))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--wheelhouse-root", default=str(DEFAULT_WHEELHOUSE_ROOT))
    parser.add_argument("--build-root", default=str(DEFAULT_BUILD_ROOT))
    parser.add_argument("--download", action="store_true", help="Download wheels into the wheelhouse")
    parser.add_argument("--verify", action="store_true", help="Install from wheelhouse into a clean venv and verify imports")
    parser.add_argument("--target", default=target_tag())
    parser.add_argument("--allow-source-build", action="store_true", help="Allow sdists/source builds; not recommended for enterprise releases")
    parser.add_argument("--playwright-browsers", action="store_true", help="Bundle Playwright browser binaries for offline RPA")
    parser.add_argument("--browser-root", default=str(DEFAULT_BROWSER_ROOT))
    parser.add_argument("--browser", action="append", default=None, help="Playwright browser to bundle; repeatable. Default: chromium")
    args = parser.parse_args()

    requirements = Path(args.requirements).resolve()
    core_manifest = Path(args.manifest).resolve()
    wheelhouse = Path(args.wheelhouse_root).resolve() / args.target
    build_root = Path(args.build_root).resolve()
    verify_venv = build_root / f"verify-{args.target}"

    if not requirements.exists():
        raise SystemExit(f"requirements file missing: {requirements}")
    if not core_manifest.exists():
        raise SystemExit(f"core manifest missing: {core_manifest}")

    wheelhouse.mkdir(parents=True, exist_ok=True)

    if args.download:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--dest",
            str(wheelhouse),
            "-r",
            str(requirements),
        ]
        if not args.allow_source_build:
            cmd.insert(4, "--only-binary=:all:")
        run(cmd)

    if not any(path.suffix == ".whl" for path in wheelhouse.iterdir()):
        raise SystemExit(
            f"wheelhouse is empty: {wheelhouse}\n"
            "Run with --download on an approved build machine, then package the generated wheelhouse."
        )

    write_wheelhouse_manifest(wheelhouse, requirements, core_manifest)

    verify_python = None
    if args.verify:
        verify_python = verify_offline_install(wheelhouse, requirements, verify_venv)

    if args.playwright_browsers:
        if verify_python is None:
            verify_python = verify_offline_install(wheelhouse, requirements, verify_venv)
        install_playwright_browsers(
            verify_python,
            Path(args.browser_root).resolve(),
            args.browser or ["chromium"],
        )

    print(f"[ok] Python core bundle ready: {wheelhouse}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
