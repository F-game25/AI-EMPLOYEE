"""Forge runtime package — Module 3 'Skill Lifecycle OS'.

Sub-packages:
    forge.lifecycle  — spec -> plan -> implement -> test -> review -> simplify -> ship
                       pipeline with a machine-checkable artifact per stage and a
                       boolean anti-rationalization ship gate.
    forge.ui_quality — static UI quality gate (placeholder/anti-slop preflight,
                       page auditor, design-language inference from real CSS).

This package only PLANS and GATES. It never writes product files; patch
application stays L3 approval-gated in the existing Forge sandbox/apply path.
"""
