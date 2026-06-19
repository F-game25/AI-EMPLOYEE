"""FinanceOps (Module 6) — ADVISORY-ONLY finance drafting.

Generates business-model drafts, cashflow/pricing analyses, revenue forecasts, and
pitch/investment memos. EVERY output is a draft staged for human review — there is
NO transaction execution, NO trade, NO payment, NO final tax/legal/accounting
advice. All numbers are clearly labelled estimates.
"""
from .financeops import FinanceOps, get_financeops

__all__ = ["FinanceOps", "get_financeops"]
