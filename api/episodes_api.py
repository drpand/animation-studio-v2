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


# ============================================
# Персонажи
# ============================================

class CharacterCreate(BaseModel):
    name: str
    description: str = ""
    voice_id: str = ""
    relations: str = ""


@router.get("/characters")
async def get_characters():
    """Получить всех персонажей."""
    data = _load_project()
    return {"characters": data.get("characters", [])}


@router.post("/character")
async def create_character(req: CharacterCreate):
    """Создать персонажа."""
    data = _load_project()
    if "characters" not in data:
        data["characters"] = []
    character = {
        "id": f"char_{len(data['characters']) + 1}",
        "name": req.name,
        "description": req.description,
        "voice_id": req.voice_id,
        "relations": req.relations,
        "created_at": datetime.now().isoformat(),
    }
    data["characters"].append(character)
    _save_project(data)
    return {"ok": True, "character": character}


@router.delete("/character/{char_id}")
async def delete_character(char_id: str):
    """Удалить персонажа."""
    data = _load_project()
    data["characters"] = [c for c in data.get("characters", []) if c.get("id") != char_id]
    _save_project(data)
    return {"ok": True}


# ============================================
# Mood Board
# ============================================

class MoodItemCreate(BaseModel):
    url: str = ""
    description: str = ""
    tags: str = ""


@router.get("/mood-board")
async def get_mood_board():
    """Получить доску настроения."""
    data = _load_project()
    return {"mood_board": data.get("mood_board", [])}


@router.post("/mood-board")
async def add_mood_item(req: MoodItemCreate):
    """Добавить элемент на доску настроения."""
    data = _load_project()
    if "mood_board" not in data:
        data["mood_board"] = []
    item = {
        "id": f"mood_{len(data['mood_board']) + 1}",
        "url": req.url,
        "description": req.description,
        "tags": req.tags,
        "created_at": datetime.now().isoformat(),
    }
    data["mood_board"].append(item)
    _save_project(data)
    return {"ok": True, "item": item}


@router.delete("/mood-board/{item_id}")
async def delete_mood_item(item_id: str):
    """Удалить элемент с доски настроения."""
    data = _load_project()
    data["mood_board"] = [m for m in data.get("mood_board", []) if m.get("id") != item_id]
    _save_project(data)
    return {"ok": True}


# ============================================
# Decision Log
# ============================================

class DecisionCreate(BaseModel):
    title: str
    description: str = ""
    agent_id: str = ""


@router.get("/decisions")
async def get_decisions():
    """Получить журнал решений."""
    data = _load_project()
    return {"decisions": data.get("decision_log", [])}


@router.post("/decision")
async def create_decision(req: DecisionCreate):
    """Записать решение."""
    data = _load_project()
    if "decision_log" not in data:
        data["decision_log"] = []
    decision = {
        "id": f"dec_{len(data['decision_log']) + 1}",
        "title": req.title,
        "description": req.description,
        "agent_id": req.agent_id,
        "created_at": datetime.now().isoformat(),
    }
    data["decision_log"].append(decision)
    _save_project(data)
    return {"ok": True, "decision": decision}


# ============================================
# Версионирование сцен
# ============================================

class SceneVersionCreate(BaseModel):
    season: int
    episode: int
    scene: int
    content: str
    comment: str = ""


@router.post("/scene/version")
async def create_scene_version(req: SceneVersionCreate):
    """Создать версию сцены."""
    data = _load_project()
    for s in data.get("seasons", []):
        if s.get("season_number") == req.season:
            for ep in s.get("episodes", []):
                if ep.get("episode_number") == req.episode:
                    for sc in ep.get("scenes", []):
                        if sc.get("scene_number") == req.scene:
                            if "versions" not in sc:
                                sc["versions"] = []
                            version = {
                                "version_number": len(sc["versions"]) + 1,
                                "content": req.content,
                                "comment": req.comment,
                                "created_at": datetime.now().isoformat(),
                            }
                            sc["versions"].append(version)
                            sc["updated_at"] = datetime.now().isoformat()
                            _save_project(data)
                            return {"ok": True, "version": version}
    raise HTTPException(404, f"Сцена {req.season}x{req.episode}:{req.scene} не найдена")


@router.get("/scene/{season_num}/{ep_num}/{scene_num}/versions")
async def get_scene_versions(season_num: int, ep_num: int, scene_num: int):
    """Получить все версии сцены."""
    data = _load_project()
    for s in data.get("seasons", []):
        if s.get("season_number") == season_num:
            for ep in s.get("episodes", []):
                if ep.get("episode_number") == ep_num:
                    for sc in ep.get("scenes", []):
                        if sc.get("scene_number") == scene_num:
                            return {"versions": sc.get("versions", [])}
    raise HTTPException(404, f"Сцена {season_num}x{ep_num}:{scene_num} не найдена")
