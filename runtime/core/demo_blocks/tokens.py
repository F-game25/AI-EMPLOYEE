"""Design tokens for the demo block system.

Curated palettes, font pairs and style themes. The composer picks a coherent
combination deterministically from a per-job seed, so every business gets a
unique-but-consistent look that cannot break (all values are hand-curated).
"""
from __future__ import annotations

# ── Palettes ─────────────────────────────────────────────────────────────────
# Each palette is a full set of colour roles. `mood` is cool/warm/neutral,
# `tone` is light/dark — used to bias selection toward the branche while still
# leaving room for variety across businesses.
PALETTES: list[dict] = [
    {"name": "deep-ocean",   "mood": "cool",    "tone": "dark",
     "primary": "#0f2c4c", "primary_dark": "#0a1f38", "accent": "#2e9bd6",
     "bg": "#ffffff", "alt": "#f3f7fb", "surface": "#ffffff", "text": "#16222e",
     "muted": "#5a6b7a", "border": "#dde6ee", "on_primary": "#ffffff"},
    {"name": "forest",       "mood": "cool",    "tone": "dark",
     "primary": "#1d4231", "primary_dark": "#13301f", "accent": "#37b87a",
     "bg": "#ffffff", "alt": "#f1f7f3", "surface": "#ffffff", "text": "#16241d",
     "muted": "#566b60", "border": "#dde9e2", "on_primary": "#ffffff"},
    {"name": "ember",        "mood": "warm",    "tone": "dark",
     "primary": "#3a1a0f", "primary_dark": "#27110a", "accent": "#e8702a",
     "bg": "#ffffff", "alt": "#fbf4ef", "surface": "#ffffff", "text": "#2a1a12",
     "muted": "#7a655a", "border": "#ecdfd6", "on_primary": "#ffffff"},
    {"name": "royal",        "mood": "cool",    "tone": "dark",
     "primary": "#2a1a5c", "primary_dark": "#1c1140", "accent": "#8e5be8",
     "bg": "#ffffff", "alt": "#f5f2fc", "surface": "#ffffff", "text": "#1f1733",
     "muted": "#6a6280", "border": "#e4ddf2", "on_primary": "#ffffff"},
    {"name": "crimson",      "mood": "warm",    "tone": "dark",
     "primary": "#4a1020", "primary_dark": "#350b17", "accent": "#e23a5e",
     "bg": "#ffffff", "alt": "#fbf0f3", "surface": "#ffffff", "text": "#2a141a",
     "muted": "#7a5b62", "border": "#eed9df", "on_primary": "#ffffff"},
    {"name": "slate-amber",  "mood": "neutral", "tone": "dark",
     "primary": "#22272e", "primary_dark": "#161a1f", "accent": "#f2a83b",
     "bg": "#ffffff", "alt": "#f4f5f7", "surface": "#ffffff", "text": "#1c2127",
     "muted": "#5f6770", "border": "#e2e5e9", "on_primary": "#ffffff"},
    {"name": "teal-coral",   "mood": "cool",    "tone": "dark",
     "primary": "#0f3b3a", "primary_dark": "#0a2a29", "accent": "#ff6b5b",
     "bg": "#ffffff", "alt": "#eff6f5", "surface": "#ffffff", "text": "#13302f",
     "muted": "#536866", "border": "#d8e7e5", "on_primary": "#ffffff"},
    {"name": "midnight-lime", "mood": "cool",   "tone": "dark",
     "primary": "#16213a", "primary_dark": "#0e1626", "accent": "#9bd62e",
     "bg": "#ffffff", "alt": "#f2f4f8", "surface": "#ffffff", "text": "#161c2a",
     "muted": "#5a6478", "border": "#dde1ea", "on_primary": "#ffffff"},
    {"name": "wine-gold",    "mood": "warm",    "tone": "dark",
     "primary": "#3d1f2a", "primary_dark": "#2a141d", "accent": "#d6a93a",
     "bg": "#ffffff", "alt": "#f8f3f0", "surface": "#ffffff", "text": "#281820",
     "muted": "#75606a", "border": "#e9dcd9", "on_primary": "#ffffff"},
    {"name": "steel-sky",    "mood": "cool",    "tone": "dark",
     "primary": "#1c3146", "primary_dark": "#132233", "accent": "#3fb0e8",
     "bg": "#ffffff", "alt": "#f1f5f9", "surface": "#ffffff", "text": "#172430",
     "muted": "#566776", "border": "#dbe4ec", "on_primary": "#ffffff"},
]

