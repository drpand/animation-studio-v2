"""
Orchestrator API — управление цепочками задач.
Префикс роутов задаётся в main.py: /api/orchestrator
"""
import asyncio
import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orchestrator.task_chain import TaskChain
from orchestrator.progress_tracker import tracker
from orchestrator.executor import execute_chain

router = APIRouter()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_FILE = os.path.join(PROJECT_ROOT, "orchestrator", "agent_registry.json")


class SubmitTaskRequest(BaseModel):
    description: str


class InterveneRequest(BaseModel):
    action: str  # cancel, pause, resume


@router.post("/submit")
async def submit_task(req: SubmitTaskRequest):
    """
    Отправить задачу Orchestrator'у.
    Orchestrator анализирует задачу, строит цепочку и запускает выполнение.
    """
    if not req.description.strip():
        raise HTTPException(400, "Описание задачи не может быть пустым")

    # Orchestrator анализирует задачу и строит цепочку
    chain = await _build_task_chain(req.description)

    if not chain or not chain.steps:
        raise HTTPException(400, "Не удалось построить цепочку для задачи")

    # Сохраняем задачу
    tracker.add_task(chain)

    # Запускаем выполнение в фоне
    asyncio.create_task(execute_chain(chain))

    return {
        "ok": True,
        "task_id": chain.task_id,
        "steps": len(chain.steps),
        "message": f"Задача '{chain.description}' запущена. {len(chain.steps)} шагов."
    }


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """Получить статус задачи."""
    chain = tracker.get_task(task_id)
    if not chain:
        raise HTTPException(404, f"Задача '{task_id}' не найдена")
    return chain.to_dict()


@router.post("/intervene/{task_id}")
async def intervene_task(task_id: str, req: InterveneRequest):
    """Вмешаться в выполнение задачи (cancel/pause/resume)."""
    chain = tracker.get_task(task_id)
    if not chain:
        raise HTTPException(404, f"Задача '{task_id}' не найдена")

    if req.action == "cancel":
        tracker.cancel_task(task_id)
        return {"ok": True, "message": f"Задача '{task_id}' отменена"}
    elif req.action == "pause":
        # Пока просто помечаем, реальная пауза требует доработки executor
        return {"ok": False, "message": "Пауза пока не поддерживается"}
    elif req.action == "resume":
        return {"ok": False, "message": "Возобновление пока не поддерживается"}
    else:
        raise HTTPException(400, f"Неизвестное действие: {req.action}")


@router.get("/history")
async def get_task_history():
    """Получить историю всех задач."""
    return {"tasks": tracker.get_all_tasks()}


@router.get("/active")
async def get_active_tasks():
    """Получить активные задачи."""
    return {"tasks": tracker.get_active_tasks()}


@router.get("/registry")
async def get_agent_registry():
    """Получить реестр агентов."""
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


async def _build_task_chain(description: str) -> TaskChain:
    """
    Orchestrator анализирует задачу и строит цепочку агентов.
    Использует LLM для определения нужных агентов на основе registry.
    """
    # Загружаем реестр агентов
    registry = []
    if os.path.exists(REGISTRY_FILE):
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            registry = json.load(f)

    # Формируем список агентов для LLM
    agents_info = "\n".join(
        f"- {a['id']}: {', '.join(a.get('capabilities', []))}"
        for a in registry
        if a.get("id") not in ("critic", "fixer")  # Critic/Fixer добавляются автоматически
    )

    # Запрашиваем у LLM цепочку агентов
    system = (
        "Ты Orchestrator аниме-студии РОДИНА. "
        "Твоя задача — определить, какие агенты нужны для выполнения задачи, и в каком порядке."
    )
    user = f"""Задача: {description}

Доступные агенты и их возможности:
{agents_info}

Верни СТРОГО JSON массив с ID агентов в порядке выполнения.
Только JSON, ничего лишнего.
Пример: ["writer", "director", "storyboarder"]"""

    try:
        from med_otdel.agent_memory import call_llm
        result, _ = await call_llm(system_prompt=system, user_prompt=user)

        # Парсим JSON из ответа
        import re
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            agent_ids = json.loads(json_match.group())
        else:
            # Fallback: используем стандартную цепочку
            agent_ids = ["writer", "director"]

    except Exception:
        # Fallback: стандартная цепочка для текстовых задач
        agent_ids = ["writer", "director"]

    # Строим цепочку
    chain = TaskChain(description)

    current_input = description
    for agent_id in agent_ids:
        # Проверяем что агент существует в registry
        if any(a.get("id") == agent_id for a in registry):
            chain.add_step(agent_id, current_input)

    # Если цепочка пуста — добавляем Writer по умолчанию
    if not chain.steps:
        chain.add_step("writer", description)

    return chain
