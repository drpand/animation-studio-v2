"""
Project API — управление активным проектом.
Префикс роутов задаётся в main.py: /api/project
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import ProjectOut, ProjectUpdate

router = APIRouter()


@router.get("/")
async def get_project(db: AsyncSession = Depends(get_session)):
    """Получить активный проект."""
    project = await crud.get_active_project(db)
    if not project:
        return {"active_project": {}}
    return {"active_project": {
        "name": project.name,
        "description": project.description,
        "file": project.file,
        "file_path": project.file_path,
        "current_season": project.current_season,
        "current_episode": project.current_episode,
        "total_episodes": project.total_episodes,
        "updated_at": project.updated_at,
    }}


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
