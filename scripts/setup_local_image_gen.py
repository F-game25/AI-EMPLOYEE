#!/usr/bin/env python3
"""One-time setup for OFFLINE local image generation (stable-diffusion.cpp).

Downloads a local model (+ the z-image llm/vae aux when needed) into SD_MODELS_DIR
from the vendored catalog, and checks for the sd-cli engine binary. The engine
itself (CUDA build) comes from github.com/leejet/stable-diffusion.cpp — this
script does NOT compile it (that's a deliberate, system-level step); it points
you at it if missing. After setup, generation runs fully offline.

Usage:
    python3 scripts/setup_local_image_gen.py                  # default model
    python3 scripts/setup_local_image_gen.py --model z-image-turbo
    python3 scripts/setup_local_image_gen.py --list
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from content import media_models as mm  # noqa: E402
from content import local_image_gen as lig  # noqa: E402


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ✓ already present: {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  ↓ {url}\n     → {dest}")
    last = [0]

    def _hook(blocks, bs, total):
        if total > 0:
            pct = min(100, int(blocks * bs * 100 / total))
            if pct >= last[0] + 10:
                last[0] = pct
                print(f"     {pct}%", flush=True)

    urllib.request.urlretrieve(url, tmp, _hook)
    tmp.rename(dest)
    print(f"  ✓ saved {dest.name} ({dest.stat().st_size / 1e9:.2f} GB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="model id (default = catalog default)")
    ap.add_argument("--list", action="store_true", help="list available local models")
    args = ap.parse_args()

    if args.list:
        for m in mm.local_models():
            print(f"  {m['id']:26} {m['type']:8} {m['size_gb']}GB  {m['name']}")
        return 0

    md = lig.models_dir()
    print(f"Model dir: {md}")
    mid = args.model or mm.default_local_model_id()
    model = mm.get_local_model(mid)
    if not model:
        print(f"unknown model '{mid}'. Use --list.")
        return 1

    print(f"\nDownloading local model: {model['id']} ({model['size_gb']}GB)")
    _download(model["download_url"], md / model["filename"])

    if model.get("requires_aux"):
        print("\nz-image model needs shared llm + vae:")
        for slot in ("llm", "vae"):
            aux = (mm.zimage_aux() or {}).get(slot)
            if aux:
                _download(aux["download_url"], md / aux["filename"])

    print("\nEngine check:")
    binary = lig.find_binary()
    if binary:
        print(f"  ✓ sd-cli found: {binary}")
        print("\nReady. Local offline generation is enabled.")
    else:
        print("  ✗ sd-cli (stable-diffusion.cpp) NOT found.")
        print("    Build or download it (CUDA for GPU), then set SD_CLI_BIN or place it at")
        print(f"    {ROOT}/runtime/vendor/local-ai/bin/sd-cli :")
        print("      git clone https://github.com/leejet/stable-diffusion.cpp")
        print("      cd stable-diffusion.cpp && cmake -B build -DSD_CUDA=ON && cmake --build build -j")
        print("    (the model is downloaded; only the engine binary is missing).")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
