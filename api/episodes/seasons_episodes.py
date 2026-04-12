"""Season and episode management endpoints."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session, Season
import crud
from models import EpisodeCreate, EpisodeUpdate
from api.episodes.helpers import (
    get_active_project_id,
    get_active_project,
    ensure_season,
    get_episode_by_number,
    now_iso,
)

router = APIRouter()


@router.get("/seasons")
async def get_seasons(db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        return {"seasons": []}
    seasons = await crud.get_seasons(db, project.id)
    result = []
    for s in seasons:
        episodes = await crud.get_episodes(db, s.id)
        result.append({
            "season_number": s.season_number,
            "title": s.title,
            "description": s.description,
            "episodes": [
                {
                    "episode_number": ep.episode_number,
                    "title": ep.title,
                    "description": ep.description,
                    "status": ep.status,
                    "created_at": ep.created_at,
                    "updated_at": ep.updated_at,
                }
                for ep in episodes
            ]
        })
    return {"seasons": result}


@router.get("/season/{season_num}")
async def get_season(season_num: int, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == season_num:
            episodes = await crud.get_episodes(db, s.id)
            return {"season": {
                "season_number": s.season_number,
            "title": s.title,
            "description": s.description,
                "episodes": [{"episode_number": ep.episode_number, "title": ep.title, "status": ep.status} for ep in episodes]
            }}
    raise HTTPException(404, f"Сезон {season_num} не найден")


@router.post("/episode")
async def create_episode(req: EpisodeCreate, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")

    season = await ensure_season(db, project.id, req.season)
    episodes = await crud.get_episodes(db, season.id)
    ep_num = len(episodes) + 1
    now = now_iso()

    episode = await crud.create_episode(db, season.id, {
        "episode_number": ep_num,
        "title": req.title or f"Эпизод {ep_num}",
        "description": req.description,
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    })
    return {"ok": True, "episode": {
        "episode_number": episode.episode_number,
        "title": episode.title,
        "description": episode.description,
        "status": episode.status,
    }}


@router.get("/episode/{season_num}/{ep_num}")
async def get_episode(season_num: int, ep_num: int, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == season_num:
            episode = await get_episode_by_number(db, s.id, ep_num)
            if episode:
                scenes = await crud.get_scenes(db, episode.id)
                return {"episode": {
                    "episode_number": episode.episode_number,
                    "title": episode.title,
                    "description": episode.description,
                    "status": episode.status,
                    "scenes": [
                        {
                            "scene_number": sc.scene_number,
                            "title": sc.title,
                            "description": sc.description,
                            "duration_seconds": sc.duration_seconds,
                            "status": sc.status,
                        }
                        for sc in scenes
                    ]
                }}
    raise HTTPException(404, f"Эпизод {season_num}x{ep_num} не найден")


@router.put("/episode/{season_num}/{ep_num}")
async def update_episode(season_num: int, ep_num: int, update: EpisodeUpdate, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == season_num:
            episode = await get_episode_by_number(db, s.id, ep_num)
            if episode:
                data = {k: v for k, v in update.model_dump().items() if v is not None}
                data["updated_at"] = now_iso()
                await crud.update_episode(db, episode.id, data)
                return {"ok": True, "episode": {
                    "episode_number": episode.episode_number,
                    "title": episode.title,
                    "status": episode.status,
                }}
    raise HTTPException(404, f"Эпизод {season_num}x{ep_num} не найден")


@router.get("/status")
async def get_production_status(db: AsyncSession = Depends(get_session)):
    analytics = await crud.get_production_analytics(db)
    return {
        "total_episodes": analytics["total_episodes"],
        "by_status": analytics["by_status"],
    }


@router.get("/analytics")
async def get_analytics(db: AsyncSession = Depends(get_session)):
    return await crud.get_production_analytics(db)
