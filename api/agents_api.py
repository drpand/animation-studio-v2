"""
Agents API — CRUD агентов, загрузка файлов.
Префикс роутов задаётся в main.py: /api/agents
"""
import os
import json
import shutil
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from agents.base_agent import BaseAgent, STATE_FILE

router = APIRouter()

MEMORY_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACHMENTS_DIR = os.path.join(MEMORY_ROOT, "memory", "attachments")

# Допустимые расширения файлов
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".json"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _load_state() -> dict:
    """Загрузить agents_state.json."""
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict):
    """Сохранить agents_state.json."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


class AgentUpdate(BaseModel):
    model: str | None = None
    instructions: str | None = None
    status: str | None = None


@router.get("/")
async def list_agents():
    """Список всех агентов."""
    state = _load_state()
    agents = []
    for agent_id, data in state.items():
        agents.append({
            "agent_id": agent_id,
            "name": data.get("name", agent_id),
            "role": data.get("role", ""),
            "model": data.get("model", ""),
            "status": data.get("status", "idle"),
            "attachments": data.get("attachments", []),
        })
    return {"agents": agents}


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """Получить данные одного агента."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")
    data = state[agent_id]
    return {
        "agent_id": agent_id,
        "name": data.get("name", agent_id),
        "role": data.get("role", ""),
        "model": data.get("model", ""),
        "status": data.get("status", "idle"),
        "instructions": data.get("instructions", ""),
        "attachments": data.get("attachments", []),
        "chat_history": data.get("chat_history", []),
    }


@router.put("/{agent_id}")
async def update_agent(agent_id: str, update: AgentUpdate):
    """Обновить модель, инструкции или статус агента."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    if update.model is not None:
        state[agent_id]["model"] = update.model
    if update.instructions is not None:
        state[agent_id]["instructions"] = update.instructions
    if update.status is not None:
        state[agent_id]["status"] = update.status

    _save_state(state)
    return {"ok": True, "agent_id": agent_id}


@router.post("/{agent_id}/upload")
async def upload_file(agent_id: str, file: UploadFile = File(...)):
    """Прикрепить файл к агенту с валидацией типа и размера."""
    state = _load_state()
    if agent_id not in state:
        raise HTTPException(404, f"Агент '{agent_id}' не найден")

    # Валидация расширения
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Недопустимый тип файла '{ext}'. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}")

    # Читаем файл и проверяем размер
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"Файл слишком большой (макс. {MAX_FILE_SIZE // 1024 // 1024} MB)")

    # Сохраняем
    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    safe_name = f"{agent_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    save_path = os.path.join(ATTACHMENTS_DIR, safe_name)

    with open(save_path, "wb") as f:
        f.write(content)

    # Добавляем в attachments агента
    if "attachments" not in state[agent_id]:
        state[agent_id]["attachments"] = []
    state[agent_id]["attachments"].append(safe_name)
    _save_state(state)

    return {"ok": True, "filename": safe_name, "path": save_path}
