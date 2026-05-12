"""
PHASE 4 AGGREGATOR ROUTER
Mounts all 12 cognitive infrastructure subsystems into FastAPI
"""
from fastapi import APIRouter
import importlib
import logging

logger = logging.getLogger(__name__)
phase4_router = APIRouter()

# Absolute module paths → mount prefixes
COGNITIVE_MODULES = [
    ("infra.cognitive.coherence.coherence_routes", "/cognitive/coherence"),
    ("infra.cognitive.executive.executive_routes", "/cognitive/executive"),
    ("infra.cognitive.guardrails.guardrail_routes", "/cognitive/guardrails"),
    ("infra.cognitive.knowledge_integrity.integrity_routes", "/cognitive/knowledge-integrity"),
    ("infra.cognitive.explainability.explainability_routes", "/cognitive/explainability"),
    ("infra.cognitive.org_model.org_model_routes", "/cognitive/org-model"),
    ("infra.cognitive.learning.learning_routes", "/cognitive/learning"),
    ("infra.cognitive.teammate.teammate_routes", "/cognitive/teammate"),
    ("infra.cognitive.temporal.temporal_routes", "/cognitive/temporal"),
    ("infra.cognitive.resilience.resilience_routes", "/cognitive/resilience"),
    ("infra.cognitive.observability.observability_routes", "/cognitive/observability"),
    ("infra.cognitive.scale.scale_routes", "/cognitive/scale"),
]

# Dynamic router mounting
for module_path, prefix in COGNITIVE_MODULES:
    try:
        module = importlib.import_module(module_path)
        if hasattr(module, 'router'):
            phase4_router.include_router(module.router, prefix=prefix)
            logger.info(f"✅ Phase 4 {prefix} mounted")
        else:
            logger.warning(f"⚠️  Phase 4 {prefix} has no 'router' export")
    except Exception as e:
        logger.warning(f"⚠️  Phase 4 {prefix} failed to mount: {e}")

__all__ = ['phase4_router']
