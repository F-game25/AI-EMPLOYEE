"""Work Acquisition + Delivery Engine (Master Plan V3 — Module 4).

A governed lifecycle for turning a raw opportunity into a delivered work product:

    ingest → evaluate → quote(HITL) → accepted → execute → deliver(HITL)
           → feedback → study

Reference pattern (architecture only, no code copied): cashclaw
(opportunity→evaluate→quote→execute→deliver→feedback→study).

Governance (non-negotiable):
  * No autonomous external send/spend/deliver. The quote step and the deliver
    step are HARD HITL gates — both return ``pending_approval`` with a gate id
    and never auto-send.
  * Every monetary figure is a labelled estimate (``is_estimate: True``), never
    presented as an actual.
  * Every executor is try/except wrapped → structured status; never throws,
    never fabricates success.

Public surface:
    from money.work_engine import get_work_engine
"""
from .engine import WorkEngine, get_work_engine

__all__ = ["WorkEngine", "get_work_engine"]
