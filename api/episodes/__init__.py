"""Episodes API router — combines all episodes sub-routers."""
from fastapi import APIRouter

from api.episodes.seasons_episodes import router as seasons_router
from api.episodes.scenes import router as scenes_router
from api.episodes.characters_mood import router as characters_router

router = APIRouter()

# Include all sub-routers
router.include_router(seasons_router)
router.include_router(scenes_router)
router.include_router(characters_router)
