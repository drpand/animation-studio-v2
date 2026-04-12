"""Med Otdel API router — combines all med_otdel sub-routers."""
from fastapi import APIRouter

from api.med_otdel.evaluation import router as evaluation_router
from api.med_otdel.memory import router as memory_router
from api.med_otdel.monitoring import router as monitoring_router

router = APIRouter()

# Include all sub-routers
router.include_router(evaluation_router)
router.include_router(memory_router)
router.include_router(monitoring_router)
