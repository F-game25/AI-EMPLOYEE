"""scanner/component_parser.py — AST-based React/Vue component parser.

Extracts:
  - structural hierarchy (component tree)
  - props usage (names, types, defaults)
  - styling patterns (className strings, inline-style objects)

Outputs a normalised JSON representation that every downstream module
can consume without depending on the original source file.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any


# ── Public API ────────────────────────────────────────────────────────────────

def parse_component(source: str, filename: str = "<unknown>") -> dict[str, Any]:
    """Parse a React (.jsx/.tsx) or Vue (.vue) component.

    Returns a normalised dict with keys:
      filename, type, props, hierarchy, class_names, inline_styles, raw_source.
    """
    filename = filename or "<unknown>"
    suffix = Path(filename).suffix.lower()

    if suffix == ".vue":
        return _parse_vue(source, filename)
    # Default: treat as React/JSX (also handles .js / .ts / .tsx)
    return _parse_react(source, filename)


def parse_file(path: str | Path) -> dict[str, Any]:
    """Convenience wrapper — read *path* and call :func:`parse_component`."""
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    return parse_component(source, filename=str(path))


def parse_to_json(source: str, filename: str = "<unknown>") -> str:
    """Return the normalised representation as a JSON string."""
    return json.dumps(parse_component(source, filename), indent=2)


# ── React / JSX ───────────────────────────────────────────────────────────────

def _parse_react(source: str, filename: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "filename": filename,
        "type": "react",
        "props": [],
        "hierarchy": [],
        "class_names": [],
        "inline_styles": [],
        "raw_source": source,
    }

    # ── 1. AST analysis (works for plain JS; skip on SyntaxError) ────────────
    try:
        tree = ast.parse(source, filename=filename, mode="exec")
        result["props"] = _extract_props_from_ast(tree)
    except SyntaxError:
        # JSX is not valid Python AST — use regex fallback below
        pass

    # ── 2. Regex-based JSX extraction ────────────────────────────────────────
    result["hierarchy"]     = _extract_jsx_hierarchy(source)
    result["class_names"]   = _extract_class_names(source)
    result["inline_styles"] = _extract_inline_styles(source)

    return result


def _extract_props_from_ast(tree: ast.AST) -> list[dict[str, Any]]:
    """Extract prop definitions from a Python/TS-style function signature."""
    props: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            defaults_offset = len(args.args) - len(args.defaults)
            for i, arg in enumerate(args.args):
                if arg.arg in ("self", "cls"):
                    continue
                prop: dict[str, Any] = {"name": arg.arg, "type": None, "default": None}
                if arg.annotation:
                    try:
                        prop["type"] = ast.unparse(arg.annotation)
                    except Exception:
                        pass
                default_idx = i - defaults_offset
                if 0 <= default_idx < len(args.defaults):
                    try:
                        prop["default"] = ast.literal_eval(args.defaults[default_idx])
                    except Exception:
                        try:
                            prop["default"] = ast.unparse(args.defaults[default_idx])
                        except Exception:
                            pass
                props.append(prop)
    return props


# ── JSX hierarchy extraction ──────────────────────────────────────────────────

_JSX_TAG_RE = re.compile(
    r"<([A-Z][A-Za-z0-9.]*|[a-z][a-z0-9-]*)(\s[^>]*)?>",
    re.MULTILINE,
)

def _extract_jsx_hierarchy(source: str) -> list[dict[str, Any]]:
    """Return a flat ordered list of JSX elements found in the source."""
    elements: list[dict[str, Any]] = []
    for m in _JSX_TAG_RE.finditer(source):
        tag  = m.group(1)
        attrs_raw = (m.group(2) or "").strip()
        attrs: dict[str, str] = {}
        # Extract key=value pairs from attrs_raw
        for am in re.finditer(r'(\w[\w-]*)(?:=(?:"([^"]*?)"|\'([^\']*?)\'|\{([^}]*?)\}))?', attrs_raw):
            key = am.group(1)
            val = am.group(2) or am.group(3) or am.group(4) or "true"
            attrs[key] = val
        elements.append({"tag": tag, "attrs": attrs, "line": source[: m.start()].count("\n") + 1})
    return elements


# ── className extraction ──────────────────────────────────────────────────────

_CLASSNAME_RE = re.compile(
    r'className\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|`([^`]*?)`|\{([^}]+?)\})',
    re.MULTILINE,
)

def _extract_class_names(source: str) -> list[dict[str, Any]]:
    """Return all className expressions (static strings and dynamic expressions)."""
    results: list[dict[str, Any]] = []
    for m in _CLASSNAME_RE.finditer(source):
        static  = m.group(1) or m.group(2) or m.group(3)
        dynamic = m.group(4)
        line = source[: m.start()].count("\n") + 1
        if static is not None:
            classes = static.split()
            results.append({"type": "static", "classes": classes, "raw": static, "line": line})
        elif dynamic is not None:
            results.append({"type": "dynamic", "expression": dynamic.strip(), "line": line})
    return results


# ── Inline style extraction ───────────────────────────────────────────────────

_INLINE_STYLE_RE = re.compile(
    r"style\s*=\s*\{\s*(\{[^}]*?\})\s*\}",
    re.MULTILINE | re.DOTALL,
)

def _extract_inline_styles(source: str) -> list[dict[str, Any]]:
    """Return all inline-style objects (style={{ ... }})."""
    results: list[dict[str, Any]] = []
    for m in _INLINE_STYLE_RE.finditer(source):
        raw  = m.group(1).strip()
        line = source[: m.start()].count("\n") + 1
        props: dict[str, str] = {}
        for pm in re.finditer(r"([a-zA-Z]+)\s*:\s*([\"'`]?[^,}\"'`]+[\"'`]?)", raw):
            props[pm.group(1).strip()] = pm.group(2).strip().strip("\"'`")
        results.append({"raw": raw, "properties": props, "line": line})
    return results


# ── Vue SFC ───────────────────────────────────────────────────────────────────

_VUE_TEMPLATE_RE = re.compile(r"<template>(.*?)</\s*template\s*>", re.DOTALL | re.IGNORECASE)
_VUE_SCRIPT_RE   = re.compile(
    r"<script[^>]*>(.*?)</\s*script(?:\s[^>]*)?>",
    re.DOTALL | re.IGNORECASE,
)
_VUE_STYLE_RE    = re.compile(r"<style[^>]*>(.*?)</\s*style\s*>",    re.DOTALL | re.IGNORECASE)


def _parse_vue(source: str, filename: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "filename": filename,
        "type": "vue",
        "props": [],
        "hierarchy": [],
        "class_names": [],
        "inline_styles": [],
        "raw_source": source,
    }

    template_m = _VUE_TEMPLATE_RE.search(source)
    script_m   = _VUE_SCRIPT_RE.search(source)
    style_m    = _VUE_STYLE_RE.search(source)

    template_src = template_m.group(1) if template_m else ""
    script_src   = script_m.group(1)   if script_m   else ""

    # hierarchy and classes come from the <template> block
    result["hierarchy"]     = _extract_jsx_hierarchy(template_src)
    result["class_names"]   = _extract_class_names(template_src)
    result["inline_styles"] = _extract_inline_styles(template_src)

    # props come from the <script> block
    result["props"] = _extract_vue_props(script_src)
    if style_m:
        result["scoped_styles"] = style_m.group(1).strip()

    return result


_VUE_PROPS_OBJECT_RE = re.compile(r"props\s*:\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}", re.DOTALL)
_VUE_PROP_ENTRY_RE   = re.compile(r"(\w+)\s*:", re.MULTILINE)


def _extract_vue_props(script_src: str) -> list[dict[str, Any]]:
    props: list[dict[str, Any]] = []
    m = _VUE_PROPS_OBJECT_RE.search(script_src)
    if not m:
        return props
    body = m.group(1)
    for pm in _VUE_PROP_ENTRY_RE.finditer(body):
        name = pm.group(1)
        if name not in ("type", "default", "required", "validator"):
            props.append({"name": name, "type": None, "default": None})
    return props


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 component_parser.py <file>", file=sys.stderr)
        sys.exit(1)
    print(parse_to_json(Path(sys.argv[1]).read_text(), filename=sys.argv[1]))
