"""Engine — Utilities sub-package.

Shared helpers used across the engine layer:
  now_iso()         — current UTC timestamp as ISO-8601 string
  truncate(text, n) — truncate a string to n characters with ellipsis
  safe_json(obj)    — serialize obj to JSON, falling back to str()
"""

from .helpers import now_iso, truncate, safe_json

__all__ = ["now_iso", "truncate", "safe_json"]
