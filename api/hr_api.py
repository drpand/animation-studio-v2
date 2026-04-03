"""
HR Agent API — Создание временных агентов под задачу.
Префикс роутов задаётся в main.py: /api/hr
"""
import os
import json
import uuid
import tempfile
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from med_otdel.agent_memory import call_llm

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")

_state_lock = threading.Lock()

AGENT_ICONS = {
    "animator": "🎨",
    "editor": "✂️",
    "composer": "🎼",
    "voice": "🎤",
    "color": "🖌️",
    "lighting": "💡",
    "vfx": "✨",
    "translator": "🌐",
    "researcher": "🔬",
    "producer": "📋",
    "director": "🎬",
    "writer": "✍️",
    "critic": "🔍",
    "fixer": "🔧",
    "sound": "🎵",
    "art": "🎨",
    "dop": "📷",
    "storyboard": "📋",
}

DEFAULT_MODELS = [
    "google/gemini-3-flash-preview",
    "anthropic/claude-sonnet-4-5",
    "qwen/qwen3.5-9b",
    "openai/gpt-4o",
]


def _load_state() -> dict:
    if not os.path.exists(AGENTS_STATE_FILE):
        return {}
    with open(AGENTS_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict):
    dir_name = os.path.dirname(AGENTS_STATE_FILE)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(state, tmp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, AGENTS_STATE_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _generate_agent_id(name: str) -> str:
    base = name.lower().replace(" ", "_").replace("-", "_")
    base = "".join(c for c in base if c.isalpha() or c == "_")
    suffix = uuid.uuid4().hex[:4]
    return f"{base}_{suffix}"


def _pick_model() -> str:
    import random
    return random.choice(DEFAULT_MODELS)


class CreateAgentRequest(BaseModel):
    task_description: str
    agent_name: str = ""
    agent_role: str = ""


@router.post("/create-agent")
async def create_agent(req: CreateAgentRequest):
    """
    HR создаёт нового агента под задачу.
    1. Анализирует задачу
    2. Генерирует имя, роль, промпт, модель
    3. Регистрирует агента в системе
    """
    if not req.task_description.strip():
        raise HTTPException(400, "Описание задачи не может быть пустым")

    analysis_prompt = f"""Ты HR аниме-студии РОДИНА. Тебе нужно создать нового агента для задачи.

Описание задачи:
{req.task_description[:2000]}

Определи:
1. Имя агента (краткое, на английском, например: Colorist, VFX Artist, Voice Director)
2. Роль агента (одно предложение на русском)
3. Системный промпт (детальные инструкции для агента, 200-500 символов)
4. Рекомендуемую модель из: google/gemini-3-flash-preview, anthropic/claude-sonnet-4-5, qwen/qwen3.5-9b, openai/gpt-4o

Формат ответа (строго):
NAME: <имя>
ROLE: <роль>
PROMPT: <промпт>
MODEL: <модель>"""

    response, _ = await call_llm(
        system_prompt="Ты HR аниме-студии. Создавай агентов под задачи.",
        user_prompt=analysis_prompt,
    )

    name, role, prompt, model = _parse_hr_response(response, req)

    agent_id = _generate_agent_id(name)
    icon = _find_icon(name)

    final_name = req.agent_name or name
    final_role = req.agent_role or role

    with _state_lock:
        state = _load_state()
        state[agent_id] = {
            "name": final_name,
            "role": final_role,
            "model": model,
            "status": "idle",
            "instructions": prompt,
            "attachments": [],
            "chat_history": [],
            "temp": True,
            "created_at": datetime.now().isoformat(),
            "created_for": req.task_description[:200],
            "icon": icon,
        }
        _save_state(state)

    return {
        "ok": True,
        "agent_id": agent_id,
        "name": final_name,
        "role": final_role,
        "model": model,
        "icon": icon,
        "temp": True,
    }


def _parse_hr_response(response: str, req: CreateAgentRequest) -> tuple:
    name = req.agent_name or "New Agent"
    role = req.agent_role or "Специалист"
    prompt = f"Ты {role}. Выполняй задачи качественно."
    model = _pick_model()

    for line in response.split("\n"):
        line_stripped = line.strip()
        if line_stripped.upper().startswith("NAME:"):
            name = line_stripped[len("NAME:"):].strip()
        elif line_stripped.upper().startswith("ROLE:"):
            role = line_stripped[len("ROLE:"):].strip()
        elif line_stripped.upper().startswith("PROMPT:"):
            prompt = line_stripped[len("PROMPT:"):].strip()
        elif line_stripped.upper().startswith("MODEL:"):
            model = line_stripped[len("MODEL:"):].strip()

    if not prompt or len(prompt) < 10:
        prompt = f"Ты {role} аниме-студии РОДИНА. {req.task_description[:500]}"

    return name, role, prompt, model


def _find_icon(name: str) -> str:
    name_lower = name.lower()
    for key, icon in AGENT_ICONS.items():
        if key in name_lower:
            return icon
    return "🤖"


@router.get("/temp-agents")
async def list_temp_agents():
    """Список временных агентов."""
    state = _load_state()
    temp_agents = []
    for agent_id, data in state.items():
        if data.get("temp"):
            temp_agents.append({
                "agent_id": agent_id,
                "name": data.get("name", agent_id),
                "role": data.get("role", ""),
                "model": data.get("model", ""),
                "status": data.get("status", "idle"),
                "icon": data.get("icon", "🤖"),
                "created_at": data.get("created_at", ""),
                "created_for": data.get("created_for", ""),
            })
    return {"agents": temp_agents}


@router.post("/{agent_id}/remove")
async def remove_agent(agent_id: str):
    """Удалить временного агента."""
    with _state_lock:
        state = _load_state()
        if agent_id not in state:
            raise HTTPException(404, f"Агент '{agent_id}' не найден")
        if not state[agent_id].get("temp"):
            raise HTTPException(400, f"Агент '{agent_id}' не является временным")
        del state[agent_id]
        _save_state(state)
    return {"ok": True, "agent_id": agent_id}
