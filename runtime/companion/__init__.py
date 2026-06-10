"""Companion Gateway — conversational front-door to the AI Operating System.

Phase P4 of MASTER_PLAN_V3. This package provides the typed contracts
(``schemas``), the capability registry the companion can route to
(``capability_registry``), and the risk-aware safety gate that decides
whether a capability call may run automatically or needs human approval
(``safety_gate``).

Stdlib-only by design — the dataclasses round-trip through ``to_dict()`` /
``from_dict()`` for JSON transport across the Node<->Python worker boundary.
"""