# ── Font pairs (Google Fonts + system fallback so the page never depends on the network) ──
FONT_PAIRS: list[dict] = [
    {"name": "inter", "heading": "'Inter', system-ui, sans-serif", "body": "'Inter', system-ui, sans-serif",
     "import": "Inter:wght@400;500;600;700;800"},
    {"name": "poppins-inter", "heading": "'Poppins', system-ui, sans-serif", "body": "'Inter', system-ui, sans-serif",
     "import": "Poppins:wght@500;600;700&family=Inter:wght@400;500;600"},
    {"name": "playfair-source", "heading": "'Playfair Display', Georgia, serif", "body": "'Source Sans 3', system-ui, sans-serif",
     "import": "Playfair+Display:wght@600;700;800&family=Source+Sans+3:wght@400;500;600"},
    {"name": "montserrat-roboto", "heading": "'Montserrat', system-ui, sans-serif", "body": "'Roboto', system-ui, sans-serif",
     "import": "Montserrat:wght@600;700;800&family=Roboto:wght@400;500"},
    {"name": "dmserif-dmsans", "heading": "'DM Serif Display', Georgia, serif", "body": "'DM Sans', system-ui, sans-serif",
     "import": "DM+Serif+Display&family=DM+Sans:wght@400;500;600"},
    {"name": "spacegrotesk", "heading": "'Space Grotesk', system-ui, sans-serif", "body": "'Inter', system-ui, sans-serif",
     "import": "Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500"},
    {"name": "lora-worksans", "heading": "'Lora', Georgia, serif", "body": "'Work Sans', system-ui, sans-serif",
     "import": "Lora:wght@600;700&family=Work+Sans:wght@400;500;600"},
]

# ── Style themes — structural knobs that change the whole feel ────────────────
STYLE_THEMES: list[dict] = [
    {"name": "soft",    "radius": "14px", "radius_lg": "24px", "shadow": "0 10px 30px rgba(16,24,40,.10)",
     "btn_radius": "10px", "section_pad": "5.5rem", "container": "1180px"},
    {"name": "sharp",   "radius": "2px",  "radius_lg": "4px",  "shadow": "0 2px 0 rgba(16,24,40,.06)",
     "btn_radius": "2px",  "section_pad": "5rem",   "container": "1200px"},
    {"name": "rounded", "radius": "20px", "radius_lg": "32px", "shadow": "0 16px 40px rgba(16,24,40,.12)",
     "btn_radius": "999px","section_pad": "6rem",   "container": "1120px"},
    {"name": "editorial","radius": "8px", "radius_lg": "12px", "shadow": "0 6px 22px rgba(16,24,40,.08)",
     "btn_radius": "6px",  "section_pad": "6.5rem", "container": "1080px"},
]

# Branche → preferred palette moods (bias only; selection still varies per job).
_BRANCHE_MOOD: list[tuple[tuple[str, ...], str]] = [
    (("loodgiet", "installat", "sanitair", "elektr", "auto", "garage"), "cool"),
    (("bouw", "timmer", "aannem", "schilder"), "neutral"),
    (("schoon", "onderhoud", "tuin", "groen", "hoveniers"), "cool"),
    (("kapper", "haar", "schoonheid", "beauty"), "warm"),
    (("restaurant", "horeca", "eten", "café", "cafe", "bakker"), "warm"),
]


def branche_mood(branche: str) -> str:
    b = (branche or "").lower()
    for keys, mood in _BRANCHE_MOOD:
        if any(k in b for k in keys):
            return mood
    return "cool"
