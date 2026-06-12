"""Skill lifecycle engines: spec -> plan -> implement -> test -> review -> simplify -> ship.

Every engine returns a machine-checkable dict (explicit status / pass / block
fields — no prose-only outputs). All engines run on deterministic heuristics;
LLM enrichment is opt-in via FORGE_LIFECYCLE_LLM and always guarded, so the
pipeline and its tests never require a live LLM.
"""
