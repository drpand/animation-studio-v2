"""Orchestrator API router — combines all orchestrator sub-routers."""
from fastapi import APIRouter

from api.orchestrator.task_chain import router as task_chain_router
from api.orchestrator.producer import router as producer_router
from api.orchestrator.storyboard import router as storyboard_router

router = APIRouter()

# Include all sub-routers
router.include_router(task_chain_router)
router.include_router(producer_router)
router.include_router(storyboard_router)
