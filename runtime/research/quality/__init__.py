"""Research Quality Engine — Module 8.

Audits a persisted DeepResearchReport dict (see
``core.deep_research_engine.DeepResearchReport``) and attaches a quality
block. Core principle: NO hallucinated sources — verified facts are kept
separate from model reasoning, unsupported claims are flagged, and
fabricated references hard-block the integrity gate.

Pipeline (all deterministic; LLM use is optional and guarded):
  citation_anchor   — bind claims to the report's OWN source list
  source_verifier   — syntactic always; live HTTP only when RESEARCH_VERIFY_LIVE=1
  claim_auditor     — unsupported claims + fabricated-reference detection
  integrity_gate    — pure boolean pass/block; no LLM override
  reviewer_panel    — 3-role review, guarded LLM with heuristic fallback
  material_passport — reproducibility metadata + content hash
  report_builder    — finalize(): attach quality block, never mutate findings
  research_planner  — staged-flow descriptor for UI display
"""
