"""
Project API — управление активным проектом.
Префикс роутов задаётся в main.py: /api/project
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_MEMORY_FILE = os.path.join(PROJECT_ROOT, "memory", "project_memory.json")


def _load_project() -> dict:
    if not os.path.exists(PROJECT_MEMORY_FILE):
        return {"active_project": {}, "projects": []}
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


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    current_season: int | None = None
    current_episode: int | None = None
    total_episodes: int | None = None


@router.get("/")
async def get_project():
    """Получить активный проект."""
    return _load_project()


@router.put("/")
async def update_project(update: ProjectUpdate):
    """Обновить параметры активного проекта."""
    data = _load_project()
    if "active_project" not in data:
        data["active_project"] = {}

    ap = data["active_project"]
    if update.name is not None:
        ap["name"] = update.name
    if update.description is not None:
        ap["description"] = update.description
    if update.current_season is not None:
        ap["current_season"] = update.current_season
    if update.current_episode is not None:
        ap["current_episode"] = update.current_episode
    if update.total_episodes is not None:
        ap["total_episodes"] = update.total_episodes

    ap["updated_at"] = datetime.now().isoformat()
    _save_project(data)
    return {"ok": True, "project": ap}


@router.post("/switch")
async def switch_project(project_name: str):
    """Переключить активный проект (для мультипроектности)."""
    data = _load_project()
    projects = data.get("projects", [])
    for p in projects:
        if p.get("name") == project_name:
            data["active_project"] = p
            _save_project(data)
            return {"ok": True, "project": p}
    return {"ok": False, "error": f"Проект '{project_name}' не найден"}
