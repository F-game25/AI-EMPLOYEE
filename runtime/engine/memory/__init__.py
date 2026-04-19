"""Engine — Memory sub-package.

Provides a lightweight key/value memory store backed by a JSON file in
the AI Employee state directory.

Public interface
----------------
  store(key, value, namespace)   → None
  retrieve(key, namespace)       → Any | None
  search(query, namespace, top_k) → list[dict]
"""

from .store import store, retrieve, search

__all__ = ["store", "retrieve", "search"]
