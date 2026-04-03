"""
Med Otdel API — API МЕД-ОТДЕЛА.
Префикс роутов задаётся в main.py: /api/med-otdel
"""
import os
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from med_otdel.med_core import (
    run_evaluation,
    run_fix,
    manual_evolve,
    write_event,
    log_med_action,
    _load_bus,
    _load_log,
    _load_agents_state,
)
from med_otdel.agent_memory import AgentMemory
from med_otdel.chain_analyzer import analyze_chains
from med_otdel.studio_monitor import check_studio_health, reset_agent_error

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_STATE_FILE = os.path.join(PROJECT_ROOT, "memory", "agents_state.json")


class EvaluateRequest(BaseModel):
    agent_id: str
    task_description: str = ""


class FixRequest(BaseModel):
    agent_id: str
    original_result: str
    critic_feedback: str


@router.post("/evaluate")
async def evaluate(req: EvaluateRequest):
    """
    Critic оценивает последний ответ агента.
    Берёт последний ответ из chat_history, формирует событие, запускает Critic.
    """
    # Загружаем состояние агента для получения chat_history
    if not os.path.exists(AGENTS_STATE_FILE):
        raise HTTPException(404, "agents_state.json не найден")

    with open(AGENTS_STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    if req.agent_id not in state:
        raise HTTPException(404, f"Агент '{req.agent_id}' не найден")

    chat_history = state[req.agent_id].get("chat_history", [])

    # Берём последний ответ агента (assistant message)
    last_result = ""
    for msg in reversed(chat_history):
        if msg.get("role") == "assistant":
            last_result = msg.get("content", "")
            break

    if not last_result:
        raise HTTPException(400, "Нет результатов для оценки. Агент ещё не ответил.")

    # Запускаем оценку
    result = await run_evaluation(
        task_result=last_result,
        agent_id=req.agent_id,
        task_description=req.task_description,
    )

    return result


@router.post("/fix")
async def fix(req: FixRequest):
    """Fixer исправляет результат по замечаниям Critic."""
    fixed_result = await run_fix(req.original_result, req.critic_feedback)
    return {"fixed_result": fixed_result}


@router.get("/{agent_id}/memory")
async def get_agent_memory(agent_id: str):
    """Получить память агента: версия, промпт, ошибки, уроки."""
    memory = AgentMemory(agent_id)
    return {
        "agent_id": agent_id,
        "current_version": memory.data.get("current_version", "v1"),
        "current_prompt": memory.data.get("current_prompt", ""),
        "total_failures": memory.data.get("total_failures", 0),
        "consecutive_failures": memory.get_consecutive_failures(),
        "failures": memory.data.get("failures", [])[-10:],  # Последние 10
        "lessons": memory.data.get("lessons", [])[-5:],  # Последние 5
        "history_versions": list(memory.data.get("history", {}).keys()),
    }


@router.post("/{agent_id}/evolve")
async def evolve_agent(agent_id: str):
    """Ручная эволюция агента."""
    result = await manual_evolve(agent_id)
    return result


@router.get("/{agent_id}/versions")
async def get_agent_versions(agent_id: str):
    """Получить историю версий промптов агента."""
    memory = AgentMemory(agent_id)
    return {
        "agent_id": agent_id,
        "current_version": memory.data.get("current_version", "v1"),
        "history": memory.data.get("history", {}),
    }


@router.get("/studio-health")
async def studio_health():
    """Здоровье всей студии (3 режима)."""
    return check_studio_health()


@router.get("/chains")
async def get_chains():
    """Проблемные цепочки агент→агент."""
    return {"chains": analyze_chains()}


@router.get("/events")
async def get_events(limit: int = 20):
    """Последние события на шине."""
    bus = _load_bus()
    events = bus.get("events", [])
    return {"events": events[-limit:]}


@router.get("/log")
async def get_med_log(limit: int = 20):
    """Лог МЕД-ОТДЕЛА."""
    log = _load_log()
    return {"entries": log.get("entries", [])[-limit:]}


@router.post("/{agent_id}/reset-error")
async def reset_error(agent_id: str):
    """Сбросить статус error агента."""
    reset_agent_error(agent_id)
    return {"ok": True, "agent_id": agent_id}
