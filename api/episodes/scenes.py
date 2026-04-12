"""Scene management endpoints."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import SceneCreate, SceneUpdate, SceneVersionCreate
from api.episodes.helpers import (
    get_active_project_id,
    get_active_project,
    ensure_season,
    get_episode_by_number,
    now_iso,
)

router = APIRouter()


@router.post("/scene")
async def create_scene(req: SceneCreate, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    season = await ensure_season(db, project.id, req.season)
    episode = await get_episode_by_number(db, season.id, req.episode)
    if episode:
        scenes = await crud.get_scenes(db, episode.id)
        scene_num = len(scenes) + 1
        now = now_iso()
        scene = await crud.create_scene(db, episode.id, {
            "scene_number": req.scene_number or scene_num,
            "title": req.title or f"Сцена {req.scene_number or scene_num}",
            "description": req.description,
            "duration_seconds": req.duration_seconds,
            "status": req.status or "draft",
            "created_at": now,
            "updated_at": now,
        })
        return {"ok": True, "scene": {
            "scene_number": scene.scene_number,
            "title": scene.title,
            "status": scene.status,
        }}
    raise HTTPException(404, f"Эпизод {req.season}x{req.episode} не найден")


@router.put("/scene/{season_num}/{ep_num}/{scene_num}")
async def update_scene(season_num: int, ep_num: int, scene_num: int, update: SceneUpdate, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    season = await ensure_season(db, project.id, season_num)
    episode = await get_episode_by_number(db, season.id, ep_num)
    if episode:
        scenes = await crud.get_scenes(db, episode.id)
        for sc in scenes:
            if sc.scene_number == scene_num:
                data = {k: v for k, v in update.model_dump().items() if v is not None}
                data["updated_at"] = now_iso()
                await crud.update_scene(db, sc.id, data)
                return {"ok": True, "scene": {"scene_number": sc.scene_number, "title": sc.title}}
    raise HTTPException(404, f"Сцена {season_num}x{ep_num}:{scene_num} не найдена")


@router.post("/scene/version")
async def create_scene_version(req: SceneVersionCreate, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    season = await ensure_season(db, project.id, req.season)
    episode = await get_episode_by_number(db, season.id, req.episode)
    if episode:
        scenes = await crud.get_scenes(db, episode.id)
        for sc in scenes:
            if sc.scene_number == req.scene:
                versions = await crud.get_scene_versions(db, sc.id)
                version = await crud.create_scene_version(db, sc.id, {
                    "version_number": len(versions) + 1,
                    "content": req.content, "comment": req.comment,
                    "created_at": now_iso(),
                })
                return {"ok": True, "version": {"version_number": version.version_number}}
    raise HTTPException(404, f"Сцена {req.season}x{req.episode}:{req.scene} не найдена")


@router.get("/scene/{season_num}/{ep_num}/{scene_num}/versions")
async def get_scene_version_list(season_num: int, ep_num: int, scene_num: int, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    season = await ensure_season(db, project.id, season_num)
    episode = await get_episode_by_number(db, season.id, ep_num)
    if episode:
        scenes = await crud.get_scenes(db, episode.id)
        for sc in scenes:
            if sc.scene_number == scene_num:
                versions = await crud.get_scene_versions(db, sc.id)
                return {"versions": [
                    {"version_number": v.version_number, "content": v.content[:500], "comment": v.comment, "created_at": v.created_at}
                    for v in versions
                ]}
    raise HTTPException(404, f"Сцена {season_num}x{ep_num}:{scene_num} не найдена")


@router.get("/export/{season_num}/{ep_num}")
async def export_episode(season_num: int, ep_num: int, db: AsyncSession = Depends(get_session)):
    project = await get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    season = await ensure_season(db, project.id, season_num)
    episode = await get_episode_by_number(db, season.id, ep_num)
    if episode:
        scenes = await crud.get_scenes(db, episode.id)
        characters = await crud.get_characters(db, project.id)
        return {"export": {
            "project": project.name, "season": season_num, "episode": ep_num,
            "title": episode.title, "description": episode.description,
            "status": episode.status,
            "scenes": [{"scene_number": sc.scene_number, "title": sc.title, "description": sc.description} for sc in scenes],
            "characters": [{"name": c.name, "description": c.description} for c in characters],
            "exported_at": now_iso(),
        }}
    raise HTTPException(404, f"Эпизод {season_num}x{ep_num} не найден")
