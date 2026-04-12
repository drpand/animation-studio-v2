"""Task chain endpoints — submit, status, intervene, history, active, registry."""
import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
import crud
from models import SubmitTaskRequest, InterveneRequest
from config import PROJECT_NAME
from api.orchestrator.helpers import (
    build_task_chain,
    execute_chain,
    REGISTRY_FILE,
)

router = APIRouter()


@router.post("/submit")
async def submit_task(req: SubmitTaskRequest, db: AsyncSession = Depends(get_session)):
    """Отправить задачу Orchestrator'у."""
    if not req.description.strip():
        raise HTTPException(400, "Описание задачи не может быть пустым")

    chain = await build_task_chain(req.description)
    if not chain or not chain.steps:
        raise HTTPException(400, "Не удалось построить цепочку для задачи")

    task_data = {
        "task_id": chain.task_id, "description": chain.description,
        "status": "pending", "current_step": 0,
    }
    task = await crud.create_orchestrator_task(db, task_data)

    for step_data in chain.steps:
        await crud.add_orchestrator_step(db, chain.task_id, {
            "agent_id": step_data.get("agent_id", ""),
            "input": step_data.get("input", ""),
            "status": "pending",
        })

    asyncio.create_task(execute_chain(chain.task_id, db))

    return {"ok": True, "task_id": chain.task_id, "steps": len(chain.steps)}


@router.get("/status/{task_id}")
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_session)):
    """Получить статус задачи."""
    task = await crud.get_orchestrator_task(db, task_id)
    if not task:
        raise HTTPException(404, f"Задача '{task_id}' не найдена")
    steps = await crud.get_orchestrator_steps(db, task_id)
    return {
        "task_id": task.task_id, "description": task.description,
        "status": task.status, "current_step": task.current_step,
        "result": task.result[:2000] if task.result else "",
        "steps": [{"agent_id": s.agent_id, "status": s.status, "output": s.output[:500] if s.output else ""} for s in steps],
    }


@router.post("/intervene/{task_id}")
async def intervene_task(task_id: str, req: InterveneRequest, db: AsyncSession = Depends(get_session)):
    """Вмешаться в выполнение."""
    if req.action == "cancel":
        await crud.update_orchestrator_task(db, task_id, {"status": "cancelled", "cancelled": True})
        return {"ok": True, "message": f"Задача '{task_id}' отменена"}
    raise HTTPException(400, f"Неизвестное действие: {req.action}")


@router.get("/history")
async def get_task_history(db: AsyncSession = Depends(get_session)):
    """История всех задач."""
    tasks = await crud.get_orchestrator_tasks(db) if hasattr(crud, 'get_orchestrator_tasks') else []
    return {"tasks": tasks}


@router.get("/active")
async def get_active_tasks(db: AsyncSession = Depends(get_session)):
    """Активные задачи."""
    tasks = await crud.get_active_orchestrator_tasks(db)
    result = []
    for t in tasks:
        steps = await crud.get_orchestrator_steps(db, t.task_id)
        result.append({
            "task_id": t.task_id, "description": t.description,
            "status": t.status, "current_step": t.current_step,
            "steps": len(steps), "progress": (t.current_step / max(len(steps), 1)) * 100,
        })
    return {"tasks": result}


@router.get("/registry")
async def get_agent_registry(db: AsyncSession = Depends(get_session)):
    """Реестр агентов."""
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
