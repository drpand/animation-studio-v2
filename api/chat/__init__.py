"""Chat API router — combines all chat sub-routers."""
from fastapi import APIRouter

from api.chat.endpoints import router as endpoints_router

router = APIRouter()

# Include all sub-routers
router.include_router(endpoints_router)
