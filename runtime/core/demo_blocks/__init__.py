"""Block-based demo site design system.

Public API:
    build_theme(seed, branche) -> theme dict (palette/fonts/style/variants)
    render_site(ctx, theme)    -> {filename: html} multi-page site
    PAGES                      -> canonical page list [(filename, label), ...]
"""
from .composer import build_theme, render_site, PAGES

__all__ = ["build_theme", "render_site", "PAGES"]
