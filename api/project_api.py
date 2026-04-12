"""
Project API — управление активным проектом.
Префикс роутов задаётся в main.py: /api/project
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import ProjectOut, ProjectUpdate

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    genre: str = ""
    visual_style: str = "2.5D аниме"
    color_palette: str = ""
    music_reference: str = ""
    duration_seconds: int = 180
    total_episodes: int = 1


@router.get("/")
async def get_project(db: AsyncSession = Depends(get_session)):
    """Получить активный проект."""
    project = await crud.get_active_project(db)
    if not project:
        return {"active_project": {}}
    return {"active_project": {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "file": project.file,
        "file_path": project.file_path,
        "current_season": project.current_season,
        "current_episode": project.current_episode,
        "total_episodes": project.total_episodes,
        "updated_at": project.updated_at,
    }}


@router.get("/list")
async def list_projects(db: AsyncSession = Depends(get_session)):
    """Список всех проектов."""
    projects = await crud.list_projects(db)
    return {"projects": [{
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "is_active": p.is_active,
        "created_at": p.updated_at,
    } for p in projects]}


@router.post("/create")
async def create_project(req: CreateProjectRequest, db: AsyncSession = Depends(get_session)):
    """Создать новый проект и сделать его активным."""
    if not req.name.strip():
        raise HTTPException(400, "Название проекта не может быть пустым")

    # Сохраняем настройки проекта в project_memory.json
    project_memory = {
        "active_project": {
            "name": req.name,
            "description": req.description,
            "file": "",
            "file_path": "",
            "current_season": 1,
            "current_episode": 1,
            "total_episodes": req.total_episodes,
            "visual_style": req.visual_style,
            "color_palette": req.color_palette,
            "music_reference": req.music_reference,
            "updated_at": datetime.now().isoformat(),
        },
        "projects": [],
        "seasons": [],
        "characters": [],
        "mood_board": [],
        "decision_log": [],
        "completed_tasks": [],
        "agent_decisions": [],
    }

    memory_path = os.path.join(PROJECT_ROOT, "memory", "project_memory.json")
    try:
        dir_name = os.path.dirname(memory_path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json.tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            json.dump(project_memory, tmp_f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, memory_path)
    except Exception as e:
        pass  # Не критичная ошибка

    # Создаём проект в БД
    project = await crud.create_project(db, {
        "name": req.name.strip(),
        "description": f"{req.description} | Жанр: {req.genre} | Стиль: {req.visual_style} | Палитра: {req.color_palette}",
        "file": "",
        "file_path": "",
        "current_season": 1,
        "current_episode": 1,
        "total_episodes": req.total_episodes,
        "updated_at": datetime.now().isoformat(),
    })

    return {"ok": True, "project_id": project.id, "name": project.name}


@router.post("/reset")
async def reset_project(db: AsyncSession = Depends(get_session)):
    """Сбросить контент текущего проекта (кадры, персонажи, сообщения, задачи)."""
    await crud.reset_project_content(db)

    # Сбрасываем агентов в idle
    agents_state_file = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")
    if os.path.exists(agents_state_file):
        with open(agents_state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        for agent_id, data in state.items():
            data["status"] = "idle"
            data["chat_history"] = []
        # Атомарная запись
        dir_name = os.path.dirname(agents_state_file)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json.tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            json.dump(state, tmp_f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, agents_state_file)

    return {"ok": True, "message": "Проект очищен для нового старта"}


@router.put("/")
async def update_project(update: ProjectUpdate, db: AsyncSession = Depends(get_session)):
    """Обновить параметры активного проекта."""
    project = await crud.get_active_project(db)
    if not project:
        raise HTTPException(404, "Активный проект не найден")
    data = {k: v for k, v in update.model_dump().items() if v is not None}
    data["updated_at"] = datetime.now().isoformat()
    await crud.update_project(db, project.id, data)
    return {"ok": True, "project": {**data, "id": project.id}}


@router.post("/switch")
async def switch_project(project_name: str, db: AsyncSession = Depends(get_session)):
    """Переключить активный проект."""
    raise HTTPException(501, "Мультипроектность ещё не реализована полностью")
