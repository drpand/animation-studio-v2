"""HR agent creation and management endpoints."""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from med_otdel.agent_memory import call_llm
from config import PROJECT_NAME
from api.hr.helpers import (
    load_state,
    save_state,
    generate_agent_id,
    parse_hr_response,
    find_icon,
    _state_lock,
)

router = APIRouter()


class CreateAgentRequest(BaseModel):
    task_description: str
    agent_name: str = ""
    agent_role: str = ""


@router.post("/create-agent")
async def create_agent(req: CreateAgentRequest):
    """
    HR creates new agent for task.
    1. Analyzes task
    2. Generates name, role, prompt, model
    3. Registers agent in system
    """
    if not req.task_description.strip():
        raise HTTPException(400, "Описание задачи не может быть пустым")

    analysis_prompt = f"""Ты HR аниме-студии {PROJECT_NAME}. Тебе нужно создать нового агента для задачи.

Описание задачи:
{req.task_description[:2000]}

Определи:
1. Имя агента (краткое, на английском, например: Colorist, VFX Artist, Voice Director)
2. Роль агента (одно предложение на русском)
3. Системный промпт (детальные инструкции для агента, 200-500 символов)
4. Рекомендуемую модель из: google/gemini-3-flash-preview, anthropic/claude-sonnet-4.5, qwen/qwen3.5-9b, openai/gpt-4o

Формат ответа (строго):
NAME: <имя>
ROLE: <роль>
PROMPT: <промпт>
MODEL: <модель>"""

    response, _ = await call_llm(
        system_prompt="Ты HR аниме-студии. Создавай агентов под задачи.",
        user_prompt=analysis_prompt,
    )

    name, role, prompt, model = parse_hr_response(
        response, req.agent_name, req.agent_role, req.task_description
    )

    agent_id = generate_agent_id(name)
    icon = find_icon(name)

    final_name = req.agent_name or name
    final_role = req.agent_role or role

    with _state_lock:
        state = load_state()
        state[agent_id] = {
            "name": final_name,
            "role": final_role,
            "model": model,
            "status": "idle",
            "instructions": prompt,
            "attachment_objects": [],
            "attachments": [],
            "chat_history": [],
            "temp": True,
            "created_at": datetime.now().isoformat(),
            "created_for": req.task_description[:200],
            "icon": icon,
        }
        save_state(state)

    return {
        "ok": True,
        "agent_id": agent_id,
        "name": final_name,
        "role": final_role,
        "model": model,
        "icon": icon,
        "temp": True,
    }


@router.get("/temp-agents")
async def list_temp_agents():
    """List temporary agents."""
    state = load_state()
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
    """Remove temporary agent."""
    with _state_lock:
        state = load_state()
        if agent_id not in state:
            raise HTTPException(404, f"Агент '{agent_id}' не найден")
        if not state[agent_id].get("temp"):
            raise HTTPException(400, f"Агент '{agent_id}' не является временным")
        del state[agent_id]
        save_state(state)
    return {"ok": True, "agent_id": agent_id}
