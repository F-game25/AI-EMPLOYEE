#!/usr/bin/env python3
"""
Generate platform-specific app icons (PNG / ICNS / ICO) from icon.svg.

Run from the launcher directory:
    python3 scripts/generate-icons.py

Requires: Pillow (PIL). For .icns it falls back to repeated PNG sizes
inside an .iconset directory if `iconutil` is not available (macOS only).
The .ico generator uses Pillow's native multi-size support.

If librsvg / rsvg-convert is unavailable, we render the SVG with Pillow's
fallback via a manual recreation of the golden-eye design at PIL level.
This guarantees the script works on any machine with Python + Pillow,
without ImageMagick / Inkscape / librsvg.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
SVG = ASSETS / 'icon.svg'

LINUX_SIZES = [16, 32, 48, 64, 128, 256, 512, 1024]
WIN_SIZES   = [16, 24, 32, 48, 64, 128, 256]
MAC_SIZES   = [16, 32, 64, 128, 256, 512, 1024]

# ── Renderer: librsvg if present, else Pillow recreation ───────────────
def try_render_svg(out_path: Path, size: int) -> bool:
    """Try external rasterizers; return True on success."""
    if shutil.which('rsvg-convert'):
        try:
            subprocess.check_call(['rsvg-convert', '-w', str(size), '-h', str(size),
                                   '-o', str(out_path), str(SVG)])
            return True
        except subprocess.CalledProcessError:
            pass
    if shutil.which('magick'):
        try:
            subprocess.check_call(['magick', '-background', 'none', '-density', '600',
                                   '-resize', f'{size}x{size}', str(SVG), str(out_path)])
            return True
        except subprocess.CalledProcessError:
            pass
    if shutil.which('convert'):
        try:
            subprocess.check_call(['convert', '-background', 'none', '-density', '600',
                                   '-resize', f'{size}x{size}', str(SVG), str(out_path)])
            return True
        except subprocess.CalledProcessError:
            pass
    return False


def render_pillow_fallback(out_path: Path, size: int):
    """Pure-Pillow recreation of the golden-eye icon — used when no SVG rasterizer is on PATH."""
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    r_squircle  = size * 0.45
    r_halo      = size * 0.40
    r_iris      = size * 0.22
    r_pupil     = size * 0.085
    r_outer     = size * 0.275
    r_outer2    = size * 0.235

    # Rounded-square background
    pad = int(size * 0.06)
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=int(size * 0.175), fill=(6, 7, 13, 255),
                        outline=(229, 199, 107, 64), width=max(1, size // 340))

    # Halo (gold blur)
    halo = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse([c - r_halo, c - r_halo, c + r_halo, c + r_halo],
               fill=(255, 184, 77, 90))
    halo = halo.filter(ImageFilter.GaussianBlur(radius=size * 0.07))
    img = Image.alpha_composite(img, halo)
    d = ImageDraw.Draw(img)

    # 24 sunburst fins
    import math
    fin_inner = size * 0.275
    fin_outer = size * 0.34
    fin_w     = max(1, int(size * 0.006))
    for i in range(24):
        angle = math.radians(i * 15)
        x1 = c + math.cos(angle) * fin_inner
        y1 = c + math.sin(angle) * fin_inner
        x2 = c + math.cos(angle) * fin_outer
        y2 = c + math.sin(angle) * fin_outer
        d.line([(x1, y1), (x2, y2)], fill=(229, 199, 107, 128), width=fin_w)

    # Outer rings
    d.ellipse([c - r_outer, c - r_outer, c + r_outer, c + r_outer],
              outline=(229, 199, 107, 102), width=max(1, size // 510))
    d.ellipse([c - r_outer2, c - r_outer2, c + r_outer2, c + r_outer2],
              outline=(229, 199, 107, 178), width=max(1, size // 340))

    # Iris ring
    d.ellipse([c - r_iris - 4, c - r_iris - 4, c + r_iris + 4, c + r_iris + 4],
              outline=(229, 199, 107, 200), width=max(1, size // 256))

    # Iris fill (radial-ish — simulate with concentric ellipses)
    iris_steps = 18
    for i in range(iris_steps, 0, -1):
        t = i / iris_steps
        rr = r_iris * t
        col = (
            int(229 * (0.55 + 0.45 * t)),
            int(199 * (0.55 + 0.45 * t)),
            int(107 * (0.40 + 0.60 * t)),
            min(255, int(200 * t))
        )
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=col)

    # Iris dark ring close to pupil
    d.ellipse([c - r_iris * 0.42, c - r_iris * 0.42, c + r_iris * 0.42, c + r_iris * 0.42],
              fill=(28, 19, 6, 255))

    # Iris striations (8 spokes)
    for i in range(8):
        angle = math.radians(i * 45)
        x1 = c + math.cos(angle) * (r_iris * 0.42)
        y1 = c + math.sin(angle) * (r_iris * 0.42)
        x2 = c + math.cos(angle) * (r_iris * 0.85)
        y2 = c + math.sin(angle) * (r_iris * 0.85)
        d.line([(x1, y1), (x2, y2)], fill=(28, 19, 6, 153), width=max(1, size // 256))

    # Pupil
    d.ellipse([c - r_pupil, c - r_pupil, c + r_pupil, c + r_pupil],
              fill=(4, 5, 10, 255))

    # Catchlight
    cl_size = max(2, size // 32)
    d.ellipse([c - cl_size * 1.6, c - cl_size * 1.6,
               c - cl_size * 0.6, c - cl_size * 0.6],
              fill=(255, 255, 255, 140))

    img.save(out_path, format='PNG')


def render(out_path: Path, size: int):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not try_render_svg(out_path, size):
        render_pillow_fallback(out_path, size)


# ── Main entry points ────────────────────────────────────────────────────
def gen_linux_pngs():
    print('Generating Linux PNGs…')
    for s in LINUX_SIZES:
        out = ASSETS / f'icon-{s}.png'
        render(out, s)
        print(f'  {out.relative_to(ASSETS.parent)} ({s}×{s})')
    # Canonical icon.png used by electron-builder defaults
    shutil.copy(ASSETS / 'icon-1024.png', ASSETS / 'icon.png')
    print(f'  assets/icon.png (1024×1024 — canonical)')


def gen_windows_ico():
    print('Generating Windows .ico…')
    from PIL import Image
    pngs = []
    for s in WIN_SIZES:
        p = ASSETS / f'icon-{s}.png'
        if not p.exists():
            render(p, s)
        pngs.append(Image.open(p).convert('RGBA'))
    pngs[0].save(ASSETS / 'icon.ico', format='ICO',
                 sizes=[(s, s) for s in WIN_SIZES])
    print(f'  assets/icon.ico (sizes {WIN_SIZES})')


def gen_mac_icns():
    print('Generating macOS .icns…')
    out = ASSETS / 'icon.icns'
    iconset = ASSETS / 'icon.iconset'
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    # Apple iconset naming convention
    pairs = [(16, '16x16'), (32, '16x16@2x'),
             (32, '32x32'), (64, '32x32@2x'),
             (128, '128x128'), (256, '128x128@2x'),
             (256, '256x256'), (512, '256x256@2x'),
             (512, '512x512'), (1024, '512x512@2x')]
    for size, name in pairs:
        p = iconset / f'icon_{name}.png'
        src = ASSETS / f'icon-{size}.png'
        if not src.exists():
            render(src, size)
        shutil.copy(src, p)
    if shutil.which('iconutil'):
        subprocess.check_call(['iconutil', '-c', 'icns', str(iconset),
                               '-o', str(out)])
        shutil.rmtree(iconset)
        print(f'  assets/icon.icns (via iconutil)')
    else:
        # Fallback: rely on electron-builder picking up the iconset dir,
        # or generate via Pillow's ICNS encoder (works only on some versions).
        try:
            from PIL import Image
            imgs = [Image.open(iconset / f'icon_{name}.png').convert('RGBA') for _, name in pairs]
            imgs[0].save(out, format='ICNS', append_images=imgs[1:])
            print(f'  assets/icon.icns (via Pillow)')
        except Exception as e:
            print(f'  ⚠ Could not write .icns ({e}); leaving iconset/ directory')


if __name__ == '__main__':
    if not SVG.exists():
        print(f'❌ Missing source: {SVG}', file=sys.stderr)
        sys.exit(1)
    gen_linux_pngs()
    gen_windows_ico()
    gen_mac_icns()
    print('Done.')
