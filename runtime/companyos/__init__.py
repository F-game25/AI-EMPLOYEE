"""CompanyOS (P10) — AI company-builder that validates before it builds.

A thin orchestration layer over the existing engines (M4 work, M5 content,
M6 finance, M7 swarm, M8 research, Forge, Money Mode). The anti-Polsia guarantees:
validate-before-build (can refuse), no fake success, approval on every external
action, local ownership, transparent decisions, a teammate that pushes back.
"""
from .companyos import CompanyOS, get_companyos

__all__ = ["CompanyOS", "get_companyos"]
