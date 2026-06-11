"""Accessibility-style page snapshot with STABLE element refs.

The key pattern: interactive elements are tagged with a persisted
``data-ai-ref`` DOM attribute by injected JS. An in-page counter
``window.__aiRefN`` only ever increments and already-tagged elements keep
their attribute — so ``@e3`` stays the same element across re-snapshots of a
mutated page. Refs reset naturally on navigation (new document, new counter).

Bounds: max 150 refs, 300 tree nodes, 80-char names.
"""
from __future__ import annotations

from typing import Any

MAX_REFS = 150
MAX_TREE_NODES = 300
MAX_NAME_LEN = 80

# One evaluate() call does tagging + ref collection + lightweight tree walk.
_SNAPSHOT_JS = """
(limits) => {
  const [MAX_REFS, MAX_NODES, MAX_NAME] = limits;
  if (window.__aiRefN === undefined) window.__aiRefN = 0;
  const INTERACTIVE = 'a[href],button,input,select,textarea,summary,' +
    '[role="button"],[role="link"],[role="checkbox"],[role="radio"],' +
    '[role="tab"],[role="menuitem"],[role="combobox"],[role="textbox"],' +
    '[role="switch"],[onclick],[contenteditable="true"]';
  const roleOf = (el) => {
    const r = el.getAttribute('role'); if (r) return r;
    const t = el.tagName.toLowerCase();
    if (t === 'a') return el.hasAttribute('href') ? 'link' : 'generic';
    if (t === 'button' || t === 'summary') return 'button';
    if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') {
      const ty = (el.getAttribute('type') || 'text').toLowerCase();
      if (['submit', 'button', 'reset', 'image'].includes(ty)) return 'button';
      if (ty === 'checkbox') return 'checkbox';
      if (ty === 'radio') return 'radio';
      if (ty === 'range') return 'slider';
      return 'textbox';
    }
    if (/^h[1-6]$/.test(t)) return 'heading';
    if (t === 'img') return 'img';
    if (t === 'nav') return 'navigation';
    if (t === 'main') return 'main';
    if (t === 'form') return 'form';
    if (t === 'ul' || t === 'ol') return 'list';
    if (t === 'li') return 'listitem';
    if (t === 'table') return 'table';
    return 'generic';
  };
  const nameOf = (el) => {
    const aria = el.getAttribute('aria-label'); if (aria) return aria;
    if (el.labels && el.labels.length) return el.labels[0].innerText || '';
    const ph = el.getAttribute('placeholder'); if (ph) return ph;
    const alt = el.getAttribute('alt'); if (alt) return alt;
    const ti = el.getAttribute('title'); if (ti) return ti;
    if (el.tagName === 'INPUT' && el.value &&
        ['submit', 'button', 'reset'].includes((el.type || '').toLowerCase()))
      return el.value;
    return (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
  };

  // 1) Stable refs: tag interactive elements; tagged ones KEEP their ref.
  let truncated = false;
  const refs = [];
  for (const el of document.querySelectorAll(INTERACTIVE)) {
    let ref = el.getAttribute('data-ai-ref');
    if (!ref) {
      if (window.__aiRefN >= MAX_REFS) { truncated = true; continue; }
      window.__aiRefN += 1;          // counter only increments — refs stay stable
      ref = 'e' + window.__aiRefN;
      el.setAttribute('data-ai-ref', ref);
    }
    if (refs.length >= MAX_REFS) { truncated = true; break; }
    const b = el.getBoundingClientRect();
    refs.push({
      ref, role: roleOf(el), name: nameOf(el).slice(0, MAX_NAME),
      tag: el.tagName.toLowerCase(),
      bbox: [Math.round(b.x), Math.round(b.y),
             Math.round(b.width), Math.round(b.height)],
    });
  }

  // 2) Lightweight tree (bounded node count + depth).
  let nodes = 0;
  const SKIP = ['script', 'style', 'noscript', 'meta', 'link', 'head', 'template'];
  const walk = (el, depth) => {
    if (nodes >= MAX_NODES || depth > 12) { truncated = true; return null; }
    if (el.nodeType !== 1) return null;
    if (SKIP.includes(el.tagName.toLowerCase())) return null;
    nodes += 1;
    const node = { role: roleOf(el), name: nameOf(el).slice(0, MAX_NAME) };
    const ref = el.getAttribute('data-ai-ref');
    if (ref) node.ref = ref;
    const children = [];
    for (const c of el.children) {
      const cn = walk(c, depth + 1);
      if (cn) children.push(cn);
      if (nodes >= MAX_NODES) break;
    }
    if (children.length) node.children = children;
    return node;
  };
  const tree = document.body ? walk(document.body, 0) : null;
  return { tree, refs, truncated };
}
"""


def snapshot(session) -> dict[str, Any]:
    """Snapshot ``session``'s page → {tree, refs, ref_count, truncated}."""
    data = session.call(
        lambda: session.page.evaluate(
            _SNAPSHOT_JS, [MAX_REFS, MAX_TREE_NODES, MAX_NAME_LEN]))
    refs = data.get("refs") or []
    return {
        "tree": data.get("tree"),
        "refs": refs,
        "ref_count": len(refs),
        "truncated": bool(data.get("truncated")),
    }
