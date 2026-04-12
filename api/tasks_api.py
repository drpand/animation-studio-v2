"""
Tasks API — Управление задачами.
Префикс роутов задаётся в main.py: /api/tasks
"""
import os
import json
import tempfile
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

MEMORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_FILE = os.path.join(MEMORY_ROOT, "memory", "tasks.json")


def _load_tasks() -> dict:
    if not os.path.exists(TASKS_FILE):
        return {"active": [], "completed": [], "med_otdel_log": []}
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_tasks(data: dict):
    """Атомарная запись JSON через временный файл."""
    dir_name = os.path.dirname(TASKS_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            json.dump(data, tmp_f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, TASKS_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


class TaskCreate(BaseModel):
    title: str
    agent_id: str
    description: str = ""


@router.get("/")
async def list_tasks():
    """Список всех задач."""
    return _load_tasks()


@router.post("/")
async def create_task(task: TaskCreate):
    """Создать новую задачу."""
    data = _load_tasks()
    new_task = {
        "id": f"task_{len(data['active']) + len(data['completed']) + 1}",
        "title": task.title,
        "agent_id": task.agent_id,
        "description": task.description,
        "status": "active",
        "created_at": datetime.now().isoformat(),
    }
    data["active"].append(new_task)
    _save_tasks(data)
    return {"ok": True, "task": new_task}


@router.post("/{task_id}/complete")
async def complete_task(task_id: str):
    """Завершить задачу."""
    data = _load_tasks()
    for i, task in enumerate(data["active"]):
        if task["id"] == task_id:
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat()
            data["active"].pop(i)
            data["completed"].append(task)
            _save_tasks(data)
            return {"ok": True, "task": task}
    raise HTTPException(404, f"Задача '{task_id}' не найдена в активных")


@router.get("/med-otdel-log")
async def med_otdel_log():
    """Лог МЕД-ОТДЕЛА."""
    data = _load_tasks()
    return {"log": data.get("med_otdel_log", [])}
