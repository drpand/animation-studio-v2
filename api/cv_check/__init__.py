"""CV Check API router — combines all CV check sub-routers."""
from fastapi import APIRouter

from api.cv_check.endpoints import router as endpoints_router

router = APIRouter()

# Include all sub-routers
router.include_router(endpoints_router)
