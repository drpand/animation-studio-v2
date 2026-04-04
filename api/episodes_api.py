"""
Episodes API — управление эпизодами, сезонами, сценами.
Префикс роутов задаётся в main.py: /api/episodes
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import (
    EpisodeCreate, EpisodeUpdate, SceneCreate, SceneUpdate,
    SceneVersionCreate, CharacterCreate, MoodItemCreate, DecisionCreate
)

router = APIRouter()


def _get_active_project_id(db):
    """Вспомогательная функция для получения ID активного проекта."""
    import asyncio
    loop = asyncio.get_event_loop()
    project = loop.run_until_complete(crud.get_active_project(db))
    return project.id if project else None


@router.get("/seasons")
async def get_seasons(db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
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
    project = await crud.get_active_project(db)
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
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")

    seasons = await crud.get_seasons(db, project.id)
    season = None
    for s in seasons:
        if s.season_number == req.season:
            season = s
            break

    if not season:
        from database import Season
        season_data = {"project_id": project.id, "season_number": req.season, "title": f"Сезон {req.season}", "description": ""}
        season_obj = Season(**season_data)
        db.add(season_obj)
        await db.commit()
        await db.refresh(season_obj)
        season = season_obj

    episodes = await crud.get_episodes(db, season.id)
    ep_num = len(episodes) + 1
    now = datetime.now().isoformat()

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
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == season_num:
            episode = await crud.get_episode(db, s.id, ep_num)
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
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == season_num:
            episode = await crud.get_episode(db, s.id, ep_num)
            if episode:
                data = {k: v for k, v in update.model_dump().items() if v is not None}
                data["updated_at"] = datetime.now().isoformat()
                await crud.update_episode(db, episode.id, data)
                return {"ok": True, "episode": {
                    "episode_number": episode.episode_number,
                    "title": episode.title,
                    "status": episode.status,
                }}
    raise HTTPException(404, f"Эпизод {season_num}x{ep_num} не найден")


@router.post("/scene")
async def create_scene(req: SceneCreate, db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == req.season:
            episode = await crud.get_episode(db, s.id, req.episode)
            if episode:
                scenes = await crud.get_scenes(db, episode.id)
                scene_num = len(scenes) + 1
                now = datetime.now().isoformat()
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
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == season_num:
            episode = await crud.get_episode(db, s.id, ep_num)
            if episode:
                scenes = await crud.get_scenes(db, episode.id)
                for sc in scenes:
                    if sc.scene_number == scene_num:
                        data = {k: v for k, v in update.model_dump().items() if v is not None}
                        data["updated_at"] = datetime.now().isoformat()
                        await crud.update_scene(db, sc.id, data)
                        return {"ok": True, "scene": {"scene_number": sc.scene_number, "title": sc.title}}
    raise HTTPException(404, f"Сцена {season_num}x{ep_num}:{scene_num} не найдена")


@router.get("/status")
async def get_production_status(db: AsyncSession = Depends(get_session)):
    analytics = await crud.get_production_analytics(db)
    return {
        "total_episodes": analytics["total_episodes"],
        "by_status": analytics["by_status"],
    }


@router.get("/characters")
async def get_characters(db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        return {"characters": []}
    characters = await crud.get_characters(db, project.id)
    return {"characters": [
        {"id": c.id, "name": c.name, "description": c.description, "voice_id": c.voice_id, "relations": c.relations}
        for c in characters
    ]}


@router.post("/character")
async def create_character(req: CharacterCreate, db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    now = datetime.now().isoformat()
    char = await crud.create_character(db, project.id, {
        "name": req.name, "description": req.description,
        "voice_id": req.voice_id, "relations": req.relations, "created_at": now,
    })
    return {"ok": True, "character": {"id": char.id, "name": char.name}}


@router.delete("/character/{char_id}")
async def delete_character(char_id: int, db: AsyncSession = Depends(get_session)):
    await crud.delete_character(db, char_id)
    return {"ok": True}


@router.get("/mood-board")
async def get_mood_board(db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        return {"mood_board": []}
    items = await crud.get_mood_board(db, project.id)
    return {"mood_board": [{"id": m.id, "url": m.url, "description": m.description, "tags": m.tags} for m in items]}


@router.post("/mood-board")
async def add_mood_item(req: MoodItemCreate, db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    item = await crud.add_mood_item(db, project.id, {
        "url": req.url, "description": req.description, "tags": req.tags,
        "created_at": datetime.now().isoformat(),
    })
    return {"ok": True, "item": {"id": item.id, "url": item.url}}


@router.delete("/mood-board/{item_id}")
async def delete_mood_item(item_id: int, db: AsyncSession = Depends(get_session)):
    await crud.delete_mood_item(db, item_id)
    return {"ok": True}


@router.get("/decisions")
async def get_decisions(db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        return {"decisions": []}
    decisions = await crud.get_decisions(db, project.id)
    return {"decisions": [
        {"id": d.id, "title": d.title, "description": d.description, "agent_id": d.agent_id, "created_at": d.created_at}
        for d in decisions
    ]}


@router.post("/decision")
async def create_decision(req: DecisionCreate, db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    dec = await crud.create_decision(db, project.id, {
        "title": req.title, "description": req.description, "agent_id": req.agent_id,
        "created_at": datetime.now().isoformat(),
    })
    return {"ok": True, "decision": {"id": dec.id, "title": dec.title}}


@router.post("/scene/version")
async def create_scene_version(req: SceneVersionCreate, db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == req.season:
            episode = await crud.get_episode(db, s.id, req.episode)
            if episode:
                scenes = await crud.get_scenes(db, episode.id)
                for sc in scenes:
                    if sc.scene_number == req.scene:
                        versions = await crud.get_scene_versions(db, sc.id)
                        version = await crud.create_scene_version(db, sc.id, {
                            "version_number": len(versions) + 1,
                            "content": req.content, "comment": req.comment,
                            "created_at": datetime.now().isoformat(),
                        })
                        return {"ok": True, "version": {"version_number": version.version_number}}
    raise HTTPException(404, f"Сцена {req.season}x{req.episode}:{req.scene} не найдена")


@router.get("/scene/{season_num}/{ep_num}/{scene_num}/versions")
async def get_scene_versions(season_num: int, ep_num: int, scene_num: int, db: AsyncSession = Depends(get_session)):
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == season_num:
            episode = await crud.get_episode(db, s.id, ep_num)
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
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Проект не найден")
    seasons = await crud.get_seasons(db, project.id)
    for s in seasons:
        if s.season_number == season_num:
            episode = await crud.get_episode(db, s.id, ep_num)
            if episode:
                scenes = await crud.get_scenes(db, episode.id)
                characters = await crud.get_characters(db, project.id)
                return {"export": {
                    "project": project.name, "season": season_num, "episode": ep_num,
                    "title": episode.title, "description": episode.description,
                    "status": episode.status,
                    "scenes": [{"scene_number": sc.scene_number, "title": sc.title, "description": sc.description} for sc in scenes],
                    "characters": [{"name": c.name, "description": c.description} for c in characters],
                    "exported_at": datetime.now().isoformat(),
                }}
    raise HTTPException(404, f"Эпизод {season_num}x{ep_num} не найден")


@router.get("/analytics")
async def get_analytics(db: AsyncSession = Depends(get_session)):
    return await crud.get_production_analytics(db)
