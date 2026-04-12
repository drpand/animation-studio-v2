"""HR API router — combines all HR sub-routers."""
from fastapi import APIRouter

from api.hr.endpoints import router as endpoints_router

router = APIRouter()

# Include all sub-routers
router.include_router(endpoints_router)
