"""Agents API router — combines all agents sub-routers."""
from fastapi import APIRouter

from api.agents.endpoints import router as endpoints_router

router = APIRouter()

# Include all sub-routers
router.include_router(endpoints_router)
