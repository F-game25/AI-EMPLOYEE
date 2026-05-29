#!/bin/bash
set -e

echo "================================================================================"
echo "PHASE 4 COGNITIVE INFRASTRUCTURE — VERIFICATION SCRIPT"
echo "================================================================================"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

check_file() {
    local file=$1
    local desc=$2
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $desc"
        ((PASS++))
    else
        echo -e "${RED}✗${NC} $desc (MISSING: $file)"
        ((FAIL++))
    fi
}

check_python_syntax() {
    local file=$1
    local desc=$2
    if python3 -m py_compile "$file" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $desc (syntax OK)"
        ((PASS++))
    else
        echo -e "${RED}✗${NC} $desc (SYNTAX ERROR)"
        ((FAIL++))
    fi
}

echo "PART 4: MEMORY SANITATION + KNOWLEDGE INTEGRITY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_file runtime/infra/cognitive/knowledge_integrity/__init__.py "knowledge_integrity/__init__.py"
check_file runtime/infra/cognitive/knowledge_integrity/schema.py "knowledge_integrity/schema.py"
check_file runtime/infra/cognitive/knowledge_integrity/lifecycle_manager.py "knowledge_integrity/lifecycle_manager.py"
check_file runtime/infra/cognitive/knowledge_integrity/deduplicator.py "knowledge_integrity/deduplicator.py"
check_file runtime/infra/cognitive/knowledge_integrity/contradiction_scanner.py "knowledge_integrity/contradiction_scanner.py"
check_file runtime/infra/cognitive/knowledge_integrity/hallucination_detector.py "knowledge_integrity/hallucination_detector.py"
check_file runtime/infra/cognitive/knowledge_integrity/entropy_reducer.py "knowledge_integrity/entropy_reducer.py"
check_file runtime/infra/cognitive/knowledge_integrity/integrity_routes.py "knowledge_integrity/integrity_routes.py"
echo ""

echo "PART 5: EXPLAINABLE AUTONOMY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_file runtime/infra/cognitive/explainability/__init__.py "explainability/__init__.py"
check_file runtime/infra/cognitive/explainability/schema.py "explainability/schema.py"
check_file runtime/infra/cognitive/explainability/decision_recorder.py "explainability/decision_recorder.py"
check_file runtime/infra/cognitive/explainability/causal_tracer.py "explainability/causal_tracer.py"
check_file runtime/infra/cognitive/explainability/reasoning_replayer.py "explainability/reasoning_replayer.py"
check_file runtime/infra/cognitive/explainability/memory_provenance.py "explainability/memory_provenance.py"
check_file runtime/infra/cognitive/explainability/explanation_builder.py "explainability/explanation_builder.py"
check_file runtime/infra/cognitive/explainability/explainability_routes.py "explainability/explainability_routes.py"
echo ""

echo "PART 6: ORGANIZATIONAL SELF-MODEL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_file runtime/infra/cognitive/org_model/__init__.py "org_model/__init__.py"
check_file runtime/infra/cognitive/org_model/schema.py "org_model/schema.py"
check_file runtime/infra/cognitive/org_model/org_topology.py "org_model/org_topology.py"
check_file runtime/infra/cognitive/org_model/dependency_graph.py "org_model/dependency_graph.py"
check_file runtime/infra/cognitive/org_model/user_profiler.py "org_model/user_profiler.py"
check_file runtime/infra/cognitive/org_model/operational_modeler.py "org_model/operational_modeler.py"
check_file runtime/infra/cognitive/org_model/org_model_routes.py "org_model/org_model_routes.py"
echo ""

echo "SYNTAX VALIDATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_python_syntax runtime/infra/cognitive/knowledge_integrity/schema.py "knowledge_integrity/schema.py"
check_python_syntax runtime/infra/cognitive/knowledge_integrity/lifecycle_manager.py "knowledge_integrity/lifecycle_manager.py"
check_python_syntax runtime/infra/cognitive/knowledge_integrity/deduplicator.py "knowledge_integrity/deduplicator.py"
check_python_syntax runtime/infra/cognitive/knowledge_integrity/contradiction_scanner.py "knowledge_integrity/contradiction_scanner.py"
check_python_syntax runtime/infra/cognitive/knowledge_integrity/hallucination_detector.py "knowledge_integrity/hallucination_detector.py"
check_python_syntax runtime/infra/cognitive/knowledge_integrity/entropy_reducer.py "knowledge_integrity/entropy_reducer.py"
check_python_syntax runtime/infra/cognitive/knowledge_integrity/integrity_routes.py "knowledge_integrity/integrity_routes.py"
check_python_syntax runtime/infra/cognitive/explainability/schema.py "explainability/schema.py"
check_python_syntax runtime/infra/cognitive/explainability/decision_recorder.py "explainability/decision_recorder.py"
check_python_syntax runtime/infra/cognitive/explainability/causal_tracer.py "explainability/causal_tracer.py"
check_python_syntax runtime/infra/cognitive/explainability/explanation_builder.py "explainability/explanation_builder.py"
check_python_syntax runtime/infra/cognitive/explainability/explainability_routes.py "explainability/explainability_routes.py"
check_python_syntax runtime/infra/cognitive/org_model/schema.py "org_model/schema.py"
check_python_syntax runtime/infra/cognitive/org_model/org_topology.py "org_model/org_topology.py"
check_python_syntax runtime/infra/cognitive/org_model/dependency_graph.py "org_model/dependency_graph.py"
check_python_syntax runtime/infra/cognitive/org_model/user_profiler.py "org_model/user_profiler.py"
check_python_syntax runtime/infra/cognitive/org_model/operational_modeler.py "org_model/operational_modeler.py"
check_python_syntax runtime/infra/cognitive/org_model/org_model_routes.py "org_model/org_model_routes.py"
echo ""

echo "DATABASE & INTEGRATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_file runtime/infra/cognitive/db.py "Core database module (cognitive_conn)"

echo ""
echo "================================================================================"
echo "SUMMARY"
echo "================================================================================"
echo -e "${GREEN}Passed:${NC} $PASS"
echo -e "${RED}Failed:${NC} $FAIL"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ ALL CHECKS PASSED${NC}"
    echo ""
    echo "Phase 4 Parts 4-6 infrastructure is ready for integration."
    echo ""
    echo "Files summary:"
    echo "  - Part 4: 8 files (Memory Sanitation + Knowledge Integrity)"
    echo "  - Part 5: 8 files (Explainable Autonomy)"
    echo "  - Part 6: 7 files (Organizational Self-Model)"
    echo "  - Total:  23 files created/enhanced"
    echo ""
    exit 0
else
    echo -e "${RED}✗ SOME CHECKS FAILED${NC}"
    echo ""
    echo "Please review failures above and ensure all files exist."
    echo ""
    exit 1
fi
