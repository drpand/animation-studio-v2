"""
Episodes API — управление эпизодами, сезонами, сценами.
Префикс роутов задаётся в main.py: /api/episodes
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_MEMORY_FILE = os.path.join(PROJECT_ROOT, "memory", "project_memory.json")


def _load_project() -> dict:
    if not os.path.exists(PROJECT_MEMORY_FILE):
        return {"seasons": [], "characters": [], "mood_board": [], "decision_log": []}
    with open(PROJECT_MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_project(data: dict):
    dir_name = os.path.dirname(PROJECT_MEMORY_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, PROJECT_MEMORY_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


class EpisodeCreate(BaseModel):
    season: int = 1
    title: str = ""
    description: str = ""


class SceneCreate(BaseModel):
    season: int = 1
    episode: int = 1
    scene_number: int = 1
    title: str = ""
    description: str = ""
    duration_seconds: int = 0
    status: str = "draft"


class EpisodeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None


class SceneUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    duration_seconds: int | None = None
    status: str | None = None


@router.get("/seasons")
async def get_seasons():
    """Получить все сезоны."""
    data = _load_project()
    return {"seasons": data.get("seasons", [])}


@router.get("/season/{season_num}")
async def get_season(season_num: int):
    """Получить конкретный сезон."""
    data = _load_project()
    for s in data.get("seasons", []):
        if s.get("season_number") == season_num:
            return {"season": s}
    raise HTTPException(404, f"Сезон {season_num} не найден")


@router.post("/episode")
async def create_episode(req: EpisodeCreate):
    """Создать новый эпизод."""
    data = _load_project()
    now = datetime.now().isoformat()

    # Найти или создать сезон
    season = None
    for s in data.get("seasons", []):
        if s.get("season_number") == req.season:
            season = s
            break

    if not season:
        season = {
            "season_number": req.season,
            "title": f"Сезон {req.season}",
            "description": "",
            "episodes": []
        }
        data["seasons"].append(season)

    ep_num = len(season.get("episodes", [])) + 1
    episode = {
        "episode_number": ep_num,
        "title": req.title or f"Эпизод {ep_num}",
        "description": req.description,
        "status": "draft",
        "scenes": [],
        "created_at": now,
        "updated_at": now,
    }
    season["episodes"].append(episode)
    _save_project(data)
    return {"ok": True, "episode": episode}


@router.get("/episode/{season_num}/{ep_num}")
async def get_episode(season_num: int, ep_num: int):
    """Получить эпизод."""
    data = _load_project()
    for s in data.get("seasons", []):
        if s.get("season_number") == season_num:
            for ep in s.get("episodes", []):
                if ep.get("episode_number") == ep_num:
                    return {"episode": ep}
    raise HTTPException(404, f"Эпизод {season_num}x{ep_num} не найден")


@router.put("/episode/{season_num}/{ep_num}")
async def update_episode(season_num: int, ep_num: int, update: EpisodeUpdate):
    """Обновить эпизод."""
    data = _load_project()
    for s in data.get("seasons", []):
        if s.get("season_number") == season_num:
            for ep in s.get("episodes", []):
                if ep.get("episode_number") == ep_num:
                    if update.title is not None:
                        ep["title"] = update.title
                    if update.description is not None:
                        ep["description"] = update.description
                    if update.status is not None:
                        ep["status"] = update.status
                    ep["updated_at"] = datetime.now().isoformat()
                    _save_project(data)
                    return {"ok": True, "episode": ep}
    raise HTTPException(404, f"Эпизод {season_num}x{ep_num} не найден")


@router.post("/scene")
async def create_scene(req: SceneCreate):
    """Создать сцену в эпизоде."""
    data = _load_project()
    now = datetime.now().isoformat()

    for s in data.get("seasons", []):
        if s.get("season_number") == req.season:
            for ep in s.get("episodes", []):
                if ep.get("episode_number") == req.episode:
                    scene_num = len(ep.get("scenes", [])) + 1
                    scene = {
                        "scene_number": req.scene_number or scene_num,
                        "title": req.title or f"Сцена {req.scene_number or scene_num}",
                        "description": req.description,
                        "duration_seconds": req.duration_seconds,
                        "status": req.status or "draft",
                        "versions": [],
                        "created_at": now,
                        "updated_at": now,
                    }
                    ep["scenes"].append(scene)
                    ep["updated_at"] = now
                    _save_project(data)
                    return {"ok": True, "scene": scene}
    raise HTTPException(404, f"Эпизод {req.season}x{req.episode} не найден")


@router.put("/scene/{season_num}/{ep_num}/{scene_num}")
async def update_scene(season_num: int, ep_num: int, scene_num: int, update: SceneUpdate):
    """Обновить сцену."""
    data = _load_project()
    for s in data.get("seasons", []):
        if s.get("season_number") == season_num:
            for ep in s.get("episodes", []):
                if ep.get("episode_number") == ep_num:
                    for sc in ep.get("scenes", []):
                        if sc.get("scene_number") == scene_num:
                            if update.title is not None:
                                sc["title"] = update.title
                            if update.description is not None:
                                sc["description"] = update.description
                            if update.duration_seconds is not None:
                                sc["duration_seconds"] = update.duration_seconds
                            if update.status is not None:
                                sc["status"] = update.status
                            sc["updated_at"] = datetime.now().isoformat()
                            _save_project(data)
                            return {"ok": True, "scene": sc}
    raise HTTPException(404, f"Сцена {season_num}x{ep_num}:{scene_num} не найдена")


@router.get("/status")
async def get_production_status():
    """Получить статусы производства всего проекта."""
    data = _load_project()
    summary = {"total_episodes": 0, "by_status": {}}
    for s in data.get("seasons", []):
        for ep in s.get("episodes", []):
            summary["total_episodes"] += 1
            status = ep.get("status", "draft")
            summary["by_status"][status] = summary["by_status"].get(status, 0) + 1
    return summary
