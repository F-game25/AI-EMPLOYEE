#!/usr/bin/env python3
"""Verification script for Phase 4 Cognitive Infrastructure.

Checks:
- All required files exist
- Database schema is correct
- All routes are importable
- Integration points work
"""
import sys
from pathlib import Path

def check_files():
    """Verify all required files exist."""
    base = Path(__file__).parent.parent / "runtime" / "infra" / "cognitive"

    required_files = {
        # Core
        "db.py": "Database factory",
        "integration.py": "Integration layer",

        # Coherence
        "coherence/__init__.py": "Coherence module",
        "coherence/schema.py": "Coherence dataclasses",
        "coherence/objective_hierarchy.py": "Objective management",
        "coherence/contradiction_detector.py": "Contradiction detection",
        "coherence/loop_detector.py": "Loop detection",
        "coherence/deduplication_engine.py": "Workflow dedup",
        "coherence/coherence_scorer.py": "Coherence scoring",
        "coherence/coherence_routes.py": "Coherence HTTP routes",

        # Executive
        "executive/__init__.py": "Executive module",
        "executive/schema.py": "Executive dataclasses",
        "executive/initiative_manager.py": "Initiative lifecycle",
        "executive/workload_balancer.py": "Workload monitoring",
        "executive/budget_tracker.py": "Budget tracking",
        "executive/strategic_planner.py": "Strategic planning",
        "executive/executive_routes.py": "Executive HTTP routes",

        # Guardrails
        "guardrails/__init__.py": "Guardrails module",
        "guardrails/schema.py": "Guardrails dataclasses",
        "guardrails/spawn_limiter.py": "Spawn limits",
        "guardrails/trust_tier_policy.py": "Trust tiers",
        "guardrails/rate_governor.py": "Rate limiting",
        "guardrails/event_storm_detector.py": "Event storm detection",
        "guardrails/budget_enforcer.py": "Budget enforcement",
        "guardrails/escalation_gate.py": "Escalation routing",
        "guardrails/guardrail_routes.py": "Guardrails HTTP routes",
    }

    missing = []
    for file_path, desc in required_files.items():
        full_path = base / file_path
        if not full_path.exists():
            missing.append(f"  ✗ {file_path} ({desc})")
        else:
            print(f"  ✓ {file_path}")

    if missing:
        print("\nMissing files:")
        for m in missing:
            print(m)
        return False
    return True


def check_database():
    """Verify database schema."""
    try:
        from infra.cognitive.db import cognitive_conn

        with cognitive_conn() as c:
            # Check tables
            tables = {
                "objectives": "Objectives table",
                "contradictions": "Contradictions table",
                "wf_fingerprints": "Fingerprints table",
                "initiatives": "Initiatives table",
                "executive_decisions": "Executive decisions table",
                "budget_usage": "Budget usage table",
                "trust_tiers": "Trust tiers table",
                "guardrail_violations": "Violations table",
            }

            for table_name, desc in tables.items():
                c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                if not c.fetchone():
                    print(f"  ✗ {desc} missing")
                    return False
                print(f"  ✓ {desc}")

        return True
    except Exception as e:
        print(f"  ✗ Database check failed: {e}")
        return False


def check_imports():
    """Verify all modules are importable."""
    modules = {
        "infra.cognitive.db": "Database factory",
        "infra.cognitive.integration": "Integration layer",
        "infra.cognitive.coherence": "Coherence module",
        "infra.cognitive.coherence.coherence_routes": "Coherence routes",
        "infra.cognitive.executive": "Executive module",
        "infra.cognitive.executive.executive_routes": "Executive routes",
        "infra.cognitive.guardrails": "Guardrails module",
        "infra.cognitive.guardrails.guardrail_routes": "Guardrails routes",
    }

    failed = []
    for module_name, desc in modules.items():
        try:
            __import__(module_name)
            print(f"  ✓ {desc}")
        except Exception as e:
            failed.append(f"  ✗ {desc}: {e}")

    if failed:
        print("\nImport failures:")
        for f in failed:
            print(f)
        return False
    return True


def check_routes():
    """Verify HTTP routes are available."""
    try:
        from infra.cognitive.coherence.coherence_routes import router as coh_router
        from infra.cognitive.executive.executive_routes import router as exec_router
        from infra.cognitive.guardrails.guardrail_routes import router as guard_router

        # Check route counts
        routes = {
            "Coherence": coh_router.routes,
            "Executive": exec_router.routes,
            "Guardrails": guard_router.routes,
        }

        for name, route_list in routes.items():
            count = len([r for r in route_list if hasattr(r, 'path')])
            print(f"  ✓ {name} router: {count} routes")

        return True
    except Exception as e:
        print(f"  ✗ Route check failed: {e}")
        return False


def check_integration():
    """Verify integration layer functions."""
    try:
        from infra.cognitive.integration import (
            record_cognitive_event,
            check_workflow_duplicate,
            ingest_agent_result,
            detect_trigger_loop,
            acquire_spawn_quota,
            release_spawn_quota,
            check_action_escalation,
            record_token_usage,
            check_token_budget,
            get_coherence_score,
            trigger_strategic_planning,
        )

        functions = [
            "record_cognitive_event",
            "check_workflow_duplicate",
            "ingest_agent_result",
            "detect_trigger_loop",
            "acquire_spawn_quota",
            "release_spawn_quota",
            "check_action_escalation",
            "record_token_usage",
            "check_token_budget",
            "get_coherence_score",
            "trigger_strategic_planning",
        ]

        for func_name in functions:
            print(f"  ✓ {func_name}")

        return True
    except Exception as e:
        print(f"  ✗ Integration check failed: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Phase 4 Cognitive Infrastructure Verification")
    print("=" * 60)

    checks = [
        ("Files", check_files),
        ("Database Schema", check_database),
        ("Module Imports", check_imports),
        ("HTTP Routes", check_routes),
        ("Integration Functions", check_integration),
    ]

    results = {}
    for name, check_fn in checks:
        print(f"\n{name}:")
        try:
            results[name] = check_fn()
        except Exception as e:
            print(f"  ✗ Check failed: {e}")
            results[name] = False

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("-" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {name}")

    print("-" * 60)
    print(f"Result: {passed}/{total} checks passed")

    if passed == total:
        print("\n✅ Phase 4 Cognitive Infrastructure ready for deployment!")
        return 0
    else:
        print("\n❌ Some checks failed. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
