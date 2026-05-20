"""Phase 3 aggregator router — autonomous workforce infrastructure."""
from __future__ import annotations
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

phase3_router = APIRouter()

try:
    from ..rpa.rpa_routes import router as _rpa
    phase3_router.include_router(_rpa, prefix="/rpa")
    logger.info("  ✓ RPA routes loaded")
except Exception as e:
    logger.warning("  ✗ RPA routes failed: %s", e)

try:
    from ..healing.healing_routes import router as _heal
    phase3_router.include_router(_heal, prefix="/healing")
    logger.info("  ✓ Healing routes loaded")
except Exception as e:
    logger.warning("  ✗ Healing routes failed: %s", e)

try:
    from ..marketplace.marketplace_routes import router as _mkt
    phase3_router.include_router(_mkt, prefix="/marketplace")
    logger.info("  ✓ Marketplace routes loaded")
except Exception as e:
    logger.warning("  ✗ Marketplace routes failed: %s", e)

try:
    from ..deployment.deployment_routes import router as _dep
    phase3_router.include_router(_dep, prefix="/deployment")
    logger.info("  ✓ Deployment routes loaded")
except Exception as e:
    logger.warning("  ✗ Deployment routes failed: %s", e)

try:
    from ..simulation.simulation_routes import router as _sim
    phase3_router.include_router(_sim, prefix="/simulation")
    logger.info("  ✓ Simulation routes loaded")
except Exception as e:
    logger.warning("  ✗ Simulation routes failed: %s", e)
